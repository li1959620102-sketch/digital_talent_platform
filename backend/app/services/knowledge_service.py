"""
知识库 RAG 服务
实现：文件元数据管理、文档切片、向量化入库(Milvus)、语义检索、RAG 问答。
设计原则（遵循项目规则）：
- 主链路：文件→切片→Embedding→Milvus→Retriever→LLM→回答
- 本地无 Milvus/Ollama 时，实例化与服务调用优雅失败（被上层 try/except 捕获），不阻断应用
- RAG 检索前执行权限过滤（permission_level），禁止 AI 越权访问
"""
import os
import time
import uuid
import asyncio
import logging
from typing import List, Dict, Any, Optional

from sqlalchemy.orm import Session
from datetime import datetime

from app.core.config import settings
from app.models.knowledge import KnowledgeFile, KnowledgeChunk
from app.services.rag_search_service import refresh_bm25_index

logger = logging.getLogger(__name__)


def _gen_code(prefix: str) -> str:
    return f"{prefix}{int(time.time()*1000)}{uuid.uuid4().hex[:6].upper()}"


class KnowledgeService:
    """知识库 RAG 服务"""

    def __init__(self):
        self.embedding_model = None
        self._bm25_loaded = False
        self._init_embedding_model()
        self.llm = None
        self._init_llm()

    def _ensure_bm25_index(self, db: Optional[Session] = None) -> None:
        """首次检索时从 MySQL 恢复 BM25，避免索引只存在于导入脚本进程内。"""
        if self._bm25_loaded or db is None:
            return
        try:
            rows = (
                db.query(KnowledgeChunk, KnowledgeFile)
                .join(KnowledgeFile, KnowledgeFile.id == KnowledgeChunk.file_id)
                .filter(KnowledgeChunk.content.is_not(None))
                .all()
            )
            refresh_bm25_index([
                {"id": str(chunk.id), "text": chunk.content or "", "metadata": {
                    "file_id": str(chunk.file_id), "file_name": str(file.file_name),
                    "knowledge_type": file.knowledge_type or "other",
                    "permission_level": int(file.permission_level or 0),
                    "chunk_id": str(chunk.chunk_code),
                }}
                for chunk, file in rows if chunk.content
            ])
            self._bm25_loaded = True
        except Exception as exc:
            logger.warning(f"BM25 索引恢复失败，将继续使用向量检索: {exc}")

    # ==================== 模型初始化 ====================

    def _init_embedding_model(self):
        try:
            try:
                from langchain_ollama import OllamaEmbeddings
            except ImportError:
                from langchain_community.embeddings import OllamaEmbeddings
            self.embedding_model = OllamaEmbeddings(
                base_url=settings.OLLAMA_BASE_URL,
                model=settings.EMBEDDING_MODEL
            )
            logger.info(f"知识库 Embedding 模型初始化成功: {settings.EMBEDDING_MODEL}")
        except Exception as e:
            logger.warning(f"知识库 Embedding 模型初始化失败: {str(e)}")
            self.embedding_model = None

    def _init_llm(self):
        """初始化LLM（RAG问答：SiliconFlow DeepSeek-V4-Flash；降级：Ollama）"""
        try:
            from app.core.llm_factory import get_llm_by_strategy
            strategy = settings.LLM_STRATEGY or "silicon_flow"
            self.llm = get_llm_by_strategy(strategy=strategy, temperature=0.1)
            logger.info(f"知识库 LLM 初始化成功: 策略={strategy}")
        except ValueError as e:
            logger.warning(f"SiliconFlow LLM未配置 ({e})，降级至 Ollama")
            try:
                from langchain_ollama import ChatOllama
                self.llm = ChatOllama(
                    base_url=settings.OLLAMA_BASE_URL,
                    model=settings.LLM_MODEL,
                    temperature=0.1,
                    model_kwargs={"think": False, "num_predict": 600},
                )
            except Exception as e2:
                logger.warning(f"知识库 Ollama LLM 也初始化失败: {e2}")
                self.llm = None
        except Exception as e:
            logger.warning(f"知识库 LLM 初始化失败: {str(e)}")
            self.llm = None

    def _embed(self, text: str) -> List[float]:
        if not self.embedding_model:
            raise RuntimeError("Embedding 模型未初始化")
        return self.embedding_model.embed_query(text)

    def _run(self, coro):
        """运行异步 Milvus 操作（兼容同步调用上下文）"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    return pool.submit(lambda: asyncio.run(coro)).result()
            return loop.run_until_complete(coro)
        except RuntimeError:
            return asyncio.run(coro)

    # ==================== 文件元数据 ====================

    def save_file_metadata(
        self, db: Session, *, file_name: str, file_type: str, file_size: int,
        file_path: str, knowledge_type: str = "other", permission_level: int = 0,
        uploader_id: Optional[int] = None
    ) -> KnowledgeFile:
        """保存上传文件元数据"""
        f = KnowledgeFile(
            file_code=_gen_code("KF"),
            file_name=file_name,
            file_type=file_type,
            file_size=file_size,
            file_path=file_path,
            knowledge_type=knowledge_type,
            permission_level=permission_level,
            uploader_id=uploader_id,
            status="uploaded"
        )
        db.add(f)
        db.commit()
        db.refresh(f)
        return f

    def get_file(self, db: Session, file_id: int) -> Optional[KnowledgeFile]:
        return db.query(KnowledgeFile).filter(KnowledgeFile.id == file_id).first()

    def list_files(
        self,
        db: Session,
        page: int = 1,
        page_size: int = 20,
        knowledge_type: Optional[str] = None,
        max_permission_level: int = 0,
    ):
        q = db.query(KnowledgeFile).filter(
            KnowledgeFile.permission_level <= max_permission_level
        )
        if knowledge_type:
            q = q.filter(KnowledgeFile.knowledge_type == knowledge_type)
        total = q.count()
        items = q.order_by(KnowledgeFile.id.desc()).offset((page-1)*page_size).limit(page_size).all()
        return items, total

    # ==================== 文本切片 ====================

    def _read_text(self, file_path: str) -> str:
        """读取文件文本（txt/md/csv 直接读取；二进制文件尽力而为，不阻断）"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()
        except (UnicodeDecodeError, FileNotFoundError):
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    return f.read()
            except Exception as e:
                logger.warning(f"文本读取失败: {str(e)}")
                return ""

    def _chunk_text(self, text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
        """
        文本切片（策略模式，对齐参考 designer/strategy/chunking_strategy.py）。
        优先 Jieba 语义分词切片，降级固定字符切片。
        参数透传给策略实例（支持 jieba / fixed 策略切换）。
        """
        if not text or not text.strip():
            return []
        text = text.replace("\r\n", "\n").strip()

        # 策略分发：优先 Jieba 中文语义切片，Jieba 不可用则降级 Fixed
        # import 延迟化避免循环（designer 模块依赖 app 层）
        try:
            from app.designer.strategy.chunking_strategy import get_chunking_strategy
            strategy = get_chunking_strategy("jieba", chunk_size=chunk_size, overlap=overlap)
            chunks = strategy.split_document(text)
            if chunks:
                return chunks
        except Exception as e:
            logger.debug(f"Jieba 策略失败，降级固定切片: {e}")

        # 降级：固定字符切片（来自 jieba_chunking_strategy._fallback_fixed）
        from app.designer.strategy.jieba_chunking_strategy import _fallback_fixed
        return _fallback_fixed(text, chunk_size, overlap)

    # ==================== 向量化入库 ====================

    def vectorize_file(self, db: Session, file_id: int) -> Dict[str, Any]:
        """切片 + Embedding + 写入 Milvus 知识库集合，并落库 KnowledgeChunk"""
        f = self.get_file(db, file_id)
        if not f:
            raise ValueError("文件不存在")
        if not self.embedding_model:
            f.status = "failed"
            f.error_msg = "Embedding 模型不可用"
            db.commit()
            return {"success": False, "message": "Embedding 模型不可用"}

        try:
            text = self._read_text(f.file_path)
            chunks = self._chunk_text(text)
            if not chunks:
                f.status = "failed"
                f.error_msg = "无有效文本内容"
                db.commit()
                return {"success": False, "message": "无有效文本内容"}

            # 先清理旧切片
            old = db.query(KnowledgeChunk).filter(KnowledgeChunk.file_id == file_id).all()
            for c in old:
                db.delete(c)
            db.commit()

            from app.core.milvus_client import MilvusService
            collection = MilvusService(settings.MILVUS_COLLECTION_KNOWLEDGE)

            # 幂等修复（2026-10-15）：Milvus 不会随 MySQL 切片重建而自动清除旧向量。
            # 原实现只删 KnowledgeChunk 行、不删 Milvus 实体，重复向量化会在同一
            # file_id 下叠加多份向量（实测重复执行一次后 73 条分块变成 146 条向量）。
            # 插入前先按 file_id 物理删除旧向量，保证与 MySQL 切片一一对应。
            try:
                # 按非主键字段删除需集合已加载，先确保加载（幂等，失败不阻断）
                try:
                    self._run(collection.load())
                except Exception:
                    pass
                deleted = self._run(collection.delete(f'file_id == "{file_id}"'))
                if deleted:
                    logger.info(f"向量化前清理旧向量 file_id={file_id}: 删除 {deleted} 条")
            except Exception as del_err:
                logger.warning(f"清理旧向量失败（继续执行插入）: {del_err}")

            vectors, metas, chunk_objs = [], [], []
            ts = int(time.time())
            for i, piece in enumerate(chunks):
                vec = self._embed(piece)
                code = _gen_code("KC")
                chunk = KnowledgeChunk(
                    chunk_code=code,
                    file_id=file_id,
                    chunk_index=i,
                    content=piece,
                    embedding_status="pending"
                )
                db.add(chunk)
                db.flush()
                chunk_objs.append((chunk, vec, code))
                metas.append({
                    "knowledge_text": piece[:65535],
                    "knowledge_type": f.knowledge_type or "other",
                    "file_id": str(file_id),
                    "file_name": str(f.file_name)[:512],
                    "chunk_id": code[:128],
                    "business_scene": "knowledge_base",
                    "permission_level": int(f.permission_level or 0),
                    "created_at": ts
                })
                vectors.append(vec)

            ids = self._run(collection.insert(vectors, metas))
            for (chunk, _vec, _code), mid in zip(chunk_objs, ids):
                chunk.vector_id = str(mid)
                chunk.embedding_status = "vectorized"
            db.commit()

            f.chunk_count = len(chunks)
            f.status = "vectorized"
            db.commit()

            # A4: 刷新 BM25 索引（向量入库后自动更新）
            try:
                all_chunks = db.query(KnowledgeChunk).filter(
                    KnowledgeChunk.file_id == file_id
                ).order_by(KnowledgeChunk.chunk_index).all()
                refresh_bm25_index([
                    {"id": str(c.id), "text": c.content,
                     "metadata": {"file_name": str(f.file_name),
                                   "knowledge_type": f.knowledge_type or "other",
                                   "permission_level": int(f.permission_level or 0),
                                   "chunk_id": str(c.chunk_code)}}
                    for c in all_chunks
                ])
            except Exception as bm25_err:
                logger.warning(f"BM25 索引刷新失败: {bm25_err}")

            return {"success": True, "chunk_count": len(chunks)}
        except Exception as e:
            db.rollback()
            f.status = "failed"
            f.error_msg = str(e)
            db.commit()
            logger.error(f"向量化失败 file_id={file_id}: {str(e)}")
            return {"success": False, "message": str(e)}

    def _remove_milvus_vectors(self, file_id: int) -> None:
        """从 Milvus knowledge_base 集合删除某文件的所有向量（同步可靠）。

        Milvus 中按 file_id 标量字段过滤删除；文件删除时 DB 记录已删，
        若 Milvus 清理失败会导致"孤儿向量"，本方法尽力清理且绝不阻断主流程。
        """
        try:
            from app.core.milvus_client import MilvusService
            collection = MilvusService(settings.MILVUS_COLLECTION_KNOWLEDGE)
            expr = f'file_id == "{str(file_id)}"'
            self._run(collection.delete(expr))
            logger.info(f"[知识库] 已清理 Milvus 中 file_id={file_id} 的向量")
        except Exception as e:
            logger.warning(f"[知识库] 清理 Milvus file_id={file_id} 向量失败(可忽略): {e}")

    def delete_file_vectors(self, db: Session, file_id: int) -> int:
        """删除知识文件的同时清理向量（DB chunks + Milvus），返回删除的 chunk 数。

        供文件删除接口统一调用，保证 MySQL 与 Milvus 对齐，不产生孤儿向量。
        """
        deleted = 0
        # 1) 删 MySQL chunk
        try:
            chunks = db.query(KnowledgeChunk).filter(KnowledgeChunk.file_id == file_id).all()
            for c in chunks:
                db.delete(c)
                deleted += 1
            db.commit()
        except Exception as e:
            db.rollback()
            logger.warning(f"[知识库] 删除 DB chunk file_id={file_id} 失败: {e}")
        # 2) 清 Milvus 向量
        self._remove_milvus_vectors(file_id)
        return deleted

    # ==================== 语义检索 ====================

    def search(self, query: str, top_k: int = 5, permission_level: int = 999, db: Optional[Session] = None) -> List[Dict[str, Any]]:
        """语义检索知识库（带权限过滤）"""
        if not self.embedding_model:
            return []
        try:
            from app.core.milvus_client import MilvusService
            qvec = self._embed(query)
            collection = MilvusService(settings.MILVUS_COLLECTION_KNOWLEDGE)
            expr = f"permission_level <= {int(permission_level)}"
            results = self._run(collection.search(
                query_embedding=qvec,
                top_k=top_k,
                expr=expr,
                output_fields=["knowledge_text", "file_name", "knowledge_type", "chunk_id"]
            ))
            return [
                {
                    "score": r.get("score", 0),
                    "content": r.get("knowledge_text", ""),
                    "file_name": r.get("file_name", ""),
                    "knowledge_type": r.get("knowledge_type", ""),
                    "chunk_id": r.get("chunk_id", "")
                }
                for r in results
            ]
        except Exception as e:
            logger.warning(f"知识库检索失败: {str(e)}")
            return []

    # ==================== RAG 问答 ====================

    def _ollama_chat(self, prompt: str, max_tokens: int = 256, seed: int = 42) -> str:
        """直连 Ollama /api/chat（绕过 langchain，确保 think:false 透传至请求顶层，关闭 qwen3 思考链）。
        加 seed 锁随机性：相同 query 返回稳定答案，避免"第一次答非所问第二次正确"。"""
        import json
        import urllib.request
        url = f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/chat"
        payload = {
            "model": settings.LLM_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "think": False,
            "options": {
                "temperature": 0.0,  # 关闭采样
                "num_predict": max_tokens,
                "seed": seed,  # 锁随机种子
            },
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=settings.OLLAMA_CHAT_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data.get("message", {}).get("content", "")

    def qa(self, query: str, permission_level: int = 999, top_k: int = 5, db: Optional[Session] = None) -> Dict[str, Any]:
        """
        RAG 问答：检索 → 拼接上下文 → LLM 生成答案（带来源追溯）
        防"答非所问"：检索结果与问题相似度过低 → 直接告知"未找到相关知识"，
        避免 LLM 在错误上下文中硬造答案。
        """
        self._ensure_bm25_index(db)
        contexts = self.search(query, top_k=top_k, permission_level=permission_level, db=db)
        # 相似度阈值：仅用于过滤"完全无关的噪声"。
        # 实测（2026-09-05）：当前 embedding 模型的 cosine 分数集中在 0.24~0.52，
        # 且与语义相关性弱相关（"岗位匹配"这类高相关问题反而只有 0.35，
        # 而"请休假几天"这类无关问题却有 0.51）。因此阈值必须设得很低，
        # 真正判断"答非所问"交给下游的关键词重叠启发式 + LLM 显式声明。
        SIMILARITY_THRESHOLD = 0.2
        relevant_contexts = [c for c in contexts if c.get("score", 0) >= SIMILARITY_THRESHOLD]
        if not relevant_contexts:
            # 没找到任何知识片段（知识库空 / 检索服务不可用）
            return {
                "answer": "未检索到与您问题相关的知识库内容。可以换个更具体的说法，或到知识文件页面补充相关文档。",
                "sources": []
            }
        contexts = relevant_contexts
        # 二次重排：按 query 与 chunk 内容的关键词重叠度把最相关的 chunk 放到 prompt 最前，
        # 解决"向量召回相近但 LLM 选错了参考文档"导致的答非所问。
        contexts = _rerank_by_keyword_overlap(query, contexts)
        context_text = "\n\n".join(
            f"[来源{idx+1}] {c['file_name']}：{c['content']}" for idx, c in enumerate(contexts)
        )
        prompt = (
            "你是企业人才管理平台的智能知识助手。请仅基于以下知识库内容回答问题，"
            "若知识库未包含与用户问题直接相关的信息，请明确回答未找到相关知识，不要编造或臆测。"
            "回答需简洁、准确，不超过120字，并标注引用来源编号。\n\n"
            f"【知识库内容】\n{context_text}\n\n【用户问题】\n{query}\n\n【回答】"
        )
        # 知识问答固定走本地 RAG（Milvus 向量检索 + Ollama 本地 LLM）。
        # 说明：此前这里会尝试 dify_adapter.completion()，但其使用的是全局 DIFY_API_KEY，
        # 指向另一个项目的 text2echarts(advanced-chat) 应用，与人才平台知识库无关，每次调用
        # 必然失败后静默回退本地，仅产生误导性日志。人才平台 Dify 未为知识问答建立 RAG 应用，
        # 故不再走 Dify。如未来要在 Dify 建知识库问答应用，需配独立 QA app key 并在此接入。
        answer = ""
        try:
            answer = self._ollama_chat(prompt)
            if not answer or not answer.strip():
                answer = "（LLM 返回为空，仅返回检索到的知识片段）\n" + context_text
            # 兜底：LLM 可能在没匹配时仍硬造答案（返回"岗位匹配是..."类答非所问），
            # 若答案中包含明显的"答非所问"标志（前缀重复出现的检索词+问号话题外的内容）
            # 这里仅做最基础的防御：检测是否提到了与问题完全无关的核心词
            if _looks_unrelated_answer(query, answer):
                return {
                    "answer": "未检索到与您问题相关的知识库内容。可以换个更具体的说法，或到知识文件页面补充相关文档。",
                    "sources": _dedup_sources_by_file([
                        {"file_name": c["file_name"], "knowledge_type": c["knowledge_type"], "score": round(c["score"], 4)}
                        for c in contexts
                    ])
                }
        except Exception as e:
            logger.warning(f"RAG 问答 LLM 调用失败: {str(e)}")
            answer = "（LLM 调用失败，仅返回检索到的知识片段）\n" + context_text

        return {
            "answer": answer,
            # 按 file_name 去重：同一文档被切片成多段只会展示一次来源
            "sources": _dedup_sources_by_file([
                {
                    "file_name": c["file_name"],
                    "knowledge_type": c["knowledge_type"],
                    "score": round(c["score"], 4),
                }
                for c in contexts
            ])
        }


def _looks_unrelated_answer(query: str, answer: str) -> bool:
    """
    检测：LLM 是否在错误上下文中硬造答案（答非所问）。

    实测背景（2026-09-05）：
    - 当前 embedding 的 cosine 分数与语义相关性弱相关，靠分数阈值判断不可靠；
    - 但"query 与 answer 是否有共享实义词"是稳定有效的信号：
      · "请休假几天？" → LLM 答"岗位匹配算法…"，零重叠 → 判定答非所问 ✓
      · "岗位匹配是怎么算的？" → LLM 答"硬条件过滤…技能重叠…"，有重叠 → 放行 ✓

    判定规则（二选一命中即视为答非所问）：
    1. query 的实义词在 answer 中"一个都没出现"；
    2. query 与 answer 的实义词重叠率 < 15%（且 query 至少有 2 个实义词）。
    """
    if not query or not answer:
        return False
    import re as _re
    STOP = {
        "什么", "怎么", "如何", "哪个", "哪些", "这个", "那个", "请", "我", "你", "的",
        "是", "了", "有", "在", "和", "与", "为", "对", "可", "可以", "需要",
        "能", "想", "了解", "一下", "请问", "你好", "吗", "呢", "啊", "多少",
        "有没有", "会不会", "是否", "以及", "或者", "一个", "一些", "怎样",
    }
    # 抽取中/英文数字实义词（中文取 2 字词更能体现语义）
    def words(text: str) -> set:
        zh = _re.findall(r"[\u4e00-\u9fff]+", text)
        en = _re.findall(r"[A-Za-z0-9]+", text)
        ws = set()
        for seg in zh:
            # 中文按 2 字滑窗切词（无 jieba 依赖的轻量方案）
            for i in range(len(seg) - 1):
                ws.add(seg[i:i + 2])
        for e in en:
            ws.add(e.lower())
        return {w for w in ws if w not in STOP and len(w) >= 2}

    q_set = words(query)
    a_set = words(answer)
    if not q_set:
        return False
    overlap = q_set & a_set
    # 规则1：完全零重叠 → 答非所问
    if len(overlap) == 0:
        return True
    # 规则2：重叠率过低（query 实义词 ≥4 个时才启用，避免误伤短问题）
    if len(q_set) >= 4 and len(overlap) / len(q_set) < 0.15:
        return True
    return False


# 中文常用停用词（重排时不计入关键词匹配，避免噪音）
_RERANK_STOPWORDS = {"的", "是", "在", "和", "与", "或", "了", "吗", "呢", "啊", "怎么", "如何",
                      "什么", "哪些", "这个", "那个", "请", "我", "你", "他", "她", "我们", "你们",
                      "可以", "能", "想", "需要", "问", "说", "话", "的", "地", "得", "把", "让", "给",
                      "做", "是", "有", "为", "了", "一下", "一下", "请问", "你好", "吗", "如何"}


def _rerank_by_keyword_overlap(query: str, contexts: list) -> list:
    """
    按 query 与 chunk 内容的关键词重叠度重排，让最相关的 chunk 排最前。
    解决向量召回相近但 LLM 选了错误参考文档导致的"答非所问"。
    重排分数 = cosine_score + 关键词重叠率 * 0.1（小幅加权，避免覆盖向量召回主排序）
    """
    import re as _re
    # 提取 query 关键词（中文 1-3 字 + 英文/数字词）
    q_words = set(w for w in _re.findall(r"[\u4e00-\u9fff]{1,3}|[A-Za-z0-9]+", query or "")
                  if w not in _RERANK_STOPWORDS and len(w) > 0)
    if not q_words or not contexts:
        return contexts
    reranked = []
    for ctx in contexts:
        content = ctx.get("content", "") or ""
        c_words = set(_re.findall(r"[\u4e00-\u9fff]{1,3}|[A-Za-z0-9]+", content))
        c_words = {w for w in c_words if w not in _RERANK_STOPWORDS}
        overlap = len(q_words & c_words)
        overlap_rate = overlap / max(len(q_words), 1)
        # 保留原 score + 关键词加权
        base = float(ctx.get("score", 0) or 0)
        ctx["_rerank_score"] = base + overlap_rate * 0.1
        reranked.append(ctx)
    reranked.sort(key=lambda x: x.get("_rerank_score", 0), reverse=True)
    return reranked


def _dedup_sources_by_file(sources: list) -> list:
    """
    按 file_name 去重来源列表，并聚合每个文件的命中分（取最高分）。
    解决："同一文档被切片成多段"导致来源区显示重复文件名的体验问题。
    """
    bucket: Dict[str, Dict[str, Any]] = {}
    for s in sources:
        fn = s.get("file_name") or "(未知文档)"
        if fn not in bucket:
            bucket[fn] = dict(s)
            bucket[fn]["hit_chunks"] = 1
        else:
            # 累计切片命中数
            bucket[fn]["hit_chunks"] = int(bucket[fn].get("hit_chunks", 1)) + 1
            # 取最高 score 作为代表分
            try:
                if float(s.get("score", 0)) > float(bucket[fn].get("score", 0)):
                    bucket[fn]["score"] = round(float(s["score"]), 4)
            except (TypeError, ValueError):
                pass
    # 按 score 降序，文件越相关越靠前
    return sorted(bucket.values(), key=lambda x: float(x.get("score") or 0), reverse=True)
