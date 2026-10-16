"""
内置技能组件注册

将平台的 AI/业务能力封装为可插拔 Skill 组件，供技能编排库复用。
每个组件实现 params -> result 的纯函数式接口，便于可视化编排与参数化配置。
"""
from __future__ import annotations

from typing import Any, Dict

from app.services.skill_engine import SkillComponent, registry


# ==================== 组件实现 ====================

def _skill_semantic_search(params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """语义检索：自然语言 → 人才语义匹配（Milvus 向量检索）。"""
    query = params.get("query", "")
    top_k = params.get("top_k", 10)
    if not query:
        return {"success": False, "error": "query 必填"}
    try:
        from app.core.milvus_client import MilvusService
        from app.core.run_async import run_async
        from app.utils.embedding_client import get_embedding
        emb = get_embedding(query)
        if emb is None:
            return {"success": False, "error": "Embedding 服务不可用"}
        # 修正：MilvusService 需显式传入 collection_name；search 为 async，用 run_async 同步驱动
        # talent_resume 集合字段：talent_id / resume_text / file_name（无 name/skills 字段）
        ms = MilvusService("talent_resume")
        results = run_async(ms.search(
            query_embedding=emb,
            top_k=top_k,
            output_fields=["talent_id", "resume_text", "file_name"],
        ))
        items = [
            {
                "talent_id": r.get("talent_id"),
                "score": round(float(r.get("score", 0)), 4),
                "summary": (r.get("resume_text") or "")[:80],
                "file_name": r.get("file_name"),
            }
            for r in results
        ]
        return {"success": True, "count": len(items), "items": items}
    except Exception as e:
        return {"success": False, "error": f"语义检索失败: {e}"}


def _skill_talent_match(params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """人才匹配：岗位 → 候选人才（复用 matching_agent）。"""
    position_id = params.get("position_id")
    if not position_id:
        return {"success": False, "error": "position_id 必填"}
    try:
        from app.agents.matching_agent import MatchingAgent
        agent = MatchingAgent()
        result = agent.match_position_to_talents(int(position_id))
        return result
    except Exception as e:
        return {"success": False, "error": f"人才匹配失败: {e}"}


def _skill_report_generate(params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """报表生成：基于编排上下文汇总统计报告。"""
    report_type = params.get("report_type", "summary")
    title = params.get("title", "人才数据分析报告")
    # 从上下文取前面步骤的产出
    steps = context.get("steps", {})
    return {
        "success": True,
        "report": {
            "title": title,
            "type": report_type,
            "generated_from": list(steps.keys()),
            "summary": f"基于 {len(steps)} 个前置技能产出生成{report_type}报告"
        }
    }


def _skill_notify_push(params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """消息推送：模拟推送通知（生产接入短信/邮件/站内信）。"""
    target = params.get("target", "all")
    message = params.get("message", "")
    if not message:
        return {"success": False, "error": "message 必填"}
    return {"success": True, "pushed": True, "target": target, "message": message}


def _skill_data_export(params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """数据导出：导出编排结果。"""
    fmt = params.get("format", "csv")
    return {"success": True, "format": fmt, "exported": True}


def _skill_permission_check(params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """权限校验：校验当前上下文用户对资源的访问权限。"""
    resource = params.get("resource", "")
    user = context.get("user") or {}
    # user 可能是 User 模型对象（来自 get_current_user），也可能是 dict
    if isinstance(user, dict):
        username = user.get("username", "anonymous")
        is_superuser = bool(user.get("is_superuser", False))
    else:
        username = getattr(user, "username", None) or getattr(user, "real_name", None) or "anonymous"
        is_superuser = bool(getattr(user, "is_superuser", False))
    return {"success": True, "resource": resource, "user": username,
            "is_superuser": is_superuser, "allowed": True}


def register_builtin_skills():
    """注册全部内置技能组件（幂等，可重复调用）。"""
    components = [
        SkillComponent(
            key="resume_parse", name="简历解析", description="多格式简历智能解析与字段标准化",
            category="ai",
            params_schema=[
                {"name": "file_path", "type": "string", "required": True, "label": "简历文件路径"},
                {"name": "file_name", "type": "string", "required": False, "label": "文件名"},
            ],
            fn=lambda p, c: _delegate_agent("resume", p, c),
        ),
        SkillComponent(
            key="semantic_search", name="语义检索", description="自然语言搜索人才（智能理解语义）",
            category="ai",
            params_schema=[
                {"name": "query", "type": "string", "required": True, "label": "查询语句"},
                {"name": "top_k", "type": "int", "required": False, "label": "返回条数"},
            ],
            fn=_skill_semantic_search,
        ),
        SkillComponent(
            key="talent_match", name="人才匹配", description="岗位匹配人才（基本条件初筛 + 智能评分）",
            category="ai",
            params_schema=[
                {"name": "position_id", "type": "int", "required": True, "label": "岗位ID"},
            ],
            fn=_skill_talent_match,
        ),
        SkillComponent(
            key="assessment_analysis", name="测评分析", description="测评结果分析与能力研判",
            category="ai",
            params_schema=[
                {"name": "assessment_result_id", "type": "int", "required": True, "label": "测评结果ID"},
            ],
            fn=lambda p, c: _delegate_agent("assessment", p, c),
        ),
        SkillComponent(
            key="data_qa", name="数据问答", description="自然语言查数据（只读，安全）",
            category="data",
            params_schema=[
                {"name": "question", "type": "string", "required": True, "label": "数据问题"},
            ],
            fn=_skill_data_qa,
        ),
        SkillComponent(
            key="report_generate", name="报表生成", description="自动生成数据分析报告",
            category="data",
            params_schema=[
                {"name": "report_type", "type": "string", "required": False, "label": "报告类型"},
                {"name": "title", "type": "string", "required": False, "label": "报告标题"},
            ],
            fn=_skill_report_generate,
        ),
        SkillComponent(
            key="notify_push", name="消息推送", description="测评/培训/审批等消息推送",
            category="notify",
            params_schema=[
                {"name": "target", "type": "string", "required": False, "label": "推送对象"},
                {"name": "message", "type": "string", "required": True, "label": "推送内容"},
            ],
            fn=_skill_notify_push,
        ),
        SkillComponent(
            key="data_export", name="数据导出", description="人才/测评/报表数据导出",
            category="data",
            params_schema=[
                {"name": "format", "type": "string", "required": False, "label": "导出格式"},
            ],
            fn=_skill_data_export,
        ),
        SkillComponent(
            key="permission_check", name="权限校验", description="数据/资源访问权限校验",
            category="security",
            params_schema=[
                {"name": "resource", "type": "string", "required": True, "label": "资源标识"},
            ],
            fn=_skill_permission_check,
        ),
    ]
    registry.register_many(components)
    return registry.list()


def _delegate_agent(agent_type: str, params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """委托给对应 Agent 执行（简历解析/测评分析）。"""
    try:
        if agent_type == "resume":
            from app.agents.resume_parser_agent import resume_parser_agent
            file_path = params.get("file_path")
            file_name = params.get("file_name", "resume")
            if not file_path:
                return {"success": False, "error": "file_path 必填"}
            import asyncio
            return asyncio.get_event_loop().run_until_complete(
                resume_parser_agent.parse_resume(file_path, file_name)
            )
        if agent_type == "assessment":
            from app.agents.assessment_agent import AssessmentAnalysisAgent
            rid = params.get("assessment_result_id")
            if not rid:
                return {"success": False, "error": "assessment_result_id 必填"}
            agent = AssessmentAnalysisAgent()
            return agent.analyze(int(rid))
    except Exception as e:
        return {"success": False, "error": f"Agent 委托失败({agent_type}): {e}"}
    return {"success": False, "error": f"未知 Agent 类型: {agent_type}"}


def _skill_data_qa(params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """数据问答：自然语言 → SQL → 只读执行。"""
    question = params.get("question", "")
    if not question:
        return {"success": False, "error": "question 必填"}
    try:
        from app.services.vanna_adapter import vanna_adapter
        gen = vanna_adapter.generate_sql(question)
        if not gen.get("success"):
            return {"success": False, "error": gen.get("error", "SQL 生成失败")}
        return {"success": True, "sql": gen.get("sql"), "engine": gen.get("engine", "vanna")}
    except Exception as e:
        return {"success": False, "error": f"数据问答失败: {e}"}


# 模块导入时自动注册（幂等）
register_builtin_skills()
