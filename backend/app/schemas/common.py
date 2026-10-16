"""
统一响应格式
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Any, Generic, TypeVar, List

T = TypeVar("T")


class ResponseModel(BaseModel, Generic[T]):
    """统一响应模型"""

    code: int = Field(..., description="状态码")
    message: str = Field(..., description="响应消息")
    data: Optional[T] = Field(None, description="响应数据")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "code": 200,
            "message": "操作成功",
            "data": None
        }
    })


class PageModel(BaseModel, Generic[T]):
    """分页响应模型"""

    items: List[T] = Field(..., description="数据列表")
    total: int = Field(..., description="总数")
    page: int = Field(..., description="当前页码")
    page_size: int = Field(..., description="每页大小")
    total_pages: int = Field(..., description="总页数")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "items": [],
            "total": 100,
            "page": 1,
            "page_size": 10,
            "total_pages": 10
        }
    })


class ErrorResponse(BaseModel):
    """错误响应模型"""

    code: int = Field(..., description="错误码")
    message: str = Field(..., description="错误消息")
    details: Optional[Any] = Field(None, description="错误详情")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "code": 400,
            "message": "请求参数错误",
            "details": "字段 'name' 不能为空"
        }
    })


class SuccessResponse(ResponseModel):
    """成功响应"""

    code: int = Field(default=200, description="状态码")
    message: str = Field(default="操作成功", description="响应消息")


class CreatedResponse(ResponseModel):
    """创建成功响应"""

    code: int = Field(default=201, description="状态码")
    message: str = Field(default="创建成功", description="响应消息")


class DeletedResponse(ResponseModel):
    """删除成功响应"""

    code: int = Field(default=200, description="状态码")
    message: str = Field(default="删除成功", description="响应消息")


class UpdatedResponse(ResponseModel):
    """更新成功响应"""

    code: int = Field(default=200, description="状态码")
    message: str = Field(default="更新成功", description="响应消息")
