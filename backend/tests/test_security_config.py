"""生产配置安全基线测试。"""
import pytest
from pydantic import ValidationError

from app.core.config import Settings


def _production_settings(**overrides):
    values = {
        "DEBUG": False,
        "SECRET_KEY": "s" * 64,
        "INITIAL_ADMIN_PASSWORD": "Admin-Strong-Password-2026",
        "MYSQL_PASSWORD": "Mysql-Strong-Password-2026",
        "POSTGRES_PASSWORD": "Postgres-Strong-Password-2026",
        "REDIS_PASSWORD": "Redis-Strong-Password-2026",
        "MINIO_SECRET_KEY": "Minio-Strong-Password-2026",
        "AUTH_COOKIE_SECURE": True,
        "CORS_ORIGINS": ["https://talent.example.com"],
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_secure_production_settings_are_accepted():
    settings = _production_settings()
    assert settings.DEBUG is False


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("SECRET_KEY", "short"),
        ("MYSQL_PASSWORD", "root"),
        ("POSTGRES_PASSWORD", "postgres"),
        ("REDIS_PASSWORD", ""),
        ("MINIO_SECRET_KEY", "minioadmin"),
        ("INITIAL_ADMIN_PASSWORD", "CHANGE_ME_password"),
        ("AUTH_COOKIE_SECURE", False),
        ("CORS_ORIGINS", ["http://localhost:5173"]),
    ],
)
def test_insecure_production_settings_are_rejected(field, value):
    with pytest.raises(ValidationError):
        _production_settings(**{field: value})
