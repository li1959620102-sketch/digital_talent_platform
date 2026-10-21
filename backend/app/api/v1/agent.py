"""
AI 智能体 API 路由（P1：五大 AI Agent 编排入口）
- 档案解析 Agent / 测评分析 Agent / 岗位匹配 Agent / 培训赋能 Agent / 数据决策 Agent
遵循项目规则：所有 AI 能力继承用户权限；Milvus/LLM 不可用时优雅降级（返回结构化结果，不崩溃）。
"""
from typing import Optional, Dict, Any
import threading
import uuid as _uuid
import time as _time
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_mysql_session, get_mysql_engine
from app.schemas.common import ResponseModel
from app.core.rbac import PermCode, require_permission_or_403, get_user_permission_codes

from app.agents.resume_parser_agent import resume_parser_agent
from app.agents.assessment_agent import AssessmentAnalysisAgent
from app.agents.matching_agent import MatchingAgent
from app.agents.training_agent import training_agent
from app.agents.data_decision_agent import data_decision_agent
from app.services.dify_adapter import dify_adapter
from app.agents.agent_runtime import runtime as agent_runtime
from app.agents.domain_agents import domain_registry
from app.agents.supervisor import supervisor_planner
from app.agents.agent_contracts import AgentContext
from app.agents.dynamic_executor import dynamic_executor

router = APIRouter()
AUTH_AGENT_EXECUTE = require_permission_or_403(PermCode.AGENT_EXECUTE)


def _apply_input_gate(result: Any, hint: str) -> Any:
    """
    为 Agent 结果补写「输入有效性」显式标记。

    背景：Agent 在目标记录不存在时返回 success=False，但 HTTP 状态与 code 仍为 200，
    调用方（含 Dify 工作流、前端）若只判断状态码，会把无数据的失败结果当作有效输入，
    继续生成一份「看似完整、实为推测」的报告——这是 AI 应用特有的可靠性风险。

    本函数不改动状态码（保持与既有集成测试一致），而是补一个机器可判定的字段：
      - data_valid:  False 表示输入数据无效，调用方应中止后续报告生成
      - gate:        "input_validation_failed"
      - gate_message: 人类可读的原因说明
    """
    if not isinstance(result, dict):
        return result
    if result.get("success") is False:
        result.setdefault("data_valid", False)
        result.setdefault("gate", "input_validation_failed")
        result.setdefault("gate_message", hint)
    else:
        result.setdefault("data_valid", True)
    return result


def _gate_message(result: Dict[str, Any], default: str) -> str:
    """根据门禁结果给出响应 message（无效输入时明确说明未生成报告）。"""
    if isinstance(result, dict) and result.get("data_valid") is False:
        return "输入数据无效，未生成报告"
    return default


@router.post("/parse-resume", response_model=ResponseModel, summary="档案解析Agent")
async def parse_resume_agent(
    payload: Dict[str, Any],
    db: Session = Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_AGENT_EXECUTE)
):
    """档案解析 Agent：简历解析→字段标准化→标签→画像→查重"""
    if payload.get("async_mode") is True or payload.get("wait") is False:
        return _submit_legacy_async("resume", payload, current_user)
    file_path = payload.get("file_path")
    file_name = payload.get("file_name", "resume")
    # 兼容 Dify Workflow 传纯文本 resume_text（无文件路径场景）：写临时文件再走原流程
    resume_text = payload.get("resume_text")
    if not file_path and resume_text:
        import os, tempfile
        file_path = os.path.join(tempfile.gettempdir(), f"dify_resume_{os.getpid()}.txt")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(resume_text)
        # 修正：file_name 必须带 .txt 扩展名，否则解析器按扩展名判格式会报"不支持的文件格式"
        file_name = f"resume_{os.getpid()}.txt"
    # if not file_path:
    #     raise HTTPException(status_code=400, detail="file_path 必填")
    if not file_path:
        raise HTTPException(status_code=400, detail="file_path 或 resume_text 必填")
    try:
        result = await resume_parser_agent.parse_resume(file_path, file_name)
        return ResponseModel(code=200, message="解析完成", data=result)
    except Exception as e:
        return ResponseModel(code=500, message=f"档案解析失败: {str(e)}", data={"success": False, "error": str(e)})


