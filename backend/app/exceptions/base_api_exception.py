# -*- coding: utf-8 -*-
"""
参考 large_health_reference/app/exceptions/base_api_exception.py
HTTP 异常继承体系 + 轻量域异常 RAGException。

派生树（status_code 基于 HTTP 标准，可被全局异常处理器统一捕获）：
- BaseAPIException(HTTPException)
  ├── 4xx 客户端错误
  │   ├── NotFound(404)
  │   ├── Conflict(409)
  │   ├── Unauthorized(401)
  │   ├── Forbidden(403)
  │   ├── BadRequest(400)
  │   └── ValidationError(422)
  ├── 服务层错误
  │   ├── DatabaseError(500)
  │   ├── ExternalServiceError(502)
  │   │   └── LLMServiceError(503)
  │   ├── WorkflowTimeout(504)
  │   └── WorkflowConfigurationError(500)
  ├── 文件错误
  │   ├── FileUploadError(500)
  │   ├── FileSizeExceeded(413)
  │   └── FileTypeUnsupported(415)
  ├── 缓存/限流
  │   ├── CacheError(500)
  │   ├── RateLimitExceeded(429)
  │   └── TimeoutError(504)
  └── UnsupportedFileType(415)
"""
from fastapi import HTTPException
from typing import Optional, Any


class BaseAPIException(HTTPException):
    """参考 large_health_reference BaseAPIException：类属性定义 status_code/detail。

    使用方式（与 HTTPException 兼容，但提供更丰富的错误结构）：
        raise NotFound("用户不存在", {"field": "user_id"})
        raise LLMServiceError("SiliconFlow 超时", {"model": "deepseek-v4"})
    """

    status_code: int = 500
    detail: str = "服务器内部错误"
    # 业务错误码（供前端解析，日志追踪）
    code: str = "INTERNAL_ERROR"

    def __init__(
        self,
        message: Optional[str] = None,
        extra: Optional[dict] = None,
    ):
        self.detail = message or self.__class__.detail
        # 合并 extra 到 __dict__，方便 JSON 序列化时透传
        if extra:
            self.extra = extra
        super().__init__(status_code=self.status_code, detail=self.detail)


# ─────────────────────────────────────────────────────────────
# 4xx 客户端错误
# ─────────────────────────────────────────────────────────────

class NotFound(BaseAPIException):
    status_code = 404
    detail = "资源不存在"
    code = "NOT_FOUND"


class Conflict(BaseAPIException):
    status_code = 409
    detail = "资源冲突"
    code = "CONFLICT"


class Unauthorized(BaseAPIException):
    status_code = 401
    detail = "未授权"
    code = "UNAUTHORIZED"


class Forbidden(BaseAPIException):
    status_code = 403
    detail = "禁止访问"
    code = "FORBIDDEN"


class BadRequest(BaseAPIException):
    status_code = 400
    detail = "请求参数错误"
    code = "BAD_REQUEST"


class ValidationError(BadRequest):
    """参数校验失败（422 通常由 Pydantic 抛出，这里提供显式调用路径）"""
    detail = "参数校验失败"
    code = "VALIDATION_ERROR"


# ─────────────────────────────────────────────────────────────
# 服务层错误
# ─────────────────────────────────────────────────────────────

class DatabaseError(BaseAPIException):
    status_code = 500
    detail = "数据库错误"
    code = "DATABASE_ERROR"


class ExternalServiceError(BaseAPIException):
    status_code = 502
    detail = "外部服务错误"
    code = "EXTERNAL_SERVICE_ERROR"


class LLMServiceError(ExternalServiceError):
    """LLM 服务不可用/超时/Key 无效"""
    status_code = 503
    detail = "LLM 服务不可用"
    code = "LLM_SERVICE_ERROR"


class WorkflowTimeout(BaseAPIException):
    status_code = 504
    detail = "Workflow 执行超时"
    code = "WORKFLOW_TIMEOUT"


class WorkflowConfigurationError(BaseAPIException):
    status_code = 500
    detail = "Workflow 配置错误"
    code = "WORKFLOW_CONFIG_ERROR"


# ─────────────────────────────────────────────────────────────
# 文件错误
# ─────────────────────────────────────────────────────────────

class FileUploadError(BaseAPIException):
    status_code = 500
    detail = "文件上传失败"
    code = "FILE_UPLOAD_ERROR"


class FileSizeExceeded(BaseAPIException):
    status_code = 413
    detail = "文件大小超出限制"
    code = "FILE_SIZE_EXCEEDED"


class FileTypeUnsupported(BaseAPIException):
    status_code = 415
    detail = "不支持的文件类型"
    code = "UNSUPPORTED_FILE_TYPE"


# ─────────────────────────────────────────────────────────────
# 缓存 / 限流 / 超时
# ─────────────────────────────────────────────────────────────

class CacheError(BaseAPIException):
    status_code = 500
    detail = "缓存服务错误"
    code = "CACHE_ERROR"


class RateLimitExceeded(BaseAPIException):
    status_code = 429
    detail = "请求频率超限"
    code = "RATE_LIMIT_EXCEEDED"


class TimeoutError(BaseAPIException):
    status_code = 504
    detail = "请求超时"
    code = "TIMEOUT"


class UnsupportedFileType(FileTypeUnsupported):
    """别名，与 HTTP 标准更一致"""
    pass


# ─────────────────────────────────────────────────────────────
# 轻量域异常（RAGException，不继承 HTTPException）
# 用于：strategy 层 / service 内部链路，携带业务 code
# 全局异常处理器统一捕获后转为 HTTP 响应
# ─────────────────────────────────────────────────────────────

class RAGException(Exception):
    """
    轻量域异常，参考 large_health_reference rag_exception.py。
    携带 code（业务错误码）+ message，供全局处理器统一转换为 HTTP 响应。
    使用方式：
        raise RAGException(code="CHUNK_EMPTY", message="文档切分为空")
        raise RAGException("VECTOR_SEARCH_FAILED", "Milvus 连接失败")
    """

    def __init__(self, code: str = "RAG_ERROR", message: str = ""):
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message}
