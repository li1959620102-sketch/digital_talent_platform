"""
pytest配置文件
"""
import pytest
import sys
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# 设置测试环境变量（必须在导入app前设置）
os.environ['TESTING'] = 'true'

# 导入所有模型以确保表结构注册
from app.core.database import Base
from app.models import talent, position, assessment, training, permission  # noqa: F401
from app.models.talent import Talent
from app.models.position import JobPosition, PositionStatus
from app.models.assessment import (
    Question, TestPaper, AssessmentTask, AssessmentResult,
    QuestionType,
    AssessmentStatus,
    CapabilityLevel
)
from app.models.permission import User, Role, Permission


@pytest.fixture(scope="session")
def engine():
    """测试引擎（SQLite内存数据库，使用StaticPool保持单一连接）"""
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False
    )
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def test_db(engine):
    """测试数据库会话fixture（每个测试重置表，保证隔离）"""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def test_client():
    """测试客户端fixture"""
    from fastapi.testclient import TestClient
    from main import app
    return TestClient(app)
