# -*- coding: utf-8 -*-
"""参考 large_health_reference/app/exceptions/ 架构，本项目统一异常体系。

异常分两类：
- BaseAPIException(HTTPException)：HTTP 层异常，全局处理器映射为标准 {code, message} 响应
- RAGException / 业务域异常：轻量域异常，携带业务 code，用于内部链路追踪
"""
from app.exceptions.base_api_exception import (
    BaseAPIException,
    # 4xx 客户端错误
    NotFound,
    Conflict,
    Unauthorized,
    Forbidden,
    BadRequest,
    ValidationError,
    # 服务层错误
    DatabaseError,
    ExternalServiceError,
    LLMServiceError,
    WorkflowTimeout,
    WorkflowConfigurationError,
    FileUploadError,
    FileSizeExceeded,
    FileTypeUnsupported,
    CacheError,
    RateLimitExceeded,
    TimeoutError,
    UnsupportedFileType,
    # 轻量域异常
    RAGException,
)
from app.exceptions.domain_exceptions import (
    ResumeParseException,
    AssessmentException,
    MatchingException,
    TrainingException,
    NL2SQLException,
    KnowledgeException,
)

__all__ = [
    # base
    "BaseAPIException",
    "RAGException",
    # HTTP 派生
    "NotFound", "Conflict", "Unauthorized", "Forbidden",
    "BadRequest", "ValidationError",
    "DatabaseError", "ExternalServiceError", "LLMServiceError",
    "WorkflowTimeout", "WorkflowConfigurationError",
    "FileUploadError", "FileSizeExceeded", "FileTypeUnsupported",
    "CacheError", "RateLimitExceeded", "TimeoutError", "UnsupportedFileType",
    # 业务域
    "ResumeParseException", "AssessmentException",
    "MatchingException", "TrainingException",
    "NL2SQLException", "KnowledgeException",
]
