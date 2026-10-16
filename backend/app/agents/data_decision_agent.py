"""
数据决策 Agent（LangGraph 工作流版）
招标文件强制要求：LangGraph + Vanna.ai + LangChain。
节点链路：nl2sql_node → [condition] → structure/trend/anomaly → report_node → END
支持自然语言 SQL 生成、结构分析、趋势分析、异常预警、报告生成。
NL2SQL 仅走 VannaAdapter 只读安全层，绝不写数据。
Dify Chatflow 触发 /api/v1/agents/nl2sql 或 /data-decision。
"""
from enum import Enum as _Enum
from typing import Dict, Any, Optional, List, TypedDict, Union, Callable
from langgraph.graph import StateGraph, END
import logging
import contextvars

from app.agents.graph_runtime import compile_graph, invoke_graph
from app.core.database import get_mysql_session
from app.services.vanna_adapter import vanna_adapter
from app.core.llm_factory import get_agent_llm
from app.core.run_async import run_async
from app.models.talent import Talent, TalentStatus
from app.models.assessment import AssessmentResult
from app.models.training import LearningRecord, ExaminationRecord

logger = logging.getLogger(__name__)

# 数据库会话通过 contextvar 在 analyze() -> 节点 之间传递，绕开 LangGraph
# state 的序列化问题（Session 不可 msgpack 序列化，进 state 会触发
# checkpointer TypeError）。concurrent.futures 线程池会传播 contextvar，
# 因此节点线程可读到当前请求的 db。
_db_ctx: contextvars.ContextVar = contextvars.ContextVar("data_decision_db", default=None)


def _enum_val(v) -> str:
    return v.value if isinstance(v, _Enum) else str(v)


# ==================== 状态定义 ====================

class DataDecisionState(TypedDict):
    """LangGraph 数据决策状态"""
    # 输入
    analysis_type: str          # nl2sql | structure | trend | anomaly | report
    nl2sql_question: str        # 自然语言问题
    engine: Any                 # SQLAlchemy read-only engine（可选）

    # 路由中间态（LangGraph 条件边用）
    _next: Optional[str]        # 内部：下一个目标节点名

    # 数据库会话（来自 FastAPI DI；测试时被 SQLite 覆盖）
    db: Any                     # SQLAlchemy Session（可选）

    # 中间结果
    nl2sql_result: Dict[str, Any]
    structure_data: Dict[str, Any]
    trend_data: Dict[str, Any]
    anomaly_data: Dict[str, Any]
    report_content: Dict[str, Any]

    # 最终输出
    output: Dict[str, Any]
    errors: List[str]


# ==================== LLM（全局单例）====================

_llm = None


def _get_llm():
    global _llm
    if _llm is None:
        try:
            _llm = get_agent_llm(temperature=0.1)
            logger.info("数据决策Agent LLM初始化成功（SiliconFlow 或回退本地 Ollama）")
        except Exception as e:
            logger.warning(f"数据决策Agent LLM初始化失败: {e}，使用规则降级")
    return _llm


# ==================== LangGraph 节点（全部同步）====================

def nl2sql_node(state: DataDecisionState) -> DataDecisionState:
    """
    节点1：NL2SQL（自然语言 → SQL → 只读执行）
    仅走 VannaAdapter 安全层，禁止写操作。
    执行失败自动重试一次（带 MySQL 报错回注让 LLM 修正 SQL），提升成功率。
    """
    try:
        question = state.get("nl2sql_question", "").strip()
        if not question:
            state["errors"].append("NL2SQL 问题为空")
            return state

        # engine 优先用传入的，否则用全局 MySQL 引擎兜底
        engine = state.get("engine")
        if engine is None:
            try:
                from app.core.database import get_mysql_engine
                engine = get_mysql_engine()
            except Exception:
                engine = None

        MAX_ATTEMPTS = 2
        last_err = ""
        for attempt in range(1, MAX_ATTEMPTS + 1):
            # Step 1: 生成 SQL（第2次起把上次报错回注让 LLM 修正）
            hint = last_err if attempt > 1 else None
            gen = vanna_adapter.generate_sql(question, retry_hint=hint)
            if not gen.get("success"):
                state["nl2sql_result"] = {
                    "success": False,
                    "message": f"NL2SQL 生成失败（第{attempt}次）：{gen.get('error', 'Vanna 不可用')}",
                    "sql": None, "columns": [], "rows": [], "chart": None
                }
                break

            sql = gen["sql"]
            logger.info(f"NL2SQL 生成(attempt {attempt}): {sql[:80]}")

            if not engine:
                state["nl2sql_result"] = {
                    "success": True, "sql": sql, "message": "SQL 已生成（无执行引擎，未执行）",
                    "columns": [], "rows": [], "chart": None
                }
                break

            # Step 2: 只读执行
            exec_res = vanna_adapter.execute_readonly(sql, engine)
            if exec_res.get("success"):
                chart = None
                if exec_res.get("columns"):
                    chart = {
                        "type": "bar",
                        "x_field": exec_res["columns"][0],
                        "series": exec_res["columns"][1:],
                        "data": exec_res["rows"]
                    }
                state["nl2sql_result"] = {
                    "success": True,
                    "sql": sql,
                    "message": exec_res.get("error", "执行完成"),
                    "columns": exec_res.get("columns", []),
                    "rows": exec_res.get("rows", []),
                    "chart": chart
                }
                break

            # 执行失败：记录报错，若还有重试次数则回注修正
            last_err = str(exec_res.get("error", "执行失败"))
            logger.warning(f"NL2SQL 执行失败(attempt {attempt}): {last_err}")
            if attempt < MAX_ATTEMPTS:
                continue
            state["nl2sql_result"] = {
                "success": False,
                "sql": sql,
                "message": f"SQL 执行失败：{last_err}",
                "columns": exec_res.get("columns", []),
                "rows": exec_res.get("rows", []),
                "chart": None
            }
    except Exception as e:
        state["errors"].append(f"NL2SQL 节点失败: {e}")
    return state


