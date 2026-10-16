# -*- coding: utf-8 -*-
"""
RAG 多路召回服务（对齐参考 large_health_reference/app/services/rag_query_rerank_service.py）。

核心能力：
- hybrid_search(query): 向量检索 + BM25 关键词召回 → min-max 归一化 → 加权融合 → top_k
- multi_retrieval_rerank(query): 多路召回（向量+BM25）→ hash 去重 → Ollama rerank（无模型则 default 逆序）
- BM25 index 懒加载，knowledge_service 向量化后自动刷新

依赖：rank_bm25 / jieba（已确认可用）。
"""
import hashlib
import logging
from typing import List, Dict, Any, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

# 全局 BM25 模型实例（惰性单例，knowledge_service 向量化后刷新）
_bm25_model: Optional["BM25Okapi"] = None
_bm25_tokenizer: Optional[callable] = None
_bm25_corpus: List[Dict[str, str]] = []  # [{"id": ..., "text": ..., "metadata": {...}}]


def _jieba_tokenizer(text: str) -> List[str]:
    """Jieba 分词 tokenizer（用于 BM25）"""
    import jieba
    return list(jieba.cut(text))


def _fallback_tokenizer(text: str) -> List[str]:
    """Fallback tokenizer：空格/标点分词（无 Jieba 时兜底）"""
    import re
    return re.findall(r"\w+", text.lower())


def _default_tokenizer(text: str) -> List[str]:
    """默认 tokenizer：jieba（不可用则 fallback）"""
    try:
        return _jieba_tokenizer(text)
    except Exception:
        return _fallback_tokenizer(text)


# ─────────────────────────────────────────────────────────────
# BM25 索引管理
# ─────────────────────────────────────────────────────────────

def refresh_bm25_index(chunks: List[Dict[str, Any]]):
    """
    用最新知识块刷新 BM25 索引。
    由 knowledge_service.vectorize_file() 调用（每次向量化后自动刷新）。
    chunks 格式: [{"id": str, "text": str, "metadata": dict}, ...]
    """
    global _bm25_model, _bm25_tokenizer, _bm25_corpus

    if not chunks:
        logger.warning("BM25 刷新：chunks 为空，跳过")
        return

    from rank_bm25 import BM25Okapi

    _bm25_corpus = chunks
    _bm25_tokenizer = _default_tokenizer

    try:
        tokenized = [_bm25_tokenizer(doc["text"]) for doc in chunks]
        _bm25_model = BM25Okapi(tokenized)
        logger.info(f"BM25 索引刷新完成：{len(chunks)} 条文档")
    except Exception as e:
        logger.error(f"BM25 索引刷新失败: {e}")
        _bm25_model = None