@router.post("/analyze-assessment", response_model=ResponseModel, summary="测评分析Agent")
async def analyze_assessment_agent(
    payload: Dict[str, Any],
    db: Session = Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_AGENT_EXECUTE)
):
    """测评分析 Agent：结果分析→雷达图→优劣分析→发展建议"""
    if payload.get("async_mode") is True or payload.get("wait") is False:
        return _submit_legacy_async("assessment", payload, current_user)
    # result_id = payload.get("result_id")
    # 兼容 Dify Workflow 传 assessment_result_id
    result_id = payload.get("result_id") or payload.get("assessment_result_id")
    if not result_id:
        raise HTTPException(status_code=400, detail="result_id 必填")
    try:
        result = AssessmentAnalysisAgent().analyze(result_id)
        result = _apply_input_gate(result, hint=f"测评结果不存在或不可分析: result_id={result_id}")
        return ResponseModel(code=200, message=_gate_message(result, "分析完成"), data=result)
    except Exception as e:
        return ResponseModel(code=500, message=f"测评分析失败: {str(e)}", data={"success": False, "error": str(e)})


@router.post("/match-position", response_model=ResponseModel, summary="岗位匹配Agent")
async def match_position_agent(
    payload: Dict[str, Any],
    db: Session = Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_AGENT_EXECUTE)
):
    """岗位匹配 Agent：硬条件过滤 + 向量匹配 + LLM 精排"""
    if payload.get("async_mode") is True or payload.get("wait") is False:
        return _submit_legacy_async("matching", payload, current_user)
    position_id = payload.get("position_id")
    talent_id = payload.get("talent_id")
    try:
        if position_id:
            result = MatchingAgent().match_position_to_talents(int(position_id))
            result = _apply_input_gate(result, hint=f"岗位不存在或无法匹配: position_id={position_id}")
        elif talent_id:
            result = MatchingAgent().match_talent_to_positions(int(talent_id))
            result = _apply_input_gate(result, hint=f"人才不存在或无法匹配: talent_id={talent_id}")
        else:
            raise HTTPException(status_code=400, detail="position_id 或 talent_id 必填其一")
        return ResponseModel(code=200, message=_gate_message(result, "匹配完成"), data=result)
    except HTTPException:
        raise
    except Exception as e:
        return ResponseModel(code=500, message=f"岗位匹配失败: {str(e)}", data={"success": False, "error": str(e)})


@router.post("/recommend-training", response_model=ResponseModel, summary="培训赋能Agent")
async def recommend_training_agent(
    payload: Dict[str, Any],
    db: Session = Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_AGENT_EXECUTE)
):
    """培训赋能 Agent：能力缺口诊断 + 个性化学习路径 + 课程推荐"""
    if payload.get("async_mode") is True or payload.get("wait") is False:
        return _submit_legacy_async("training", payload, current_user)
    talent_id = payload.get("talent_id")
    position_id = payload.get("position_id")
    if not talent_id:
        raise HTTPException(status_code=400, detail="talent_id 必填")
    try:
        result = training_agent.analyze(int(talent_id), int(position_id) if position_id else None)
        result = _apply_input_gate(result, hint=f"人才不存在或无法生成培训方案: talent_id={talent_id}")
        return ResponseModel(code=200, message=_gate_message(result, "培训推荐完成"), data=result)
    except Exception as e:
        return ResponseModel(code=500, message=f"培训推荐失败: {str(e)}", data={"success": False, "error": str(e)})


