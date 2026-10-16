"""
培训赋能 Agent（LangGraph 工作流版）
招标文件强制要求：LangGraph 有状态工作流，「测评→诊断→培训→提升→复测」闭环。
节点链路：diagnose_gap → recommend_courses → build_learning_path → generate_suggestions → END
Dify Chatflow 触发本模块 training endpoint。
"""
from typing import Dict, Any, List, Optional, TypedDict
from langgraph.graph import StateGraph, END
import logging

from app.agents.graph_runtime import compile_graph, invoke_graph
from app.core.database import get_mysql_session
from app.core.llm_factory import get_agent_llm
from app.models.talent import Talent
from app.models.position import JobPosition
from app.models.assessment import AssessmentResult
from app.models.training import Course

logger = logging.getLogger(__name__)


# ==================== 状态定义 ====================

class TrainingState(TypedDict):
    """LangGraph 培训赋能状态"""
    talent_id: int
    position_id: Optional[int]

    # 中间结果
    capability_profile: Dict[str, float]          # 人才当前能力画像
    target_capability: Dict[str, float]            # 目标岗位能力要求
    gaps: List[Dict[str, Any]]                     # 能力缺口列表
    recommended_courses: List[Dict[str, Any]]       # 推荐课程
    learning_path: List[Dict[str, Any]]             # 学习路径
    suggestions: str                               # LLM 提升建议
    talent_skills: List[str]                       # 人才技能名（课程推荐兜底用）

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
            logger.info("培训赋能Agent LLM初始化成功（SiliconFlow 或回退本地 Ollama）")
        except Exception as e:
            logger.warning(f"培训赋能Agent LLM初始化失败: {e}，使用规则降级")
    return _llm


# ==================== LangGraph 节点（全部同步）====================

def diagnose_gap(state: TrainingState) -> TrainingState:
    """
    节点1：能力缺口诊断
    - 优先取人才最新测评结果（capability_dimensions）
    - 次取 talent.portrait 字段
    - 对比目标岗位能力要求（position.capability_requirements）
    - 输出缺口列表（dimension / current / required / gap）
    """
    try:
        db = next(get_mysql_session())
        talent = db.query(Talent).filter(Talent.id == state["talent_id"]).first()
        if not talent:
            state["errors"].append("人才不存在")
            return state

        # 人才能力画像
        capability: Dict[str, float] = {}
        latest = db.query(AssessmentResult).filter(
            AssessmentResult.talent_id == state["talent_id"]
        ).order_by(AssessmentResult.submit_time.desc()).first()

        if latest and latest.capability_dimensions:
            dims = latest.capability_dimensions
            capability = dims if isinstance(dims, dict) else {}
        elif isinstance(getattr(talent, "portrait", None), dict):
            capability = talent.portrait.get("capability", {}) or {}

        # 人才技能名（供课程推荐兜底 + 能力画像兜底）
        skill_names: List[str] = []
        for s in (talent.skills_certificates or []):
            n = s.get("name") if isinstance(s, dict) else str(s)
            if n:
                skill_names.append(str(n).lower().strip())
        state["talent_skills"] = skill_names

        # 兜底：无测评结果、无画像 capability 时，基于人才技能/经验/学历生成基础能力画像，
        # 避免能力诊断返回空导致"培训赋能"空洞（甲方场景：未测评的人才也应得到基础诊断）。
        if not capability:
            exp = talent.experience_years or 0
            edu = (talent.education.value if getattr(talent, "education", None) else None) or "本科"
            capability = {
                "专业技能": min(45.0 + len(skill_names) * 6, 88.0),
                "项目经验": min(30.0 + exp * 6, 90.0),
                "学习能力": 70.0 if edu in ("本科", "硕士", "博士") else 55.0,
                "综合素质": 60.0,
            }

        state["capability_profile"] = capability

        # 目标能力要求
        target: Dict[str, float] = {}
        pos_id = state.get("position_id")
        if pos_id:
            position = db.query(JobPosition).filter(JobPosition.id == pos_id).first()
            if position and position.capability_requirements:
                req = position.capability_requirements
                target = req if isinstance(req, dict) else {}

        state["target_capability"] = target

        # 计算缺口
        gaps: List[Dict[str, Any]] = []
        for dim, req_val in target.items():
            cur = capability.get(dim, 0)
            try:
                req_val = float(req_val)
            except (TypeError, ValueError):
                req_val = 0.0
            if cur < req_val:
                gaps.append({
                    "dimension": dim,
                    "current": float(cur),
                    "required": req_val,
                    "gap": round(req_val - float(cur), 2)
                })

        # 无目标岗位时，基于能力画像给出通用短板
        if not gaps and capability:
            gaps = [
                {"dimension": d, "current": float(v), "required": 100.0, "gap": round(100.0 - float(v), 2)}
                for d, v in capability.items()
                if isinstance(v, (int, float)) and float(v) < 80
            ]

        state["gaps"] = gaps
        logger.info(f"能力缺口诊断: {len(gaps)} 个缺口")
    except Exception as e:
        state["errors"].append(f"能力缺口诊断失败: {e}")
    return state


