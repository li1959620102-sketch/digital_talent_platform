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

# ── Milvus 测试隔离（重要）─────────────────────────────────────────────────
# 本文件用 SQLite 内存库，测试里的自增 id 从 1 开始；而 Milvus 没有数据库级的
# 事务回滚，测试写入会**真实落到运行中的集合里**。两个 id 空间一旦冲突，就会
# 出现「测试上传的文件拿到 file_id=2 → vectorize 先删掉生产 file_id=2 的向量
# 再写入测试向量」，结果是知识库向量被静默覆盖（实测 knowledge_base 72→67）。
# 因此这里把三个集合全部指向 *_test 专用集合，会话结束时由 fixture 删除。
os.environ.setdefault('MILVUS_COLLECTION_TALENT', 'talent_resume_test')
os.environ.setdefault('MILVUS_COLLECTION_JOB', 'job_position_test')
os.environ.setdefault('MILVUS_COLLECTION_KNOWLEDGE', 'knowledge_base_test')

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
        # 若后缀没生效（环境变量没读到），说明不是测试环境，不要动真实桶
        if not all(b.endswith("-test") for b in buckets):
            print("[conftest] MinIO 桶隔离未启用（桶名无 -test 后缀），跳过清理")
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
