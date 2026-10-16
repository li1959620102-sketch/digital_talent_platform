"""
人才档案模型
"""
from sqlalchemy import (
    Column, Integer, String, Date, DateTime, Text, Boolean,
    Enum, ForeignKey, JSON, Index
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base
import enum


class GenderEnum(str, enum.Enum):
    """性别枚举"""
    MALE = "male"
    FEMALE = "female"


class EducationLevel(str, enum.Enum):
    """学历枚举"""
    HIGH_SCHOOL = "高中"
    COLLEGE = "大专"
    BACHELOR = "本科"
    MASTER = "硕士"
    DOCTOR = "博士"


class TalentStatus(str, enum.Enum):
    """人才状态枚举"""
    ACTIVE = "active"  # 在岗
    RESERVE = "reserve"  # 储备
    RESIGNED = "resigned"  # 离职
    ON_LEAVE = "on_leave"  # 休假


class Talent(Base):
    """人才档案表"""
    __tablename__ = "talents"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    talent_code = Column(String(50), unique=True, index=True, nullable=False, comment="人才编号")
    name = Column(String(50), nullable=False, comment="姓名")
    gender = Column(Enum(GenderEnum, values_callable=lambda e: [m.value for m in e]), nullable=False, comment="性别")
    birth_date = Column(Date, nullable=True, comment="出生日期")
    id_card = Column(String(18), nullable=True, comment="身份证号")
    phone = Column(String(20), nullable=False, index=True, comment="手机号")
    email = Column(String(100), nullable=True, comment="邮箱")
    address = Column(String(200), nullable=True, comment="地址")
    
    # 教育背景
    education = Column(Enum(EducationLevel, values_callable=lambda e: [m.value for m in e]), nullable=True, comment="最高学历")
    major = Column(String(100), nullable=True, comment="专业")
    education_records = Column(JSON, default=[], comment="教育背景列表")
    
    # 工作经历
    experience_years = Column(Integer, default=0, comment="工作年限")
    current_company = Column(String(100), nullable=True, comment="当前公司")
    current_position = Column(String(100), nullable=True, comment="当前职位")
    work_experiences = Column(JSON, default=[], comment="工作经历列表")
    
    # 技能证书
    skills_certificates = Column(JSON, default=[], comment="技能证书列表")
    
    # 期望
    expected_salary_min = Column(Integer, nullable=True, comment="期望薪资下限")
    expected_salary_max = Column(Integer, nullable=True, comment="期望薪资上限")
    expected_position = Column(String(100), nullable=True, comment="期望职位")
    
    # 其他
    self_introduction = Column(Text, nullable=True, comment="自我介绍")
    status = Column(Enum(TalentStatus, values_callable=lambda e: [m.value for m in e]), default=TalentStatus.RESERVE, comment="状态")
    department_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, comment="所属部门ID")
    # 归属：自助服务的普通员工档案绑定到 users.id（隔离于 HR 全局人才池；HR 录入的档案 user_id 为空）
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True, comment="归属用户ID（员工自助档案）")
    
    # 标签与画像
    tags = Column(JSON, default=[], comment="标签列表")
    portrait = Column(JSON, nullable=True, comment="人才画像")
    capability_rating = Column(JSON, nullable=True, comment="能力评级")
    
    # 简历文件
    resume_file_id = Column(String(128), nullable=True, comment="简历文件ID")
    resume_file_name = Column(String(512), nullable=True, comment="简历文件名")
    is_parsed = Column(Boolean, default=False, comment="是否已解析")
    
    # 时间戳
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")
    
    # 索引
    __table_args__ = (
        Index('idx_talent_name', 'name'),
        Index('idx_talent_phone', 'phone'),
        Index('idx_talent_status', 'status'),
        Index('idx_talent_department', 'department_id'),
        Index('idx_talent_education', 'education'),
        Index('idx_talent_experience', 'experience_years'),
    )
    
    # 关系
    department = relationship("Organization", back_populates="talents")
    user = relationship("User", back_populates="talents")
    assessment_results = relationship("AssessmentResult", back_populates="talent")
    learning_records = relationship("LearningRecord", back_populates="talent")
    match_records = relationship("MatchRecord", back_populates="talent")


class Organization(Base):
    """组织架构表"""
    __tablename__ = "organizations"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    org_code = Column(String(50), unique=True, index=True, nullable=False, comment="组织编码")
    org_name = Column(String(100), nullable=False, comment="组织名称")
    org_type = Column(String(50), nullable=False, comment="组织类型: 公司/部门/团队")
    parent_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, comment="上级组织ID")
    description = Column(Text, nullable=True, comment="组织描述")
    status = Column(String(20), default="active", comment="状态")
    
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")
    
    # 关系
    parent = relationship("Organization", remote_side=[id], backref="children")
    talents = relationship("Talent", back_populates="department")
    positions = relationship("JobPosition", back_populates="department")


# 移除遗留表 talent_tags / talent_tag_relations：之前定义了但前后端均未使用，
# 改用 talents.tags JSON 字段存储（更简洁，足以覆盖甲方演示场景）。
# 注释保留以备将来若需标签管理 UI 时重新启用。
