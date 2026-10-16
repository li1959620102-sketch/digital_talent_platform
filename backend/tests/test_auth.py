"""
认证服务单元测试
"""
import pytest
from datetime import datetime, timedelta

from app.utils.jwt_handler import JWTHandler
from app.services.auth_service import AuthService
from app.models.permission import User, UserStatus, AuditLog
from app.core.exceptions import UnauthorizedException


class TestJWTHandler:
    """JWT处理器测试"""

    def test_password_hash(self):
        """测试密码哈希"""
        password = "test_password_123"
        hashed = JWTHandler.get_password_hash(password)

        assert hashed != password
        assert JWTHandler.verify_password(password, hashed)
        assert not JWTHandler.verify_password("wrong_password", hashed)

    def test_create_access_token(self):
        """测试创建访问令牌"""
        user_id = 1
        username = "test_user"

        token = JWTHandler.create_access_token(
            data={"user_id": user_id, "username": username}
        )

        assert token is not None
        assert isinstance(token, str)

        # 解码验证
        payload = JWTHandler.decode_token(token)
        assert payload["user_id"] == user_id
        assert payload["username"] == username
        assert payload["type"] == "access"

    def test_create_refresh_token(self):
        """测试创建刷新令牌"""
        user_id = 1
        username = "test_user"

        token = JWTHandler.create_refresh_token(
            data={"user_id": user_id, "username": username}
        )

        assert token is not None

        # 解码验证
        payload = JWTHandler.decode_token(token)
        assert payload["type"] == "refresh"

    def test_decode_invalid_token(self):
        """测试解码无效令牌"""
        invalid_token = "invalid_token_string"

        with pytest.raises(Exception):
            JWTHandler.decode_token(invalid_token)

    def test_token_expiration(self):
        """测试令牌过期"""
        # 创建一个立即过期的令牌
        user_id = 1
        username = "test_user"

        # 使用已过期的时间
        token = JWTHandler.create_access_token(
            data={"user_id": user_id, "username": username},
            expires_delta=timedelta(seconds=-1)
        )

        # 解码应该失败或标记为过期
        with pytest.raises(Exception):
            JWTHandler.decode_token(token)


class TestAuthService:
    """认证服务测试

    注（2026-10-13）：本类 5 个用例此前为 `pass` 空桩——虽被 pytest 收集并计为
    「通过」，但不含任何断言，导致认证服务层实际处于零自动化覆盖状态。
    现已补齐为有效断言用例，并新增 2 个安全边界用例。
    """

    PASSWORD = "Str0ng_Passw0rd!"

    _seq = 0

    @classmethod
    def _make_user(cls, db, username, password=None, **kwargs):
        """构造一个可登录的用户（密码已哈希），手机号/邮箱自动避免唯一冲突"""
        cls._seq += 1
        user = User(
            username=username,
            password_hash=JWTHandler.get_password_hash(password or cls.PASSWORD),
            real_name="认证测试用户",
            phone=kwargs.pop("phone", f"1390000{cls._seq:04d}"),
            email=kwargs.pop("email", f"{username}@example.com"),
            status=kwargs.pop("status", UserStatus.ACTIVE),
            is_superuser=kwargs.pop("is_superuser", False),
            login_count=kwargs.pop("login_count", 0),
            failed_login_count=kwargs.pop("failed_login_count", 0),
            **kwargs,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    async def test_login_success(self, test_db):
        """登录成功：签发双令牌、重置失败计数、登录计数+1、写审计日志"""
        user = self._make_user(test_db, "login_ok")

        result = await AuthService.login(
            test_db, "login_ok", self.PASSWORD, ip_address="127.0.0.1"
        )

        # 响应结构
        assert result["token_type"] == "bearer"
        assert result["access_token"]
        assert result["refresh_token"]
        assert result["user"]["username"] == "login_ok"

        # 令牌类型正确且可解码
        assert JWTHandler.decode_token(result["access_token"])["type"] == "access"
        assert JWTHandler.decode_token(result["refresh_token"])["type"] == "refresh"

        # 登录副作用已落库
        test_db.refresh(user)
        assert user.login_count == 1
        assert user.failed_login_count == 0
        assert user.last_login_ip == "127.0.0.1"
        assert user.last_login_time is not None

        # 审计日志
        log = (
            test_db.query(AuditLog)
            .filter(AuditLog.operation == "login", AuditLog.username == "login_ok")
            .first()
        )
        assert log is not None
        assert log.status == "success"
        assert log.ip_address == "127.0.0.1"

    async def test_login_invalid_credentials(self, test_db):
        """凭据错误：抛 UnauthorizedException，失败计数累加"""
        user = self._make_user(test_db, "login_bad")

        with pytest.raises(UnauthorizedException):
            await AuthService.login(test_db, "login_bad", "definitely_wrong")

        test_db.refresh(user)
        assert user.failed_login_count == 1
        assert user.locked_until is None

    async def test_login_nonexistent_user(self, test_db):
        """用户名不存在：抛 UnauthorizedException（不泄露用户是否存在）"""
        with pytest.raises(UnauthorizedException):
            await AuthService.login(test_db, "no_such_user", self.PASSWORD)

    async def test_login_account_locked(self, test_db):
        """账号处于锁定期内：即使密码正确也拒绝登录"""
        locked_until = datetime.now() + timedelta(minutes=10)
        self._make_user(test_db, "login_locked", locked_until=locked_until)

        with pytest.raises(UnauthorizedException) as exc:
            await AuthService.login(test_db, "login_locked", self.PASSWORD)

        assert "锁定" in str(exc.value.message)

    async def test_login_auto_lock_after_failures(self, test_db):
        """连续失败达 5 次：自动锁定账号 30 分钟"""
        user = self._make_user(test_db, "login_bruteforce", failed_login_count=4)

        with pytest.raises(UnauthorizedException):
            await AuthService.login(test_db, "login_bruteforce", "wrong_password")

        test_db.refresh(user)
        assert user.failed_login_count == 5
        assert user.locked_until is not None
        assert user.locked_until > datetime.now()

    async def test_refresh_token(self, test_db):
        """刷新令牌：合法 refresh token 换取新的 access token"""
        user = self._make_user(test_db, "refresh_ok")
        rt = JWTHandler.create_refresh_token(
            data={"sub": user.id, "username": user.username}
        )

        result = await AuthService.refresh_token(test_db, rt)

        assert result["token_type"] == "bearer"
        assert JWTHandler.decode_token(result["access_token"])["type"] == "access"

    async def test_refresh_token_rejects_access_token(self, test_db):
        """安全边界：刷新接口必须拒绝用 access token 冒充 refresh token"""
        user = self._make_user(test_db, "refresh_bad")
        at = JWTHandler.create_access_token(
            data={"sub": user.id, "username": user.username}
        )

        with pytest.raises(UnauthorizedException):
            await AuthService.refresh_token(test_db, at)

    async def test_logout(self, test_db):
        """登出：返回 True 并写审计日志"""
        user = self._make_user(test_db, "logout_ok")

        ok = await AuthService.logout(test_db, user.id, ip_address="10.0.0.9")

        assert ok is True
        log = (
            test_db.query(AuditLog)
            .filter(AuditLog.operation == "logout", AuditLog.username == "logout_ok")
            .first()
        )
        assert log is not None
        assert log.ip_address == "10.0.0.9"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