def recommend_courses(state: TrainingState) -> TrainingState:
    """
    节点2：课程推荐
    基于能力缺口维度的标签匹配，推荐 top_k 课程。
    """
    try:
        if state.get("errors"):
            state["recommended_courses"] = []
            return state

        db = next(get_mysql_session())
        gap_dims = {g["dimension"] for g in state.get("gaps", [])}
        talent_skills = [s for s in (state.get("talent_skills") or [])]

        # 查询已发布课程（兼容 status 的 active/published 两种取值）
        try:
            courses = db.query(Course).filter(
                Course.status.in_(["published", "active", "PUBLISHED", "ACTIVE"])
            ).all()
        except Exception:
            courses = db.query(Course).all()

        scored: List[Dict[str, Any]] = []
        for c in courses:
            tags = [t for t in (c.tags if isinstance(c.tags, list) else [])]
            # 通道1：缺口维度 ∩ 课程标签
            gap_match = list(gap_dims & set(tags))
            # 通道2：人才技能与课程标签/课程名的语义子串匹配（缺口维度与技能标签体系不一致时的兜底）
            skill_match = []
            if not gap_match:
                for t in tags:
                    tl = str(t).lower()
                    for sk in talent_skills:
                        if sk and (sk in tl or tl in sk):
                            skill_match.append(t)
                            break
            match_count = len(gap_match) or len(skill_match)
            scored.append({
                "course_id": c.id,
                "course_name": c.course_name,
                "category": getattr(c, "course_category", "通用"),
                "tags": c.tags if isinstance(c.tags, list) else [],
                "match_score": match_count,
                "match_dimensions": gap_match or skill_match
            })

        scored.sort(key=lambda x: x["match_score"], reverse=True)
        state["recommended_courses"] = scored[:5]
        logger.info(f"课程推荐完成: {len(state['recommended_courses'])} 门")
    except Exception as e:
        state["errors"].append(f"课程推荐失败: {e}")
        state["recommended_courses"] = []
    return state


def build_learning_path(state: TrainingState) -> TrainingState:
    """
    节点3：生成有序学习路径
    按课程匹配度排序，末节点标注为综合考核节点。
    """
    try:
        courses = state.get("recommended_courses", [])
        path: List[Dict[str, Any]] = []
        for idx, c in enumerate(courses, start=1):
            path.append({
                "step": idx,
                "course_id": c["course_id"],
                "course_name": c["course_name"],
                "category": c.get("category", "通用"),
                "match_dimensions": c.get("match_dimensions", []),
                "is_exam_node": idx == len(courses),
                "reminder": f"建议在第{idx}阶段完成《{c['course_name']}》学习并通过阶段考核"
            })

        # 末节点加综合考核
        if path:
            path.append({
                "step": len(path) + 1,
                "course_id": 0,
                "course_name": "综合能力考核",
                "category": "考核",
                "match_dimensions": list({d for c in courses for d in c.get("match_dimensions", [])}),
                "is_exam_node": True,
                "reminder": "完成全部学习后参加综合能力考核，验证培训效果"
            })

        state["learning_path"] = path
        logger.info(f"学习路径生成: {len(path)} 个步骤")
    except Exception as e:
        state["errors"].append(f"生成学习路径失败: {e}")
        state["learning_path"] = []
    return state


