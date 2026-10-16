"""
PostgreSQL 分析库 ORM 模型（PgSQL 分库）
遵循招标文件强制要求：PgSQL 用于海量分析数据和时序数据。
MySQL（digital_talent）保留：Talent/Position/Course 等业务主数据
PgSQL（talent_analytics）新增：时序分析数据、行为日志、分析报表

这些模型通过 init_pgsql_tables() 在应用启动时自动创建。
MySQL 端的 models.talent / models.assessment 等保持不变（双写同步）。
"""
from datetime import datetime
from typing import Dict, Any, Optional, List
from sqlalchemy import (
    Column, Integer, BigInteger, String, Float, Boolean,
    DateTime, Text, JSON, Index, ForeignKey
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP

from app.core.postgresql.client import Base


class TalentBehaviorLog(Base):
    """
    人才行为时序日志（PgSQL 专属）
    记录：简历查看/岗位申请/测评参与/培训学习等行为事件。
    时序数据存储在 PgSQL，利用其时序特性做趋势分析。
    """
    __tablename__ = "talent_behavior_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    talent_id = Column(BigInteger, nullable=False, index=True)
    organization_id = Column(Integer, nullable=True)
    user_id = Column(Integer, nullable=True, comment="操作用户")

    event_type = Column(String(64), nullable=False, index=True)
    # event_type 示例: resume_view / position_apply / assessment_submit / training_complete / exam_pass

    event_data = Column(JSONB, nullable=True, comment="事件附加数据（JSON）")
    # event_data 示例: {"position_id": 5, "score": 85}

    occurred_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_talent_behavior_talent_time", "talent_id", "occurred_at"),
        Index("ix_talent_behavior_org_time", "organization_id", "occurred_at"),
    )


class TalentTrendSnapshot(Base):
    """
    人才能力趋势快照（PgSQL 专属）
    每次测评完成后记录一次快照，支持纵向趋势分析。
    """
    __tablename__ = "talent_trend_snapshots"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    talent_id = Column(BigInteger, nullable=False, index=True)
    assessment_result_id = Column(BigInteger, nullable=False, unique=True)

    # 能力维度得分（JSONB，支持任意维度）
    capability_dimensions = Column(JSONB, nullable=False, default=dict)

    total_score = Column(Float, nullable=False, default=0)
    ability_level = Column(String(32), nullable=True)
    # ability_level: 初级/中级/高级/骨干/核心人才

    snapshot_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_trend_talent_snapshot", "talent_id", "snapshot_at"),
    )


class TrainingAnalytics(Base):
    """
    培训赋能分析数据（PgSQL 专属）
    记录课程完成率/学习时长/考核通过率等，用于培训效果分析。
    """
    __tablename__ = "training_analytics"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    talent_id = Column(BigInteger, nullable=False, index=True)
    course_id = Column(Integer, nullable=True)
    learning_record_id = Column(BigInteger, nullable=True, unique=True)

    # 学习行为数据
    study_duration_minutes = Column(Float, nullable=False, default=0)
    completion_rate = Column(Float, nullable=False, default=0, comment="0-100%")
    exam_score = Column(Float, nullable=True, comment="考核得分")
    passed = Column(Boolean, nullable=True)

    # 学习路径上下文
    learning_path_step = Column(Integer, nullable=True)

    recorded_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_training_talent_time", "talent_id", "recorded_at"),
    )


class MatchAnalytics(Base):
    """
    匹配效果分析数据（PgSQL 专属）
    记录每次匹配请求的输入/输出/结果，用于匹配算法调优和效果评估。
    """
    __tablename__ = "match_analytics"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    request_id = Column(String(128), nullable=False, unique=True)

    talent_id = Column(BigInteger, nullable=True, index=True)
    position_id = Column(Integer, nullable=True, index=True)

    # 匹配参数
    match_type = Column(String(32), nullable=False)
    filter_count = Column(Integer, nullable=False, default=0, comment="硬过滤后候选数")
    match_count = Column(Integer, nullable=False, default=0, comment="最终匹配数")

    # Top1 匹配分
    top1_score = Column(Float, nullable=True)
    top1_candidate_id = Column(BigInteger, nullable=True)

    # 执行耗时（ms）
    duration_ms = Column(Float, nullable=True)

    # LLM 精排是否启用
    llm_ranking_used = Column(Boolean, nullable=False, default=False)

    request_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_match_talent_time", "talent_id", "request_at"),
        Index("ix_match_position_time", "position_id", "request_at"),
    )


class DashboardSummary(Base):
    """
    看板预聚合数据（PgSQL 专属）
    按天/周/月预计算关键指标，加速 Dashboard 响应。
    由定时任务（cron）更新。
    """
    __tablename__ = "dashboard_summaries"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    organization_id = Column(Integer, nullable=False, index=True)

    period_type = Column(String(8), nullable=False, comment="day / week / month")
    period_start = Column(DateTime, nullable=False, index=True)

    # 关键指标
    total_talents = Column(Integer, nullable=False, default=0)
    active_talents = Column(Integer, nullable=False, default=0)
    reserve_talents = Column(Integer, nullable=False, default=0)

    new_talents = Column(Integer, nullable=False, default=0)
    open_positions = Column(Integer, nullable=False, default=0)

    assessment_count = Column(Integer, nullable=False, default=0)
    avg_score = Column(Float, nullable=True)

    training_completion_rate = Column(Float, nullable=True)
    exam_pass_rate = Column(Float, nullable=True)

    # 能力维度均值（JSONB）
    avg_capabilities = Column(JSONB, nullable=True)

    computed_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_dashboard_org_period", "organization_id", "period_type", "period_start", unique=True),
    )
