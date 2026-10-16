"""
LangGraph 通用运行时能力层

考核强制要求（模块三②）：
- 所有智能体支持 LangGraph 状态持久化（checkpointer）
- 人工介入（interrupt 节点）
- 任务循环调度 / 分支判断
- 失败重试机制

本模块提供统一的能力封装，供五大 Agent 复用：

1. get_checkpointer()          —— 状态持久化（优先 RedisSaver，降级 MemorySaver，SQLite 可选）
2. compile_graph(...)          —— 统一编译入口，自动注入 checkpointer
3. retry_loop / interrupt 能力 —— 通过 build_retry_loop_graph 构建「循环 + 人工介入」工作流
4. HumanApprovalNode           —— 人工介入挂起/恢复的封装

设计原则：不破坏现有五大 Agent 的直线/分支逻辑，通过统一编译入口注入持久化能力；
同时提供一个完整的「循环 + 人工介入」通用工作流（RetryWithHumanApproval），
演示并落地 LangGraph 的 interrupt / loop / checkpointer 三大高级能力。
"""
from __future__ import annotations

import logging
import threading
import uuid
from typing import Any, Callable, Dict, List, Optional, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, END

logger = logging.getLogger(__name__)


def invoke_graph(graph: Any, state: Dict[str, Any], thread_id: Optional[str] = None):
    """
    带 checkpointer 的图统一调用入口。

    当图编译时注入了 checkpointer（MemorySaver/RedisSaver），invoke 必须提供
    configurable.thread_id，否则抛 "Checkpointer requires ... 'configurable' keys"。
    这里自动生成 thread_id（或使用调用方传入的），保证 5 大 Agent 的 invoke 都能正确执行。
    """
    config = {"configurable": {"thread_id": thread_id or f"agent-{uuid.uuid4().hex[:12]}"}}
    return graph.invoke(state, config=config)


# ==================== 状态持久化（Checkpointer） ====================

_checkpointer = None
_checkpointer_lock = threading.Lock()


def get_checkpointer():
    """
    获取全局共享 checkpointer（状态持久化）。

    优先级：
    1. RedisSaver —— 生产环境跨进程持久化（langgraph-checkpoint-redis）
    2. MemorySaver —— 单进程内存持久化（开发/默认，零额外依赖，已实测可用）
    3. 返回 None —— 极端情况（此时 Agent 退化为无持久化，仅日志告警）

    线程安全懒初始化，避免多 Agent 重复创建。
    """
    global _checkpointer
    if _checkpointer is not None:
        return _checkpointer

    with _checkpointer_lock:
        if _checkpointer is not None:
            return _checkpointer

        # 1) 尝试 RedisSaver（生产级跨进程持久化）
        try:
            from app.core.config import settings
            from langgraph.checkpoint.redis import RedisSaver
            redis_uri = getattr(settings, "REDIS_URI", "redis://localhost:6379")
            saver = RedisSaver.from_conn_string(redis_uri)
            logger.info("LangGraph checkpointer: RedisSaver 就绪（跨进程持久化）")
            _checkpointer = saver
            return _checkpointer
        except Exception as e:
            logger.info(f"RedisSaver 不可用（{e}），降级 MemorySaver")

        # 2) MemorySaver（进程内持久化）
        try:
            saver = MemorySaver()
            logger.info("LangGraph checkpointer: MemorySaver 就绪（进程内持久化）")
            _checkpointer = saver
            return _checkpointer
        except Exception as e:
            logger.error(f"MemorySaver 初始化失败: {e}")
            return None


def compile_graph(state_graph: StateGraph, interrupt_before: Optional[List[str]] = None,
                  interrupt_after: Optional[List[str]] = None, checkpointer=None):
    """
    统一编译入口：自动注入 checkpointer（状态持久化）+ interrupt（人工介入）。

    参数：
    - state_graph: 已 add_node / add_edge 的 StateGraph 实例
    - interrupt_before: 在执行这些节点前挂起，等待人工介入
    - interrupt_after:  在执行这些节点后挂起，等待人工介入
    - checkpointer: 显式传入则优先使用，否则走全局 get_checkpointer()
    """
    checkpointer = checkpointer or get_checkpointer()

    compile_kwargs: Dict[str, Any] = {}
    if checkpointer is not None:
        compile_kwargs["checkpointer"] = checkpointer
    if interrupt_before:
        compile_kwargs["interrupt_before"] = interrupt_before
    if interrupt_after:
        compile_kwargs["interrupt_after"] = interrupt_after

    try:
        return state_graph.compile(**compile_kwargs)
    except TypeError:
        # 兼容不支持某些参数的 LangGraph 版本，退化为最保守编译
        if "interrupt_after" in compile_kwargs:
            compile_kwargs.pop("interrupt_after")
        if "interrupt_before" in compile_kwargs:
            compile_kwargs.pop("interrupt_before")
        logger.warning("LangGraph 版本不支持 interrupt 参数，退化为仅 checkpointer 编译")
        return state_graph.compile(**compile_kwargs)


# ==================== 人工介入 + 循环（通用能力演示） ====================

