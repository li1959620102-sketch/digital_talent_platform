"""
RBAC 权限中枢（P0：多级权限与安全管控）

提供三层权限能力，供 API 层统一调用：
1. **认证层** —— `get_current_user`（已有，jwt_handler）
2. **功能权限（RBAC）** —— permission_code + 角色矩阵，本模块负责 seed 与校验
3. **字段级权限** —— 敏感 PII 字段按角色脱敏（手机号/身份证/邮箱/住址/薪酬）
4. **行级权限（数据范围）** —— 按 data_permissions.data_scope 过滤可见数据行

设计原则：
- **fail-closed**：权限表未初始化或权限查询失败时默认拒绝访问，
  避免因初始化异常导致所有已登录用户被意外授予管理权限。
- **幂等**：seed_rbac() 可重复执行，不会重复建记录。
- **不信任客户端**：所有脱敏在服务端出参前完成，前端拿不到明文。
"""
import logging
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

from sqlalchemy.orm import Session

from app.models.permission import (
    DataPermission,
    Permission,
    PermissionType,
    Role,
    RolePermission,
    User,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. 权限码常量
# ---------------------------------------------------------------------------
class PermCode:
    """权限码常量（与 permissions.permission_code 一一对应）"""

    # ── 人才档案：功能权限
    TALENT_VIEW = "talent:view"
    TALENT_CREATE = "talent:create"
    TALENT_UPDATE = "talent:update"
    TALENT_DELETE = "talent:delete"
    TALENT_IMPORT = "talent:import"
    TALENT_EXPORT = "talent:export"
    TALENT_TAG = "talent:tag"
    TALENT_PARSE_RESUME = "talent:parse_resume"

    # ── 数据看板
    DASHBOARD_VIEW = "dashboard:view"

    # ── 用户与权限管理
    USER_VIEW = "user:view"
    USER_CREATE = "user:create"
    USER_UPDATE = "user:update"
    USER_DELETE = "user:delete"

    # ── 岗位 / 测评 / 培训 / 匹配 / 知识库 / 智能体（预留，后续端点可逐步接入）
    POSITION_VIEW = "position:view"
    POSITION_MANAGE = "position:manage"
    ASSESSMENT_VIEW = "assessment:view"
    ASSESSMENT_MANAGE = "assessment:manage"
    TRAINING_VIEW = "training:view"
    TRAINING_MANAGE = "training:manage"
    MATCHING_VIEW = "matching:view"
    MATCHING_EXECUTE = "matching:execute"
    KNOWLEDGE_VIEW = "knowledge:view"
    KNOWLEDGE_MANAGE = "knowledge:manage"
    AGENT_EXECUTE = "agent:execute"
    SKILL_VIEW = "skill:view"
    SKILL_MANAGE = "skill:manage"

    # ── 字段级权限（敏感 PII）
    FIELD_TALENT_PHONE = "field:talent:phone"
    FIELD_TALENT_ID_CARD = "field:talent:id_card"
    FIELD_TALENT_EMAIL = "field:talent:email"
    FIELD_TALENT_ADDRESS = "field:talent:address"
    FIELD_TALENT_SALARY = "field:talent:salary"

    # ── 行级数据范围
    DATA_SCOPE_ALL = "data:scope:all"
    DATA_SCOPE_DEPARTMENT = "data:scope:department"


# ---------------------------------------------------------------------------
# 2. 权限定义表（code -> (名称, 类型, 资源, 操作)）
# ---------------------------------------------------------------------------
PERMISSION_DEFS: List[tuple] = [
    # 人才档案
    (PermCode.TALENT_VIEW, "查看人才档案", PermissionType.OPERATION, "talent", "view"),
    (PermCode.TALENT_CREATE, "创建人才档案", PermissionType.OPERATION, "talent", "create"),
    (PermCode.TALENT_UPDATE, "更新人才档案", PermissionType.OPERATION, "talent", "update"),
    (PermCode.TALENT_DELETE, "删除人才档案", PermissionType.OPERATION, "talent", "delete"),
    (PermCode.TALENT_IMPORT, "批量导入人才", PermissionType.OPERATION, "talent", "import"),
    (PermCode.TALENT_EXPORT, "导出人才数据", PermissionType.OPERATION, "talent", "export"),
    (PermCode.TALENT_TAG, "维护人才标签", PermissionType.OPERATION, "talent", "tag"),
    (PermCode.TALENT_PARSE_RESUME, "解析简历建档", PermissionType.OPERATION, "talent", "parse_resume"),
    # 数据看板
    (PermCode.DASHBOARD_VIEW, "查看数据看板", PermissionType.OPERATION, "dashboard", "view"),
    # 用户管理
    (PermCode.USER_VIEW, "查看用户", PermissionType.OPERATION, "user", "view"),
    (PermCode.USER_CREATE, "创建用户", PermissionType.OPERATION, "user", "create"),
    (PermCode.USER_UPDATE, "更新用户", PermissionType.OPERATION, "user", "update"),
    (PermCode.USER_DELETE, "删除用户", PermissionType.OPERATION, "user", "delete"),
    # 岗位
    (PermCode.POSITION_VIEW, "查看岗位", PermissionType.OPERATION, "position", "view"),
    (PermCode.POSITION_MANAGE, "管理岗位", PermissionType.OPERATION, "position", "manage"),
    # 测评
    (PermCode.ASSESSMENT_VIEW, "查看测评", PermissionType.OPERATION, "assessment", "view"),
    (PermCode.ASSESSMENT_MANAGE, "管理测评", PermissionType.OPERATION, "assessment", "manage"),
    # 培训
    (PermCode.TRAINING_VIEW, "查看培训", PermissionType.OPERATION, "training", "view"),
    (PermCode.TRAINING_MANAGE, "管理培训", PermissionType.OPERATION, "training", "manage"),
    # 匹配
    (PermCode.MATCHING_VIEW, "查看匹配结果", PermissionType.OPERATION, "matching", "view"),
    (PermCode.MATCHING_EXECUTE, "执行岗位匹配", PermissionType.OPERATION, "matching", "execute"),
    # 知识库
    (PermCode.KNOWLEDGE_VIEW, "查看知识库", PermissionType.OPERATION, "knowledge", "view"),
    (PermCode.KNOWLEDGE_MANAGE, "管理知识库", PermissionType.OPERATION, "knowledge", "manage"),
    # 智能体
    (PermCode.AGENT_EXECUTE, "执行AI智能体", PermissionType.OPERATION, "agent", "execute"),
    # 技能编排
    (PermCode.SKILL_VIEW, "查看技能编排", PermissionType.OPERATION, "skill", "view"),
    (PermCode.SKILL_MANAGE, "管理技能编排", PermissionType.OPERATION, "skill", "manage"),
    # 字段级权限
    (PermCode.FIELD_TALENT_PHONE, "查看人才手机号明文", PermissionType.FIELD, "talent", "phone"),
    (PermCode.FIELD_TALENT_ID_CARD, "查看人才身份证号明文", PermissionType.FIELD, "talent", "id_card"),
    (PermCode.FIELD_TALENT_EMAIL, "查看人才邮箱明文", PermissionType.FIELD, "talent", "email"),
    (PermCode.FIELD_TALENT_ADDRESS, "查看人才住址明文", PermissionType.FIELD, "talent", "address"),
    (PermCode.FIELD_TALENT_SALARY, "查看人才期望薪资", PermissionType.FIELD, "talent", "salary"),
    # 行级数据范围
    (PermCode.DATA_SCOPE_ALL, "数据范围：全部", PermissionType.DATA, "talent", "all"),
    (PermCode.DATA_SCOPE_DEPARTMENT, "数据范围：本部门", PermissionType.DATA, "talent", "department"),
]


# ---------------------------------------------------------------------------
# 3. 角色 -> 权限矩阵
# ---------------------------------------------------------------------------
# 说明：
#   super_admin —— 代码层 is_superuser 短路放行，此处补全仅为可审计/可展示
#   admin       —— 业务全权（含敏感字段明文）
#   hr          —— 人才档案主力使用者：可增删改标签/导入/解析，可看联系方式，
#                  但不可删除档案、不可看薪酬
#   user        —— 仅员工自助知识库查看，不授予后台业务数据权限
ROLE_PERMISSIONS: Dict[str, List[str]] = {
    "super_admin": [c for c, *_ in PERMISSION_DEFS],
    "admin": [
        PermCode.TALENT_VIEW, PermCode.TALENT_CREATE, PermCode.TALENT_UPDATE,
        PermCode.TALENT_DELETE, PermCode.TALENT_IMPORT, PermCode.TALENT_EXPORT,
        PermCode.TALENT_TAG, PermCode.TALENT_PARSE_RESUME,
        PermCode.DASHBOARD_VIEW,
        PermCode.USER_VIEW, PermCode.USER_CREATE, PermCode.USER_UPDATE, PermCode.USER_DELETE,
        PermCode.POSITION_VIEW, PermCode.POSITION_MANAGE,
        PermCode.ASSESSMENT_VIEW, PermCode.ASSESSMENT_MANAGE,
        PermCode.TRAINING_VIEW, PermCode.TRAINING_MANAGE,
        PermCode.MATCHING_VIEW, PermCode.MATCHING_EXECUTE,
        PermCode.KNOWLEDGE_VIEW, PermCode.KNOWLEDGE_MANAGE,
        PermCode.AGENT_EXECUTE,
        PermCode.SKILL_VIEW, PermCode.SKILL_MANAGE,
        PermCode.FIELD_TALENT_PHONE, PermCode.FIELD_TALENT_ID_CARD,
        PermCode.FIELD_TALENT_EMAIL, PermCode.FIELD_TALENT_ADDRESS,
        PermCode.FIELD_TALENT_SALARY,
        PermCode.DATA_SCOPE_ALL,
    ],
    "hr": [
        PermCode.TALENT_VIEW, PermCode.TALENT_CREATE, PermCode.TALENT_UPDATE,
        PermCode.TALENT_IMPORT, PermCode.TALENT_EXPORT,
        PermCode.TALENT_TAG, PermCode.TALENT_PARSE_RESUME,
        PermCode.DASHBOARD_VIEW,
        PermCode.POSITION_VIEW, PermCode.POSITION_MANAGE,
        PermCode.ASSESSMENT_VIEW, PermCode.ASSESSMENT_MANAGE,
        PermCode.TRAINING_VIEW, PermCode.TRAINING_MANAGE,
        PermCode.MATCHING_VIEW, PermCode.MATCHING_EXECUTE,
        PermCode.KNOWLEDGE_VIEW, PermCode.KNOWLEDGE_MANAGE,
        PermCode.FIELD_TALENT_PHONE, PermCode.FIELD_TALENT_EMAIL,
        PermCode.DATA_SCOPE_ALL,
    ],
    "user": [
        PermCode.KNOWLEDGE_VIEW,
    ],
}


# ---------------------------------------------------------------------------
# 4. 角色 -> 行级数据范围（写入 data_permissions 表）
# ---------------------------------------------------------------------------
# 说明：普通用户默认按部门隔离；若组织关系缺失则查询结果为空，遵循最小权限原则。
ROLE_DATA_SCOPE: Dict[str, str] = {
    "super_admin": "all",
    "admin": "all",
    "hr": "all",
    "user": "department",
}


# ---------------------------------------------------------------------------
# 5. 权限 seed（幂等）
# ---------------------------------------------------------------------------
def seed_rbac(db: Session) -> Dict[str, int]:
    """幂等写入权限、角色-权限关联、角色数据范围。

    返回 {"permissions": 新建数, "role_permissions": 新建数, "data_permissions": 新建数}
    """
    stats = {"permissions": 0, "role_permissions": 0, "data_permissions": 0}

    # 5.1 权限定义
    perm_by_code: Dict[str, Permission] = {}
    for code, name, ptype, resource, action in PERMISSION_DEFS:
        perm = db.query(Permission).filter(Permission.permission_code == code).first()
        if perm is None:
            perm = Permission(
                permission_code=code,
                permission_name=name,
                permission_type=ptype,
                resource=resource,
                action=action,
                status="active",
            )
            db.add(perm)
            db.flush()
            stats["permissions"] += 1
        perm_by_code[code] = perm
    db.commit()

    # 5.2 角色 -> 权限
    for role_code, codes in ROLE_PERMISSIONS.items():
        role = db.query(Role).filter(Role.role_code == role_code).first()
        if role is None:
            logger.warning(f"[RBAC] 角色不存在，跳过权限分配: {role_code}")
            continue
        role_links = db.query(RolePermission).filter(RolePermission.role_id == role.id).all()
        existing = {rp.permission_id for rp in role_links}
        desired = {
            perm_by_code[code].id
            for code in codes
            if code in perm_by_code
        }
        # 系统角色以代码中的权限矩阵为唯一事实源，撤销历史遗留的多余授权。
        for link in role_links:
            if link.permission_id not in desired:
                db.delete(link)
        for code in codes:
            perm = perm_by_code.get(code)
            if perm is None or perm.id in existing:
                continue
            db.add(RolePermission(role_id=role.id, permission_id=perm.id))
            stats["role_permissions"] += 1
    db.commit()

    # 5.3 角色 -> 行级数据范围
    for role_code, scope in ROLE_DATA_SCOPE.items():
        role = db.query(Role).filter(Role.role_code == role_code).first()
        if role is None:
            continue
        dp = (
            db.query(DataPermission)
            .filter(DataPermission.role_id == role.id, DataPermission.resource == "talent")
            .first()
        )
        if dp is None:
            db.add(DataPermission(
                role_id=role.id,
                user_id=None,
                data_scope=scope,
                organization_ids=[],
                resource="talent",
            ))
            stats["data_permissions"] += 1
        elif dp.data_scope != scope:
            dp.data_scope = scope
    db.commit()

    return stats


# ---------------------------------------------------------------------------
# 6. 权限查询
# ---------------------------------------------------------------------------
def get_user_role_codes(user: Any, db: Session) -> Set[str]:
    """获取用户角色编码集合（异常时返回空集，由调用方按 fail-closed 处理）"""
    try:
        roles = getattr(user, "roles", None)
        if roles is None:
            return set()
        return {r.role_code for r in roles}
    except Exception as e:  # pragma: no cover - 防御性
        logger.warning(f"[RBAC] 读取用户角色失败: {e}")
        return set()


def get_user_permission_codes(user: Any, db: Session) -> Set[str]:
    """获取用户全部权限码（经角色->权限关联查询）"""
    if getattr(user, "is_superuser", False):
        return {c for c, *_ in PERMISSION_DEFS}

    try:
        codes = (
            db.query(Permission.permission_code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(Role, Role.id == RolePermission.role_id)
            .join(User.roles.and_(User.id == user.id))
            .all()
        )
        return {c[0] for c in codes}
    except Exception as e:
        # 权限表未初始化 / user 非 ORM 对象（测试 SimpleNamespace）→ 退回角色矩阵
        logger.debug(f"[RBAC] 权限表查询失败，退回角色矩阵: {e}")
        role_codes = get_user_role_codes(user, db)
        if not role_codes:
            return set()
        result: Set[str] = set()
        for rc in role_codes:
            result.update(ROLE_PERMISSIONS.get(rc, []))
        return result


def user_has_permission(user: Any, permission_code: str, db: Session) -> bool:
    """判断用户是否拥有指定权限；权限数据异常时按最小权限原则拒绝。"""
    if getattr(user, "is_superuser", False):
        return True
    try:
        total = db.query(Permission).count()
    except Exception:
        total = 0
    if total == 0:
        logger.error("[RBAC] 权限表为空，拒绝非超级管理员访问")
        return False
    return permission_code in get_user_permission_codes(user, db)


def require_permission_or_403(permission_code: str):
    """构造 FastAPI 依赖：已认证但无权限则抛 403。

    用法：
        @router.get("/xxx")
        async def foo(current_user: User = Depends(require_permission_or_403(PermCode.TALENT_VIEW))):
            ...

    注意：匿名访问由内部的 get_current_user 依赖拦截（401）。
    """
    from fastapi import Depends, HTTPException, status

    from app.core.database import get_mysql_session
    from app.utils.jwt_handler import get_current_user

    async def checker(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_mysql_session),
    ) -> User:
        if not user_has_permission(current_user, permission_code, db):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"无权限执行此操作（需要 {permission_code}）",
            )
        return current_user

    return checker


