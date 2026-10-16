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
from app.core.llm_factory import get_silicon_flow_llm
from app.core.run_async import run_async
from app.utils.resume_parser import ResumeParser
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
    """构建 SiliconFlow LLM，失败返回 None"""
    try:
        return get_silicon_flow_llm(temperature=0.1)
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
    """节点2：LLM 结构化信息提取（姓名/学历/公司/职位等）"""
    try:
        if not state.get("raw_text"):
            state["errors"].append("无原始文本可提取")
            return state

        if _llm is None:
            state["errors"].append("LLM 不可用，跳过结构化提取")
            return state

        prompt = (
            "你是一个专业的简历解析助手。请从以下简历文本中提取结构化信息。\n\n"
            f"简历文本:\n{state['raw_text'][:4000]}\n\n"
            "请以JSON格式返回（无法提取的字段填null）:\n"
            '{"name":"姓名","gender":"male/female","phone":"手机号",'
            '"education":"学历","major":"专业","experience_years":工作年限数字,'
            '"current_company":"当前公司","current_position":"当前职位",'
            '"skills":"技能列表","self_introduction":"自我介绍"}'
        )
        resp = _llm.invoke(prompt)
        content = resp.content if hasattr(resp, "content") else str(resp)
        extracted = extract_json(content) or {}
        state["extracted_data"].update({k: v for k, v in extracted.items() if v is not None})
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


def generate_tags(state: AgentState) -> AgentState:
    """节点4：LLM 生成人才标签（技能/行业/能力/经验标签）"""
    try:
        if not _llm:
            state["tags"] = []
            return state

        raw = state.get("raw_text", "")[:3000]
        prompt = (
            "根据以下简历文本，生成5-10个人才标签（技能/行业/能力/经验方向）。\n"
            f"简历:\n{raw}\n\n"
            "请以JSON数组格式返回标签列表，如：[\"Python\", \"团队管理\", \"金融行业\"]"
        )
        resp = _llm.invoke(prompt)
        content = resp.content if hasattr(resp, "content") else str(resp)
        tags = extract_json(content) or []
        state["tags"] = tags if isinstance(tags, list) else []
    except Exception as e:
        state["errors"].append(f"标签生成失败: {e}")
        state["tags"] = []
    return state


def generate_portrait(state: AgentState) -> AgentState:
    """节点5：LLM 生成人才画像（技术/管理/沟通/创新/协作/学习能力评分）"""
    try:
        if not _llm:
            state["portrait"] = {}
            return state

        raw = state.get("raw_text", "")[:3000]
        tags_str = ", ".join(state.get("tags", [])) or "无"
        prompt = (
            "根据以下简历和标签，生成人才能力画像评分（每项0-100分）。\n"
            f"简历:\n{raw}\n标签: {tags_str}\n\n"
            "请以JSON格式返回:\n"
            '{"technical_ability":分数,"management_ability":分数,'
            '"communication_ability":分数,"innovation_ability":分数,'
            '"teamwork_ability":分数,"learning_ability":分数,'
            '"summary":"综合评价一段话"}'
        )
        resp = _llm.invoke(prompt)
        content = resp.content if hasattr(resp, "content") else str(resp)
        portrait = extract_json(content) or {}
        state["portrait"] = portrait
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
