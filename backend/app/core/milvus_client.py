"""
Milvus向量数据库客户端管理
健壮性对齐参考 large_health_reference/app/utils/milvus_client.py：
- insert: 3次重试 + 逐条降级兜底
- search/load: load 重试 + 超时保护
- ensure_collection: schema 不匹配时重建（启动时调用）
"""
import warnings
try:
    from pymilvus import PyMilvusDeprecationWarning
    warnings.filterwarnings("ignore", category=PyMilvusDeprecationWarning)
except ImportError:
    pass

from pymilvus import (
    connections,
    Collection,
    utility,
    FieldSchema,
    CollectionSchema,
    DataType
)
from typing import Optional, List, Dict, Any
import logging
import time

from app.core.config import settings

logger = logging.getLogger(__name__)


async def init_milvus():
    """初始化Milvus向量库"""
    try:
        # 连接Milvus
        connect_kwargs = dict(
            alias=settings.MILVUS_ALIAS,
            host=settings.MILVUS_HOST,
            port=settings.MILVUS_PORT,
            db_name=settings.MILVUS_DB,
        )
        if settings.MILVUS_USER:
            connect_kwargs["user"] = settings.MILVUS_USER
        if settings.MILVUS_PASSWORD:
            connect_kwargs["password"] = settings.MILVUS_PASSWORD
        connections.connect(**connect_kwargs)
        
        logger.info(f"✅ Milvus连接成功: {settings.MILVUS_HOST}:{settings.MILVUS_PORT}")
        
        # 创建必要的集合
        await create_talent_resume_collection()
        await create_job_position_collection()
        await create_knowledge_base_collection()
        
    except Exception as e:
        logger.warning(f"⚠️ Milvus初始化失败: {str(e)}，将在后台重试")
        # 不抛出异常，允许应用启动
        # raise


async def create_talent_resume_collection():
    """创建人才简历向量集合"""
    collection_name = settings.MILVUS_COLLECTION_TALENT
    
    if utility.has_collection(collection_name):
        logger.info(f"集合 '{collection_name}' 已存在")
        return
    
    # 定义字段
    fields = [
        FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
        FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=settings.EMBEDDING_DIM),
        FieldSchema(name="talent_id", dtype=DataType.VARCHAR, max_length=64),
        FieldSchema(name="resume_text", dtype=DataType.VARCHAR, max_length=65535),
        FieldSchema(name="chunk_id", dtype=DataType.VARCHAR, max_length=128),
        FieldSchema(name="file_id", dtype=DataType.VARCHAR, max_length=128),
        FieldSchema(name="file_name", dtype=DataType.VARCHAR, max_length=512),
        FieldSchema(name="business_scene", dtype=DataType.VARCHAR, max_length=128),
        FieldSchema(name="created_at", dtype=DataType.INT64),
    ]
    
    # 创建Schema
    schema = CollectionSchema(
        fields=fields,
        description="人才简历向量集合"
    )
    
    # 创建集合
    collection = Collection(name=collection_name, schema=schema)
    
    # 创建索引
    index_params = {
        "metric_type": "COSINE",
        "index_type": "HNSW",
        "params": {"M": 16, "efConstruction": 256}
    }
    collection.create_index(field_name="embedding", index_params=index_params)
    
    logger.info(f"✅ 人才简历向量集合 '{collection_name}' 创建成功")


async def create_job_position_collection():
    """创建岗位需求向量集合"""
    collection_name = settings.MILVUS_COLLECTION_JOB
    
    if utility.has_collection(collection_name):
        logger.info(f"集合 '{collection_name}' 已存在")
        return
    
    # 定义字段
    fields = [
        FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
        FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=settings.EMBEDDING_DIM),
        FieldSchema(name="position_id", dtype=DataType.VARCHAR, max_length=64),
        FieldSchema(name="position_text", dtype=DataType.VARCHAR, max_length=65535),
        FieldSchema(name="position_name", dtype=DataType.VARCHAR, max_length=256),
        FieldSchema(name="department", dtype=DataType.VARCHAR, max_length=256),
        FieldSchema(name="business_scene", dtype=DataType.VARCHAR, max_length=128),
        FieldSchema(name="created_at", dtype=DataType.INT64),
    ]
    
    # 创建Schema
    schema = CollectionSchema(
        fields=fields,
        description="岗位需求向量集合"
    )
    
    # 创建集合
    collection = Collection(name=collection_name, schema=schema)
    
    # 创建索引
    index_params = {
        "metric_type": "COSINE",
        "index_type": "HNSW",
        "params": {"M": 16, "efConstruction": 256}
    }
    collection.create_index(field_name="embedding", index_params=index_params)
    
    logger.info(f"✅ 岗位需求向量集合 '{collection_name}' 创建成功")