@router.post("/data-analysis", response_model=ResponseModel, summary="数据决策Agent")
async def data_analysis_agent(
    payload: Dict[str, Any],
    db: Session = Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_AGENT_EXECUTE)
):
    """数据决策 Agent：结构/趋势/异常分析 或 NL2SQL 自然语言查询"""
    if payload.get("async_mode") is True or payload.get("wait") is False:
        return _submit_legacy_async("data_decision", payload, current_user)
    analysis_type = payload.get("analysis_type", "structure")
    question = payload.get("question")
    try:
        if analysis_type == "nl2sql":
            result = data_decision_agent.analyze(
                analysis_type="nl2sql",
                nl2sql_question=question,
                engine=get_mysql_engine(),  # 传入只读 engine，让 SQL 真正执行返回结果
                db=db
            )
        else:
            result = data_decision_agent.analyze(analysis_type=analysis_type, db=db)
        return ResponseModel(code=200, message="分析完成", data=result)
    except Exception as e:
        return ResponseModel(code=500, message=f"数据分析失败: {str(e)}", data={"success": False, "error": str(e)})


@router.post("/nl2sql", response_model=ResponseModel, summary="自然语言查询")
async def nl2sql_query(
    payload: Dict[str, Any],
    current_user: dict = Depends(AUTH_AGENT_EXECUTE)
):
    """自然语言→SQL→只读分析（经 VannaAdapter 安全层，仅只读库执行）"""
    question = payload.get("question")
    if not question:
        raise HTTPException(status_code=400, detail="question 必填")
    try:
        result = data_decision_agent.analyze(
            analysis_type="nl2sql",
            nl2sql_question=question,
            engine=get_mysql_engine()  # 传入只读 engine，让 SQL 真正执行返回结果
        )
        return ResponseModel(code=200, message="NL2SQL 完成", data=result)
    except Exception as e:
        return ResponseModel(code=500, message=f"NL2SQL 失败: {str(e)}", data={"success": False, "error": str(e)})


# 支持生成深度报告的各 Agent 类型
_DIFY_REPORT_AGENTS = {"resume", "assessment", "matching", "training", "data_decision"}

# ── Dify 深度报告 异步任务表（单进程内存存储，演示/答辩足够）────────────
# task_id -> {status: pending|running|success|failed, agent, report, message, created_at, updated_at}
_dify_tasks: Dict[str, Dict[str, Any]] = {}
_dify_tasks_lock = threading.Lock()
_DIFY_TASK_TTL = 3600  # 任务结果保留 1h（防内存膨胀，过期懒清理）


def _run_dify_task_async(agent: str, inputs: Dict[str, Any], task_id: str, timeout: int = 300):
    """后台线程执行 Dify 工作流生成报告，结果写入任务表。"""
    try:
        with _dify_tasks_lock:
            if task_id in _dify_tasks:
                _dify_tasks[task_id]["status"] = "running"
                _dify_tasks[task_id]["updated_at"] = _time.time()
        result = dify_adapter.run_report(agent=agent, inputs=inputs, timeout=timeout)
        with _dify_tasks_lock:
            if task_id in _dify_tasks:
                if result.get("success"):
                    _dify_tasks[task_id].update(
                        status="success", report=result.get("report", ""),
                        message="深度报告生成完成", updated_at=_time.time())
                else:
                    _dify_tasks[task_id].update(
                        status="failed", report="",
                        message=result.get("message", "Dify 深度报告生成失败"),
                        updated_at=_time.time())
    except Exception as e:
        with _dify_tasks_lock:
            if task_id in _dify_tasks:
                _dify_tasks[task_id].update(status="failed", message=str(e), updated_at=_time.time())


