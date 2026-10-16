"""
简历解析 Agent（LangGraph 工作流版）
招标文件强制要求：LangGraph 有状态工作流。
节点链路：parse_file → extract_info → validate_data → generate_tags → generate_portrait
"""
import re
import logging
from typing import Dict, Any, List, TypedDict

from langgraph.graph import StateGraph, END

from app.agents.graph_runtime import compile_graph, invoke_graph
from app.core.config import settings
from app.core.llm_factory import get_agent_llm
from app.core.run_async import run_async
from app.utils.resume_parser import ResumeParser, extract_skills_by_rule
from app.utils.json_utils import extract_json

logger = logging.getLogger(__name__)


# ==================== 状态定义 ====================

class AgentState(TypedDict):
    """LangGraph Agent 状态（所有字段显式声明）"""
    file_path: str
    file_name: str
    raw_text: str
    extracted_data: Dict[str, Any]
    validated_data: Dict[str, Any]
    tags: List[str]
    portrait: Dict[str, Any]
    confidence: float
    errors: List[str]


# ==================== LLM 初始化 ====================

def _build_llm():
    """构建 LLM：优先 SiliconFlow，未配密钥时自动回退本地 Ollama；全部不可用返回 None"""
    try:
        return get_agent_llm(temperature=0.1)
    except Exception as e:
        logger.warning(f"简历解析Agent LLM初始化失败: {e}，使用规则降级")
        return None


_llm = _build_llm()


# ==================== LangGraph 节点（全部同步）====================

def parse_file(state: AgentState) -> AgentState:
    """节点1：PDF/Word 解析，提取原始文本"""
    try:
        parser = ResumeParser()
        # ResumeParser.parse 为 async def，通过 run_async 驱动
        result = run_async(parser.parse(state["file_path"], state["file_name"]))
        if result.get("success"):
            state["raw_text"] = result.get("text", "")
            state["extracted_data"] = result.get("talent_data", {})
            state["confidence"] = result.get("confidence", 0.85)
        else:
            state["errors"].append(result.get("error", "解析失败"))
    except Exception as e:
        state["errors"].append(f"文件解析失败: {e}")
    return state


def extract_info(state: AgentState) -> AgentState:
    """节点2：**一次** LLM 调用同时产出「结构化字段 + 人才标签 + 能力画像」

    为什么合并（2026-10-16 实测）：原实现由 extract_info / generate_tags /
    generate_portrait 三个节点各发一次 LLM 请求，本地 CPU 上三次串行推理耗时
    超过 300s，正好撞上 Nginx `proxy_read_timeout 300s` —— 前端拿到 504，
    请求被取消、档案也没落库，表现为「简历解析不可用」。
    合并为单次调用后耗时降到约 1/3，后续两个节点改为在本节点结果上做规整与
    规则兜底，既保留 5 节点工作流结构，又让端到端稳定落在超时之内。
    """
    try:
        if not state.get("raw_text"):
            state["errors"].append("无原始文本可提取")
            return state

        if _llm is None:
            state["errors"].append("LLM 不可用，跳过结构化提取")
            return state

        prompt = (
            "你是专业的简历解析助手。请从下面的简历文本中一次性完成三项任务。\n\n"
            f"简历文本:\n{state['raw_text'][:4000]}\n\n"
            "请严格以 JSON 对象返回，不要输出任何多余文字，格式：\n"
            "{\n"
            '  "talent": {"name":"姓名","gender":"男或女","phone":"手机号","email":"邮箱",'
            '"education":"高中/大专/本科/硕士/博士","major":"专业","experience_years":工作年限数字,'
            '"current_company":"当前公司","current_position":"当前职位",'
            '"skills":["3-15个专业技能名词，单个不超过20字，如 Python、MySQL、分布式系统"],'
            '"self_introduction":"一段话自我介绍"},\n'
            '  "tags": ["5-10个人才标签，技能/行业/能力/经验方向"],\n'
            '  "portrait": {"technical_ability":0-100,"management_ability":0-100,'
            '"communication_ability":0-100,"innovation_ability":0-100,'
            '"teamwork_ability":0-100,"learning_ability":0-100,"summary":"综合评价一段话"}\n'
            "}\n"
            "无法确定的字段填 null。"
        )
        resp = _llm.invoke(prompt)
        content = resp.content if hasattr(resp, "content") else str(resp)
        parsed = extract_json(content) or {}

        talent = parsed.get("talent")
        if isinstance(talent, dict):
            # 只覆盖"有效值"：LLM 对某字段返回 null / "" / [] / {} 时保留规则基线结果，
            # 避免空值把基线已抽到的字段抹掉（实测 1.7B 模型常把 skills 返回成空列表）。
            state["extracted_data"].update({
                k: v for k, v in talent.items()
                if v is not None and v != "" and v != [] and v != {}
            })

        tags = parsed.get("tags")
        if isinstance(tags, list):
            state["tags"] = [str(t).strip() for t in tags if str(t).strip()]

        portrait = parsed.get("portrait")
        if isinstance(portrait, dict):
            state["portrait"] = portrait

        # 技能兜底：LLM 未给出技能时用规则词典从原文再抽一次。
        # skills_certificates 是岗位匹配硬条件过滤的输入，为空会让候选人被整体筛掉。
        if not state["extracted_data"].get("skills") and state.get("raw_text"):
            fallback_skills = extract_skills_by_rule(state["raw_text"])
            if fallback_skills:
                state["extracted_data"]["skills"] = fallback_skills
    except Exception as e:
        state["errors"].append(f"信息提取失败: {e}")
    return state


