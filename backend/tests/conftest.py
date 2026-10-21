"""
pytest配置文件
"""
import pytest
import sys
import os
import uuid
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# 设置测试环境变量（必须在导入 app 前设置）。
# 每次运行使用不可预测的专属后缀，不能让外部注入的生产变量覆盖测试隔离。
os.environ['TESTING'] = 'true'
os.environ['TEST_RUN_ID'] = uuid.uuid4().hex[:12]
os.environ['MILVUS_COLLECTION_TALENT'] = f"talent_resume_test_{os.environ['TEST_RUN_ID']}"
os.environ['MILVUS_COLLECTION_JOB'] = f"job_position_test_{os.environ['TEST_RUN_ID']}"
os.environ['MILVUS_COLLECTION_KNOWLEDGE'] = f"knowledge_base_test_{os.environ['TEST_RUN_ID']}"

# 导入所有模型以确保表结构注册
from app.core.database import Base  # noqa: E402
from app.models import talent, position, assessment, training, permission  # noqa: F401,E402
from app.models.talent import Talent  # noqa: F401,E402
from app.models.position import JobPosition, PositionStatus  # noqa: F401,E402
from app.models.assessment import (  # noqa: F401,E402
    Question, TestPaper, AssessmentTask, AssessmentResult,
    QuestionType,
    AssessmentStatus,
    CapabilityLevel
)
from app.models.permission import User, Role, Permission  # noqa: F401,E402


@pytest.fixture(scope="session", autouse=True)
def isolated_milvus_collections():
    """创建测试专用 Milvus 集合，会话结束后删除。

    为什么需要：SQLite 内存库的事务回滚管不到 Milvus。测试若直接写生产集合，
    会用测试库的 id 覆盖生产向量，且不会有任何报错——RAG 只是悄悄少召回内容。
    这里让测试跑在 *_test 集合上，跑完删掉，做到「零残留 + 零污染」。
    """
    names = []
    try:
        from pymilvus import connections as milvus_connections

        from app.core import milvus_client as mc
        from app.core.config import settings
        from app.core.run_async import run_async

        # create_*_collection() 内部走 pymilvus.utility，必须先建立连接，
        # 否则报 ConnectionNotExistException，集合建不出来 —— 测试会退化成
        # 「写不进任何集合」而看起来全绿，向量相关用例实际被静默跳过。
        try:
            if not milvus_connections.has_connection(settings.MILVUS_ALIAS):
                milvus_connections.connect(
                    alias=settings.MILVUS_ALIAS,
                    host=settings.MILVUS_HOST,
                    port=settings.MILVUS_PORT,
                    db_name=settings.MILVUS_DB,
                    user=settings.MILVUS_USER or "",
                    password=settings.MILVUS_PASSWORD or "",
                )
        except Exception as exc:  # noqa: BLE001
            print(f"[conftest] Milvus 连接建立失败，向量用例将优雅降级：{exc}")

        plan = (
            (mc.create_talent_resume_collection, settings.MILVUS_COLLECTION_TALENT),
            (mc.create_job_position_collection, settings.MILVUS_COLLECTION_JOB),
            (mc.create_knowledge_base_collection, settings.MILVUS_COLLECTION_KNOWLEDGE),
        )
        for create_fn, name in plan:
            try:
                run_async(create_fn())
                names.append(name)
                print(f"[conftest] 测试集合已就绪：{name}")
            except Exception as exc:  # noqa: BLE001
                # Milvus 不可用时不让整个测试会话失败：相关用例本身会优雅降级
                print(f"[conftest] 测试集合 {name} 创建跳过：{exc}")
    except Exception as exc:  # noqa: BLE001
        print(f"[conftest] Milvus 隔离未启用：{exc}")

    yield

    for name in names:
        try:
            # 注意：pymilvus 的 utility.drop_collection 是**同步**函数，
            # 用 run_async 包会报 "a coroutine was expected, got None"
            mc.utility.drop_collection(name)
            print(f"[conftest] 已清理测试集合 {name}")
        except Exception as exc:  # noqa: BLE001
            print(f"[conftest] 测试集合 {name} 清理失败（不影响结果）：{exc}")


@pytest.fixture(scope="session", autouse=True)
def isolated_minio_buckets():
    """会话结束后清空测试专用的 MinIO 桶（*_test），避免留下孤儿上传文件。

    与 Milvus 隔离同一类问题：对象存储没有事务回滚，测试上传的文件会真实落盘，
    而对应 MySQL 记录随内存库一起消失，于是变成零引用的孤儿对象。
    """
    try:
        from app.utils.minio_client import (
            BUCKET_IMPORTS, BUCKET_KNOWLEDGE, BUCKET_RESUMES, MinioClient,
        )

        buckets = [BUCKET_RESUMES, BUCKET_KNOWLEDGE, BUCKET_IMPORTS]
        # 只允许清理本次运行生成的唯一测试桶；后缀缺失或运行 ID 不一致时绝不触碰对象存储。
        run_id = os.environ.get("TEST_RUN_ID", "")
        expected_suffix = f"-test-{run_id}" if run_id else ""
        if not run_id or not all(b.endswith(expected_suffix) for b in buckets):
            print("[conftest] MinIO 桶隔离未启用（缺少当前运行专属后缀），跳过清理")
            yield
            return

        yield

        for bucket in buckets:
            try:
                mc = MinioClient(bucket)
                client = mc.client
                if client.bucket_exists(bucket):
                    for obj in client.list_objects(bucket, recursive=True):
                        client.remove_object(bucket, obj.object_name)
                    client.remove_bucket(bucket)
                print(f"[conftest] 已清理测试桶 {bucket}")
            except Exception as exc:  # noqa: BLE001
                print(f"[conftest] 测试桶 {bucket} 清理失败（不影响结果）：{exc}")
    except Exception as exc:  # noqa: BLE001
        print(f"[conftest] MinIO 桶隔离未启用：{exc}")
        yield


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