@router.post("/dify-report", response_model=ResponseModel, summary="提交 Dify 深度报告任务（异步）")
async def dify_deep_report_submit(
    payload: Dict[str, Any],
    current_user: dict = Depends(AUTH_AGENT_EXECUTE)
):
    """
    提交 Dify 深度报告任务（异步，立即返回 task_id，前端轮询结果）。

    设计（异步任务模式）：
    - 本地 Agent 结构化结果已驱动前端表格/雷达图（主链路不变）；
    - Dify 工作流链路长（内部回调本后端再叠加 LLM 生成，30s~数分钟），
      同步等待不可靠，故改为「提交即返回 + 后台线程执行 + 前端轮询」；
    - Dify 未启用/无 key/失败 → 任务 status=failed，前端据此优雅降级。

    请求: { agent, inputs, timeout? }
    返回: data = { task_id, status: "pending|running" }
    """
    agent = (payload.get("agent") or "").strip().lower()
    if agent not in _DIFY_REPORT_AGENTS:
        raise HTTPException(status_code=400, detail=f"不支持的 agent 类型: {agent}（可选: {sorted(_DIFY_REPORT_AGENTS)}）")
    inputs = payload.get("inputs") or {}
    timeout = int(payload.get("timeout", 300))

    task_id = f"dr_{int(_time.time() * 1000)}{_uuid.uuid4().hex[:6]}"
    # 过期懒清理
    now = _time.time()
    with _dify_tasks_lock:
        for tid in [t for t, v in _dify_tasks.items() if now - v.get("created_at", now) > _DIFY_TASK_TTL]:
            _dify_tasks.pop(tid, None)
        _dify_tasks[task_id] = {
            "status": "pending", "agent": agent, "report": "", "message": "任务已提交",
            "created_at": now, "updated_at": now,
        }

    thread = threading.Thread(target=_run_dify_task_async, args=(agent, inputs, task_id, timeout), daemon=True)
    thread.start()
    return ResponseModel(code=200, message="深度报告任务已提交", data={
        "task_id": task_id, "status": "pending", "agent": agent,
        "hint": "Dify 工作流执行约需 30s~数分钟，请轮询查询进度。",
    })


@router.get("/dify-report/{task_id}", response_model=ResponseModel, summary="查询 Dify 深度报告任务")
async def dify_deep_report_query(
    task_id: str,
    current_user: dict = Depends(AUTH_AGENT_EXECUTE)
):
    """查询 Dify 深度报告任务状态；完成后返回 report。"""
    with _dify_tasks_lock:
        task = dict(_dify_tasks.get(task_id) or {})
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    data = {
        "task_id": task_id,
        "status": task.get("status"),
        "agent": task.get("agent"),
        "report": task.get("report", ""),
        "message": task.get("message"),
    }
    if task.get("status") == "success":
        return ResponseModel(code=200, message="深度报告生成完成", data=data)
    if task.get("status") == "failed":
        return ResponseModel(code=200, message="深度报告生成失败", data=data)
    # pending / running
    return ResponseModel(code=202, message="深度报告生成中", data=data)


# ==================== 统一 Agent 任务控制面 ====================
_AGENT_NAMES = {"supervisor", "resume", "assessment", "matching", "training", "data_decision"}
_task_runners: Dict[str, Any] = {}


def _actor(user: dict) -> Optional[str]:
    if not isinstance(user, dict):
        return str(getattr(user, "id", None) or getattr(user, "user_id", None) or getattr(user, "username", None) or "") or None
    return str((user or {}).get("id") or (user or {}).get("user_id") or
               (user or {}).get("username") or (user or {}).get("sub") or "") or None


def _ensure_task_access(task: Dict[str, Any], user: Any) -> None:
    """任务级访问控制：仅任务所有者或超级管理员可读取、审批、转交和取消。"""
    if getattr(user, "is_superuser", False):
        return
    owner = task.get("owner")
    actor = _actor(user)
    if owner and actor != owner:
        raise HTTPException(status_code=403, detail="无权操作该 Agent 任务")


