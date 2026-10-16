"""
权限体系模型
"""
from sqlalchemy import (
    Column, Integer, String, DateTime, Text, Boolean,
    Enum, ForeignKey, JSON, Index
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base
import enum


class UserStatus(str, enum.Enum):
    """用户状态枚举"""
    ACTIVE = "active"  # 激活
    INACTIVE = "inactive"  # 未激活
    LOCKED = "locked"  # 锁定
    DELETED = "deleted"  # 已删除


class PermissionType(str, enum.Enum):
    """权限类型枚举"""
    MENU = "menu"  # 菜单权限
    OPERATION = "operation"  # 操作权限
    DATA = "data"  # 数据权限
    FIELD = "field"  # 字段权限


class User(Base):
    """用户表"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username = Column(String(50), unique=True, index=True, nullable=False, comment="用户名")
    password_hash = Column(String(255), nullable=False, comment="密码哈希")
    
    # 个人信息
    real_name = Column(String(50), nullable=True, comment="真实姓名")
    phone = Column(String(20), unique=True, index=True, nullable=True, comment="手机号")
    email = Column(String(100), unique=True, index=True, nullable=True, comment="邮箱")
    avatar = Column(String(500), nullable=True, comment="头像URL")
    
    # 组织与角色
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, comment="组织ID")
    
    # 状态
    status = Column(Enum(UserStatus, values_callable=lambda e: [m.value for m in e]), default=UserStatus.ACTIVE, comment="状态")
    is_superuser = Column(Boolean, default=False, comment="是否超级管理员")
    
    # 登录信息
    last_login_time = Column(DateTime, nullable=True, comment="最后登录时间")
    last_login_ip = Column(String(50), nullable=True, comment="最后登录IP")
    login_count = Column(Integer, default=0, comment="登录次数")
    
    # 安全
    failed_login_count = Column(Integer, default=0, comment="失败登录次数")
    locked_until = Column(DateTime, nullable=True, comment="锁定至")
    
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")
    
    # 关系
    organization = relationship("Organization", backref="users")
    roles = relationship("Role", secondary="user_roles", back_populates="users")
    talents = relationship("Talent", back_populates="user", foreign_keys="Talent.user_id")
    
    __table_args__ = (
        Index('idx_user_username', 'username'),
        Index('idx_user_phone', 'phone'),
        Index('idx_user_email', 'email'),
    )


class Role(Base):
    """角色表"""
    __tablename__ = "roles"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    role_code = Column(String(50), unique=True, index=True, nullable=False, comment="角色编码")
    role_name = Column(String(50), nullable=False, comment="角色名称")
    description = Column(Text, nullable=True, comment="角色描述")
    
    # 状态
    status = Column(String(20), default="active", comment="状态")
    is_system = Column(Boolean, default=False, comment="是否系统角色")
    
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")
    
    # 关系
    users = relationship("User", secondary="user_roles", back_populates="roles")
    permissions = relationship("Permission", secondary="role_permissions", back_populates="roles")


class Permission(Base):
    """权限表"""
    __tablename__ = "permissions"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    permission_code = Column(String(100), unique=True, index=True, nullable=False, comment="权限编码")
    permission_name = Column(String(100), nullable=False, comment="权限名称")
    permission_type = Column(Enum(PermissionType, values_callable=lambda e: [m.value for m in e]), nullable=False, comment="权限类型")
    
    # 权限描述
    description = Column(Text, nullable=True, comment="权限描述")
    
    # 父权限
    parent_id = Column(Integer, ForeignKey("permissions.id"), nullable=True, comment="父权限ID")
    
    # 资源标识
    resource = Column(String(200), nullable=True, comment="资源标识(菜单路径/操作代码/数据范围)")
    action = Column(String(50), nullable=True, comment="操作(查看/编辑/删除等)")
    
    # 状态
    status = Column(String(20), default="active", comment="状态")
    
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")
    
    # 关系
    parent = relationship("Permission", remote_side=[id], backref="children")
    roles = relationship("Role", secondary="role_permissions", back_populates="permissions")


class UserRole(Base):
    """用户-角色关联表"""
    __tablename__ = "user_roles"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, comment="用户ID")
    role_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, comment="角色ID")
    
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    
    __table_args__ = (
        Index('idx_user_role', 'user_id', 'role_id', unique=True),
    )


class RolePermission(Base):
    """角色-权限关联表"""
    __tablename__ = "role_permissions"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    role_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, comment="角色ID")
    permission_id = Column(Integer, ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False, comment="权限ID")
    
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    
    __table_args__ = (
        Index('idx_role_permission', 'role_id', 'permission_id', unique=True),
    )


class AuditLog(Base):
    """审计日志表"""
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    
    # 操作用户
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, comment="用户ID")
    username = Column(String(50), nullable=True, comment="用户名")
    
    # 操作信息
    operation = Column(String(100), nullable=False, comment="操作类型")
    resource = Column(String(200), nullable=True, comment="资源")
    resource_id = Column(String(100), nullable=True, comment="资源ID")
    
    # 请求信息
    request_method = Column(String(10), nullable=True, comment="请求方法")
    request_url = Column(String(500), nullable=True, comment="请求URL")
    request_params = Column(Text, nullable=True, comment="请求参数")
    
    # 响应信息
    response_code = Column(Integer, nullable=True, comment="响应码")
    response_message = Column(Text, nullable=True, comment="响应消息")
    
    # 客户端信息
    ip_address = Column(String(50), nullable=True, comment="IP地址")
    user_agent = Column(String(500), nullable=True, comment="用户代理")
    
    # 组织信息
    organization_id = Column(Integer, nullable=True, comment="组织ID")
    
    # 时间
    operation_time = Column(DateTime, server_default=func.now(), comment="操作时间")
    duration_ms = Column(Integer, nullable=True, comment="耗时(毫秒)")
    
    # 结果
    status = Column(String(20), default="success", comment="状态: success/failed")
    error_message = Column(Text, nullable=True, comment="错误消息")
    
    __table_args__ = (
        Index('idx_audit_user', 'user_id'),
        Index('idx_audit_operation', 'operation'),
        Index('idx_audit_time', 'operation_time'),
        Index('idx_audit_resource', 'resource', 'resource_id'),
    )


class DataPermission(Base):
    """数据权限表"""
    __tablename__ = "data_permissions"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    
    # 角色或用户
    role_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), nullable=True, comment="角色ID")
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, comment="用户ID")
    
    # 数据范围
    data_scope = Column(String(50), nullable=False, comment="数据范围: all/department/subordinate/custom")
    organization_ids = Column(JSON, default=[], comment="组织ID列表")
    
    # 资源
    resource = Column(String(200), nullable=True, comment="资源")
    
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")
    
    __table_args__ = (
        Index('idx_data_permission_role', 'role_id'),
        Index('idx_data_permission_user', 'user_id'),
    )