def structure_node(state: DataDecisionState) -> DataDecisionState:
    """节点2a：人才结构分析（状态分布/学历分布/年龄结构）"""
    try:
        db = _db_ctx.get() or state.get("db") or next(get_mysql_session())
        total = db.query(Talent).count()

        from sqlalchemy import func
        from sqlalchemy import text

        # 状态分布（text() 包裹列名，避免 Enum 列 group_by 歧义）
        status_rows = db.query(
            Talent.status, func.count(Talent.id).label("cnt")
        ).group_by(text("status")).all()
        by_status = {_enum_val(r[0]): r[1] for r in status_rows}

        # 学历分布
        edu_rows = db.query(
            Talent.education, func.count(Talent.id).label("cnt")
        ).group_by(text("education")).all()
        by_education = {_enum_val(r[0]): r[1] for r in edu_rows}

        state["structure_data"] = {
            "total_talents": total,
            "by_status": by_status,
            "by_education": by_education,
            "chart": {
                "type": "pie",
                "title": "人才学历结构",
                "data": [{"name": k, "value": v} for k, v in by_education.items()]
            }
        }
        logger.info(f"结构分析完成: total={total}")
    except Exception as e:
        state["errors"].append(f"结构分析失败: {e}")
    return state


def trend_node(state: DataDecisionState) -> DataDecisionState:
    """节点2b：人才增长趋势（按月新增）"""
    try:
        db = _db_ctx.get() or state.get("db") or next(get_mysql_session())
        try:
            from sqlalchemy import func
            rows = db.query(
                func.date_format(Talent.created_at, "%Y-%m").label("month"),
                func.count().label("cnt")
            ).group_by("month").order_by("month").all()
            data = [{"month": r.month, "count": r.cnt} for r in rows]
        except Exception:
            # SQLite 等不支持 date_format 时降级
            rows = db.query(
                func.date(Talent.created_at).label("day"),
                func.count().label("cnt")
            ).group_by("day").order_by("day").all()
            data = [{"month": str(r.day), "count": r.cnt} for r in rows]

        state["trend_data"] = {
            "trend": data,
            "chart": {"type": "line", "x_field": "month", "series": ["count"], "data": data}
        }
    except Exception as e:
        state["errors"].append(f"趋势分析失败: {e}")
    return state


def anomaly_node(state: DataDecisionState) -> DataDecisionState:
    """节点2c：异常/预警分析（储备不足/培训滞后/技能短板）"""
    try:
        db = _db_ctx.get() or state.get("db") or next(get_mysql_session())
        alerts: List[Dict[str, Any]] = []

        reserve = db.query(Talent).filter(Talent.status == TalentStatus.RESERVE).count()
        active = db.query(Talent).filter(Talent.status == TalentStatus.ACTIVE).count()
        if active and reserve / max(active, 1) < 0.2:
            alerts.append({
                "level": "warning",
                "type": "人才储备不足",
                "detail": f"储备/在岗比={round(reserve / max(active, 1), 2)}"
            })

        unpassed = db.query(ExaminationRecord).filter(ExaminationRecord.passed == False).count()
        if unpassed:
            alerts.append({
                "level": "info",
                "type": "考核未通过",
                "detail": f"未通过考核 {unpassed} 人次"
            })

        state["anomaly_data"] = {"alerts": alerts, "alert_count": len(alerts)}
        logger.info(f"异常检测完成: {len(alerts)} 条预警")
    except Exception as e:
        state["errors"].append(f"异常检测失败: {e}")
    return state