class RetryWithHumanApprovalState(TypedDict, total=False):
    """
    「循环 + 人工介入」通用状态。

    字段：
    - task: 待处理的任务负载（dict）
    - max_retries: 最大重试次数（循环上限，防死循环）
    - attempt: 当前尝试次数
    - result: 任务执行结果
    - success: 最近一次执行是否成功
    - approved: 人工审批结果（None=待审批）
    - error: 最近一次错误
    - next: 内部路由字段（条件边用）
    """
    task: Dict[str, Any]
    max_retries: int
    attempt: int
    result: Dict[str, Any]
    success: bool
    approved: Optional[bool]
    error: str
    next: str


def build_retry_loop_graph(
    execute_fn: Callable[[Dict[str, Any]], Dict[str, Any]],
    approve_fn: Callable[[Dict[str, Any]], bool] = None,
    should_retry_fn: Callable[[Dict[str, Any]], bool] = None,
    max_retries: int = 3,
):
    """
    构建一个完整的「循环 + 人工介入 + 状态持久化」LangGraph 工作流：

        entry(execute) ──失败──> human_approval(interrupt) ──批准──> retry(循环)
              │ 成功                     │拒绝                          │
              v                          v                             v
           success ──────────────────> END ───────────────────────> (回到 execute)

    三大能力落地：
    - 循环：retry 节点通过条件边回到 execute，形成回环（attempt 递增，max_retries 兜底）
    - 人工介入：human_approval 节点设置 interrupt，执行时挂起等待外部注入审批结果后 resume
    - 状态持久化：compile 时注入 checkpointer，任意节点后可保存/恢复状态

    参数：
    - execute_fn: 任务执行函数，入参 state dict，返回结果 dict（含 "success" 字段）
    - approve_fn: 审批函数，返回 True/False（默认：始终批准）
    - should_retry_fn: 是否重试判断，入参 state，返回 bool（默认：attempt < max_retries）
    - max_retries: 最大重试次数
    """

    def execute_node(state: Dict[str, Any]) -> Dict[str, Any]:
        state["attempt"] = state.get("attempt", 0) + 1
        try:
            result = execute_fn(state.get("task") or {})
            state["result"] = result
            state["success"] = bool(result.get("success", False))
            if state["success"]:
                state["next"] = "success"
            else:
                state["error"] = result.get("error", "执行失败")
                state["next"] = "human_approval"
        except Exception as e:
            state["success"] = False
            state["error"] = str(e)
            state["next"] = "human_approval"
        return state

    def human_approval_node(state: Dict[str, Any]) -> Dict[str, Any]:
        # 人工介入节点：正常会在 interrupt 处挂起，等待外部 approve 后 resume。
        # 若已携带审批结果（approved 非 None），直接判定。
        if state.get("approved") is None:
            if approve_fn is not None:
                state["approved"] = bool(approve_fn(state))
            else:
                # 默认策略：无审批函数时自动批准（保证流程可闭环，避免永久挂起）
                state["approved"] = True
        state["next"] = "retry" if state["approved"] else "end"
        return state

    def retry_node(state: Dict[str, Any]) -> Dict[str, Any]:
        # 判断是否继续循环
        if should_retry_fn is not None:
            can_retry = bool(should_retry_fn(state))
        else:
            can_retry = state.get("attempt", 0) < max_retries
        state["next"] = "execute" if can_retry else "end"
        return state

    def success_node(state: Dict[str, Any]) -> Dict[str, Any]:
        return state

    def _route(state: Dict[str, Any]) -> str:
        return state.get("next", "end")

    graph = StateGraph(RetryWithHumanApprovalState)
    graph.add_node("execute", execute_node)
    graph.add_node("human_approval", human_approval_node)
    graph.add_node("retry", retry_node)
    graph.add_node("success_end", success_node)

    graph.set_entry_point("execute")

    # 条件边：按 state["next"] 路由
    graph.add_conditional_edges("execute", _route, {
        "success": "success_end",
        "human_approval": "human_approval",
        "end": END,
    })
    graph.add_conditional_edges("human_approval", _route, {
        "retry": "retry",
        "end": END,
    })
    graph.add_conditional_edges("retry", _route, {
        "execute": "execute",  # 循环回环
        "end": END,
    })
    graph.add_edge("success_end", END)

    # 人工介入：human_approval 节点前挂起
    return compile_graph(graph, interrupt_before=["human_approval"])


# ==================== 人工介入封装 ====================

class HumanApproval:
    """
    人工介入（interrupt）的高层封装。

    用法：
        ha = HumanApproval()
        # 构建带审批节点的图（interrupt_before 已设置）
        graph = build_retry_loop_graph(...)
        # 首次 invoke 会挂起在 human_approval 前，返回 __interrupt__
        # 审批后通过 approve_and_resume 恢复执行
    """

    @staticmethod
    def is_interrupted(result: Any) -> bool:
        """判断 invoke 是否因 interrupt 挂起（LangGraph 0.2.x：无错误但未到 END）。"""
        if isinstance(result, dict) and result.get("__interrupt__") is not None:
            return True
        return False

    @staticmethod
    def is_paused(graph: Any, config: Dict[str, Any]) -> bool:
        """通过 graph.get_state 判断线程是否处于挂起（interrupt）状态。"""
        try:
            state = graph.get_state(config)
            return bool(state and state.next)
        except Exception:
            return False

    @staticmethod
    def get_interrupt(result: Any) -> Any:
        """提取 interrupt 挂起信息。"""
        if isinstance(result, dict):
            return result.get("__interrupt__")
        return None