def _build_agent_runner(agent: str, inputs: Dict[str, Any]):
    """把现有五个业务 Agent 接入统一任务运行时。"""
    if agent == "resume":
        file_path = inputs.get("file_path")
        file_name = inputs.get("file_name", "resume")
        if not file_path and inputs.get("resume_text"):
            import os, tempfile
            file_path = os.path.join(tempfile.gettempdir(), f"agent_resume_{_uuid.uuid4().hex}.txt")
            with open(file_path, "w", encoding="utf-8") as fh:
                fh.write(str(inputs["resume_text"]))
            file_name = "resume.txt"
        if not file_path:
            raise HTTPException(status_code=400, detail="resume Agent 需要 file_path 或 resume_text")
        return lambda: resume_parser_agent.parse_resume(file_path, file_name)
    if agent == "assessment":
        result_id = inputs.get("result_id") or inputs.get("assessment_result_id")
        if not result_id:
            raise HTTPException(status_code=400, detail="assessment Agent 需要 result_id")
        return lambda: AssessmentAnalysisAgent().analyze(int(result_id))
    if agent == "matching":
        if inputs.get("position_id"):
            return lambda: MatchingAgent().match_position_to_talents(int(inputs["position_id"]))
        if inputs.get("talent_id"):
            return lambda: MatchingAgent().match_talent_to_positions(int(inputs["talent_id"]))
        raise HTTPException(status_code=400, detail="matching Agent 需要 position_id 或 talent_id")
    if agent == "training":
        if not inputs.get("talent_id"):
            raise HTTPException(status_code=400, detail="training Agent 需要 talent_id")
        return lambda: training_agent.analyze(int(inputs["talent_id"]), int(inputs["position_id"]) if inputs.get("position_id") else None)
    if agent == "data_decision":
        analysis_type = inputs.get("analysis_type", "structure")
        if analysis_type == "nl2sql":
            return lambda: data_decision_agent.analyze(analysis_type="nl2sql", nl2sql_question=inputs.get("question"), engine=get_mysql_engine())
        return lambda: data_decision_agent.analyze(analysis_type=analysis_type)
    raise HTTPException(status_code=400, detail="不支持的 Agent")


def _submit_legacy_async(agent: str, payload: Dict[str, Any], current_user: dict):
    """旧路由的异步兼容入口；默认保持原同步响应，async_mode=true 时返回任务。"""
    inputs = dict(payload)
    runner = _build_agent_runner(agent, inputs)
    task = agent_runtime.create_task(
        agent,
        payload.get("goal") or f"执行 {agent} Agent",
        inputs,
        session_id=payload.get("session_id"),
        requires_approval=bool(payload.get("requires_approval", False)),
        owner=_actor(current_user),
        dynamic_plan=bool(payload.get("dynamic_plan", False)),
        idempotency_key=payload.get("idempotency_key"),
    )
    _task_runners[task["task_id"]] = runner
    if task["status"] == "pending":
        agent_runtime._executor.submit(agent_runtime._run, task["task_id"], runner)
    return ResponseModel(code=202, message="Agent 异步任务已提交", data=task)


@router.post("/tasks", response_model=ResponseModel, summary="提交可追踪 Agent 任务")
async def submit_agent_task(payload: Dict[str, Any], db: Session = Depends(get_mysql_session), current_user: dict = Depends(AUTH_AGENT_EXECUTE)):
    agent = (payload.get("agent") or "").strip().lower()
    if agent not in _AGENT_NAMES:
        raise HTTPException(status_code=400, detail=f"agent 必须是 {sorted(_AGENT_NAMES)}")
    inputs = payload.get("inputs") or {}
    permissions = get_user_permission_codes(current_user, db)
    goal = payload.get("goal") or f"执行 {agent} Agent"
    supervisor_plan = None
    if agent == "supervisor":
        supervisor_plan = supervisor_planner.plan(
            goal,
            inputs,
            use_llm=payload.get("dynamic_plan"),
        )
        runner = None
    else:
        runner = _build_agent_runner(agent, inputs)
    task = agent_runtime.create_task(agent, goal, inputs,
                                     session_id=payload.get("session_id"),
                                     requires_approval=bool(payload.get("requires_approval", False)),
                                     owner=_actor(current_user),
                                     dynamic_plan=bool(payload.get("dynamic_plan", False)),
                                     plan_override=supervisor_plan,
                                     permissions=permissions,
                                     idempotency_key=payload.get("idempotency_key"))
    if agent == "supervisor":
        runner = lambda: dynamic_executor.execute(
            supervisor_plan,
            AgentContext.create(task_id=task["task_id"], session_id=task["session_id"], user_id=_actor(current_user), metadata={"permissions": set(task.get("permissions", []))}),
            replan_fn=lambda goal, inputs, context: supervisor_planner.plan(goal, inputs, context=context, use_llm=payload.get("dynamic_plan")),
        )
    _task_runners[task["task_id"]] = runner
    if task["status"] == "pending":
        agent_runtime._executor.submit(agent_runtime._run, task["task_id"], runner)
    return ResponseModel(code=202, message="Agent 任务已提交", data=task)


