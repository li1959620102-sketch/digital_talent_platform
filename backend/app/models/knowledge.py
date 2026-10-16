"""
知识库模型（RAG 数据源管理）
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Float, ForeignKey, JSON
from sqlalchemy.sql import func
from datetime import datetime
from app.core.database import Base


class KnowledgeFile(Base):
    """知识库文件（简历/岗位说明/人才制度/培训课件/测评标准/历史案例/培养方案等）"""

    __tablename__ = "knowledge_files"

    id = Column(Integer, primary_key=True, autoincrement=True)
    file_code = Column(String(50), unique=True, index=True, nullable=False, comment="文件编号")
    file_name = Column(String(512), nullable=False, comment="文件名")
    file_type = Column(String(32), comment="文件类型(txt/md/pdf/docx...)")
    file_size = Column(Integer, default=0, comment="文件大小(字节)")
    file_path = Column(String(1024), comment="存储路径")
    knowledge_type = Column(String(64), default="other", comment="知识类型(制度/课件/标准/案例/其他)")
    status = Column(String(32), default="uploaded", comment="状态(uploaded/vectorized/failed)")
    chunk_count = Column(Integer, default=0, comment="切片数量")
    permission_level = Column(Integer, default=0, comment="权限级别(用于RAG检索权限过滤)")
    uploader_id = Column(Integer, nullable=True, comment="上传人")
    error_msg = Column(Text, nullable=True, comment="处理错误信息")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=datetime.now)


class KnowledgeChunk(Base):
    """知识库切片（向量化单元）"""

    __tablename__ = "knowledge_chunks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chunk_code = Column(String(50), unique=True, index=True, nullable=False, comment="切片编号")
    file_id = Column(Integer, ForeignKey("knowledge_files.id", ondelete="CASCADE"), nullable=False)
    chunk_index = Column(Integer, default=0, comment="切片序号")
    content = Column(Text, comment="切片文本")
    vector_id = Column(String(64), nullable=True, comment="Milvus 向量ID")
    embedding_status = Column(String(32), default="pending", comment="向量化状态")
    created_at = Column(DateTime, server_default=func.now())