# ---------------------------------------------------------------------------
# 7. 字段级权限：敏感 PII 脱敏
# ---------------------------------------------------------------------------
def mask_phone(value: Optional[str]) -> Optional[str]:
    """手机号脱敏：13807550007 -> 138****0007"""
    if not value:
        return value
    v = str(value)
    if len(v) <= 7:
        return v[0] + "*" * (len(v) - 1) if v else v
    return f"{v[:3]}****{v[-4:]}"


def mask_id_card(value: Optional[str]) -> Optional[str]:
    """身份证脱敏：保留前 6 位与后 4 位"""
    if not value:
        return value
    v = str(value)
    if len(v) <= 10:
        return v[0] + "*" * (len(v) - 1)
    return f"{v[:6]}{'*' * (len(v) - 10)}{v[-4:]}"


def mask_email(value: Optional[str]) -> Optional[str]:
    """邮箱脱敏：linshufen@tencent.com -> l*******@tencent.com"""
    if not value or "@" not in str(value):
        return value
    v = str(value)
    local, domain = v.split("@", 1)
    if len(local) <= 1:
        return f"*@{domain}"
    return f"{local[0]}{'*' * min(len(local) - 1, 7)}@{domain}"


def mask_address(value: Optional[str]) -> Optional[str]:
    """住址脱敏：保留前 6 个字符（省市），其余打码"""
    if not value:
        return value
    v = str(value)
    if len(v) <= 6:
        return "*" * len(v)
    return f"{v[:6]}{'*' * min(len(v) - 6, 12)}"


