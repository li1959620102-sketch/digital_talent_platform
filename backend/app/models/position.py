"""
岗位信息模型
"""
from sqlalchemy import (
    Column, Integer, String, DateTime, Text, Boolean,
    Enum, ForeignKey, JSON, Index, Numeric
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base
import enum


class PositionStatus(str, enum.Enum):
    """岗位状态枚举"""
    OPEN = "open"  # 招聘中
    CLOSED = "closed"  # 已关闭
    SUSPENDED = "suspended"  # 已暂停
    DRAFT = "draft"  # 草稿


class PositionLevel(str, enum.Enum):
    """岗位级别枚举"""
    ENTRY = "entry"  # 初级
    JUNIOR = "junior"  # 初级
    INTERMEDIATE = "intermediate"  # 中级
    SENIOR = "senior"  # 高级
    EXPERT = "expert"  # 专家
    MANAGER = "manager"  # 管理岗
    DIRECTOR = "director"  # 总监


class JobPosition(Base):
    """岗位信息表"""
    __tablename__ = "job_positions"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    position_code = Column(String(50), unique=True, index=True, nullable=False, comment="岗位编号")
    position_name = Column(String(100), nullable=False, comment="岗位名称")
    department_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, comment="所属部门ID")
    
    # 基本信息
    position_category = Column(String(50), nullable=True, comment="岗位类别")
    position_level = Column(Enum(PositionLevel, values_callable=lambda e: [m.value for m in e]), nullable=True, comment="岗位级别")
    position_type = Column(String(50), nullable=True, comment="岗位类型: 全职/兼职/实习")
    headcount = Column(Integer, default=1, comment="招聘人数")
    filled_count = Column(Integer, default=0, comment="已招人数")
    
    # 薪资范围
    salary_min = Column(Integer, nullable=True, comment="薪资下限")
    salary_max = Column(Integer, nullable=True, comment="薪资上限")
    
    # 工作地点
    work_location = Column(String(200), nullable=True, comment="工作地点")
    
    # 岗位要求
    education_requirement = Column(String(50), nullable=True, comment="学历要求")
    experience_requirement = Column(Integer, nullable=True, comment="工作经验要求(年)")
    skill_requirements = Column(JSON, default=[], comment="技能要求列表")
    capability_requirements = Column(JSON, default=[], comment="能力要求列表")
    
    # 岗位描述
    job_description = Column(Text, nullable=True, comment="岗位描述")
    job_responsibilities = Column(Text, nullable=True, comment="岗位职责")
    
    # 标签
    tags = Column(JSON, default=[], comment="标签列表")
    
    # 状态
    status = Column(Enum(PositionStatus, values_callable=lambda e: [m.value for m in e]), default=PositionStatus.OPEN, comment="状态")
    publish_date = Column(DateTime, nullable=True, comment="发布日期")
    deadline = Column(DateTime, nullable=True, comment="截止日期")
    
    # 向量ID
    vector_id = Column(String(128), nullable=True, comment="向量库ID")
    
    # 时间戳
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")
    
    # 索引
    __table_args__ = (
        Index('idx_position_name', 'position_name'),
        Index('idx_position_department', 'department_id'),
        Index('idx_position_status', 'status'),
        Index('idx_position_level', 'position_level'),
    )
    
    # 关系
    department = relationship("Organization", back_populates="positions")
    match_records = relationship("MatchRecord", back_populates="position")


class MatchRecord(Base):
    """匹配记录表"""
    __tablename__ = "match_records"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    talent_id = Column(Integer, ForeignKey("talents.id", ondelete="CASCADE"), nullable=False, comment="人才ID")
    position_id = Column(Integer, ForeignKey("job_positions.id", ondelete="CASCADE"), nullable=False, comment="岗位ID")
    
    # 匹配分数
    match_score = Column(Numeric(5, 2), nullable=False, comment="匹配分数(0-100)")
    match_dimensions = Column(JSON, nullable=True, comment="匹配维度得分")
    
    # 匹配依据
    match_basis = Column(Text, nullable=True, comment="匹配依据")
    strengths = Column(Text, nullable=True, comment="优势亮点")
    weaknesses = Column(Text, nullable=True, comment="存在短板")
    suggestions = Column(Text, nullable=True, comment="适配建议")
    
    # 匹配状态
    status = Column(String(50), default="pending", comment="状态: pending/shortlisted/interviewed/hired/rejected")
    feedback = Column(Text, nullable=True, comment="反馈")
    
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")
    
    # 关系
    talent = relationship("Talent", back_populates="match_records")
    position = relationship("JobPosition", back_populates="match_records")
    
    __table_args__ = (
        Index('idx_match_talent_position', 'talent_id', 'position_id', unique=True),
    )


# 移除遗留表 talent_pools / talent_pool_relations：之前定义了但前后端均未使用。
# 若将来需要"后备人才库"功能，可重新启用并补对应 CRUD + UI。
