"""
数据库连接管理
"""
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, Session, declarative_base
from sqlalchemy.pool import QueuePool
from typing import AsyncGenerator, Optional
import logging
import os

from app.core.config import settings

logger = logging.getLogger(__name__)

# 基础模型类
Base = declarative_base()

# 延迟初始化引擎（避免在测试时立即连接数据库）
_mysql_engine: Optional[any] = None
_mysql_async_engine: Optional[any] = None
_postgres_async_engine: Optional[any] = None

def get_mysql_engine():
    """获取MySQL同步引擎（延迟初始化）"""
    global _mysql_engine
    if _mysql_engine is None and not os.getenv('TESTING'):
        _mysql_engine = create_engine(
            settings.MYSQL_URI,
            pool_size=20,
            max_overflow=10,
            pool_pre_ping=True,
            pool_recycle=3600,
            echo=False,
            poolclass=QueuePool
        )
    return _mysql_engine

def get_mysql_async_engine():
    """获取MySQL异步引擎（延迟初始化）"""
    global _mysql_async_engine
    if _mysql_async_engine is None and not os.getenv('TESTING'):
        _mysql_async_engine = create_async_engine(
            settings.MYSQL_ASYNC_URI,
            pool_size=20,
            max_overflow=10,
            pool_pre_ping=True,
            pool_recycle=3600,
            echo=settings.DEBUG
        )
    return _mysql_async_engine

def get_postgres_async_engine():
    """获取PostgreSQL异步引擎（延迟初始化）"""
    global _postgres_async_engine
    if _postgres_async_engine is None and not os.getenv('TESTING'):
        _postgres_async_engine = create_async_engine(
            settings.POSTGRES_ASYNC_URI,
            pool_size=20,
            max_overflow=10,
            pool_pre_ping=True,
            pool_recycle=3600,
            echo=settings.DEBUG
        )
    return _postgres_async_engine

# 为了向后兼容，提供模块级别的属性访问
# 但这些会触发警告，建议使用get_*方法
@property
def mysql_engine():
    return get_mysql_engine()

@property
def mysql_async_engine():
    return get_mysql_async_engine()

@property
def postgres_async_engine():
    return get_postgres_async_engine()

# MySQL同步会话工厂
def get_mysql_session_factory():
    engine = get_mysql_engine()
    if engine:
        return sessionmaker(bind=engine, autocommit=False, autoflush=False)
    return None

# MySQL异步会话工厂
def get_mysql_async_session_factory():
    engine = get_mysql_async_engine()
    if engine:
        return sessionmaker(bind=engine, class_=AsyncSession, autocommit=False, autoflush=False, expire_on_commit=False)
    return None

# PostgreSQL异步会话工厂
def get_postgres_async_session_factory():
    engine = get_postgres_async_engine()
    if engine:
        return sessionmaker(bind=engine, class_=AsyncSession, autocommit=False, autoflush=False, expire_on_commit=False)
    return None

# 依赖注入：获取MySQL同步会话
def get_mysql_session() -> Session:
    """获取MySQL同步会话"""
    factory = get_mysql_session_factory()
    if not factory:
        raise RuntimeError("MySQL engine not initialized. Call get_mysql_engine() first.")
    session = factory()
    try:
        yield session
    finally:
        session.close()

# 依赖注入：获取MySQL异步会话
async def get_mysql_async_session() -> AsyncGenerator[AsyncSession, None]:
    """获取MySQL异步会话"""
    factory = get_mysql_async_session_factory()
    if not factory:
        raise RuntimeError("MySQL async engine not initialized. Call get_mysql_async_engine() first.")
    async with factory() as session:
        try:
            yield session
        finally:
            await session.close()

# 依赖注入：获取PostgreSQL异步会话
async def get_postgres_async_session() -> AsyncGenerator[AsyncSession, None]:
    """获取PostgreSQL异步会话"""
    factory = get_postgres_async_session_factory()
    if not factory:
        raise RuntimeError("PostgreSQL async engine not initialized. Call get_postgres_async_engine() first.")
    async with factory() as session:
        try:
            yield session
        finally:
            await session.close()

# 初始化所有数据库连接
def init_db():
    """初始化数据库连接"""
    get_mysql_engine()
    get_mysql_async_engine()
    get_postgres_async_engine()
    logger.info("数据库连接初始化完成")


# 初始化 MySQL 业务表结构
def init_mysql_tables() -> bool:
    """应用启动时调用：按 ORM 元数据创建 MySQL 业务表（幂等）。

    以 ORM 模型为 schema 唯一事实源，避免 docker/mysql/init 下手工 DDL
    与模型漂移（漏建表/漏列），否则运行期会抛 `Table/Column doesn't exist` 500。
    create_all 为增量语义：已存在的表只校验不重建，不覆盖存量数据。
    """
    try:
        engine = get_mysql_engine()
        if engine is None:
            logger.warning("MySQL 引擎未初始化，跳过业务表创建")
            return False
        # 延迟导入：注册全部 ORM 映射到 Base.metadata，同时规避循环导入
        import app.models  # noqa: F401
        Base.metadata.create_all(engine)
        logger.info("✅ MySQL 业务表创建/验证完成")
        return True
    except Exception as e:
        logger.error(f"❌ MySQL 业务表初始化失败: {e}")
        return False

# 关闭所有数据库连接
async def close_db():
    """关闭数据库连接"""
    global _mysql_engine, _mysql_async_engine, _postgres_async_engine
    
    if _mysql_engine:
        _mysql_engine.dispose()
        logger.info("MySQL同步引擎已关闭")
    
    if _mysql_async_engine:
        await _mysql_async_engine.dispose()
        logger.info("MySQL异步引擎已关闭")
    
    if _postgres_async_engine:
        await _postgres_async_engine.dispose()
        logger.info("PostgreSQL异步引擎已关闭")
