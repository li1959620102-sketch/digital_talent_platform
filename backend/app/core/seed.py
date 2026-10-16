"""
种子数据初始化（幂等）

启动时由 main.py lifespan 调用，创建：
- 默认组织（总部）
- 4 种角色：super_admin / admin / hr / user
- 可选的初始超管账号（仅在 INITIAL_ADMIN_PASSWORD 已配置时创建）

幂等设计：多次启动不会重复创建，已存在的记录会被跳过。
不抛异常以避免阻断后端启动；失败仅记录错误日志。
"""
import logging
from typing import Dict, Optional

from sqlalchemy.orm import Session

from app.core.database import get_mysql_session_factory
from app.core.config import settings
from app.models.permission import (
    User, Role, UserRole, UserStatus,
)
from app.models.talent import Organization
from app.utils.jwt_handler import JWTHandler
from app.core.rbac import seed_rbac

logger = logging.getLogger(__name__)


# 4 种角色定义（role_code 即 RBAC 菜单判断依据）
ROLES = [
    {
        "role_code": "super_admin",
        "role_name": "超级管理员",
        "description": "系统最高权限，可管理所有数据、用户和系统配置",
        "is_system": True,
    },
    {
        "role_code": "admin",
        "role_name": "管理员",
        "description": "管理人才/岗位/测评/培训等全部业务数据",
        "is_system": True,
    },
    {
        "role_code": "hr",
        "role_name": "HR专员",
        "description": "管理人才档案、岗位匹配、测评实施",
        "is_system": True,
    },
    {
        "role_code": "user",
        "role_name": "普通用户",
        "description": "查看个人档案、参加培训、查看公告",
        "is_system": True,
    },
]


# 初始超管账号（密码必须通过环境变量显式提供，禁止代码内置弱口令）
DEFAULT_ADMIN = {
    "real_name": "系统管理员",
    "email": "admin@digital-talent.com",
    "phone": "13800000000",
}


def _get_or_create_organization(db: Session) -> Organization:
    """获取或创建默认组织（总部，org_code=HQ）"""
    org = db.query(Organization).filter(Organization.org_code == "HQ").first()
    if org is None:
        org = Organization(
            org_code="HQ",
            org_name="总部",
            org_type="公司",
            description="系统默认组织",
            status="active",
        )
        db.add(org)
        db.commit()
        db.refresh(org)
        logger.info(f"[Seed] 创建默认组织: {org.org_name} (id={org.id})")
    return org


def _get_or_create_roles(db: Session) -> Dict[str, Role]:
    """获取或创建 4 种角色，返回 {role_code: Role} 映射"""
    result: Dict[str, Role] = {}
    for role_data in ROLES:
        role = db.query(Role).filter(Role.role_code == role_data["role_code"]).first()
        if role is None:
            role = Role(**role_data, status="active")
            db.add(role)
            db.commit()
            db.refresh(role)
            logger.info(f"[Seed] 创建角色: {role.role_name} ({role.role_code})")
        result[role.role_code] = role
    return result


def _get_or_create_admin(db: Session, org: Organization, super_admin_role: Role) -> Optional[User]:
    """获取或创建默认超管账号，并关联 super_admin 角色（幂等）"""
    username = settings.INITIAL_ADMIN_USERNAME.strip() or "admin"
    password = settings.INITIAL_ADMIN_PASSWORD
    admin = db.query(User).filter(User.username == username).first()
    if admin is None:
        if not password:
            logger.warning(
                "[Seed] 未配置 INITIAL_ADMIN_PASSWORD，跳过初始超管创建；"
                "请通过受控管理流程创建首个管理员"
            )
            return None
        admin = User(
            username=username,
            password_hash=JWTHandler.get_password_hash(password),
            real_name=DEFAULT_ADMIN["real_name"],
            email=DEFAULT_ADMIN["email"],
            phone=DEFAULT_ADMIN["phone"],
            organization_id=org.id,
            status=UserStatus.ACTIVE,
            is_superuser=True,
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)
        logger.info(f"[Seed] 创建初始超管账号: {admin.username} (id={admin.id})")

    # 关联 super_admin 角色（幂等：已关联则跳过）
    existing = (
        db.query(UserRole)
        .filter(
            UserRole.user_id == admin.id,
            UserRole.role_id == super_admin_role.id,
        )
        .first()
    )
    if existing is None:
        db.add(UserRole(user_id=admin.id, role_id=super_admin_role.id))
        db.commit()
        logger.info(
            f"[Seed] 关联 {admin.username} → {super_admin_role.role_name}"
        )

    return admin


def init_seed_data() -> None:
    """初始化种子数据（幂等，启动时调用一次）"""
    SessionFactory = get_mysql_session_factory()
    if SessionFactory is None:
        logger.warning("[Seed] MySQL session factory 未初始化（TESTING 环境或 init_db 未调用），跳过种子初始化")
        return
    db: Session = SessionFactory()
    try:
        org = _get_or_create_organization(db)
        roles = _get_or_create_roles(db)
        _get_or_create_admin(db, org, roles["super_admin"])

        # RBAC 权限体系（P0 安全加固）：权限定义 + 角色授权 + 行级数据范围
        stats = seed_rbac(db)
        logger.info(
            f"[Seed] RBAC 权限体系同步完成：权限 {stats['permissions']} 条新增 / "
            f"角色授权 {stats['role_permissions']} 条新增 / "
            f"数据范围 {stats['data_permissions']} 条新增"
        )

        logger.info("[Seed] 种子数据初始化完成（组织 + 4 角色 + 超管账号 + RBAC 权限）")
    except Exception as e:
        # 种子失败不阻断后端启动，仅记录错误日志
        logger.error(f"[Seed] 种子初始化失败: {e}", exc_info=True)
    finally:
        db.close()


if __name__ == "__main__":
    # 手动执行：python -m app.core.seed
    logging.basicConfig(level=logging.INFO)
    init_seed_data()