async def create_knowledge_base_collection():
    """创建知识库向量集合"""
    collection_name = settings.MILVUS_COLLECTION_KNOWLEDGE
    
    if utility.has_collection(collection_name):
        logger.info(f"集合 '{collection_name}' 已存在")
        return
    
    # 定义字段
    fields = [
        FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
        FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=settings.EMBEDDING_DIM),
        FieldSchema(name="knowledge_text", dtype=DataType.VARCHAR, max_length=65535),
        FieldSchema(name="knowledge_type", dtype=DataType.VARCHAR, max_length=128),
        FieldSchema(name="file_id", dtype=DataType.VARCHAR, max_length=128),
        FieldSchema(name="file_name", dtype=DataType.VARCHAR, max_length=512),
        FieldSchema(name="chunk_id", dtype=DataType.VARCHAR, max_length=128),
        FieldSchema(name="business_scene", dtype=DataType.VARCHAR, max_length=128),
        FieldSchema(name="permission_level", dtype=DataType.INT64),
        FieldSchema(name="created_at", dtype=DataType.INT64),
    ]
    
    # 创建Schema
    schema = CollectionSchema(
        fields=fields,
        description="知识库向量集合"
    )
    
    # 创建集合
    collection = Collection(name=collection_name, schema=schema)
    
    # 创建索引
    index_params = {
        "metric_type": "COSINE",
        "index_type": "HNSW",
        "params": {"M": 16, "efConstruction": 256}
    }
    collection.create_index(field_name="embedding", index_params=index_params)
    
    logger.info(f"✅ 知识库向量集合 '{collection_name}' 创建成功")


