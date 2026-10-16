# -*- coding: utf-8 -*-
"""
业务域异常（轻量，非 HTTPException）。
每个 Agent 一个专用异常，code 命名空间隔离。
全局异常处理器统一捕获后转为 HTTP 响应（code → HTTP status 映射见 main.py）。
"""
from app.exceptions.base_api_exception import BaseAPIException, RAGException


# ─────────────────────────────────────────────────────────────
# 五大 Agent 域异常
# ─────────────────────────────────────────────────────────────

class ResumeParseException(BaseAPIException):
    """简历解析失败（文件损坏/格式不支持/LLM 解析异常）"""
    status_code = 422
    detail = "简历解析失败"
    code = "RESUME_PARSE_ERROR"


class AssessmentException(BaseAPIException):
    """人才测评失败（问卷未完成/结果不存在/AI 分析异常）"""
    status_code = 422
    detail = "人才测评分析失败"
    code = "ASSESSMENT_ERROR"


class MatchingException(BaseAPIException):
    """岗位匹配失败（无候选人/向量库为空/匹配计算异常）"""
    status_code = 422
    detail = "岗位匹配失败"
    code = "MATCHING_ERROR"


class TrainingException(BaseAPIException):
    """培训赋能失败（学员档案缺失/Gap 诊断失败/课程推荐异常）"""
    status_code = 422
    detail = "培训赋能分析失败"
    code = "TRAINING_ERROR"


class NL2SQLException(BaseAPIException):
    """NL2SQL 失败（LLM 生成失败/ SQL 校验不通过/执行异常）"""
    status_code = 422
    detail = "自然语言转 SQL 失败"
    code = "NL2SQL_ERROR"


class KnowledgeException(BaseAPIException):
    """知识库操作失败（文件解析/向量化/检索异常）"""
    status_code = 422
    detail = "知识库操作失败"
    code = "KNOWLEDGE_ERROR"