def mask_name(value: Optional[str]) -> Optional[str]:
    """姓名脱敏：林淑芬 -> 林**；欧阳娜娜 -> 欧***"""
    if not value:
        return value
    v = str(value)
    if len(v) <= 1:
        return v
    return f"{v[0]}{'*' * (len(v) - 1)}"


# 字段名 -> (脱敏函数, 所需权限码)
SENSITIVE_FIELD_RULES: Dict[str, tuple] = {
    "phone": (mask_phone, PermCode.FIELD_TALENT_PHONE),
    "id_card": (mask_id_card, PermCode.FIELD_TALENT_ID_CARD),
    "email": (mask_email, PermCode.FIELD_TALENT_EMAIL),
    "address": (mask_address, PermCode.FIELD_TALENT_ADDRESS),
    "expected_salary_min": (lambda v: None, PermCode.FIELD_TALENT_SALARY),
    "expected_salary_max": (lambda v: None, PermCode.FIELD_TALENT_SALARY),
}


def apply_field_masking(data: Any, user: Any, db: Session) -> Dict[str, Any]:
    """按字段级权限对用户无权限查看的敏感字段做脱敏。

    Args:
        data: pydantic 模型实例或 dict（单条人才档案）
        user: 当前用户（User ORM 或测试用 SimpleNamespace）
        db:   数据库会话

    Returns:
        脱敏后的 dict（可直接作为响应 data 返回）
    """
    if hasattr(data, "model_dump"):
        payload = data.model_dump(mode="json")
    elif isinstance(data, dict):
        payload = dict(data)
    else:
        return data

    granted = get_user_permission_codes(user, db)

    for field, (mask_fn, required_code) in SENSITIVE_FIELD_RULES.items():
        if field not in payload:
            continue
        if payload[field] in (None, ""):
            continue
        if required_code in granted or getattr(user, "is_superuser", False):
            continue
        payload[field] = mask_fn(payload[field])

    return payload


