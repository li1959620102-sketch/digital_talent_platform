"""
测评体系模型
"""
from sqlalchemy import (
    Column, Integer, String, DateTime, Text, Boolean,
    Enum, ForeignKey, JSON, Index, Numeric
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base
import enum


class QuestionType(str, enum.Enum):
    """题目类型枚举"""
    SINGLE_CHOICE = "single_choice"  # 单选
    MULTIPLE_CHOICE = "multiple_choice"  # 多选
    TRUE_FALSE = "true_false"  # 判断
    FILL_BLANK = "fill_blank"  # 填空
    SHORT_ANSWER = "short_answer"  # 简答
    ESSAY = "essay"  # 论述


class AssessmentStatus(str, enum.Enum):
    """测评状态枚举"""
    DRAFT = "draft"  # 草稿
    PUBLISHED = "published"  # 已发布
    IN_PROGRESS = "in_progress"  # 进行中
    COMPLETED = "completed"  # 已完成
    CANCELLED = "cancelled"  # 已取消


class CapabilityLevel(str, enum.Enum):
    """能力等级枚举"""
    ENTRY = "entry"  # 初级
    JUNIOR = "junior"  # 初级
    INTERMEDIATE = "intermediate"  # 中级
    SENIOR = "senior"  # 高级
    EXPERT = "expert"  # 专家
    BACKBONE = "backbone"  # 骨干
    CORE = "core"  # 核心


class Question(Base):
    """题库表"""
    __tablename__ = "questions"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    question_code = Column(String(50), unique=True, index=True, nullable=False, comment="题目编号")
    
    # 题目内容
    question_content = Column(Text, nullable=False, comment="题目内容")
    question_type = Column(Enum(QuestionType, values_callable=lambda e: [m.value for m in e]), nullable=False, comment="题目类型")
    question_category = Column(String(50), nullable=True, comment="题目分类: 综合/专业/性格/岗位/抗压/团队")
    
    # 选项与答案
    options = Column(JSON, nullable=True, comment="选项列表(ABCD)")
    correct_answer = Column(Text, nullable=False, comment="正确答案")
    answer_analysis = Column(Text, nullable=True, comment="答案解析")
    
    # 分值
    score_value = Column(Numeric(5, 2), default=1.00, comment="分值")
    difficulty = Column(Integer, default=3, comment="难度(1-5)")
    
    # 能力维度
    capability_dimension = Column(String(50), nullable=True, comment="能力维度")
    
    # 标签
    tags = Column(JSON, default=[], comment="标签列表")
    
    # 状态
    status = Column(String(20), default="active", comment="状态")
    
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")
    
    __table_args__ = (
        Index('idx_question_category', 'question_category'),
        Index('idx_question_type', 'question_type'),
    )


class TestPaper(Base):
    """试卷表"""
    __tablename__ = "test_papers"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    paper_code = Column(String(50), unique=True, index=True, nullable=False, comment="试卷编号")
    paper_name = Column(String(100), nullable=False, comment="试卷名称")
    
    # 试卷类型
    paper_type = Column(String(50), nullable=False, comment="试卷类型: 综合测评/专业技能/职业性格/岗位适配")
    paper_description = Column(Text, nullable=True, comment="试卷描述")
    
    # 题目配置
    questions = Column(JSON, default=[], comment="题目列表(题目ID及分值)")
    total_score = Column(Numeric(5, 2), default=100.00, comment="总分")
    duration_minutes = Column(Integer, default=60, comment="考试时长(分钟)")
    
    # 难度分布
    difficulty_distribution = Column(JSON, nullable=True, comment="难度分布")
    
    # 能力维度
    capability_dimensions = Column(JSON, default=[], comment="能力维度列表")
    
    # 状态
    status = Column(String(20), default="draft", comment="状态")
    
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")


class AssessmentTask(Base):
    """测评任务表"""
    __tablename__ = "assessment_tasks"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    task_code = Column(String(50), unique=True, index=True, nullable=False, comment="任务编号")
    task_name = Column(String(100), nullable=False, comment="任务名称")
    
    # 测评对象
    target_type = Column(String(50), default="batch", comment="测评对象类型: batch/directed/self_signup")
    target_talents = Column(JSON, default=[], comment="测评对象ID列表")
    
    # 测评试卷
    paper_id = Column(Integer, ForeignKey("test_papers.id", ondelete="CASCADE"), nullable=False, comment="试卷ID")
    
    # 时间
    start_time = Column(DateTime, nullable=True, comment="开始时间")
    end_time = Column(DateTime, nullable=True, comment="结束时间")
    
    # 配置
    allow_retake = Column(Boolean, default=False, comment="允许重考")
    max_attempts = Column(Integer, default=1, comment="最大尝试次数")
    show_answer = Column(Boolean, default=False, comment="是否显示答案")
    anti_cheating = Column(Boolean, default=True, comment="防作弊")
    
    # 状态
    status = Column(Enum(AssessmentStatus, values_callable=lambda e: [m.value for m in e]), default=AssessmentStatus.DRAFT, comment="状态")
    
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")
    
    # 关系
    results = relationship("AssessmentResult", back_populates="task")

    __table_args__ = (
        Index('idx_assessment_task_status_time', 'status', 'start_time', 'end_time'),
    )


class AssessmentResult(Base):
    """测评结果表"""
    __tablename__ = "assessment_results"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    result_code = Column(String(50), unique=True, index=True, nullable=False, comment="结果编号")
    
    # 关联
    talent_id = Column(Integer, ForeignKey("talents.id", ondelete="CASCADE"), nullable=False, comment="人才ID")
    task_id = Column(Integer, ForeignKey("assessment_tasks.id", ondelete="CASCADE"), nullable=False, comment="任务ID")
    paper_id = Column(Integer, ForeignKey("test_papers.id", ondelete="CASCADE"), nullable=False, comment="试卷ID")
    
    # 答题情况
    answers = Column(JSON, default=[], comment="答题情况")
    
    # 分数
    total_score = Column(Numeric(5, 2), nullable=False, comment="总分")
    correct_count = Column(Integer, default=0, comment="正确题数")
    wrong_count = Column(Integer, default=0, comment="错误题数")
    unanswered_count = Column(Integer, default=0, comment="未答题数")
    
    # 能力维度
    capability_dimensions = Column(JSON, default={}, comment="能力维度得分")
    
    # 雷达图数据
    radar_chart_data = Column(JSON, nullable=True, comment="雷达图数据")
    
    # 测评报告
    report = Column(Text, nullable=True, comment="测评报告")
    strengths = Column(Text, nullable=True, comment="优势")
    weaknesses = Column(Text, nullable=True, comment="短板")
    suggestions = Column(Text, nullable=True, comment="发展建议")
    
    # 能力等级
    capability_level = Column(Enum(CapabilityLevel, values_callable=lambda e: [m.value for m in e]), nullable=True, comment="能力等级")
    
    # 时间
    start_time = Column(DateTime, nullable=True, comment="开始时间")
    submit_time = Column(DateTime, nullable=True, comment="提交时间")
    duration_seconds = Column(Integer, default=0, comment="用时(秒)")
    
    # 状态
    status = Column(String(20), default="completed", comment="状态")
    
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")
    
    # 关系
    talent = relationship("Talent", back_populates="assessment_results")
    task = relationship("AssessmentTask", back_populates="results")
    
    __table_args__ = (
        Index('idx_result_talent_task', 'talent_id', 'task_id', unique=True),
        Index('idx_result_task_submit', 'task_id', 'submit_time'),
        Index('idx_result_score', 'total_score'),
    )
