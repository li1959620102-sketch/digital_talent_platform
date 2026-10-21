"""统一 Agent 运行时：任务、规划、工具、审批、转交、审计与指标。"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentStore:
    """任务状态存储；配置 AGENT_REDIS_URL 后使用 Redis，否则使用线程安全内存存储。"""
    def __init__(self) -> None:
        self._data: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._redis = None
        url = os.getenv("AGENT_REDIS_URL") or os.getenv("REDIS_URI")
        if not url:
            try:
                from app.core.config import settings
                url = getattr(settings, "REDIS_URI", None)
            except Exception:
                url = None
        if url:
            try:
                import redis
                self._redis = redis.Redis.from_url(url, decode_responses=True, socket_timeout=2)
                self._redis.ping()
                logger.info("AgentStore 使用 Redis 持久化")
            except Exception as exc:
                logger.warning("AgentStore Redis 不可用，降级内存: %s", exc)
                self._redis = None

    def put(self, key: str, value: Dict[str, Any], ttl: int = 86400) -> None:
        payload = dict(value)
        if self._redis:
            try:
                self._redis.setex("agent:task:" + key, ttl, json.dumps(payload, ensure_ascii=False))
                return
            except Exception as exc:
                logger.warning("AgentStore 写 Redis 失败: %s", exc)
        with self._lock:
            self._data[key] = payload

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        if self._redis:
            try:
                raw = self._redis.get("agent:task:" + key)
                return json.loads(raw) if raw else None
            except Exception as exc:
                logger.warning("AgentStore 读 Redis 失败: %s", exc)
        with self._lock:
            value = self._data.get(key)
            return dict(value) if value else None

    def update(self, key: str, **changes: Any) -> Optional[Dict[str, Any]]:
        current = self.get(key) or {}
        current.update(changes)
        self.put(key, current)
        return current

    def list(self, limit: int = 100) -> list[Dict[str, Any]]:
        if self._redis:
            try:
                keys = self._redis.keys("agent:task:*")[-limit:]
                return [json.loads(v) for v in self._redis.mget(keys) if v]
            except Exception:
                pass
        with self._lock:
            return list(self._data.values())[-limit:]


class SessionMemory:
    """按会话隔离的短期/长期记忆，避免把所有历史内容塞进 Agent prompt。"""
    def __init__(self) -> None:
        self._memory: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()

    def remember(self, session_id: str, key: str, value: Any, *, long_term: bool = False) -> None:
        with self._lock:
            bucket = self._memory.setdefault(session_id, {"short_term": {}, "long_term": {}})
            bucket["long_term" if long_term else "short_term"][key] = value

    def recall(self, session_id: str, *, keys: Optional[list[str]] = None) -> Dict[str, Any]:
        with self._lock:
            bucket = self._memory.get(session_id, {"short_term": {}, "long_term": {}})
            if not keys:
                return {"short_term": dict(bucket["short_term"]), "long_term": dict(bucket["long_term"])}
            return {key: bucket["short_term"].get(key, bucket["long_term"].get(key)) for key in keys}


class AuditLog:
    def __init__(self) -> None:
        path = Path(os.getenv("AGENT_AUDIT_LOG", "backend/logs/agent_audit.jsonl"))
        self.path = path
        self._lock = threading.Lock()

    def write(self, event: str, **data: Any) -> None:
        record = {"event": event, "ts": _now(), **data}
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self._lock, self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        except Exception as exc:
            logger.warning("Agent 审计日志写入失败: %s", exc)


class AgentMetrics:
    def __init__(self) -> None:
        self._counts = Counter()
        self._durations: list[float] = []
        self._lock = threading.Lock()

    def observe(self, name: str, status: str, duration_ms: float) -> None:
        with self._lock:
            self._counts[f"{name}.{status}"] += 1
            self._counts["agent.calls"] += 1
            self._durations.append(duration_ms)
            self._durations = self._durations[-5000:]

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            durations = sorted(self._durations)
            p95 = durations[min(len(durations) - 1, int(len(durations) * .95))] if durations else 0
            return {"counters": dict(self._counts), "latency_ms": {"count": len(durations), "p95": round(p95, 2), "avg": round(sum(durations) / len(durations), 2) if durations else 0}}

    def prometheus(self) -> str:
        snap = self.snapshot()
        lines = ["# TYPE agent_calls_total counter"]
        for key, value in snap["counters"].items():
            metric = key.replace(".", "_")
            lines.append(f"agent_{metric} {value}")
        lines.append(f"agent_latency_p95_ms {snap['latency_ms']['p95']}")
        return "\n".join(lines) + "\n"


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, Dict[str, Any]] = {}

    def register(self, name: str, fn: Callable[..., Any], *, description: str = "", permission: str = "agent:execute", risk: str = "low") -> None:
        self._tools[name] = {"fn": fn, "description": description, "permission": permission, "risk": risk}

    def describe(self) -> list[Dict[str, Any]]:
        return [{k: v for k, v in item.items() if k != "fn"} | {"name": name} for name, item in self._tools.items()]

    def call(self, name: str, args: Dict[str, Any], *, timeout: int = 120) -> Any:
        item = self._tools.get(name)
        if not item:
            raise KeyError(f"未注册工具: {name}")
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(item["fn"], **args)
            try:
                return future.result(timeout=timeout)
            except TimeoutError as exc:
                future.cancel()
                raise TimeoutError(f"工具 {name} 执行超时") from exc


class AgentPlanner:
    """可审计规划器：优先使用 LLM 动态拆解，失败时回退到业务模板。"""
    TEMPLATES = {
        "resume": ["parse_file", "extract_info", "validate_data", "generate_tags", "generate_portrait"],
        "assessment": ["load_result", "analyze_categories", "identify_strengths", "calculate_level", "generate_suggestions"],
        "matching": ["load_candidates", "filter_hard_conditions", "vector_match", "llm_rank", "generate_results"],
        "training": ["diagnose_gap", "recommend_courses", "build_learning_path", "generate_suggestions"],
        "data_decision": ["route", "query_or_analyze", "validate_result", "generate_report"],
    }

    def _template_plan(self, agent: str, goal: str, context: Dict[str, Any], source: str = "template") -> Dict[str, Any]:
        steps = self.TEMPLATES.get(agent, ["understand_goal", "select_tools", "execute", "validate"])
        return {"plan_id": "plan_" + uuid.uuid4().hex[:12], "agent": agent, "goal": goal,
                "steps": [{"index": i + 1, "name": step, "status": "pending"} for i, step in enumerate(steps)],
                "context_keys": sorted(context.keys()), "source": source, "created_at": _now()}

    def plan(self, agent: str, goal: str, context: Optional[Dict[str, Any]] = None, *, use_llm: Optional[bool] = None) -> Dict[str, Any]:
        context = context or {}
        use_llm = use_llm if use_llm is not None else os.getenv("AGENT_PLANNER_LLM", "false").lower() in {"1", "true", "yes"}
        if use_llm:
            try:
                from app.core.llm_factory import get_agent_llm
                from app.utils.json_utils import extract_json
                tools = self.TEMPLATES.get(agent, [])
                prompt = ("你是企业 Agent 规划器。请把用户目标拆成 2-8 个可执行步骤。"
                          "只能从候选步骤中选择，禁止编造工具；返回 JSON："
                          '{"steps":[{"name":"步骤名","reason":"目的"}],"completion":"完成条件"}。'
                          f"\\nAgent={agent}\\n候选步骤={tools}\\n目标={goal}\\n上下文键={sorted(context.keys())}")
                response = get_agent_llm(temperature=0).invoke(prompt)
                parsed = extract_json(getattr(response, "content", str(response))) or {}
                raw_steps = parsed.get("steps")
                allowed = set(tools)
                steps = [s for s in raw_steps if isinstance(s, dict) and s.get("name") in allowed] if isinstance(raw_steps, list) else []
                if steps:
                    return {"plan_id": "plan_" + uuid.uuid4().hex[:12], "agent": agent, "goal": goal,
                            "steps": [{"index": i + 1, "name": s["name"], "reason": s.get("reason", ""), "status": "pending"} for i, s in enumerate(steps)],
                            "completion": parsed.get("completion", "所有步骤成功完成"), "context_keys": sorted(context.keys()),
                            "source": "llm", "created_at": _now()}
            except Exception as exc:
                logger.warning("动态规划失败，回退模板: %s", exc)
        return self._template_plan(agent, goal, context)


class AgentRuntime:
    def __init__(self) -> None:
        self.store = AgentStore()
        self.audit = AuditLog()
        self.metrics = AgentMetrics()
        self.tools = ToolRegistry()
        self.memory = SessionMemory()
        self.planner = AgentPlanner()
        self._executor = ThreadPoolExecutor(max_workers=int(os.getenv("AGENT_WORKERS", "8")))
        self._cancel_events: Dict[str, threading.Event] = {}
        self._idempotency_lock = threading.RLock()

    def create_task(self, agent: str, goal: str, inputs: Dict[str, Any], *, session_id: Optional[str] = None, requires_approval: bool = False, owner: Optional[str] = None, dynamic_plan: bool = False, plan_override: Optional[Dict[str, Any]] = None, permissions: Optional[set[str]] = None, idempotency_key: Optional[str] = None) -> Dict[str, Any]:
        if idempotency_key:
            with self._idempotency_lock:
                for existing in self.store.list(limit=1000):
                    if (existing.get("idempotency_key") == idempotency_key
                            and existing.get("owner") == owner
                            and existing.get("agent") == agent):
                        return existing
        task_id = "agt_" + uuid.uuid4().hex[:16]
        session_id = session_id or "ses_" + uuid.uuid4().hex[:16]
        plan = plan_override or self.planner.plan(agent, goal, inputs, use_llm=dynamic_plan)
        risk_levels = {str(step.get("risk_level", "low")).lower() for step in plan.get("steps", []) if isinstance(step, dict)}
        risk_level = "critical" if "critical" in risk_levels else ("high" if "high" in risk_levels else ("medium" if "medium" in risk_levels else "low"))
        requires_approval = bool(requires_approval or risk_level in {"high", "critical"})
        task = {"task_id": task_id, "session_id": session_id, "agent": agent, "goal": goal, "inputs": inputs, "plan": plan, "status": "pending_approval" if requires_approval else "pending", "requires_approval": requires_approval, "approved": not requires_approval, "owner": owner, "permissions": sorted(permissions or set()), "idempotency_key": idempotency_key, "risk_level": risk_level, "created_at": _now(), "updated_at": _now(), "attempt": 0, "events": []}
        self.memory.remember(session_id, "last_goal", goal)
        self.memory.remember(session_id, "last_inputs", inputs)
        task["memory"] = self.memory.recall(session_id)
        self.store.put(task_id, task)
        self._cancel_events[task_id] = threading.Event()
        self.audit.write("task_created", task_id=task_id, session_id=session_id, agent=agent, owner=owner, requires_approval=requires_approval)
        return task

    def submit(self, agent: str, goal: str, inputs: Dict[str, Any], runner: Callable[[], Dict[str, Any]], *, session_id: Optional[str] = None, requires_approval: bool = False, owner: Optional[str] = None, dynamic_plan: bool = False) -> Dict[str, Any]:
        task = self.create_task(agent, goal, inputs, session_id=session_id, requires_approval=requires_approval, owner=owner, dynamic_plan=dynamic_plan)
        if not requires_approval:
            self._executor.submit(self._run, task["task_id"], runner)
        return task

    def _run(self, task_id: str, runner: Callable[[], Dict[str, Any]], max_retries: int = 2) -> None:
        task = self.store.get(task_id) or {}
        if not task.get("approved", False):
            return
        cancel_event = self._cancel_events.setdefault(task_id, threading.Event())
        if cancel_event.is_set() or task.get("status") == "canceled":
            self.store.update(task_id, status="canceled", finished_at=_now(), updated_at=_now())
            return
        self.store.update(task_id, status="running", started_at=_now())
        started = time.perf_counter()
        last_error = ""
        for attempt in range(1, max_retries + 1):
            if cancel_event.is_set():
                self.store.update(task_id, status="canceled", finished_at=_now(), updated_at=_now())
                self.audit.write("task_canceled", task_id=task_id, agent=task.get("agent"), attempt=attempt)
                return
            self.store.update(task_id, attempt=attempt)
            try:
                result = runner()
                status = "success" if result.get("success", True) is not False else "failed"
                elapsed = (time.perf_counter() - started) * 1000
                self.store.update(task_id, status=status, result=result, finished_at=_now(), updated_at=_now())
                self.metrics.observe(task["agent"], status, elapsed)
                self.audit.write("task_finished", task_id=task_id, agent=task["agent"], status=status, attempt=attempt, duration_ms=round(elapsed, 2))
                return
            except Exception as exc:
                last_error = str(exc)
                self.audit.write("task_retry", task_id=task_id, agent=task["agent"], attempt=attempt, error=last_error)
        elapsed = (time.perf_counter() - started) * 1000
        self.store.update(task_id, status="failed", error=last_error, finished_at=_now(), updated_at=_now())
        self.metrics.observe(task["agent"], "failed", elapsed)
        self.audit.write("task_failed", task_id=task_id, agent=task["agent"], error=last_error, duration_ms=round(elapsed, 2))

    def approve(self, task_id: str, approved: bool, actor: Optional[str] = None) -> Optional[Dict[str, Any]]:
        task = self.store.get(task_id)
        if not task:
            return None
        if task.get("status") not in {"pending_approval", "pending"}:
            return task
        status = "pending" if approved else "rejected"
        task = self.store.update(task_id, approved=approved, status=status, approval_actor=actor, approved_at=_now())
        self.audit.write("task_approval", task_id=task_id, approved=approved, actor=actor)
        return task

    def cancel(self, task_id: str, actor: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """取消排队或正在执行的任务；运行中的业务函数在重试边界停止。"""
        task = self.store.get(task_id)
        if not task:
            return None
        if task.get("status") in {"success", "failed", "rejected", "canceled"}:
            return task
        self._cancel_events.setdefault(task_id, threading.Event()).set()
        task = self.store.update(task_id, status="canceled", canceled_by=actor, canceled_at=_now(), updated_at=_now())
        self.audit.write("task_canceled", task_id=task_id, actor=actor)
        return task

    def handoff(self, task_id: str, assignee: str, actor: Optional[str] = None) -> Optional[Dict[str, Any]]:
        task = self.store.update(task_id, owner=assignee, status="handed_off", handoff_actor=actor, updated_at=_now())
        if task:
            self.audit.write("task_handoff", task_id=task_id, assignee=assignee, actor=actor)
        return task

    def get(self, task_id: str) -> Optional[Dict[str, Any]]:
        return self.store.get(task_id)

    def recover_tasks(self, runner_factory: Callable[[Dict[str, Any]], Optional[Callable[[], Dict[str, Any]]]]) -> int:
        """进程启动时恢复可重建的任务；无法重建的任务保留状态并写入审计。"""
        recovered = 0
        for task in self.store.list(limit=1000):
            if task.get("status") not in {"pending", "running", "retrying"}:
                continue
            runner = runner_factory(task)
            if not runner:
                self.audit.write("task_recovery_skipped", task_id=task.get("task_id"), agent=task.get("agent"))
                continue
            task_id = task.get("task_id")
            self.store.update(task_id, status="pending", recovered_at=_now())
            self._executor.submit(self._run, task_id, runner)
            recovered += 1
            self.audit.write("task_recovered", task_id=task_id, agent=task.get("agent"))
        return recovered


runtime = AgentRuntime()
