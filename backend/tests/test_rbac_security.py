"""RBAC 安全回归测试。"""
from types import SimpleNamespace

from app.core.rbac import (
    PermCode,
    ROLE_DATA_SCOPE,
    ROLE_PERMISSIONS,
    seed_rbac,
    user_has_permission,
)
from app.models.permission import Permission, PermissionType, Role, RolePermission


def test_regular_user_uses_least_privilege_matrix():
    """普通员工只能查看知识库，不能访问管理后台能力。"""
    assert set(ROLE_PERMISSIONS["user"]) == {PermCode.KNOWLEDGE_VIEW}
    assert ROLE_DATA_SCOPE["user"] == "department"


def test_permission_check_fails_closed_when_permission_table_empty(test_db):
    """权限种子缺失时，非超级管理员必须被拒绝。"""
    user = SimpleNamespace(id=1, is_superuser=False, roles=[])
    assert user_has_permission(user, PermCode.KNOWLEDGE_VIEW, test_db) is False


def test_superuser_is_still_available_during_rbac_recovery(test_db):
    """超级管理员可在权限表异常时执行恢复操作。"""
    user = SimpleNamespace(id=1, is_superuser=True, roles=[])
    assert user_has_permission(user, PermCode.USER_UPDATE, test_db) is True


def test_seed_removes_stale_system_role_grants(test_db):
    """重复执行种子时会撤销系统角色的历史越权授权。"""
    role = Role(role_code="user", role_name="普通用户", is_system=True)
    stale = Permission(
        permission_code="legacy:dangerous",
        permission_name="遗留危险权限",
        permission_type=PermissionType.OPERATION,
        status="active",
    )
    test_db.add_all([role, stale])
    test_db.flush()
    test_db.add(RolePermission(role_id=role.id, permission_id=stale.id))
    test_db.commit()

    seed_rbac(test_db)

    granted = {
        code
        for (code,) in (
            test_db.query(Permission.permission_code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .filter(RolePermission.role_id == role.id)
            .all()
        )
    }
    assert granted == {PermCode.KNOWLEDGE_VIEW}
