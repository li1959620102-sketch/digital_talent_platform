"""
认证服务
"""
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import logging

from starlette.concurrency import run_in_threadpool

from app.models.permission import User, Role, UserRole, AuditLog, UserStatus
from app.models.talent import Organization
from app.utils.jwt_handler import JWTHandler
from app.core.exceptions import (
    UnauthorizedException,
    BadRequestException,
    NotFoundException
)

logger = logging.getLogger(__name__)


class AuthService:
    """认证服务"""
    
    @staticmethod
    async def login(
        db: Session,
        username: str,
        password: str,
        ip_address: Optional[str] = None
    ) -> Dict[str, Any]:
        """用户登录"""
        # 查询用户
        user = db.query(User).filter(
            (User.username == username) | (User.phone == username) | (User.email == username)
        ).first()
        
        if not user:
            raise UnauthorizedException(message="用户名或密码错误")
        
        # 检查用户状态
        if user.status == "locked":
            raise UnauthorizedException(message="账号已被锁定")
        
        if user.status != "active":
            raise UnauthorizedException(message="账号未激活")
        
        # 检查是否锁定
        if user.locked_until and user.locked_until > datetime.now():
            raise UnauthorizedException(
                message=f"账号已被锁定，请稍后再试",
                details={"locked_until": user.locked_until.isoformat()}
            )
        
        # 验证密码（CPU 密集， offload 到线程池避免阻塞事件循环，提升并发）
        if not await run_in_threadpool(JWTHandler.verify_password, password, user.password_hash):
            # 失败次数+1
            user.failed_login_count += 1
            
            # 超过5次锁定账号30分钟
            if user.failed_login_count >= 5:
                user.locked_until = datetime.now() + timedelta(minutes=30)
                db.commit()
                raise UnauthorizedException(
                    message="密码错误次数过多，账号已被锁定30分钟"
                )
            
            db.commit()
            raise UnauthorizedException(
                message=f"用户名或密码错误，还剩{5 - user.failed_login_count}次机会"
            )
        
        # 登录成功，重置失败次数
        user.failed_login_count = 0
        user.locked_until = None
        user.last_login_time = datetime.now()
        user.last_login_ip = ip_address
        user.login_count += 1
        
        # 生成Token
        access_token = JWTHandler.create_access_token(
            data={"sub": user.id, "username": user.username}
        )
        refresh_token = JWTHandler.create_refresh_token(
            data={"sub": user.id, "username": user.username}
        )
        
        db.commit()
        
        # 记录审计日志
        audit_log = AuditLog(
            user_id=user.id,
            username=user.username,
            operation="login",
            resource="auth",
            request_method="POST",
            request_url="/api/v1/auth/login",
            ip_address=ip_address,
            organization_id=user.organization_id,
            operation_time=datetime.now(),
            status="success"
        )
        db.add(audit_log)
        db.commit()
        
        logger.info(f"用户登录成功: {user.username}")
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "username": user.username,
                "real_name": user.real_name,
                "email": user.email,
                "phone": user.phone,
                "avatar": user.avatar,
                "is_superuser": user.is_superuser,
                "roles": [role.role_code for role in user.roles]
            }
        }
    
    @staticmethod
    async def logout(
        db: Session,
        user_id: int,
        ip_address: Optional[str] = None
    ) -> bool:
        """用户登出"""
        user = db.query(User).filter(User.id == user_id).first()
        
        if not user:
            raise NotFoundException(message="用户不存在")
        
        # 记录审计日志
        audit_log = AuditLog(
            user_id=user.id,
            username=user.username,
            operation="logout",
            resource="auth",
            request_method="POST",
            request_url="/api/v1/auth/logout",
            ip_address=ip_address,
            organization_id=user.organization_id,
            operation_time=datetime.now(),
            status="success"
        )
        db.add(audit_log)
        db.commit()
        
        logger.info(f"用户登出成功: {user.username}")
        
        return True
    
    @staticmethod
    async def refresh_token(
        db: Session,
        refresh_token: str
    ) -> Dict[str, str]:
        """刷新Token"""
        try:
            # 解码刷新令牌
            payload = JWTHandler.decode_token(refresh_token)
            
            # 检查token类型
            if payload.get("type") != "refresh":
                raise UnauthorizedException(message="无效的刷新令牌")
            
            user_id = payload.get("sub")
            
            # 查询用户
            user = db.query(User).filter(User.id == user_id).first()
            
            if not user or user.status != "active":
                raise UnauthorizedException(message="用户不存在或未激活")
            
            # 生成新的访问令牌
            access_token = JWTHandler.create_access_token(
                data={"sub": user.id, "username": user.username}
            )
            
            logger.info(f"刷新Token成功: {user.username}")
            
            return {
                "access_token": access_token,
                "token_type": "bearer"
            }
            
        except Exception as e:
            logger.error(f"刷新Token失败: {str(e)}")
            raise
    
    @staticmethod
    async def get_current_user_info(
        db: Session,
        user_id: int
    ) -> Dict[str, Any]:
        """获取当前用户信息"""
        user = db.query(User).filter(User.id == user_id).first()
        
        if not user:
            raise NotFoundException(message="用户不存在")
        
        # 获取用户角色（用 role_code 供前端 RBAC 菜单判断）
        roles = [role.role_code for role in user.roles]

        # 获取用户权限
        permissions = []
        if user.is_superuser:
            permissions = ["*"]
        else:
            for role in user.roles:
                for permission in role.permissions:
                    permissions.append(permission.permission_code)

        return {
            "id": user.id,
            "username": user.username,
            "real_name": user.real_name,
            "email": user.email,
            "phone": user.phone,
            "avatar": user.avatar,
            "status": user.status,
            "is_superuser": user.is_superuser,
            "organization_id": user.organization_id,
            "roles": roles,
            "permissions": list(set(permissions))
        }

    @staticmethod
    async def register(
        db: Session,
        username: str,
        password: str,
        real_name: Optional[str] = None,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        role_code: str = "user",
        ip_address: Optional[str] = None,
    ) -> Dict[str, Any]:
        """用户注册（公开注册默认 user 角色；超管后台创建可指定 role_code）"""
        # 用户名唯一性
        if db.query(User).filter(User.username == username).first():
            raise BadRequestException(message="用户名已存在")

        # 邮箱唯一性
        if email and db.query(User).filter(User.email == email).first():
            raise BadRequestException(message="邮箱已被注册")

        # 手机号唯一性
        if phone and db.query(User).filter(User.phone == phone).first():
            raise BadRequestException(message="手机号已被注册")

        # 查找角色（不存在则报错）
        role = db.query(Role).filter(Role.role_code == role_code).first()
        if role is None:
            raise BadRequestException(message=f"角色不存在: {role_code}")

        # 查找默认组织（HQ，seed 创建）
        org = db.query(Organization).filter(Organization.org_code == "HQ").first()

        # 创建用户（密码哈希走线程池避免阻塞事件循环）
        password_hash = await run_in_threadpool(
            JWTHandler.get_password_hash, password
        )
        user = User(
            username=username,
            password_hash=password_hash,
            real_name=real_name,
            email=email,
            phone=phone,
            organization_id=org.id if org else None,
            status=UserStatus.ACTIVE,
            is_superuser=False,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        # 关联角色
        db.add(UserRole(user_id=user.id, role_id=role.id))
        db.commit()

        # 审计日志
        db.add(AuditLog(
            user_id=user.id,
            username=user.username,
            operation="register",
            resource="auth",
            request_method="POST",
            request_url="/api/v1/auth/register",
            ip_address=ip_address,
            organization_id=user.organization_id,
            operation_time=datetime.now(),
            status="success",
        ))
        db.commit()

        logger.info(f"用户注册成功: {user.username} (角色: {role.role_name})")

        # 注册即登录（返回 token，前端无需再次登录）
        access_token = JWTHandler.create_access_token(
            data={"sub": user.id, "username": user.username}
        )
        refresh_token = JWTHandler.create_refresh_token(
            data={"sub": user.id, "username": user.username}
        )

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "username": user.username,
                "real_name": user.real_name,
                "email": user.email,
                "phone": user.phone,
                "avatar": user.avatar,
                "is_superuser": user.is_superuser,
                "roles": [role.role_code for role in user.roles],
            },
        }


# 导入timedelta
from datetime import timedelta
