"""
自定义异常
"""
from typing import Any, Optional


class AppException(Exception):
    """应用基础异常"""
    
    def __init__(
        self,
        code: int,
        message: str,
        status_code: int = 400,
        details: Optional[Any] = None
    ):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details
        super().__init__(f"[{code}] {message}")


# ==================== 通用异常 ====================

class BadRequestException(AppException):
    """400 Bad Request"""
    
    def __init__(self, message: str = "请求参数错误", details: Optional[Any] = None):
        super().__init__(code=400, message=message, status_code=400, details=details)


class UnauthorizedException(AppException):
    """401 Unauthorized"""
    
    def __init__(self, message: str = "未授权访问", details: Optional[Any] = None):
        super().__init__(code=401, message=message, status_code=401, details=details)


class ForbiddenException(AppException):
    """403 Forbidden"""
    
    def __init__(self, message: str = "禁止访问", details: Optional[Any] = None):
        super().__init__(code=403, message=message, status_code=403, details=details)


class NotFoundException(AppException):
    """404 Not Found"""
    
    def __init__(self, message: str = "资源不存在", details: Optional[Any] = None):
        super().__init__(code=404, message=message, status_code=404, details=details)


class ConflictException(AppException):
    """409 Conflict"""
    
    def __init__(self, message: str = "资源冲突", details: Optional[Any] = None):
        super().__init__(code=409, message=message, status_code=409, details=details)


class ValidationException(AppException):
    """422 Validation Error"""
    
    def __init__(self, message: str = "数据验证失败", details: Optional[Any] = None):
        super().__init__(code=422, message=message, status_code=422, details=details)


class RateLimitException(AppException):
    """429 Too Many Requests"""
    
    def __init__(self, message: str = "请求过于频繁", details: Optional[Any] = None):
        super().__init__(code=429, message=message, status_code=429, details=details)


class InternalServerException(AppException):
    """500 Internal Server Error"""
    
    def __init__(self, message: str = "服务器内部错误", details: Optional[Any] = None):
        super().__init__(code=500, message=message, status_code=500, details=details)


class ServiceUnavailableException(AppException):
    """503 Service Unavailable"""
    
    def __init__(self, message: str = "服务暂不可用", details: Optional[Any] = None):
        super().__init__(code=503, message=message, status_code=503, details=details)


# ==================== 业务异常 ====================

class AuthenticationException(AppException):
    """认证异常"""
    
    def __init__(self, message: str = "认证失败", details: Optional[Any] = None):
        super().__init__(code=1001, message=message, status_code=401, details=details)


class TokenExpiredException(AppException):
    """Token过期异常"""
    
    def __init__(self, message: str = "Token已过期", details: Optional[Any] = None):
        super().__init__(code=1002, message=message, status_code=401, details=details)


class PermissionDeniedException(AppException):
    """权限拒绝异常"""
    
    def __init__(self, message: str = "无权限执行此操作", details: Optional[Any] = None):
        super().__init__(code=1003, message=message, status_code=403, details=details)


class UserExistsException(AppException):
    """用户已存在异常"""
    
    def __init__(self, message: str = "用户已存在", details: Optional[Any] = None):
        super().__init__(code=2001, message=message, status_code=409, details=details)


class TalentNotFoundException(AppException):
    """人才不存在异常"""
    
    def __init__(self, message: str = "人才不存在", details: Optional[Any] = None):
        super().__init__(code=3001, message=message, status_code=404, details=details)


class PositionNotFoundException(AppException):
    """岗位不存在异常"""
    
    def __init__(self, message: str = "岗位不存在", details: Optional[Any] = None):
        super().__init__(code=3002, message=message, status_code=404, details=details)


class ResumeParseException(AppException):
    """简历解析异常"""
    
    def __init__(self, message: str = "简历解析失败", details: Optional[Any] = None):
        super().__init__(code=3003, message=message, status_code=400, details=details)


class AssessmentNotFoundException(AppException):
    """测评不存在异常"""
    
    def __init__(self, message: str = "测评不存在", details: Optional[Any] = None):
        super().__init__(code=4001, message=message, status_code=404, details=details)


class TrainingNotFoundException(AppException):
    """培训不存在异常"""
    
    def __init__(self, message: str = "培训不存在", details: Optional[Any] = None):
        super().__init__(code=5001, message=message, status_code=404, details=details)


# ==================== AI异常 ====================

class AIModelException(AppException):
    """AI模型异常"""
    
    def __init__(self, message: str = "AI模型调用失败", details: Optional[Any] = None):
        super().__init__(code=6001, message=message, status_code=500, details=details)


class EmbeddingException(AppException):
    """Embedding异常"""
    
    def __init__(self, message: str = "向量嵌入失败", details: Optional[Any] = None):
        super().__init__(code=6002, message=message, status_code=500, details=details)


class RAGException(AppException):
    """RAG检索异常"""
    
    def __init__(self, message: str = "RAG检索失败", details: Optional[Any] = None):
        super().__init__(code=6003, message=message, status_code=500, details=details)


class NL2SQLException(AppException):
    """NL2SQL异常"""
    
    def __init__(self, message: str = "NL2SQL转换失败", details: Optional[Any] = None):
        super().__init__(code=6004, message=message, status_code=500, details=details)


class AgentException(AppException):
    """Agent异常"""
    
    def __init__(self, message: str = "Agent执行失败", details: Optional[Any] = None):
        super().__init__(code=6005, message=message, status_code=500, details=details)


# ==================== 数据库异常 ====================

class DatabaseException(AppException):
    """数据库异常"""
    
    def __init__(self, message: str = "数据库操作失败", details: Optional[Any] = None):
        super().__init__(code=7001, message=message, status_code=500, details=details)


class DuplicateKeyException(AppException):
    """重复键异常"""
    
    def __init__(self, message: str = "数据已存在", details: Optional[Any] = None):
        super().__init__(code=7002, message=message, status_code=409, details=details)


class VectorDBException(AppException):
    """向量数据库异常"""
    
    def __init__(self, message: str = "向量数据库操作失败", details: Optional[Any] = None):
        super().__init__(code=7003, message=message, status_code=500, details=details)


# ==================== 文件异常 ====================

class FileUploadException(AppException):
    """文件上传异常"""
    
    def __init__(self, message: str = "文件上传失败", details: Optional[Any] = None):
        super().__init__(code=8001, message=message, status_code=400, details=details)


class FileTooLargeException(AppException):
    """文件过大异常"""
    
    def __init__(self, message: str = "文件大小超出限制", details: Optional[Any] = None):
        super().__init__(code=8002, message=message, status_code=400, details=details)


class UnsupportedFileTypeException(AppException):
    """不支持的文件类型异常"""
    
    def __init__(self, message: str = "不支持的文件类型", details: Optional[Any] = None):
        super().__init__(code=8003, message=message, status_code=400, details=details)