def validate_data(state: AgentState) -> AgentState:
    """节点3：字段格式验证，手机号/邮箱/必填字段"""
    try:
        data = state.get("extracted_data", {})
        if not data:
            state["errors"].append("无提取数据可验证")
            state["confidence"] = 0
            return state

        # 必填字段
        for field, label in [("name", "姓名"), ("phone", "手机号")]:
            if not data.get(field):
                state["errors"].append(f"缺少必填字段: {label}")

        # 手机号格式
        phone = data.get("phone", "")
        if phone and not re.match(r"^1[3-9]\d{9}$", str(phone)):
            state["errors"].append("手机号格式不正确")

        # 邮箱格式
        email = data.get("email", "")
        if email and not re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", str(email)):
            state["errors"].append("邮箱格式不正确")

        if not state["errors"]:
            state["validated_data"] = data
        else:
            state["confidence"] = round(state.get("confidence", 1.0) * 0.8, 4)
    except Exception as e:
        state["errors"].append(f"数据验证失败: {e}")
    return state


# 标签上限与画像六维
_TAG_LIMIT = 10
_PORTRAIT_KEYS = (
    "technical_ability",
    "management_ability",
    "communication_ability",
    "innovation_ability",
    "teamwork_ability",
    "learning_ability",
)
_EDU_INDEX = {"高中": 0, "中专": 0, "大专": 1, "本科": 2, "硕士": 3, "博士": 4}


def generate_tags(state: AgentState) -> AgentState:
    """节点4：标签规整 + 规则兜底

    LLM 已在节点2一并产出标签，本节点负责清洗、去重、限量；
    若 LLM 未产出（不可用或未返回），则按学历/经验/技能做规则推导，
    保证这条链路在任何情况下都有结果（不再发第二次 LLM 请求）。
    """
    try:
        raw_tags = [str(t).strip() for t in (state.get("tags") or []) if str(t).strip()]

        seen, cleaned = set(), []
        for t in raw_tags:
            key = t.lower()
            if key not in seen:
                seen.add(key)
                cleaned.append(t)

        if not cleaned:
            data = state.get("extracted_data") or {}
            edu = data.get("education")
            years = data.get("experience_years") or 0
            if edu:
                cleaned.append(str(edu))
            if years:
                cleaned.append(f"{years}年经验")
            skills = data.get("skills")
            if isinstance(skills, list):
                cleaned.extend(str(s) for s in skills if s)
            elif isinstance(skills, str) and skills.strip():
                cleaned.extend(s.strip() for s in skills.replace("、", ",").split(",") if s.strip())

        state["tags"] = cleaned[:_TAG_LIMIT]
    except Exception as e:
        state["errors"].append(f"标签生成失败: {e}")
        state["tags"] = []
    return state