@router.get("/tasks/{task_id}", response_model=ResponseModel, summary="查询 Agent 任务")
async def get_agent_task(task_id: str, current_user: dict = Depends(AUTH_AGENT_EXECUTE)):
    task = agent_runtime.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    _ensure_task_access(task, current_user)
    return ResponseModel(code=200, message="查询成功", data=task)


@router.post("/tasks/{task_id}/approve", response_model=ResponseModel, summary="审批并恢复 Agent 任务")
async def approve_agent_task(task_id: str, payload: Dict[str, Any], current_user: dict = Depends(AUTH_AGENT_EXECUTE)):
    approved = bool(payload.get("approved", False))
    existing = agent_runtime.get(task_id)
    if not existing:
        raise HTTPException(status_code=404, detail="任务不存在")
    _ensure_task_access(existing, current_user)
    task = agent_runtime.approve(task_id, approved, _actor(current_user))
    if approved and task.get("status") == "pending" and task_id in _task_runners:
        agent_runtime._executor.submit(agent_runtime._run, task_id, _task_runners[task_id])
    return ResponseModel(code=200, message="已批准并恢复" if approved else "已拒绝", data=agent_runtime.get(task_id))


@router.post("/tasks/{task_id}/cancel", response_model=ResponseModel, summary="取消 Agent 任务")
async def cancel_agent_task(task_id: str, current_user: dict = Depends(AUTH_AGENT_EXECUTE)):
    task = agent_runtime.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    _ensure_task_access(task, current_user)
    task = agent_runtime.cancel(task_id, _actor(current_user))
    return ResponseModel(code=200, message="任务已取消", data=task)


@router.post("/tasks/{task_id}/handoff", response_model=ResponseModel, summary="转交 Agent 任务")
async def handoff_agent_task(task_id: str, payload: Dict[str, Any], current_user: dict = Depends(AUTH_AGENT_EXECUTE)):
    assignee = (payload.get("assignee") or "").strip()
    if not assignee:
        raise HTTPException(status_code=400, detail="assignee 必填")
    existing = agent_runtime.get(task_id)
    if not existing:
        raise HTTPException(status_code=404, detail="任务不存在")
    _ensure_task_access(existing, current_user)
    task = agent_runtime.handoff(task_id, assignee, _actor(current_user))
    return ResponseModel(code=200, message="任务已转交", data=task)


@router.get("/metrics", summary="Agent 指标")
async def agent_metrics(current_user: dict = Depends(AUTH_AGENT_EXECUTE)):
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(agent_runtime.metrics.prometheus(), media_type="text/plain; version=0.0.4")


@router.get("/capabilities", response_model=ResponseModel, summary="查询 Agent 能力目录")
async def agent_capabilities(current_user: dict = Depends(AUTH_AGENT_EXECUTE)):
    """向 Supervisor/Planner 暴露可选领域 Agent 和能力，避免硬编码调用函数。"""
    return ResponseModel(code=200, message="能力目录查询成功", data={
        "agents": domain_registry.list_agents(),
        "capabilities": domain_registry.list_capabilities(),
    })


@router.post("/plan", response_model=ResponseModel, summary="生成 Supervisor 动态计划")
async def create_supervisor_plan(payload: Dict[str, Any], current_user: dict = Depends(AUTH_AGENT_EXECUTE)):
    """只生成并校验计划，不执行任务，供前端预览和人工审批。"""
    goal = (payload.get("goal") or "").strip()
    if not goal:
        raise HTTPException(status_code=400, detail="goal 必填")
    context = AgentContext.create(session_id=payload.get("session_id"), user_id=_actor(current_user))
    plan = supervisor_planner.plan(
        goal,
        payload.get("inputs") or {},
        context=context,
        use_llm=payload.get("dynamic_plan"),
    )
    return ResponseModel(code=200, message="Supervisor 计划生成成功", data=plan)