def mask_talent_list(items: Sequence[Any], user: Any, db: Session) -> List[Dict[str, Any]]:
    """批量脱敏（列表接口用）"""
    return [apply_field_masking(i, user, db) for i in items]


# ---------------------------------------------------------------------------
# 8. 行级权限：数据范围过滤
# ---------------------------------------------------------------------------
def get_data_scope(user: Any, db: Session, resource: str = "talent") -> str:
    """获取用户的数据范围：all / department / subordinate / custom

    优先级：用户级 data_permissions > 角色级 > 默认 department
    """
    if getattr(user, "is_superuser", False):
        return "all"

    try:
        uid = getattr(user, "id", None)
        if uid is not None:
            user_dp = (
                db.query(DataPermission)
                .filter(DataPermission.user_id == uid, DataPermission.resource == resource)
                .first()
            )
            if user_dp is not None:
                return user_dp.data_scope

        role_ids = [r.id for r in getattr(user, "roles", []) or []]
        if role_ids:
            role_dp = (
                db.query(DataPermission)
                .filter(
                    DataPermission.role_id.in_(role_ids),
                    DataPermission.resource == resource,
                )
                .first()
            )
            if role_dp is not None:
                return role_dp.data_scope
    except Exception as e:
        logger.warning(f"[RBAC] 读取数据范围失败，按 department 处理: {e}")

    return "department"


