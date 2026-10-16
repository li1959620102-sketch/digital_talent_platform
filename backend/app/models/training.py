"""
培训体系模型
"""
from sqlalchemy import (
    Column, Integer, String, DateTime, Text, Boolean,
    Enum, ForeignKey, JSON, Index, Numeric
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base
import enum


class CourseType(str, enum.Enum):
    """课程类型枚举"""
    TEXT_IMAGE = "text_image"  # 图文
    VIDEO = "video"  # 视频
    DOCUMENT = "document"  # 文档
    COURSEWARE = "courseware"  # 课件


class CourseCategory(str, enum.Enum):
    """课程分类枚举"""
    POSITION = "position"  # 按岗位
    SKILL = "skill"  # 按技能
    LEVEL = "level"  # 按层级
    PROFESSION = "profession"  # 按专业


class TrainingStatus(str, enum.Enum):
    """培训状态枚举"""
    DRAFT = "draft"  # 草稿
    PUBLISHED = "published"  # 已发布
    IN_PROGRESS = "in_progress"  # 进行中
    COMPLETED = "completed"  # 已完成
    CANCELLED = "cancelled"  # 已取消


class LearningStatus(str, enum.Enum):
    """学习状态枚举"""
    NOT_STARTED = "not_started"  # 未开始
    IN_PROGRESS = "in_progress"  # 进行中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"  # 未通过


class Course(Base):
    """课程库表"""
    __tablename__ = "courses"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    course_code = Column(String(50), unique=True, index=True, nullable=False, comment="课程编号")
    course_name = Column(String(100), nullable=False, comment="课程名称")
    
    # 课程分类
    course_category = Column(Enum(CourseCategory, values_callable=lambda e: [m.value for m in e]), nullable=False, comment="课程分类")
    course_type = Column(Enum(CourseType, values_callable=lambda e: [m.value for m in e]), nullable=False, comment="课程类型")
    
    # 课程内容
    course_content = Column(Text, nullable=True, comment="课程内容")
    course_url = Column(String(500), nullable=True, comment="课程资源URL")
    course_file_id = Column(String(128), nullable=True, comment="课程文件ID")
    
    # 课程信息
    duration_minutes = Column(Integer, default=0, comment="课程时长(分钟)")
    instructor = Column(String(100), nullable=True, comment="讲师")
    
    # 权限
    permissions = Column(JSON, default=[], comment="权限列表(角色/部门/人员)")
    
    # 评分评论
    rating = Column(Numeric(3, 2), default=0.00, comment="评分(0-5)")
    rating_count = Column(Integer, default=0, comment="评分人数")
    comments = Column(JSON, default=[], comment="评论列表")
    
    # 标签
    tags = Column(JSON, default=[], comment="标签列表")
    
    # 状态
    status = Column(String(20), default="active", comment="状态")
    
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")
    
    __table_args__ = (
        Index('idx_course_category', 'course_category'),
        Index('idx_course_type', 'course_type'),
    )


class TrainingPlan(Base):
    """培训计划表"""
    __tablename__ = "training_plans"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    plan_code = Column(String(50), unique=True, index=True, nullable=False, comment="计划编号")
    plan_name = Column(String(100), nullable=False, comment="计划名称")
    
    # 培训对象
    target_talents = Column(JSON, default=[], comment="培训对象ID列表")
    target_type = Column(String(50), default="batch", comment="培训对象类型")
    
    # 课程列表
    courses = Column(JSON, default=[], comment="课程列表")
    
    # 时间
    start_time = Column(DateTime, nullable=True, comment="开始时间")
    end_time = Column(DateTime, nullable=True, comment="结束时间")
    
    # 配置
    learning_reminder = Column(Boolean, default=True, comment="学习提醒")
    examination_required = Column(Boolean, default=True, comment="是否需要考核")
    
    # 状态
    status = Column(Enum(TrainingStatus, values_callable=lambda e: [m.value for m in e]), default=TrainingStatus.DRAFT, comment="状态")
    
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")
    
    # 关系
    learning_records = relationship("LearningRecord", back_populates="plan")


class LearningRecord(Base):
    """学习记录表"""
    __tablename__ = "learning_records"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    record_code = Column(String(50), unique=True, index=True, nullable=False, comment="记录编号")
    
    # 关联
    talent_id = Column(Integer, ForeignKey("talents.id", ondelete="CASCADE"), nullable=False, comment="人才ID")
    course_id = Column(Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, comment="课程ID")
    plan_id = Column(Integer, ForeignKey("training_plans.id", ondelete="CASCADE"), nullable=True, comment="计划ID")
    
    # 学习进度
    progress = Column(Numeric(5, 2), default=0.00, comment="进度(0-100)")
    duration_minutes = Column(Integer, default=0, comment="学习时长(分钟)")
    
    # 学习状态
    status = Column(Enum(LearningStatus, values_callable=lambda e: [m.value for m in e]), default=LearningStatus.NOT_STARTED, comment="状态")
    
    # 学习时间
    last_learning_time = Column(DateTime, nullable=True, comment="最后学习时间")
    completed_time = Column(DateTime, nullable=True, comment="完成时间")
    
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")
    
    # 关系
    talent = relationship("Talent", back_populates="learning_records")
    plan = relationship("TrainingPlan", back_populates="learning_records")
    
    __table_args__ = (
        Index('idx_learning_talent_course', 'talent_id', 'course_id', unique=True),
        Index('idx_learning_status_updated', 'status', 'updated_at'),
        Index('idx_learning_plan_status', 'plan_id', 'status'),
    )


class ExaminationRecord(Base):
    """考核记录表"""
    __tablename__ = "examination_records"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    record_code = Column(String(50), unique=True, index=True, nullable=False, comment="记录编号")
    
    # 关联
    talent_id = Column(Integer, ForeignKey("talents.id", ondelete="CASCADE"), nullable=False, comment="人才ID")
    course_id = Column(Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, comment="课程ID")
    plan_id = Column(Integer, ForeignKey("training_plans.id", ondelete="CASCADE"), nullable=True, comment="计划ID")
    
    # 答题情况
    answers = Column(JSON, default=[], comment="答题情况")
    
    # 分数
    score = Column(Numeric(5, 2), nullable=False, comment="分数")
    passed = Column(Boolean, default=False, comment="是否通过")
    
    # 时间
    start_time = Column(DateTime, nullable=True, comment="开始时间")
    submit_time = Column(DateTime, nullable=True, comment="提交时间")
    duration_seconds = Column(Integer, default=0, comment="用时(秒)")
    
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")
    
    __table_args__ = (
        Index('idx_examination_talent_course', 'talent_id', 'course_id'),
        Index('idx_examination_passed_submit', 'passed', 'submit_time'),
        Index('idx_examination_plan_submit', 'plan_id', 'submit_time'),
    )
