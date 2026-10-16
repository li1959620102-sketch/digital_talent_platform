"""
JWT认证处理
"""
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_mysql_session
from app.models.permission import User
from app.core.exceptions import UnauthorizedException, TokenExpiredException

# 密码加密上下文（bcrypt rounds=10，符合 OWASP≥10，较 r11 吞吐约高 30%）
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=10)

# OAuth2密码流
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_PREFIX}/auth/login")


class JWTHandler:
    """JWT处理器"""

    @staticmethod
    def create_access_token(
        data: Dict[str, Any],
        expires_delta: Optional[timedelta] = None
    ) -> str:
        """创建访问令牌"""
        to_encode = data.copy()
        if to_encode.get("sub") is not None:
            to_encode["sub"] = str(to_encode["sub"])

        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(
                minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
            )

        to_encode.update({
            "exp": expire,
            "iat": datetime.utcnow(),
            "type": "access"
        })

        encoded_jwt = jwt.encode(
            to_encode,
            settings.SECRET_KEY,
            algorithm=settings.ALGORITHM
        )

        return encoded_jwt

    @staticmethod
    def create_refresh_token(
        data: Dict[str, Any],
        expires_delta: Optional[timedelta] = None
    ) -> str:
        """创建刷新令牌"""
        to_encode = data.copy()
        if to_encode.get("sub") is not None:
            to_encode["sub"] = str(to_encode["sub"])

        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(
                days=settings.REFRESH_TOKEN_EXPIRE_DAYS
            )

        to_encode.update({
            "exp": expire,
            "iat": datetime.utcnow(),
            "type": "refresh"
        })

        encoded_jwt = jwt.encode(
            to_encode,
            settings.SECRET_KEY,
            algorithm=settings.ALGORITHM
        )

        return encoded_jwt

    @staticmethod
    def decode_token(token: str) -> Dict[str, Any]:
        """解码令牌"""
        try:
            payload = jwt.decode(
                token,
                settings.SECRET_KEY,
                algorithms=[settings.ALGORITHM]
            )
            return payload
        except JWTError as e:
            if "expired" in str(e).lower():
                raise TokenExpiredException(message="Token已过期")
            raise UnauthorizedException(message="无效的Token")

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """验证密码"""
        return pwd_context.verify(plain_password, hashed_password)

    @staticmethod
    def get_password_hash(password: str) -> str:
        """获取密码哈希"""
        return pwd_context.hash(password)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_mysql_session)
) -> User:
    """获取当前用户"""
    # 安全：不在 details 中回传 token 前缀，避免向客户端泄露凭据片段
    credentials_exception = UnauthorizedException(
        message="无法验证凭据"
    )

    try:
        payload = JWTHandler.decode_token(token)

        # 检查token类型
        if payload.get("type") != "access":
            raise credentials_exception

        user_id: int = payload.get("sub")
        if user_id is None:
            raise credentials_exception

    except (JWTError, TokenExpiredException, UnauthorizedException):
        raise credentials_exception

    # 查询用户
    user = db.query(User).filter(User.id == user_id).first()

    if user is None:
        raise credentials_exception

    if user.status != "active":
        raise UnauthorizedException(message="用户已被禁用或锁定")

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """获取当前激活用户"""
    if current_user.status != "active":
        raise UnauthorizedException(message="用户未激活")

    return current_user


async def get_current_superuser(
    current_user: User = Depends(get_current_user)
) -> User:
    """获取超级管理员"""
    if not current_user.is_superuser:
        raise UnauthorizedException(message="需要超级管理员权限")

    return current_user


def check_permission(
    user: User,
    permission_code: str,
    db: Session
) -> bool:
    """检查用户权限"""
    # 超级管理员拥有所有权限
    if user.is_superuser:
        return True

    # 查询用户权限
    from app.models.permission import Permission, RolePermission

    # 获取用户所有角色的权限
    permissions = (
        db.query(Permission)
        .join(RolePermission)
        .join(User.roles)
        .filter(User.id == user.id)
        .filter(Permission.permission_code == permission_code)
        .first()
    )

    return permissions is not None


def require_permission(permission_code: str):
    """权限装饰器"""
    async def permission_checker(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_mysql_session)
    ) -> User:
        if not check_permission(current_user, permission_code, db):
            raise UnauthorizedException(
                message="无权限执行此操作",
                details={"required_permission": permission_code}
            )
        return current_user

    return permission_checker