def report_node(state: DataDecisionState) -> DataDecisionState:
    """节点3：综合报告生成（汇总 + LLM 决策建议）"""
    try:
        llm = _get_llm()
        suggestions = ""

        if llm:
            try:
                # 收集各维度数据
                summary_parts = []
                if state.get("structure_data"):
                    sd = state["structure_data"]
                    summary_parts.append(
                        f"人才总量 {sd.get('total_talents', 0)}，"
                        f"状态分布 {sd.get('by_status', {})}，"
                        f"学历分布 {sd.get('by_education', {})}"
                    )
                if state.get("anomaly_data"):
                    summary_parts.append(f"预警 {state['anomaly_data'].get('alerts', [])}")
                if state.get("nl2sql_result", {}).get("success"):
                    nr = state["nl2sql_result"]
                    summary_parts.append(
                        f"自定义查询: {nr.get('question', '')}，"
                        f"返回 {len(nr.get('rows', []))} 条记录"
                    )

                if summary_parts:
                    prompt = (
                        f"以下是人才平台数据概览：{'；'.join(summary_parts)}。"
                        "请给出2条具体、可执行的人才管理决策建议（每条不超过40字）。"
                    )
                    resp = llm.invoke(prompt)
                    suggestions = resp.content if hasattr(resp, "content") else str(resp)
            except Exception as e:
                logger.warning(f"LLM 决策建议失败: {e}")

        if not suggestions:
            suggestions = "建议补充储备人才、加强培训滞后人员赋能、关注关键岗位继任计划。"

        # 保持旧 API 兼容：structure 分析时将 total_talents 放到顶层
        analysis_type = state.get("analysis_type", "report")

        # structure/nl2sql 跳过 LLM 建议（LLM 调用慢，超 FastAPI 超时），直接给默认值
        if analysis_type in ("structure", "nl2sql"):
            suggestions = "建议补充储备人才、加强培训滞后人员赋能、关注关键岗位继任计划。"

        output = {
            "success": True,
            "suggestions": suggestions,
            "nl2sql": state.get("nl2sql_result"),
            "structure": state.get("structure_data"),
            "trend": state.get("trend_data"),
            "anomaly": state.get("anomaly_data"),
            "errors": state.get("errors", [])
        }
        # 结构分析：展平 total_talents 等关键字段到顶层（兼容旧测试）
        if analysis_type == "structure" and state.get("structure_data"):
            sd = state["structure_data"]
            output["total_talents"] = sd.get("total_talents", 0)
            output["by_status"] = sd.get("by_status", {})
            output["by_education"] = sd.get("by_education", {})
        state["output"] = output
        logger.info("报告生成完成")
    except Exception as e:
        state["errors"].append(f"报告生成失败: {e}")
    return state


# ==================== 路由函数（LangGraph 条件边）====================

# 路由映射表（用于 add_conditional_edges）
_ANALYSIS_TYPE_MAPPING = {
    "nl2sql": "nl2sql",
    "structure": "structure",
    "trend": "trend",
    "anomaly": "anomaly",
    "report": "report",
}


def _route_analysis_type(state: DataDecisionState) -> str:
    """LangGraph 0.2.x 条件路由：读取 state['_next'] 返回目标节点名"""
    return state.get("_next", "report")


# ==================== 工作流构建 ====================

_workflow = None


def _route_node(state: DataDecisionState) -> DataDecisionState:
    """专用路由节点（LangGraph 0.2.x：入口必须是命名节点）"""
    t = state.get("analysis_type", "report")
    state["_next"] = _ANALYSIS_TYPE_MAPPING.get(t, "report")
    return state


def _get_workflow():
    global _workflow
    if _workflow is None:
        wf = StateGraph(DataDecisionState)

        # 分析节点
        wf.add_node("route", _route_node)
        wf.add_node("nl2sql", nl2sql_node)
        wf.add_node("structure", structure_node)
        wf.add_node("trend", trend_node)
        wf.add_node("anomaly", anomaly_node)
        wf.add_node("report", report_node)

        # 入口 → 路由节点
        wf.set_entry_point("route")

        # 条件边：按 analysis_type 路由到对应分析节点
        # path_map 将函数返回值映射到实际节点名（LangGraph 0.2.x 要求）
        wf.add_conditional_edges(
            source="route",
            path=_route_analysis_type,
            path_map={
                "nl2sql": "nl2sql",
                "structure": "structure",
                "trend": "trend",
                "anomaly": "anomaly",
                "report": "report",
            },
        )

        # 各分析类型节点 → report → END
        wf.add_edge("nl2sql", "report")
        wf.add_edge("structure", "report")
        wf.add_edge("trend", "report")
        wf.add_edge("anomaly", "report")
        wf.add_edge("report", END)

        _workflow = compile_graph(wf)  # 注入 checkpointer 状态持久化
    return _workflow