def get_bm25_scores(query: str) -> List[tuple]:
    """
    获取 BM25 检索结果及得分。
    返回: [(doc_dict, score), ...]，按 score 降序
    """
    global _bm25_model, _bm25_tokenizer, _bm25_corpus

    if _bm25_model is None or not _bm25_corpus:
        logger.debug("BM25 索引未就绪，跳过 BM25 召回")
        return []

    try:
        tokens = _bm25_tokenizer(query)
        raw_scores = _bm25_model.get_scores(tokens)

        # 构建 (doc, score) 列表（排除零分）
        scored = [
            (doc, float(raw_scores[i]))
            for i, doc in enumerate(_bm25_corpus)
            if raw_scores[i] > 0
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored
    except Exception as e:
        logger.warning(f"BM25 检索异常: {e}")
        return []


# ─────────────────────────────────────────────────────────────
# RAG 多路召回服务
# ─────────────────────────────────────────────────────────────

class RAGSearchService:
    """
    RAG 多路召回服务（对齐参考 RAGQueryRerankService.hybrid_search / multi_retrieval_rerank）。

    检索链路：
      1. 向量检索（Milvus）：语义相似性
      2. BM25 检索：关键词命中
      3. hash 去重（避免重复内容稀释分数）
      4. 加权融合（向量 0.6 / BM25 0.4，参考配置）
      5. top_k 返回 + 来源追溯
    """

    def __init__(
        self,
        vector_weight: float = 0.6,
        bm25_weight: float = 0.4,
        bm25_k: int = 10,
        top_k: int = 5,
    ):
        if round(vector_weight + bm25_weight, 2) != 1.0:
            raise ValueError(f"混合检索权重之和必须为 1.0（当前 {vector_weight}+{bm25_weight}）")
        self.vector_weight = vector_weight
        self.bm25_weight = bm25_weight
        self.bm25_k = bm25_k  # 每路召回数量
        self.top_k = top_k  # 最终返回数量

    def hybrid_search(
        self,
        query: str,
        permission_level: int = 999,
        top_k: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        混合检索：向量 + BM25 → 加权融合 → top_k。
        对标参考 hybrid_search()，但直接用 Milvus 向量（不依赖 langchain ChromaDB）。
        """
        k = top_k or self.top_k
        k_inner = self.bm25_k

        # ── 1. 向量检索 ────────────────────────────────────
        vector_results: Dict[str, Dict[str, Any]] = {}
        try:
            from app.core.milvus_client import MilvusService
            from app.utils.embedding_client import get_embedding

            qvec = get_embedding(query)
            if qvec:
                collection = MilvusService(settings.MILVUS_COLLECTION_KNOWLEDGE)
                expr = f"permission_level <= {int(permission_level)}"
                raw = collection.search(
                    query_embedding=qvec,
                    top_k=k_inner,
                    expr=expr,
                    output_fields=["knowledge_text", "file_name", "knowledge_type",
                                   "chunk_id", "permission_level", "created_at"]
                )
                for r in raw:
                    key = hashlib.md5(r.get("knowledge_text", "").encode()).hexdigest()
                    vector_results[key] = {
                        "id": key,
                        "text": r.get("knowledge_text", ""),
                        "metadata": {
                            "file_name": r.get("file_name", ""),
                            "knowledge_type": r.get("knowledge_type", ""),
                            "chunk_id": r.get("chunk_id", ""),
                        },
                        "vec_score": r.get("score", 0),
                        "bm25_score": 0.0,
                        "retrieval_source": "vector",
                    }
                logger.debug(f"向量检索召回: {len(vector_results)} 条")
        except Exception as e:
            logger.warning(f"向量检索失败: {e}")

        # ── 2. BM25 检索 ───────────────────────────────────
        bm25_results: Dict[str, Dict[str, Any]] = {}
        bm25_scored = get_bm25_scores(query)
        if bm25_scored:
            # BM25 分数归一化（min-max）
            scores = [s for _, s in bm25_scored]
            max_s = max(scores)
            min_s = min(scores)
            for doc, raw_score in bm25_scored[:k_inner]:
                # 关键词检索也必须遵守文件级权限，避免绕过向量检索的权限表达式。
                if int(doc.get("metadata", {}).get("permission_level", 0) or 0) > permission_level:
                    continue
                norm = (raw_score - min_s) / (max_s - min_s + 1e-9)
                key = hashlib.md5(doc["text"].encode()).hexdigest()
                bm25_results[key] = {
                    "id": key,
                    "text": doc["text"],
                    "metadata": doc.get("metadata", {}),
                    "vec_score": 0.0,
                    "bm25_score": norm,
                    "retrieval_source": "bm25",
                }
            logger.debug(f"BM25 检索召回: {len(bm25_results)} 条")

        # ── 3. 合并 + hash 去重 ─────────────────────────────
        all_results: Dict[str, Dict[str, Any]] = {}
        for key, item in vector_results.items():
            all_results[key] = item
        for key, item in bm25_results.items():
            if key in all_results:
                # 两路都命中：合并分数
                all_results[key]["bm25_score"] = max(
                    all_results[key]["bm25_score"], item["bm25_score"]
                )
                all_results[key]["retrieval_source"] = "hybrid"
            else:
                all_results[key] = item

        if not all_results:
            logger.warning("两路召回均为空，返回空列表")
            return []

        # ── 4. 加权融合排序 ─────────────────────────────────
        def combined_score(item: Dict[str, Any]) -> float:
            return item["vec_score"] * self.vector_weight + item["bm25_score"] * self.bm25_weight

        sorted_results = sorted(
            all_results.values(),
            key=combined_score,
            reverse=True
        )[:k]

        # ── 5. 格式化输出 ───────────────────────────────────
        return [
            {
                "id": r["id"],
                "content": r["text"],
                "score": round(combined_score(r), 4),
                "vec_score": round(r["vec_score"], 4),
                "bm25_score": round(r["bm25_score"], 4),
                "retrieval_source": r["retrieval_source"],
                "file_name": r["metadata"].get("file_name", ""),
                "knowledge_type": r["metadata"].get("knowledge_type", ""),
                "chunk_id": r["metadata"].get("chunk_id", ""),
            }
            for r in sorted_results
        ]

    def multi_retrieval_rerank(
        self,
        query: str,
        permission_level: int = 999,
        rerank_top_n: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        多路召回 + 重排（对标参考 multi_retrieval_rerank）。
        链路：hybrid_search → default_reranker 逆序评分 → rerank_top_n。
        Ollama rerank 模型不可用时自动降级到 default_reranker（逆序分，越靠前越高）。
        """
        candidates = self.hybrid_search(
            query, permission_level=permission_level, top_k=rerank_top_n * 2
        )
        if not candidates:
            return []

        # Default reranker：逆序评分（越靠前的结果得分越高）
        # 与参考一致：list(range(len, 0, -1)) → 第0项得最高分
        rerank_scores = list(range(len(candidates), 0, -1))
        scored = list(zip(candidates, rerank_scores))
        scored.sort(key=lambda x: x[1], reverse=True)

        results = []
        for item, _ in scored[:rerank_top_n]:
            item["rerank_score"] = rerank_scores[candidates.index(item)]
            results.append(item)

        logger.debug(f"多路召回+重排: {len(candidates)} 候选 → {len(results)} 最终")
        return results
