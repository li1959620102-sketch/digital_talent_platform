"""
用户管理 API 路由（仅超级管理员可访问）

提供：
- 用户列表（分页/搜索/角色筛选）
- 创建用户（可指定角色，超管后台创建）
- 用户详情
- 更新用户（改角色/状态/基本信息）
- 启停用户
- 重置密码
- 删除用户
"""
from fastapi import APIRouter, Depends, Request, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional, List

from app.core.database import get_mysql_session
from app.schemas.common import ResponseModel, PageModel
from app.services.auth_service import AuthService
from app.utils.jwt_handler import get_current_superuser, JWTHandler
from app.models.permission import User, Role, UserRole, UserStatus, AuditLog, DataPermission
from app.models.talent import Organization
from app.core.exceptions import NotFoundException, BadRequestException
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


# ── 请求 Schema ────────────────────────────────────────────────

class UserCreateRequest(BaseModel):
    """超管创建用户请求（可指定任意角色）"""
    username: str = Field(..., min_length=3, max_length=50, description="用户名")
    password: str = Field(..., min_length=12, max_length=64, description="初始密码")
    real_name: Optional[str] = Field(None, max_length=50, description="真实姓名")
    email: Optional[str] = Field(None, max_length=100, description="邮箱")
    phone: Optional[str] = Field(None, max_length=20, description="手机号")
    role_code: str = Field("user", description="角色编码: super_admin/admin/hr/user")
    organization_id: Optional[int] = Field(None, description="组织ID")


class UserUpdateRequest(BaseModel):
    """更新用户请求（部分更新）"""
    real_name: Optional[str] = Field(None, max_length=50)
    email: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=20)
    role_code: Optional[str] = Field(None, description="改角色: super_admin/admin/hr/user")
    organization_id: Optional[int] = Field(None)


class ResetPasswordRequest(BaseModel):
    """重置密码请求"""
    new_password: str = Field(..., min_length=12, max_length=64, description="新密码")


# ── 响应 Schema ────────────────────────────────────────────────

class UserItem(BaseModel):
    """用户列表项"""
    id: int
    username: str
    real_name: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    avatar: Optional[str]
    status: str
    is_superuser: bool
    organization_id: Optional[int]
    roles: List[str]  # role_code 列表
    last_login_time: Optional[str]
    created_at: Optional[str]

    model_config = {"from_attributes": True}


def _to_user_item(user: User) -> UserItem:
    """ORM User → UserItem"""
    return UserItem(
        id=user.id,
        username=user.username,
        real_name=user.real_name,
        email=user.email,
        phone=user.phone,
        avatar=user.avatar,
        status=user.status.value if hasattr(user.status, "value") else str(user.status),
        is_superuser=user.is_superuser,
        organization_id=user.organization_id,
        roles=[role.role_code for role in user.roles],
        last_login_time=user.last_login_time.isoformat() if user.last_login_time else None,
        created_at=user.created_at.isoformat() if user.created_at else None,
    )


# ── 路由 ────────────────────────────────────────────────────────

