"""Supervisor 计划执行器：依赖执行、并行、权限门禁和失败重规划。"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional, Set

from app.agents.agent_contracts import AgentContext, AgentResult, PlanStep, domain_registry


class DynamicPlanExecutor:
    def __init__(self, max_total_steps: int = 32, max_replans: int = 1, max_parallel: int = 4) -> None:
        self.max_total_steps = max_total_steps
        self.max_replans = max_replans
        self.max_parallel = max_parallel

    def _permission_error(self, capability: Any, context: AgentContext) -> Optional[str]:
        """执行前门禁：若上下文携带权限集合，则强制校验能力权限。"""
        permissions = context.metadata.get("permissions")
        if permissions is None:
            return None  # API 层已通过 agent:execute 时，兼容旧调用方
        permissions = set(permissions)
        if "*" in permissions or capability.permission in permissions:
            return None
        return f"缺少能力权限: {capability.permission}"

    def _run_step(self, step: PlanStep, context: AgentContext) -> Dict[str, Any]:
        started = time.perf_counter()
        agent, capability = domain_registry.resolve_capability(step.capability)
        denied = self._permission_error(capability, context)
        if denied:
            result = AgentResult(success=False, errors=[denied])
            return {"step_id": step.step_id, "capability": step.capability, "status": "permission_denied", "attempts": 0, "duration_ms": 0, "result": result.as_dict()}

        resolved_inputs = self._resolve_inputs(step.inputs, context.tool_results)
        last_errors: List[str] = []
        result: AgentResult | None = None
        attempts = capability.max_retries + 1
        for attempt in range(1, attempts + 1):
            try:
                result = agent.execute(step.capability, resolved_inputs, context)
                validation_errors = agent.validate(result, context)
                if validation_errors:
                    result.success = False
                    result.errors.extend(validation_errors)
                if result.success:
                    break
                last_errors = list(result.errors)
            except Exception as exc:
                last_errors = [str(exc)]
                result = AgentResult(success=False, errors=last_errors)
            if attempt < attempts:
                time.sleep(min(attempt, 2))
        assert result is not None
        if not result.success and last_errors:
            result.errors = last_errors
        elapsed = round((time.perf_counter() - started) * 1000, 2)
        return {"step_id": step.step_id, "capability": step.capability, "status": "success" if result.success else "failed", "attempts": attempt, "duration_ms": elapsed, "result": result.as_dict()}

    def execute(self, plan: Dict[str, Any], context: AgentContext, *, approved: bool = True,
                replan_fn: Optional[Callable[[str, Dict[str, Any], AgentContext], Dict[str, Any]]] = None) -> Dict[str, Any]:
        if not approved:
            return {"success": False, "status": "awaiting_approval", "plan_id": plan.get("plan_id"), "steps": []}
        if len(plan.get("steps") or []) > self.max_total_steps:
            return {"success": False, "status": "rejected", "error": "计划步骤超过安全上限", "plan_id": plan.get("plan_id"), "steps": []}

        steps = [step if isinstance(step, PlanStep) else PlanStep(**step) for step in plan.get("steps", [])]
        completed: Set[str] = set()
        step_results: List[Dict[str, Any]] = []
        pending = {step.step_id: step for step in steps}
        replans = 0

        while pending:
            ready = [step for step in pending.values() if all(dep in completed for dep in step.depends_on)]
            if not ready:
                return self._failed(plan, "计划依赖存在环或缺失", step_results, context)

            # 同一层无依赖关系的步骤并行执行，依赖步骤仍按层推进。
            with ThreadPoolExecutor(max_workers=min(self.max_parallel, len(ready))) as pool:
                futures = {pool.submit(self._run_step, step, context): step for step in ready}
                layer_results = [future.result() for future in as_completed(futures)]
            layer_results.sort(key=lambda item: next(index for index, step in enumerate(ready) if step.step_id == item["step_id"]))

            failed = None
            for record in layer_results:
                step_results.append(record)
                context.tool_results[record["step_id"]] = record["result"]
                pending.pop(record["step_id"], None)
                if record["status"] != "success" and failed is None:
                    failed = record
                else:
                    completed.add(record["step_id"])
            if failed:
                if replan_fn and replans < self.max_replans:
                    replans += 1
                    failed_capability = failed["capability"]
                    context.metadata.setdefault("failed_capabilities", []).append(failed_capability)
                    new_plan = replan_fn(plan.get("goal", ""), {"tool_results": context.tool_results, "failed_capability": failed_capability}, context)
                    new_steps = [PlanStep(**item) for item in new_plan.get("steps", [])]
                    new_steps = [step for step in new_steps if step.capability != failed_capability]
                    if new_steps:
                        for step in new_steps:
                            step.depends_on = [dep for dep in step.depends_on if dep in completed]
                            pending[step.step_id] = step
                        plan = new_plan
                        continue
                return self._failed(plan, "; ".join(failed["result"].get("errors", [])) or "步骤执行失败", step_results, context)

        return {"success": True, "status": "succeeded", "plan_id": plan.get("plan_id"), "steps": step_results, "context": context.tool_results, "replans": replans}

    @staticmethod
    def _failed(plan: Dict[str, Any], error: str, steps: List[Dict[str, Any]], context: AgentContext) -> Dict[str, Any]:
        return {"success": False, "status": "failed", "error": error, "plan_id": plan.get("plan_id"), "steps": steps, "context": context.tool_results}

    @staticmethod
    def _resolve_inputs(value: Any, results: Dict[str, Any]) -> Any:
        if isinstance(value, str) and value.startswith("$"):
            current: Any = results
            for part in value[1:].split("."):
                if not isinstance(current, dict):
                    return None
                current = current.get(part)
            return current
        if isinstance(value, dict):
            return {key: DynamicPlanExecutor._resolve_inputs(item, results) for key, item in value.items()}
        if isinstance(value, list):
            return [DynamicPlanExecutor._resolve_inputs(item, results) for item in value]
        return value


dynamic_executor = DynamicPlanExecutor()


def build_recovery_runner(task: Dict[str, Any]):
    """为进程重启后的任务重建可执行函数。"""
    context = AgentContext.create(
        task_id=task.get("task_id"),
        session_id=task.get("session_id"),
        user_id=task.get("owner"),
        metadata={"permissions": set(task.get("permissions", []))} if task.get("permissions") else {},
    )
    if task.get("agent") == "supervisor" and task.get("plan"):
        return lambda: dynamic_executor.execute(task["plan"], context)
    inputs = task.get("inputs") or {}
    agent_name = task.get("agent")
    if agent_name == "resume":
        from app.agents.resume_parser_agent import resume_parser_agent
        return lambda: resume_parser_agent.parse_resume(inputs.get("file_path"), inputs.get("file_name", "resume"))
    if agent_name == "assessment":
        from app.agents.assessment_agent import AssessmentAnalysisAgent
        return lambda: AssessmentAnalysisAgent().analyze(int(inputs["result_id"]))
    if agent_name == "matching":
        from app.agents.matching_agent import MatchingAgent
        if inputs.get("position_id"):
            return lambda: MatchingAgent().match_position_to_talents(int(inputs["position_id"]))
        return lambda: MatchingAgent().match_talent_to_positions(int(inputs["talent_id"]))
    if agent_name == "training":
        from app.agents.training_agent import training_agent
        return lambda: training_agent.analyze(int(inputs["talent_id"]), int(inputs["position_id"]) if inputs.get("position_id") else None)
    if agent_name == "data_decision":
        from app.agents.data_decision_agent import data_decision_agent
        return lambda: data_decision_agent.analyze(analysis_type=inputs.get("analysis_type", "structure"), nl2sql_question=inputs.get("question"))
    return None