# ==================== 公开接口（兼容旧 API）====================

class DataDecisionAgent:
    """数据决策 Agent（LangGraph 工作流 + 向后兼容方法）"""

    def __init__(self):
        self._graph = _get_workflow()
        self._llm = _get_llm()

    def _run(self, state: DataDecisionState) -> Dict[str, Any]:
        final = invoke_graph(self._graph, state)
        analysis_type = final.get("analysis_type", "")

        # 根据 analysis_type 从正确的 state 字段提取结果
        if analysis_type == "structure":
            sd = final.get("structure_data", {})
            output = dict(sd)  # 展平：total_talents / by_status / by_education 到顶层
            output.update({
                "success": True,
                "suggestions": final.get("output", {}).get("suggestions", ""),
                "structure": sd,
                "errors": final.get("errors", []),
            })
            return output
        elif analysis_type == "trend":
            return {
                "success": True,
                "trend": final.get("trend_data", {}),
                "suggestions": final.get("output", {}).get("suggestions", ""),
                "errors": final.get("errors", []),
            }
        elif analysis_type == "anomaly":
            return {
                "success": True,
                "anomaly": final.get("anomaly_data", {}),
                "suggestions": final.get("output", {}).get("suggestions", ""),
                "errors": final.get("errors", []),
            }
        elif analysis_type == "nl2sql":
            return {
                "success": True,
                "nl2sql": final.get("nl2sql_result", {}),
                "suggestions": final.get("output", {}).get("suggestions", ""),
                "errors": final.get("errors", []),
            }
        elif analysis_type == "report":
            return {
                "success": True,
                "report_content": final.get("report_content", {}),
                "nl2sql": final.get("nl2sql_result", {}),
                "structure": final.get("structure_data", {}),
                "trend": final.get("trend_data", {}),
                "anomaly": final.get("anomaly_data", {}),
                "suggestions": final.get("output", {}).get("suggestions", ""),
                "errors": final.get("errors", []),
            }

        # 通用意图：直接返回 output
        out = final.get("output")
        if out:
            return out
        return {
            "success": False,
            "errors": final.get("errors", ["未知错误"])
        }

    def analyze(
        self,
        analysis_type: str = "structure",
        nl2sql_question: Optional[str] = None,
        engine=None,
        db=None
    ) -> Dict[str, Any]:
        """
        统一分析入口（LangGraph 路由）
        analysis_type: nl2sql | structure | trend | anomaly | report
        db: SQLAlchemy Session（可选；测试时由 FastAPI DI 注入 SQLite 会话）
        """
        state: DataDecisionState = {
            "analysis_type": analysis_type,
            "nl2sql_question": nl2sql_question or "",
            # 注意：engine（SQLAlchemy Engine）不可序列化，不能塞入 state
            # （LangGraph checkpointer 保存状态时需序列化，Engine 会报错）。
            # nl2sql_node 内部会通过 get_mysql_engine() 自行获取引擎执行 SQL。
            "engine": None,
            # 注意：db（SQLAlchemy Session）不可序列化，不能塞入 state
            # （LangGraph checkpointer 保存状态时需 msgpack 序列化，Session 会报错）。
            # 节点内部已通过 next(get_mysql_session()) 自行获取会话。
            "db": None,
            "nl2sql_result": {},
            "structure_data": {},
            "trend_data": {},
            "anomaly_data": {},
            "report_content": {},
            "output": {},
            "errors": []
        }
        # 通过 contextvar 传递 db（不塞入 state，避免 checkpointer 序列化失败）
        token = _db_ctx.set(db)
        try:
            return self._run(state)
        finally:
            _db_ctx.reset(token)

    # ── 向后兼容的旧方法（LangGraph 内部调用对应节点）──────────────

    def nl2sql(self, question: str, engine=None) -> Dict[str, Any]:
        return self.analyze(analysis_type="nl2sql", nl2sql_question=question, engine=engine)

    def analyze_structure(self) -> Dict[str, Any]:
        return self.analyze(analysis_type="structure")

    def analyze_trend(self) -> Dict[str, Any]:
        return self.analyze(analysis_type="trend")

    def analyze_anomaly(self) -> Dict[str, Any]:
        return self.analyze(analysis_type="anomaly")

    def generate_report(self) -> Dict[str, Any]:
        return self.analyze(analysis_type="report")


data_decision_agent = DataDecisionAgent()