def generate_suggestions(state: TrainingState) -> TrainingState:
    """
    节点4：LLM 生成提升建议（SiliconFlow DeepSeek-V4-Flash）
    无 LLM 时使用规则建议。
    """
    try:
        suggestions = ""
        gaps = state.get("gaps", [])
        llm = _get_llm()

        if llm and gaps:
            try:
                gap_summary = "; ".join(
                    f"{g['dimension']}（当前{g['current']}分，差距{g['gap']}分）"
                    for g in gaps[:5]
                )
                prompt = (
                    f"人才能力缺口分析如下：{gap_summary}。"
                    "请给出3条具体、可执行的能力提升建议（每条不超过40字），"
                    "结合当前缺口维度和推荐课程方向。"
                )
                resp = llm.invoke(prompt)
                suggestions = resp.content if hasattr(resp, "content") else str(resp)
            except Exception as e:
                logger.warning(f"LLM 建议生成失败: {e}")

        if not suggestions:
            suggestions = (
                "基于能力缺口匹配课程，按顺序完成学习路径并在末节点参加综合考核。"
                "建议关注短板维度，重点突破，争取在下一轮测评中达到目标分数。"
            )

        state["suggestions"] = suggestions

        # 组装最终输出
        state["output"] = {
            "success": len(state["errors"]) == 0,
            "talent_id": state["talent_id"],
            "position_id": state.get("position_id"),
            "capability_profile": state.get("capability_profile", {}),
            "gaps": gaps,
            "recommended_courses": state.get("recommended_courses", []),
            "learning_path": state.get("learning_path", []),
            "suggestions": suggestions,
            "errors": state.get("errors", [])
        }
        logger.info("培训赋能建议生成完成")
    except Exception as e:
        state["errors"].append(f"生成建议失败: {e}")
        state["output"] = {"success": False, "errors": state.get("errors", [])}
    return state


# ==================== 工作流构建 ====================

_workflow = None


def _get_workflow():
    global _workflow
    if _workflow is None:
        wf = StateGraph(TrainingState)
        wf.add_node("diagnose_gap", diagnose_gap)
        wf.add_node("recommend_courses", recommend_courses)
        wf.add_node("build_learning_path", build_learning_path)
        wf.add_node("generate_suggestions", generate_suggestions)

        wf.set_entry_point("diagnose_gap")
        wf.add_edge("diagnose_gap", "recommend_courses")
        wf.add_edge("recommend_courses", "build_learning_path")
        wf.add_edge("build_learning_path", "generate_suggestions")
        wf.add_edge("generate_suggestions", END)

        _workflow = compile_graph(wf)  # 注入 checkpointer 状态持久化
    return _workflow


# ==================== 公开接口（兼容旧 API）====================

class TrainingAgent:
    """培训赋能 Agent（LangGraph 工作流 + 向后兼容方法）"""

    def __init__(self):
        self._graph = _get_workflow()
        self._llm = _get_llm()

    def analyze(self, talent_id: int, position_id: Optional[int] = None) -> Dict[str, Any]:
        """统一分析入口（LangGraph 工作流）"""
        state: TrainingState = {
            "talent_id": talent_id,
            "position_id": position_id,
            "capability_profile": {},
            "target_capability": {},
            "gaps": [],
            "recommended_courses": [],
            "learning_path": [],
            "suggestions": "",
            "output": {},
            "errors": []
        }
        final = invoke_graph(self._graph, state)
        return final.get("output") or {
            "success": False,
            "errors": final.get("errors", ["未知错误"])
        }

    # ── 向后兼容的旧方法 ───────────────────────────────────────

    def diagnose_gap(self, talent_id: int, position_id: Optional[int] = None) -> Dict[str, Any]:
        state: TrainingState = {
            "talent_id": talent_id, "position_id": position_id,
            "capability_profile": {}, "target_capability": {}, "gaps": [],
            "recommended_courses": [], "learning_path": [], "suggestions": "", "talent_skills": [], "output": {}, "errors": []
        }
        from langgraph.graph import StateGraph, END as _END
        wf = StateGraph(TrainingState)
        wf.add_node("diagnose_gap", diagnose_gap)
        wf.set_entry_point("diagnose_gap")
        wf.add_edge("diagnose_gap", _END)
        result = invoke_graph(compile_graph(wf), state)
        return {"success": len(result.get("errors", [])) == 0, "gaps": result.get("gaps", [])}

    def recommend_courses(self, gaps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        state: TrainingState = {
            "talent_id": 0, "position_id": None,
            "capability_profile": {}, "target_capability": {}, "gaps": gaps,
            "recommended_courses": [], "learning_path": [], "suggestions": "", "talent_skills": [], "output": {}, "errors": []
        }
        state = recommend_courses(state)
        return state.get("recommended_courses", [])

    def build_learning_path(self, courses: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        state: TrainingState = {
            "talent_id": 0, "position_id": None,
            "capability_profile": {}, "target_capability": {}, "gaps": [],
            "recommended_courses": courses, "learning_path": [], "suggestions": "", "output": {}, "errors": []
        }
        state = build_learning_path(state)
        return state.get("learning_path", [])


training_agent = TrainingAgent()
