"""
PostgreSQL 分析库客户端（PgSQL 分库）
遵循招标文件强制要求：PgSQL 用于海量分析数据和时序数据。
MySQL（digital_talent）保留：用户/组织/角色等核心主数据
PgSQL（talent_analytics）新增：人才行为分析/培训记录/测评时序数据
"""
from contextlib import contextmanager
from typing import Generator, Optional
import logging

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session, declarative_base
from sqlalchemy.pool import QueuePool

from app.core.config import settings

logger = logging.getLogger(__name__)

# PostgreSQL 连接 URI
_pgsql_uri: Optional[str] = None


def _get_pgsql_uri() -> str:
    global _pgsql_uri
    if _pgsql_uri is None:
        _pgsql_uri = settings.POSTGRES_URI
    return _pgsql_uri


# PostgreSQL Engine（全局单例，懒初始化）
_pgsql_engine = None


def get_pgsql_engine():
    global _pgsql_engine
    if _pgsql_engine is None:
        _pgsql_engine = create_engine(
            _get_pgsql_uri(),
            poolclass=QueuePool,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            pool_recycle=3600,
            echo=False,
        )
        logger.info(f"PgSQL 连接池创建: {settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}")
    return _pgsql_engine


# Session 工厂
_PgsqlSessionFactory: Optional[sessionmaker] = None


def _get_session_factory() -> sessionmaker:
    global _PgsqlSessionFactory
    if _PgsqlSessionFactory is None:
        _PgsqlSessionFactory = sessionmaker(
            bind=get_pgsql_engine(),
            autocommit=False,
            autoflush=False,
        )
    return _PgsqlSessionFactory


@contextmanager
def get_pgsql_session() -> Generator[Session, None, None]:
    """
    PostgreSQL 数据库上下文管理器。
    用法：
        from app.core.postgresql import get_pgsql_session
        with get_pgsql_session() as db:
            result = db.query(PgModel).all()
    """
    factory = _get_session_factory()
    session: Session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_pgsql_check() -> bool:
    """检查 PgSQL 连接是否可用"""
    try:
        with get_pgsql_session() as db:
            db.execute("SELECT 1")
        logger.info("✅ PgSQL 连接正常")
        return True
    except Exception as e:
        logger.warning(f"⚠️ PgSQL 连接失败: {e}，部分分析功能将回退到 MySQL")
        return False


# ── 分析库 ORM Base ──────────────────────────────────────────────
# 用于 PgSQL 专属的分析表（不从 MySQL 模型继承）
Base = declarative_base()
