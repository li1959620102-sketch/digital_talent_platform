"""
认证API路由
"""
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional
import logging

from app.core.config import settings
from app.core.database import get_mysql_session
from app.core.rbac import PermCode, user_has_permission
from app.schemas.common import ResponseModel
from app.services.auth_service import AuthService
from app.utils.jwt_handler import get_current_user
from app.models.permission import User

router = APIRouter()
logger = logging.getLogger(__name__)


class LoginRequest(BaseModel):
    """登录请求"""
    username: str
    password: str


class RegisterRequest(BaseModel):
    """注册请求（默认仅管理员可调用；开放自助注册时固定 user 角色）"""
    username: str = Field(..., min_length=3, max_length=50, description="用户名")
    password: str = Field(..., min_length=12, max_length=64, description="密码")
    real_name: Optional[str] = Field(None, max_length=50, description="真实姓名")
    email: Optional[str] = Field(None, max_length=100, description="邮箱")
    phone: Optional[str] = Field(None, max_length=20, description="手机号")
    role_code: Optional[str] = Field(
        None,
        description="角色编码(user/hr/admin/super_admin)，仅管理员创建时可指定；留空默认 user"
    )


class RefreshTokenRequest(BaseModel):
    """刷新令牌请求体，避免令牌出现在 URL、代理日志和浏览器历史中。"""
    refresh_token: Optional[str] = Field(None, min_length=20)


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    """将长期令牌限制在 HttpOnly Cookie 中，避免前端脚本读取。"""
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=settings.AUTH_COOKIE_SECURE,
        samesite="strict",
        path=f"{settings.API_PREFIX}/auth",
    )


async def register_guard(
    request: Request,
    db: Session = Depends(get_mysql_session)
) -> Optional[User]:
    """注册守卫（P0 安全加固）

    - `ALLOW_SELF_REGISTER=true` → 放行，返回 None（游客自助注册）
    - 否则 → 必须携带有效 token 且具备 `user:create` 权限（管理员代建账号）
    """
    if settings.ALLOW_SELF_REGISTER:
        return None

    auth_header = request.headers.get("Authorization") or ""
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="账号创建需要管理员权限，请先登录",
        )

    token = auth_header.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="账号创建需要管理员权限，请先登录",
        )

    user = await get_current_user(token=token, db=db)
    if not user_has_permission(user, PermCode.USER_CREATE, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权限创建账号（需要 user:create 权限）",
        )
    return user


@router.post("/login", response_model=ResponseModel, summary="用户登录")
async def login(
    login_data: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_mysql_session)
):
    """用户登录"""
    # 获取客户端IP
    ip_address = request.client.host if request.client else None
    
    # 登录
    result = await AuthService.login(
        db=db,
        username=login_data.username,
        password=login_data.password,
        ip_address=ip_address
    )
    
    refresh_token = result.pop("refresh_token")
    _set_refresh_cookie(response, refresh_token)
    return ResponseModel(
        code=200,
        message="登录成功",
        data=result
    )


@router.post("/register", response_model=ResponseModel, summary="用户注册")
async def register(
    register_data: RegisterRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_mysql_session),
    operator: Optional[User] = Depends(register_guard)
):
    """用户注册

    **P0 安全加固**：默认（`ALLOW_SELF_REGISTER=false`）仅限具备 `user:create`
    权限的管理员调用，游客自助注册已关闭 —— 否则任何人可自助开户并拿到 JWT，
    绕过 RBAC 第一道门。置 `ALLOW_SELF_REGISTER=true` 可恢复自助注册
    （自助注册固定为 user 角色）。
    """
    ip_address = request.client.host if request.client else None

    result = await AuthService.register(
        db=db,
        username=register_data.username,
        password=register_data.password,
        real_name=register_data.real_name,
        email=register_data.email,
        phone=register_data.phone,
        role_code=register_data.role_code or "user",
        ip_address=ip_address
    )

    logger.info(
        f"[注册] 新账号 {register_data.username} 由 "
        f"{operator.username if operator else '自助注册'} 创建 (IP={ip_address})"
    )

    refresh_token = result.pop("refresh_token")
    _set_refresh_cookie(response, refresh_token)
    return ResponseModel(
        code=201,
        message="注册成功",
        data=result
    )


@router.post("/logout", response_model=ResponseModel, summary="用户登出")
async def logout(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_mysql_session)
):
    """用户登出"""
    # 获取客户端IP
    ip_address = request.client.host if request.client else None
    
    # 登出
    await AuthService.logout(
        db=db,
        user_id=current_user.id,
        ip_address=ip_address
    )
    
    response.delete_cookie(
        key="refresh_token",
        path=f"{settings.API_PREFIX}/auth",
        secure=settings.AUTH_COOKIE_SECURE,
        httponly=True,
        samesite="strict",
    )
    return ResponseModel(
        code=200,
        message="登出成功"
    )


@router.post("/refresh", response_model=ResponseModel, summary="刷新Token")
async def refresh_token(
    payload: Optional[RefreshTokenRequest] = None,
    refresh_cookie: Optional[str] = Cookie(None, alias="refresh_token"),
    db: Session = Depends(get_mysql_session)
):
    """刷新Token"""
    token = refresh_cookie or (payload.refresh_token if payload else None)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="缺少刷新令牌")
    result = await AuthService.refresh_token(
        db=db,
        refresh_token=token
    )
    
    return ResponseModel(
        code=200,
        message="刷新成功",
        data=result
    )


@router.get("/me", response_model=ResponseModel, summary="获取当前用户")
async def get_current_user_info(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_mysql_session)
):
    """获取当前用户"""
    result = await AuthService.get_current_user_info(
        db=db,
        user_id=current_user.id
    )
    
    return ResponseModel(
        code=200,
        message="获取成功",
        data=result
    )
