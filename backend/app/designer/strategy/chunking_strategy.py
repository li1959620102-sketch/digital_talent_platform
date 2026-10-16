# -*- coding: utf-8 -*-
"""
文本切片策略接口与注册表（参考 large_health_reference/app/designer/strategy/chunking_strategy.py）。
Protocol 模式 + 运行时注入，使 knowledge_service 可按文档类型切换切片逻辑。
"""
import logging
from abc import ABC, abstractmethod
from typing import List, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class ChunkingStrategy(Protocol):
    """
    切片策略 Protocol（对标参考 ChunkingStrategy interface）。
    实现类必须实现 split_document(text: str, **kwargs) -> List[str]。
    """
    @property
    def name(self) -> str:
        """策略名称，用于注册表 key"""
        ...

    def split_document(self, text: str, **kwargs) -> List[str]:
        """
        将文档文本切分为多个语义块。
        返回: List[str]，每个元素为一个语义完整的文本块
        """
        ...


class BaseChunkingStrategy(ABC):
    """切片策略基类（可选基类，提供通用参数解析）"""

    def __init__(self, chunk_size: int = 500, overlap: int = 50):
        self.chunk_size = chunk_size
        self.overlap = overlap

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def split_document(self, text: str, **kwargs) -> List[str]:
        ...


# ─────────────────────────────────────────────────────────────
# 注册表（全局策略实例缓存）
# ─────────────────────────────────────────────────────────────

_STRATEGY_REGISTRY: dict[str, ChunkingStrategy] = {}


def register_strategy(strategy: ChunkingStrategy) -> None:
    """将策略实例注册到全局注册表（启动时调用）"""
    _STRATEGY_REGISTRY[strategy.name] = strategy
    logger.debug(f"切片策略已注册: {strategy.name}")


def get_chunking_strategy(name: str, **init_kwargs) -> ChunkingStrategy:
    """
    获取指定名称的策略实例。
    若未注册，则尝试延迟导入（支持运行时动态注册）。
    """
    if name in _STRATEGY_REGISTRY:
        return _STRATEGY_REGISTRY[name]

    # 延迟导入已知策略（支持注册表外置场景）
    KNOWN_STRATEGIES = {
        "jieba": ("app.designer.strategy.jieba_chunking_strategy", "JiebaChunkingStrategy"),
        "fixed": ("app.designer.strategy.fixed_chunking_strategy", "FixedChunkingStrategy"),
        "recursive": ("app.designer.strategy.fixed_chunking_strategy", "RecursiveCharacterChunkingStrategy"),
    }
    if name in KNOWN_STRATEGIES:
        module_path, cls_name = KNOWN_STRATEGIES[name]
        import importlib
        mod = importlib.import_module(module_path)
        cls = getattr(mod, cls_name)
        instance = cls(**init_kwargs) if init_kwargs else cls()
        _STRATEGY_REGISTRY[name] = instance
        logger.debug(f"切片策略懒加载注册: {name}")
        return instance

    logger.warning(f"未知切片策略 '{name}'，降级为 fixed 策略")
    return get_chunking_strategy("fixed")


def list_strategies() -> List[str]:
    """返回所有已注册策略名称"""
    return list(_STRATEGY_REGISTRY.keys())