@router.get("", response_model=ResponseModel[PageModel[UserItem]], summary="用户列表（超管）")
async def list_users(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=100, description="每页数量"),
    keyword: Optional[str] = Query(None, description="搜索关键词（用户名/真实姓名/手机号/邮箱）"),
    role_code: Optional[str] = Query(None, description="按角色筛选"),
    status: Optional[str] = Query(None, description="按状态筛选: active/inactive/locked"),
    db: Session = Depends(get_mysql_session),
    current_user: User = Depends(get_current_superuser),
):
    """用户列表（分页 + 关键词搜索 + 角色/状态筛选）"""
    query = db.query(User)

    # 关键词搜索
    if keyword:
        kw = f"%{keyword}%"
        query = query.filter(
            (User.username.like(kw))
            | (User.real_name.like(kw))
            | (User.phone.like(kw))
            | (User.email.like(kw))
        )

    # 状态筛选
    if status:
        query = query.filter(User.status == status)

    # 角色筛选（JOIN user_roles + roles）
    if role_code:
        query = (
            query.join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .filter(Role.role_code == role_code)
        )

    total = query.count()
    users = (
        query.order_by(User.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = [_to_user_item(u) for u in users]
    total_pages = (total + page_size - 1) // page_size

    return ResponseModel(
        code=200,
        message="获取成功",
        data=PageModel(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        ),
    )


@router.post("", response_model=ResponseModel[UserItem], summary="创建用户（超管）")
async def create_user(
    payload: UserCreateRequest,
    request: Request,
    db: Session = Depends(get_mysql_session),
    current_user: User = Depends(get_current_superuser),
):
    """超管创建用户（可指定任意角色）"""
    ip_address = request.client.host if request.client else None

    # 用户名唯一性
    if db.query(User).filter(User.username == payload.username).first():
        raise BadRequestException(message="用户名已存在")
    if payload.email and db.query(User).filter(User.email == payload.email).first():
        raise BadRequestException(message="邮箱已被注册")
    if payload.phone and db.query(User).filter(User.phone == payload.phone).first():
        raise BadRequestException(message="手机号已被注册")

    # 角色必须存在
    role = db.query(Role).filter(Role.role_code == payload.role_code).first()
    if role is None:
        raise BadRequestException(message=f"角色不存在: {payload.role_code}")

    # 组织（如指定则校验，否则用 HQ 默认）
    org_id = payload.organization_id
    if org_id is None:
        org = db.query(Organization).filter(Organization.org_code == "HQ").first()
        org_id = org.id if org else None
    else:
        org = db.query(Organization).filter(Organization.id == org_id).first()
        if org is None:
            raise BadRequestException(message=f"组织不存在: {org_id}")

    # 创建用户
    user = User(
        username=payload.username,
        password_hash=JWTHandler.get_password_hash(payload.password),
        real_name=payload.real_name,
        email=payload.email,
        phone=payload.phone,
        organization_id=org_id,
        status=UserStatus.ACTIVE,
        is_superuser=(payload.role_code == "super_admin"),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # 关联角色
    db.add(UserRole(user_id=user.id, role_id=role.id))
    db.commit()

    # 审计日志
    db.add(AuditLog(
        user_id=current_user.id,
        username=current_user.username,
        operation="create_user",
        resource="user",
        resource_id=str(user.id),
        request_method="POST",
        request_url="/api/v1/users",
        ip_address=ip_address,
        organization_id=current_user.organization_id,
        operation_time=datetime.now(),
        status="success",
    ))
    db.commit()

    db.refresh(user)
    logger.info(f"[User] 超管 {current_user.username} 创建用户: {user.username} (角色: {role.role_name})")

    return ResponseModel(code=201, message="创建成功", data=_to_user_item(user))


@router.get("/{user_id}", response_model=ResponseModel[UserItem], summary="用户详情（超管）")
async def get_user(
    user_id: int,
    db: Session = Depends(get_mysql_session),
    current_user: User = Depends(get_current_superuser),
):
    """获取用户详情"""
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise NotFoundException(message="用户不存在")
    return ResponseModel(code=200, message="获取成功", data=_to_user_item(user))


@router.put("/{user_id}", response_model=ResponseModel[UserItem], summary="更新用户（超管）")
async def update_user(
    user_id: int,
    payload: UserUpdateRequest,
    request: Request,
    db: Session = Depends(get_mysql_session),
    current_user: User = Depends(get_current_superuser),
):
    """更新用户基本信息/角色/组织（部分更新）"""
    ip_address = request.client.host if request.client else None
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise NotFoundException(message="用户不存在")

    # 基本信息
    if payload.real_name is not None:
        user.real_name = payload.real_name
    if payload.email is not None:
        if db.query(User).filter(User.email == payload.email, User.id != user_id).first():
            raise BadRequestException(message="邮箱已被其他用户占用")
        user.email = payload.email
    if payload.phone is not None:
        if db.query(User).filter(User.phone == payload.phone, User.id != user_id).first():
            raise BadRequestException(message="手机号已被其他用户占用")
        user.phone = payload.phone
    if payload.organization_id is not None:
        org = db.query(Organization).filter(Organization.id == payload.organization_id).first()
        if org is None:
            raise BadRequestException(message=f"组织不存在: {payload.organization_id}")
        user.organization_id = payload.organization_id

    # 改角色（先删后建）
    if payload.role_code is not None:
        role = db.query(Role).filter(Role.role_code == payload.role_code).first()
        if role is None:
            raise BadRequestException(message=f"角色不存在: {payload.role_code}")
        # 删除旧角色关联
        db.query(UserRole).filter(UserRole.user_id == user.id).delete()
        # 新建角色关联
        db.add(UserRole(user_id=user.id, role_id=role.id))
        # 同步 is_superuser 标记
        user.is_superuser = (payload.role_code == "super_admin")

    db.commit()
    db.refresh(user)

    # 审计日志
    db.add(AuditLog(
        user_id=current_user.id,
        username=current_user.username,
        operation="update_user",
        resource="user",
        resource_id=str(user.id),
        request_method="PUT",
        request_url=f"/api/v1/users/{user_id}",
        ip_address=ip_address,
        organization_id=current_user.organization_id,
        operation_time=datetime.now(),
        status="success",
    ))
    db.commit()

    logger.info(f"[User] 超管 {current_user.username} 更新用户: {user.username}")
    return ResponseModel(code=200, message="更新成功", data=_to_user_item(user))


@router.post("/{user_id}/toggle-status", response_model=ResponseModel[UserItem], summary="启停用户（超管）")
async def toggle_user_status(
    user_id: int,
    request: Request,
    db: Session = Depends(get_mysql_session),
    current_user: User = Depends(get_current_superuser),
):
    """切换用户状态：active ↔ inactive（不允许锁定自己或超管同伴，避免锁死系统）"""
    ip_address = request.client.host if request.client else None
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise NotFoundException(message="用户不存在")

    if user.id == current_user.id:
        raise BadRequestException(message="不允许停用自己的账号")
    if user.is_superuser and not current_user.is_superuser:
        raise BadRequestException(message="无权操作其他超管账号")

    # 切换状态
    if user.status == UserStatus.ACTIVE:
        user.status = UserStatus.INACTIVE
        msg = "已停用"
    else:
        user.status = UserStatus.ACTIVE
        msg = "已启用"
    db.commit()
    db.refresh(user)

    # 审计日志
    db.add(AuditLog(
        user_id=current_user.id,
        username=current_user.username,
        operation="toggle_user_status",
        resource="user",
        resource_id=str(user.id),
        request_method="POST",
        request_url=f"/api/v1/users/{user_id}/toggle-status",
        ip_address=ip_address,
        organization_id=current_user.organization_id,
        operation_time=datetime.now(),
        status="success",
    ))
    db.commit()

    logger.info(f"[User] 超管 {current_user.username} {msg} 用户: {user.username}")
    return ResponseModel(code=200, message=msg, data=_to_user_item(user))


@router.post("/{user_id}/reset-password", response_model=ResponseModel, summary="重置密码（超管）")
async def reset_password(
    user_id: int,
    payload: ResetPasswordRequest,
    request: Request,
    db: Session = Depends(get_mysql_session),
    current_user: User = Depends(get_current_superuser),
):
    """重置用户密码（超管操作，不返回新密码，仅超管自己知道）"""
    ip_address = request.client.host if request.client else None
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise NotFoundException(message="用户不存在")

    if user.id == current_user.id:
        raise BadRequestException(message="重置自己密码请走个人设置接口")

    user.password_hash = JWTHandler.get_password_hash(payload.new_password)
    user.failed_login_count = 0
    user.locked_until = None
    db.commit()

    # 审计日志
    db.add(AuditLog(
        user_id=current_user.id,
        username=current_user.username,
        operation="reset_password",
        resource="user",
        resource_id=str(user.id),
        request_method="POST",
        request_url=f"/api/v1/users/{user_id}/reset-password",
        ip_address=ip_address,
        organization_id=current_user.organization_id,
        operation_time=datetime.now(),
        status="success",
    ))
    db.commit()

    logger.info(f"[User] 超管 {current_user.username} 重置用户密码: {user.username}")
    return ResponseModel(code=200, message="密码重置成功")


@router.delete("/{user_id}", response_model=ResponseModel, summary="删除用户（超管）")
async def delete_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_mysql_session),
    current_user: User = Depends(get_current_superuser),
):
    """删除用户（硬删除 + 级联清理角色关联 + 审计日志）

    保护规则：
    - 不能删除自己
    - 不能删除其他超管（避免系统失去超管入口）
    - 至少保留一个超管（双保险）
    """
    ip_address = request.client.host if request.client else None
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise NotFoundException(message="用户不存在")

    if user.id == current_user.id:
        raise BadRequestException(message="不允许删除自己的账号")

    if user.is_superuser:
        # 统计剩余超管数量（不含当前超管自己已被排除，这里检查的是目标用户的超管身份）
        super_count = db.query(User).filter(User.is_superuser == True, User.id != user_id).count()
        if super_count == 0:
            raise BadRequestException(message="系统至少需要保留 1 名超级管理员，无法删除")
        raise BadRequestException(message="不允许删除其他超级管理员")

    # 删除前清理：用户-角色关联
    db.query(UserRole).filter(UserRole.user_id == user_id).delete()

    # 删除前清理：审计日志中该用户作为操作人的记录（置空 user_id，保留日志）
    db.query(AuditLog).filter(AuditLog.user_id == user_id).update(
        {AuditLog.user_id: None}, synchronize_session=False
    )

    # 删除前清理：数据权限关联
    db.query(DataPermission).filter(DataPermission.user_id == user_id).delete()

    # 记录被删除用户的用户名（删除后无法再查）
    deleted_username = user.username

    # 硬删除用户
    db.delete(user)
    db.commit()

    # 审计日志（user_id 记操作人，resource 记被删用户）
    db.add(AuditLog(
        user_id=current_user.id,
        username=current_user.username,
        operation="delete_user",
        resource="user",
        resource_id=str(user_id),
        request_method="DELETE",
        request_url=f"/api/v1/users/{user_id}",
        ip_address=ip_address,
        organization_id=current_user.organization_id,
        operation_time=datetime.now(),
        status="success",
        response_message=f"删除用户: {deleted_username}",
    ))
    db.commit()

    logger.info(f"[User] 超管 {current_user.username} 删除用户: {deleted_username} (id={user_id})")
    return ResponseModel(code=200, message=f"用户 {deleted_username} 已删除")


@router.get("/roles/all", response_model=ResponseModel, summary="获取所有角色（超管）")
async def list_roles(
    db: Session = Depends(get_mysql_session),
    current_user: User = Depends(get_current_superuser),
):
    """获取所有角色（供前端用户管理页下拉选择）"""
    roles = db.query(Role).filter(Role.status == "active").order_by(Role.id).all()
    return ResponseModel(
        code=200,
        message="获取成功",
        data=[
            {
                "id": r.id,
                "role_code": r.role_code,
                "role_name": r.role_name,
                "description": r.description,
                "is_system": r.is_system,
            }
            for r in roles
        ],
    )
