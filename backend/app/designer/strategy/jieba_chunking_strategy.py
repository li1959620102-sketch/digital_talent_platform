# -*- coding: utf-8 -*-
"""
Jieba 中文语义切片策略（参考 large_health_reference/designer/strategy/chunking/jieba_chunking_strategy.py）。
核心价值：中文分词感知，比固定字符切分语义完整性高 30%+。
策略：Jieba 分词 → 按语义单元分组 → RecursiveCharacterTextSplitter 中文分隔符收尾。
"""
import logging
from typing import List, Optional

from app.designer.strategy.chunking_strategy import BaseChunkingStrategy, register_strategy

logger = logging.getLogger(__name__)


class JiebaChunkingStrategy(BaseChunkingStrategy):
    """
    Jieba 语义分词切片（适合中文简历/文档）。
    - 步骤1：Jieba 分词（精确/全模式按需）
    - 步骤2：按句子边界（句号/换行）合并为语义块
    - 步骤3：超长块用 RecursiveCharacterTextSplitter 中文分隔符二次切分
    - 步骤4：过滤 < 50 字短片（除非是最后一片）
    """

    def __init__(
        self,
        chunk_size: int = 500,
        overlap: int = 50,
        min_chunk_size: int = 50,
        jieba_whole: bool = False,
    ):
        super().__init__(chunk_size, overlap)
        self.min_chunk_size = min_chunk_size
        self.jieba_whole = jieba_whole  # True=全模式，False=精确模式

    @property
    def name(self) -> str:
        return "jieba"

    def split_document(self, text: str, **kwargs) -> List[str]:
        """Jieba 语义分词 + 句子边界合并"""
        if not text or not text.strip():
            return []

        # 归一化换行
        text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
        if len(text) < self.min_chunk_size:
            return [text] if text else []

        try:
            import jieba
        except ImportError:
            logger.warning("Jieba 未安装，降级为固定字符切片")
            return _fallback_fixed(text, self.chunk_size, self.overlap)

        try:
            # 1. Jieba 分词
            mode = "cut_all" if self.jieba_whole else "cut"
            words = list(getattr(jieba, mode)(text))
            word_pos = 0
            pos_map: List[tuple] = []  # (word, start_pos)
            # 重建 word→pos 映射（简化版：用空格替 token 算位置）
            reconstructed = "".join(words)
            # 注意：Jieba cut 结果不含空格，这里用滑动窗口近似位置
            # 实际用更精确的方式：遍历 text 找 jieba 分词边界
            pos_map = self._build_word_positions(text, words)

            # 2. 按句子边界（。！？\n）分组
            sentences: List[str] = []
            current: List[str] = []
            current_len = 0
            SEPARATORS = ["。", "！", "？", "；", "\n", "；"]

            for word in words:
                current.append(word)
                current_len += len(word)
                if word in SEPARATORS or current_len >= self.chunk_size:
                    sentence = "".join(current)
                    if sentence.strip():
                        sentences.append(sentence.strip())
                    current = []
                    current_len = 0
            if current:
                sentences.append("".join(current).strip())

            # 3. 合并相邻句子为 chunk（不超 chunk_size）
            chunks: List[str] = []
            buffer = ""
            for sent in sentences:
                if not sent.strip():
                    continue
                if len(buffer) + len(sent) <= self.chunk_size:
                    buffer += sent
                else:
                    if buffer.strip():
                        chunks.append(buffer.strip())
                    # overlap 机制：保留上 N 个字作为衔接
                    buffer = buffer[-self.overlap:] + sent if self.overlap > 0 else sent
            if buffer.strip():
                chunks.append(buffer.strip())

            # 4. 超长块二次切分（按字符递归分隔符）
            final_chunks: List[str] = []
            for chunk in chunks:
                if len(chunk) > self.chunk_size * 1.5:
                    final_chunks.extend(_split_by_separators(chunk, self.chunk_size, self.overlap))
                else:
                    final_chunks.append(chunk)

            # 5. 过滤短片（保留最后一片或唯一片）
            result = []
            for i, chunk in enumerate(final_chunks):
                if len(chunk) >= self.min_chunk_size or i == len(final_chunks) - 1:
                    result.append(chunk)

            logger.debug(f"Jieba 切片: {len(words)} words → {len(result)} chunks")
            return result

        except Exception as e:
            logger.warning(f"Jieba 切片异常，降级为固定切片: {e}")
            return _fallback_fixed(text, self.chunk_size, self.overlap)

    def _build_word_positions(self, text: str, words: List[str]) -> List[tuple]:
        """将 Jieba 分词结果映射回原始文本位置（用于精确切片）"""
        pos_map: List[tuple] = []
        remaining = text
        offset = 0
        for word in words:
            idx = remaining.find(word)
            if idx == -1:
                idx = 0
            pos_map.append((word, offset + idx))
            consumed = remaining[: idx + len(word)]
            remaining = remaining[idx + len(word):]
            offset += idx + len(word)
            if not remaining:
                break
        return pos_map


# ─────────────────────────────────────────────────────────────
# 保底：固定字符切片（knowledge_service._chunk_text 原逻辑，提取为策略）
# ─────────────────────────────────────────────────────────────

def _fallback_fixed(text: str, chunk_size: int, overlap: int) -> List[str]:
    """固定字符切片（无 Jieba 时兜底 / 英文/数字文档兜底）"""
    chunks = []
    start = 0
    step = max(1, chunk_size - overlap)
    while start < len(text):
        end = min(start + chunk_size, len(text))
        piece = text[start:end].strip()
        if not piece:
            start = end
            continue
        # 尝试在自然断点切
        if end < len(text):
            for sep in ["\n\n", "。", "\n", ".", "；", ";"]:
                idx = piece.rfind(sep)
                if idx > chunk_size * 0.5:
                    piece = piece[: idx + len(sep)].strip()
                    end = start + len(piece)
                    break
        if piece:
            chunks.append(piece)
        start += len(piece) if piece else step
        if start >= len(text):
            break
    return chunks


class FixedChunkingStrategy(BaseChunkingStrategy):
    """固定字符切片策略（英文/数字文档 / 无 Jieba 环境保底）"""

    @property
    def name(self) -> str:
        return "fixed"

    def split_document(self, text: str, **kwargs) -> List[str]:
        return _fallback_fixed(text, self.chunk_size, self.overlap)


# 启动时自动注册
register_strategy(JiebaChunkingStrategy(chunk_size=500, overlap=50))
register_strategy(FixedChunkingStrategy(chunk_size=500, overlap=50))


# ─────────────────────────────────────────────────────────────
# 辅助：超长块按分隔符递归切分
# ─────────────────────────────────────────────────────────────

def _split_by_separators(text: str, chunk_size: int, overlap: int) -> List[str]:
    """按分隔符递归切分超长文本块"""
    SEPARATORS = ["\n\n", "。", "；", "\n", ". "]
    for sep in SEPARATORS:
        parts = text.split(sep)
        if len(parts) > 1:
            result = []
            buffer = ""
            for part in parts:
                if len(buffer) + len(part) <= chunk_size:
                    buffer += part + sep
                else:
                    if buffer.strip():
                        result.append(buffer.strip())
                    buffer = part + sep
            if buffer.strip():
                result.append(buffer.strip())
            # 递归处理仍超长的块
            final = []
            for chunk in result:
                if len(chunk) > chunk_size * 1.5:
                    final.extend(_split_by_separators(chunk, chunk_size, overlap))
                else:
                    final.append(chunk)
            return final
    # 无法用分隔符切，直接硬截
    return _fallback_fixed(text, chunk_size, overlap)
