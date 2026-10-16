"""
向量检索服务
基于Milvus实现人才简历和岗位需求的向量检索。
本地无Milvus/Ollama时，实例化与服务调用会优雅失败（被上层try/except捕获）。
"""
from typing import List, Dict, Any, Optional
import logging
import asyncio

from app.core.config import settings

logger = logging.getLogger(__name__)


class VectorSearchService:
    """向量检索服务"""

    def __init__(self):
        self.embedding_model = None
        self._init_embedding_model()

    def _init_embedding_model(self):
        """初始化Embedding模型（Ollama bge-m3）"""
        try:
            try:
                from langchain_ollama import OllamaEmbeddings
            except ImportError:
                from langchain_community.embeddings import OllamaEmbeddings
            self.embedding_model = OllamaEmbeddings(
                base_url=settings.OLLAMA_BASE_URL,
                model=settings.EMBEDDING_MODEL
            )
            logger.info(f"Embedding模型初始化成功: {settings.EMBEDDING_MODEL}")
        except Exception as e:
            logger.warning(f"Embedding模型初始化失败: {str(e)}")
            self.embedding_model = None

    def _embed(self, text: str) -> List[float]:
        """文本向量化"""
        if not self.embedding_model:
            raise RuntimeError("Embedding模型未初始化")
        return self.embedding_model.embed_query(text)

    def _run(self, coro):
        """运行异步Milvus操作（兼容同步调用）"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 已在事件循环中，使用新线程运行
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    return pool.submit(lambda: asyncio.run(coro)).result()
            return loop.run_until_complete(coro)
        except RuntimeError:
            return asyncio.run(coro)

    # ==================== 岗位需求向量 ====================

    def create_job_position_vector(
        self,
        position_id: int,
        text: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[int]:
        """创建岗位需求向量"""
        try:
            from app.core.milvus_client import MilvusService

            vector = self._embed(text)
            collection = MilvusService(settings.MILVUS_COLLECTION_JOB)

            metadata = metadata or {}
            ts = int(__import__("time").time())
            # 注意：MilvusService.insert(embeddings, metadata) 内部已把 embeddings
            # 作为第一列拼入，row 不能再带 embedding（否则列数多 1 → DataNotMatchException）
            row = {
                "position_id": str(position_id),
                "position_text": text[:65535],
                "position_name": str(metadata.get("position_name", ""))[:256],
                "department": str(metadata.get("department_id", ""))[:256],
                "business_scene": "job_position",
                "created_at": ts
            }

            ids = self._run(collection.insert([vector], [row]))
            return ids[0] if ids else None

        except Exception as e:
            logger.warning(f"创建岗位向量失败: {str(e)}")
            return None

    def update_job_position_vector(self, position_id: int, text: str) -> Optional[int]:
        """更新岗位需求向量（先删除旧向量，再插入新向量）"""
        try:
            from app.core.milvus_client import MilvusService

            collection = MilvusService(settings.MILVUS_COLLECTION_JOB)
            try:
                self._run(collection.delete(f"position_id == '{position_id}'"))
            except Exception:
                pass

            return self.create_job_position_vector(position_id, text)

        except Exception as e:
            logger.warning(f"更新岗位向量失败: {str(e)}")
            return None

    def search_job_positions(
        self,
        query_text: str,
        filters: Optional[Dict[str, Any]] = None,
        top_k: int = 10
    ) -> List[Dict[str, Any]]:
        """搜索岗位（向量语义检索）"""
        try:
            from app.core.milvus_client import MilvusService

            query_vector = self._embed(query_text)
            collection = MilvusService(settings.MILVUS_COLLECTION_JOB)

            expr = None
            if filters:
                conditions = []
                if filters.get("department_id"):
                    conditions.append(f"department == '{filters['department_id']}'")
                if conditions:
                    expr = " and ".join(conditions)

            results = self._run(collection.search(
                query_embedding=query_vector,
                top_k=top_k,
                expr=expr,
                output_fields=["position_id", "position_name", "department"]
            ))

            return [
                {
                    "id": r.get("position_id"),
                    "score": r.get("score", 0),
                    "position_name": r.get("position_name"),
                    "department": r.get("department")
                }
                for r in results
            ]

        except Exception as e:
            logger.warning(f"岗位向量搜索失败: {str(e)}")
            return []

    # ==================== 人才简历向量 ====================

    def create_talent_resume_vector(
        self,
        talent_id: int,
        text: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[int]:
        """创建人才简历向量"""
        try:
            from app.core.milvus_client import MilvusService

            vector = self._embed(text)
            collection = MilvusService(settings.MILVUS_COLLECTION_TALENT)

            metadata = metadata or {}
            ts = int(__import__("time").time())
            # 注意：MilvusService.insert(embeddings, metadata) 内部已把 embeddings
            # 作为第一列拼入，row 不能再带 embedding（否则列数多 1 → DataNotMatchException）
            row = {
                "talent_id": str(talent_id),
                "resume_text": text[:65535],
                "chunk_id": str(metadata.get("chunk_id", f"t{talent_id}")),
                "file_id": str(metadata.get("file_id", "")),
                "file_name": str(metadata.get("file_name", ""))[:512],
                "business_scene": "talent_resume",
                "created_at": ts
            }

            ids = self._run(collection.insert([vector], [row]))
            return ids[0] if ids else None

        except Exception as e:
            logger.warning(f"创建人才简历向量失败: {str(e)}")
            return None

    def search_matching_talents(
        self,
        query_text: str,
        top_k: int = 10,
        expr: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """语义检索匹配人才"""
        try:
            from app.core.milvus_client import MilvusService

            query_vector = self._embed(query_text)
            collection = MilvusService(settings.MILVUS_COLLECTION_TALENT)

            results = self._run(collection.search(
                query_embedding=query_vector,
                top_k=top_k,
                expr=expr,
                output_fields=["talent_id", "file_name"]
            ))

            return [
                {
                    "id": r.get("talent_id"),
                    "score": r.get("score", 0),
                    "file_name": r.get("file_name")
                }
                for r in results
            ]

        except Exception as e:
            logger.warning(f"人才向量搜索失败: {str(e)}")
            return []


# 全局实例（FastAPI启动时初始化；无Milvus时实例化会失败，由调用方catch）
try:
    vector_search_service = VectorSearchService()
except Exception as e:
    logger.warning(f"全局向量检索服务初始化失败: {str(e)}")
    vector_search_service = None
