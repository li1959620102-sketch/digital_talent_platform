# -*- coding: utf-8 -*-
"""
元数据策略接口（参考 large_health_reference/designer/strategy/metadata_strategy.py）。
每个向量记录注入哪些元数据字段，由 MetadataStrategy 决定。
"""
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class MetadataStrategy(Protocol):
    """
    元数据注入策略 Protocol。
    实现类注入：向量记录的元数据字段（供 Milvus 标量过滤）。
    """
    @property
    def name(self) -> str:
        ...

    def build_metadata(
        self,
        chunk_text: str,
        chunk_index: int,
        total_chunks: int,
        **context,
    ) -> Dict[str, Any]:
        """构建向量记录的元数据字段"""
        ...


class MinIOMetadataStrategy:
    """
    MinIO 文件元数据策略（参考 large_health_reference MinIOMetadataStrategy）。
    注入字段：file_id / file_name / minio_path / chunk_id / created_at / chunk_index / total_chunks。
    用于知识库文件向量记录。
    """
    def __init__(self, file_id: str = "", file_name: str = "", minio_path: str = ""):
        self.file_id = file_id
        self.file_name = file_name
        self.minio_path = minio_path

    @property
    def name(self) -> str:
        return "minio"

    def build_metadata(
        self,
        chunk_text: str,
        chunk_index: int,
        total_chunks: int,
        **context,
    ) -> Dict[str, Any]:
        import time
        import uuid
        return {
            "file_id": self.file_id or context.get("file_id", ""),
            "file_name": self.file_name or context.get("file_name", ""),
            "minio_path": self.minio_path or context.get("minio_path", ""),
            "chunk_id": context.get("chunk_code", f"kc{int(time.time()*1000)}{uuid.uuid4().hex[:6].upper()}"),
            "created_at": int(time.time()),
            "chunk_index": chunk_index,
            "total_chunks": total_chunks,
            "permission_level": context.get("permission_level", 0),
            "business_scene": context.get("business_scene", "knowledge_base"),
            "knowledge_type": context.get("knowledge_type", "other"),
        }


class TalentMetadataStrategy:
    """
    人才平台专用元数据策略（结合需求改造复用）。
    按 Agent 注入 business_scene + agent_type + 业务追踪字段。
    """
    # Agent → business_scene 映射
    AGENT_SCENE_MAP = {
        "resume_parser": "resume",
        "assessment": "assessment",
        "matching": "matching",
        "training": "training",
        "data_decision": "data_decision",
        "knowledge": "knowledge_base",
    }

    def __init__(self, agent_type: str = "knowledge"):
        self.agent_type = agent_type
        self.business_scene = self.AGENT_SCENE_MAP.get(agent_type, "knowledge_base")

    @property
    def name(self) -> str:
        return f"talent_{self.agent_type}"

    def build_metadata(
        self,
        chunk_text: str,
        chunk_index: int,
        total_chunks: int,
        **context,
    ) -> Dict[str, Any]:
        import time
        import uuid
        base = {
            "business_scene": self.business_scene,
            "agent_type": self.agent_type,
            "chunk_index": chunk_index,
            "total_chunks": total_chunks,
            "created_at": int(time.time()),
            "chunk_id": context.get("chunk_code", f"kc{int(time.time()*1000)}{uuid.uuid4().hex[:6].upper()}"),
            "permission_level": context.get("permission_level", 0),
            "knowledge_type": context.get("knowledge_type", "other"),
            "file_id": str(context.get("file_id", "")),
            "file_name": str(context.get("file_name", ""))[:512],
        }
        # 按 agent 类型追加业务字段
        if self.agent_type == "matching":
            base["position_id"] = str(context.get("position_id", ""))
            base["talent_id"] = str(context.get("talent_id", ""))
        elif self.agent_type == "training":
            base["course_id"] = str(context.get("course_id", ""))
            base["talent_id"] = str(context.get("talent_id", ""))
        elif self.agent_type == "resume_parser":
            base["talent_id"] = str(context.get("talent_id", ""))
        elif self.agent_type == "assessment":
            base["assessment_id"] = str(context.get("assessment_id", ""))
            base["talent_id"] = str(context.get("talent_id", ""))
        return base
