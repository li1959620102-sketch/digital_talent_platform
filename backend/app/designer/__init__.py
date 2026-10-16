# -*- coding: utf-8 -*-
"""designer/ 架构层（参考 large_health_reference/designer/）
策略模式：运行时按文档类型 / Agent 类型切换切片与元数据策略。
"""
from app.designer.strategy.chunking_strategy import (
    ChunkingStrategy,
    BaseChunkingStrategy,
    get_chunking_strategy,
    list_strategies,
    register_strategy,
)
from app.designer.strategy.metadata_strategy import (
    MetadataStrategy,
    MinIOMetadataStrategy,
    TalentMetadataStrategy,
)

__all__ = [
    "ChunkingStrategy",
    "BaseChunkingStrategy",
    "get_chunking_strategy",
    "list_strategies",
    "register_strategy",
    "MetadataStrategy",
    "MinIOMetadataStrategy",
    "TalentMetadataStrategy",
]
