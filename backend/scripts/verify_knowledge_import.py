"""校验知识库元数据、切片和 Milvus 向量数量。"""
import asyncio
from app.core.config import settings
from app.core.database import get_mysql_session_factory
from app.core.milvus_client import MilvusService
from app.models.knowledge import KnowledgeFile, KnowledgeChunk

db = get_mysql_session_factory()()
try:
    files = db.query(KnowledgeFile).order_by(KnowledgeFile.id).all()
    print(f"files={len(files)} vectorized={sum(f.status == 'vectorized' for f in files)} chunks={db.query(KnowledgeChunk).count()}")
    for item in files:
        print(f"- {item.file_name} | {item.knowledge_type} | {item.status} | chunks={item.chunk_count}")
finally:
    db.close()

print(f"milvus_collection={settings.MILVUS_COLLECTION_KNOWLEDGE}")
print(f"milvus_vectors={asyncio.run(MilvusService(settings.MILVUS_COLLECTION_KNOWLEDGE).count())}")