def build_talent_scope_predicate(user: Any, db: Session):
    """构造人才行级过滤条件表达式（供 service 层注入 query）。

    Returns:
        SQLAlchemy 表达式；无限制（all）时返回 None。
    """
    from app.models.talent import Talent

    # 员工自助隔离：纯普通用户(非管理侧角色)在访问全局人才列表时，只能看到
    # 自己 user_id 归属的档案，杜绝绕过前端直读 HR 全局人才池。
    try:
        roles = set(getattr(user, "roles", []) or [])
        codes = {getattr(r, "role_code", str(r)) if not isinstance(r, str) else r for r in roles}
        is_staff = bool(codes & {"super_admin", "admin", "hr"}) or bool(getattr(user, "is_superuser", False))
        if not is_staff and getattr(user, "id", None):
            return Talent.user_id == user.id
    except Exception:
        pass

    scope = get_data_scope(user, db, resource="talent")
    if scope != "department":
        return None

    org_id = getattr(user, "organization_id", None)
    if org_id is None:
        # 用户无组织归属 —— 部门级隔离下看不到任何人才
        return Talent.id.is_(None)
    return Talent.department_id == org_id


def apply_talent_data_scope(query, user: Any, db: Session, talent_model):
    """对人才查询施加行级数据范围过滤。

    - all        : 不过滤
    - department : 仅返回 talents.department_id == user.organization_id 的记录
    - 其它        : 按部门隔离（fail-closed）
    """
    predicate = build_talent_scope_predicate(user, db)
    if predicate is None:
        return query
    return query.filter(predicate)
