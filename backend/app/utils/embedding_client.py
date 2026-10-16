# -*- coding: utf-8 -*-
"""
Embedding 客户端（参考 large_health_reference/app/utils/embedding_client.py）。
统一 embedding 调用入口，支持 Ollama bge-m3 / nomic，支持多模型路由。
"""
import logging
import time
from typing import List, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

# 缓存：避免同一文本重复请求 embedding（进程内短生命周期缓存）
_EMBEDDING_CACHE: dict[str, List[float]] = {}
_CACHE_MAX_SIZE = 500


def _cache_key(text: str) -> str:
    """简单缓存 key（文本过长则截断）"""
    return text[:512]


def get_embedding(
    text: str,
    model: Optional[str] = None,
    use_cache: bool = True,
) -> Optional[List[float]]:
    """
    获取文本的 embedding 向量（同步版本，对标参考 async 实现）。
    策略：Ollama bge-m3（默认）/ nomic（可选），失败返回 None（上层降级）。

    参数:
        text: 待向量化的文本
        model: 模型名，默认从 settings.EMBEDDING_MODEL 读取
        use_cache: 是否使用进程内缓存（默认开启，节省 Ollama 请求）
    返回:
        List[float]: 1024 维向量，失败返回 None
    """
    if not text or not text.strip():
        return None

    model = model or settings.EMBEDDING_MODEL
    cache_key = _cache_key(text)

    # 缓存命中
    if use_cache and cache_key in _EMBEDDING_CACHE:
        return _EMBEDDING_CACHE[cache_key]

    # LRU 淘汰（缓存满时清最老的 20%）
    if len(_EMBEDDING_CACHE) >= _CACHE_MAX_SIZE:
        for k in list(_EMBEDDING_CACHE.keys())[: __CACHE_MAX_SIZE // 5]:
            del _EMBEDDING_CACHE[k]

    try:
        import urllib.request
        import json

        payload = json.dumps({
            "model": model,
            "prompt": text,
            "stream": False,
        }).encode("utf-8")

        # Ollama embedding 专用端点（/api/embeddings，返回 {embedding: [...]}）
        req = urllib.request.Request(
            f"{settings.OLLAMA_BASE_URL}/api/embeddings",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=getattr(settings, "OLLAMA_EMBED_TIMEOUT", 60)) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            embedding = result.get("embedding", [])

            if not isinstance(embedding, list) or len(embedding) == 0:
                logger.warning(f"Ollama embedding 为空，model={model}")
                return None

            vec = embedding[:1024]  # 截断/补齐到 1024
            while len(vec) < 1024:
                vec.append(0.0)

            if use_cache:
                _EMBEDDING_CACHE[cache_key] = vec

            return vec

    except Exception as e:
        logger.warning(f"Embedding 请求失败 model={model}: {e}")
        return None


def clear_cache():
    """清空 embedding 缓存（测试/重置用）"""
    global _EMBEDDING_CACHE
    _EMBEDDING_CACHE = {}
    logger.info("Embedding 缓存已清空")