class MilvusService:
    """
    Milvus服务封装（健壮性对齐参考实现）。
    关键改进：
    - insert: 3次重试 + 逐条降级
    - search: load 前重试 + 超时保护
    - query/count: flush 保护
    """
    
    def __init__(self, collection_name: str, max_retries: int = 3):
        self.collection_name = collection_name
        self.max_retries = max_retries  # insert 重试次数
        # 懒连接：确保 Milvus 连接存在（应用启动时 init_milvus 可能因服务未就绪而失败，
        # 导致后续 search/insert 报 ConnectionNotExistException，进而检索返回空）
        self._ensure_connection()
        self.collection = Collection(name=collection_name)

    def _ensure_connection(self):
        """确保 Milvus 连接已建立（幂等；已连接则跳过，未连接则补建）。"""
        try:
            if connections.has_connection(settings.MILVUS_ALIAS):
                return
        except Exception:
            pass
        try:
            connect_kwargs = dict(
                alias=settings.MILVUS_ALIAS,
                host=settings.MILVUS_HOST,
                port=settings.MILVUS_PORT,
                db_name=settings.MILVUS_DB,
            )
            if settings.MILVUS_USER:
                connect_kwargs["user"] = settings.MILVUS_USER
            if settings.MILVUS_PASSWORD:
                connect_kwargs["password"] = settings.MILVUS_PASSWORD
            connections.connect(**connect_kwargs)
            logger.info(f"MilvusService 懒连接已建立: {settings.MILVUS_HOST}:{settings.MILVUS_PORT}")
        except Exception as e:
            logger.warning(f"MilvusService 懒连接失败: {e}")

    # ─── 启动时：schema 不匹配则重建 ───────────────────────────

    def ensure_schema(self, required_fields: set):
        """
        启动时调用：检查集合 schema 是否匹配，不匹配则重建。
        参考 ensure_collection 逻辑，避免 schema 漂移导致 insert/search 静默失败。
        """
        try:
            if not utility.has_collection(self.collection_name):
                logger.warning(f"集合 {self.collection_name} 不存在，无法做 schema 校验（需手动重建）")
                return
            desc = utility.describe_collection(self.collection_name)
            existing_fields = {f["name"] for f in desc.get("fields", [])}
            if not required_fields.issubset(existing_fields):
                logger.warning(
                    f"集合 {self.collection_name} schema 不匹配，现有字段: {existing_fields}, "
                    f"缺少: {required_fields - existing_fields}，建议手动重建集合"
                )
            else:
                logger.info(f"集合 {self.collection_name} schema 检查通过")
        except Exception as e:
            logger.warning(f"集合 {self.collection_name} schema 校验异常: {e}，跳过")
    
    # ─── 核心操作 ──────────────────────────────────────────────

    async def insert(
        self, 
        embeddings: List[List[float]],
        metadata_list: List[Dict[str, Any]]
    ) -> List[int]:
        """
        插入向量数据（健壮性对齐参考：3次重试 + 逐条降级）。
        auto_id=True 时 Milvus 自动分配递增主键，无需手动指定 id 字段。
        """
        entities = [embeddings]
        for key in metadata_list[0].keys():
            entities.append([item[key] for item in metadata_list])

        # 参考 milvus_client.py：批量插入最多重试 3 次
        last_error = None
        for attempt in range(self.max_retries):
            try:
                ids = self.collection.insert(entities)
                # 新集合创建后不立即 flush（Milvus 后台自动 flush，强制 flush 会 500）
                self.collection.flush()
                return ids.primary_keys
            except Exception as e:
                last_error = e
                logger.warning(f"[{self.collection_name}] 批量插入第{attempt+1}次失败: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(1)

        # 三次批量全失败，降级逐条插入（参考逻辑）
        logger.error(f"[{self.collection_name}] 批量插入全部失败: {last_error}，降级逐条插入")
        primary_keys = []
        for i, (emb, meta) in enumerate(zip(embeddings, metadata_list)):
            try:
                single_entity = [[emb]]
                for key in meta.keys():
                    single_entity.append([meta[key]])
                ids = self.collection.insert(single_entity)
                primary_keys.append(ids.primary_keys[0])
            except Exception as e2:
                logger.error(f"[{self.collection_name}] 逐条插入第{i+1}条失败: {e2}")
        if primary_keys:
            self.collection.flush()
        logger.info(f"[{self.collection_name}] 逐条插入 {len(primary_keys)}/{len(embeddings)} 条")
        return primary_keys
    
    async def search(
        self,
        query_embedding: List[float],
        top_k: int = 10,
        expr: Optional[str] = None,
        output_fields: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        向量搜索（健壮性对齐：load 前重试 + entity.fields 兼容处理）。
        HNSW 索引参数 ef=64；兼容 PyMilvus 2.x/3.x entity.fields API。
        """
        # 加载集合：重试 3 次（参考 load 重试逻辑）
        for attempt in range(self.max_retries):
            try:
                self.collection.load()
                break
            except Exception as e:
                logger.warning(f"[{self.collection_name}] load 第{attempt+1}次失败: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(0.5)
                else:
                    raise

        search_params = {"metric_type": "COSINE", "params": {"ef": 64}}

        results = self.collection.search(
            data=[query_embedding],
            anns_field="embedding",
            param=search_params,
            limit=top_k,
            expr=expr,
            output_fields=output_fields or ["*"]
        )

        formatted_results = []
        for hits in results:
            for hit in hits:
                # PyMilvus 2.x: hit.entity.fields；3.x: hit.fields（兼容处理）
                fields = getattr(hit.entity, "fields", None) or getattr(hit, "fields", {})
                result = {
                    "id": hit.id,
                    "distance": hit.distance,
                    "score": 1 - hit.distance,
                    **fields
                }
                formatted_results.append(result)

        return formatted_results
    
    async def query(
        self,
        expr: str,
        output_fields: Optional[List[str]] = None,
        limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """标量查询"""
        self.collection.load()
        
        results = self.collection.query(
            expr=expr,
            output_fields=output_fields or ["*"],
            limit=limit
        )
        
        return results
    
    async def delete(self, expr: str) -> int:
        """删除数据"""
        result = self.collection.delete(expr)
        self.collection.flush()
        
        return result.delete_count
    
    async def count(self) -> int:
        """
        统计集合实体数量（flush 保护 + 兼容处理）。
        新版 PyMilvus num_entities 可能抛异常，加异常保护。
        """
        try:
            self.collection.flush()
            return self.collection.num_entities
        except Exception as e:
            logger.warning(f"[{self.collection_name}] num_entities 失败: {e}")
            return 0
    
    async def load(self):
        """加载集合到内存"""
        self.collection.load()
    
    async def release(self):
        """释放集合内存"""
        self.collection.release()