def generate_portrait(state: AgentState) -> AgentState:
    """节点5：画像规整 + 规则兜底

    LLM 已在节点2一并产出六维评分，本节点做取值范围修正与缺失补齐；
    若 LLM 未产出，则按学历/经验/技能数量推导一份规则画像（不再发第三次 LLM 请求）。
    """
    try:
        raw_portrait = dict(state.get("portrait") or {})
        cleaned: Dict[str, Any] = {}
        for key in _PORTRAIT_KEYS:
            try:
                cleaned[key] = int(max(0, min(100, round(float(raw_portrait.get(key))))))
            except (TypeError, ValueError):
                cleaned[key] = None

        if all(v is None for v in cleaned.values()):
            data = state.get("extracted_data") or {}
            years = data.get("experience_years") or 0
            edu_idx = _EDU_INDEX.get(str(data.get("education")), 2)
            skills = data.get("skills")
            if isinstance(skills, list):
                skill_cnt = len(skills)
            elif isinstance(skills, str):
                skill_cnt = len([s for s in skills.replace("、", ",").split(",") if s.strip()])
            else:
                skill_cnt = 0

            base = 55 + edu_idx * 5 + min(years, 10)
            cleaned = {
                "technical_ability": min(100, base + skill_cnt * 3),
                "management_ability": min(100, base - 5 + (5 if years >= 5 else 0)),
                "communication_ability": min(100, base),
                "innovation_ability": min(100, base - 3),
                "teamwork_ability": min(100, base + 2),
                "learning_ability": min(100, base + 4),
            }
            cleaned = {k: int(v) for k, v in cleaned.items()}
            summary = "基于学历/经验/技能推导的规则画像（LLM 未参与）"
        else:
            cleaned = {k: (v if v is not None else 60) for k, v in cleaned.items()}
            summary = str(raw_portrait.get("summary") or "").strip() or "综合简历信息生成"

        cleaned["summary"] = summary
        state["portrait"] = cleaned
    except Exception as e:
        state["errors"].append(f"画像生成失败: {e}")
        state["portrait"] = {}
    return state


# ==================== 工作流构建 ====================

def _build_workflow():
    workflow = StateGraph(AgentState)
    workflow.add_node("parse_file", parse_file)
    workflow.add_node("extract_info", extract_info)
    workflow.add_node("validate_data", validate_data)
    workflow.add_node("generate_tags", generate_tags)
    workflow.add_node("generate_portrait", generate_portrait)

    workflow.set_entry_point("parse_file")
    workflow.add_edge("parse_file", "extract_info")
    workflow.add_edge("extract_info", "validate_data")
    workflow.add_edge("validate_data", "generate_tags")
    workflow.add_edge("generate_tags", "generate_portrait")
    workflow.add_edge("generate_portrait", END)
    return compile_graph(workflow)  # 注入 checkpointer 状态持久化


_agent = _build_workflow()


# ==================== 公开接口 ====================

def parse_resume(file_path: str, file_name: str = "resume") -> Dict[str, Any]:
    """
    LangGraph 工作流入口（同步，LangGraph 0.2.x StateGraph.invoke）
    文件解析 → LLM提取 → 验证 → 标签 → 画像
    """
    try:
        initial_state: AgentState = {
            "file_path": file_path,
            "file_name": file_name,
            "raw_text": "",
            "extracted_data": {},
            "validated_data": {},
            "tags": [],
            "portrait": {},
            "confidence": 0.85,
            "errors": []
        }

        final_state = invoke_graph(_agent, initial_state)

        return {
            "success": len(final_state["errors"]) == 0,
            "talent_data": final_state.get("validated_data") or final_state.get("extracted_data", {}),
            "tags": final_state.get("tags", []),
            "portrait": final_state.get("portrait", {}),
            "confidence": final_state.get("confidence", 0),
            "raw_text": final_state.get("raw_text", ""),
            "warnings": final_state.get("errors", [])
        }
    except Exception as e:
        logger.error(f"简历解析Agent执行失败: {e}")
        return {
            "success": False,
            "error": str(e),
            "talent_data": None,
            "tags": [],
            "portrait": {},
            "confidence": 0,
            "raw_text": "",
            "warnings": []
        }


# 向后兼容旧全局实例（同步包装）
class ResumeParserAgent:
    async def parse_resume(self, file_path: str, file_name: str = "resume") -> Dict[str, Any]:
        return parse_resume(file_path, file_name)


resume_parser_agent = ResumeParserAgent()
