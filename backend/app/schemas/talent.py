"""
人才档案相关Schema
"""
from pydantic import BaseModel, Field, EmailStr, ConfigDict
from typing import Optional, List
from datetime import datetime, date
from enum import Enum


class GenderEnum(str, Enum):
    """性别枚举"""
    MALE = "male"
    FEMALE = "female"


class EducationLevel(str, Enum):
    """学历枚举"""
    HIGH_SCHOOL = "高中"
    COLLEGE = "大专"
    BACHELOR = "本科"
    MASTER = "硕士"
    DOCTOR = "博士"


class TalentStatus(str, Enum):
    """人才状态枚举"""
    ACTIVE = "active"  # 在岗
    RESERVE = "reserve"  # 储备
    RESIGNED = "resigned"  # 离职
    ON_LEAVE = "on_leave"  # 休假


class EducationRecordBase(BaseModel):
    """教育背景基础模型"""
    school: str = Field(..., description="学校名称")
    major: str = Field(..., description="专业")
    degree: EducationLevel = Field(..., description="学历")
    start_date: date = Field(..., description="开始时间")
    end_date: Optional[date] = Field(None, description="结束时间")
    description: Optional[str] = Field(None, description="描述")


class WorkExperienceBase(BaseModel):
    """工作经历基础模型"""
    company: str = Field(..., description="公司名称")
    position: str = Field(..., description="职位")
    start_date: date = Field(..., description="开始时间")
    end_date: Optional[date] = Field(None, description="结束时间")
    responsibilities: Optional[str] = Field(None, description="工作职责")
    achievements: Optional[str] = Field(None, description="工作成果")


class SkillCertificateBase(BaseModel):
    """技能证书基础模型"""
    name: str = Field(..., description="证书/技能名称")
    level: Optional[str] = Field(None, description="等级")
    obtained_date: Optional[date] = Field(None, description="获得时间")
    expiry_date: Optional[date] = Field(None, description="过期时间")
    issuing_authority: Optional[str] = Field(None, description="颁发机构")


class TalentBase(BaseModel):
    """人才基础模型"""
    name: str = Field(..., description="姓名", max_length=50)
    gender: GenderEnum = Field(..., description="性别")
    birth_date: Optional[date] = Field(None, description="出生日期")
    id_card: Optional[str] = Field(None, description="身份证号", max_length=18)
    phone: str = Field(..., description="手机号", max_length=20)
    email: Optional[EmailStr] = Field(None, description="邮箱")
    address: Optional[str] = Field(None, description="地址", max_length=200)
    education: Optional[EducationLevel] = Field(None, description="最高学历")
    major: Optional[str] = Field(None, description="专业", max_length=100)
    experience_years: Optional[int] = Field(None, ge=0, description="工作年限")
    current_company: Optional[str] = Field(None, description="当前公司", max_length=100)
    current_position: Optional[str] = Field(None, description="当前职位", max_length=100)
    expected_salary_min: Optional[int] = Field(None, ge=0, description="期望薪资下限")
    expected_salary_max: Optional[int] = Field(None, ge=0, description="期望薪资上限")
    expected_position: Optional[str] = Field(None, description="期望职位", max_length=100)
    self_introduction: Optional[str] = Field(None, description="自我介绍")
    status: TalentStatus = Field(default=TalentStatus.RESERVE, description="状态")
    department_id: Optional[int] = Field(None, description="所属部门ID")


class TalentCreate(TalentBase):
    """创建人才"""
    education_records: Optional[List[EducationRecordBase]] = Field(default=[], description="教育背景")
    work_experiences: Optional[List[WorkExperienceBase]] = Field(default=[], description="工作经历")
    skills_certificates: Optional[List[SkillCertificateBase]] = Field(default=[], description="技能证书")
    tags: Optional[List[str]] = Field(default=[], description="标签列表")
    # 以下三个由简历解析链路回填：文件已上传到对象存储后，把对象名与解析标记写回档案，
    # 否则会出现「MinIO 里有文件、档案里没有引用」的断裂（实测过的真实缺陷）。
    resume_file_id: Optional[str] = Field(None, description="简历文件对象名(MinIO)", max_length=128)
    resume_file_name: Optional[str] = Field(None, description="简历原始文件名", max_length=512)
    is_parsed: bool = Field(False, description="是否由简历解析生成")


class TalentUpdate(BaseModel):
    """更新人才"""
    name: Optional[str] = Field(None, description="姓名", max_length=50)
    gender: Optional[GenderEnum] = Field(None, description="性别")
    birth_date: Optional[date] = Field(None, description="出生日期")
    id_card: Optional[str] = Field(None, description="身份证号", max_length=18)
    phone: Optional[str] = Field(None, description="手机号", max_length=20)
    email: Optional[EmailStr] = Field(None, description="邮箱")
    address: Optional[str] = Field(None, description="地址", max_length=200)
    education: Optional[EducationLevel] = Field(None, description="最高学历")
    major: Optional[str] = Field(None, description="专业", max_length=100)
    experience_years: Optional[int] = Field(None, ge=0, description="工作年限")
    current_company: Optional[str] = Field(None, description="当前公司", max_length=100)
    current_position: Optional[str] = Field(None, description="当前职位", max_length=100)
    expected_salary_min: Optional[int] = Field(None, ge=0, description="期望薪资下限")
    expected_salary_max: Optional[int] = Field(None, ge=0, description="期望薪资上限")
    expected_position: Optional[str] = Field(None, description="期望职位", max_length=100)
    self_introduction: Optional[str] = Field(None, description="自我介绍")
    status: Optional[TalentStatus] = Field(None, description="状态")
    department_id: Optional[int] = Field(None, description="所属部门ID")
    tags: Optional[List[str]] = Field(None, description="标签列表")


class TalentInDB(TalentBase):
    """数据库中的人才"""
    id: int
    talent_code: str = Field(..., description="人才编号")
    education_records: List[dict] = Field(default=[], description="教育背景")
    work_experiences: List[dict] = Field(default=[], description="工作经历")
    skills_certificates: List[dict] = Field(default=[], description="技能证书")
    tags: List[str] = Field(default=[], description="标签列表")
    portrait: Optional[dict] = Field(None, description="人才画像")
    capability_rating: Optional[dict] = Field(None, description="能力评级")
    resume_file_id: Optional[str] = Field(None, description="简历文件ID")
    resume_file_name: Optional[str] = Field(None, description="简历文件名")
    is_parsed: bool = Field(default=False, description="是否已解析")
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TalentResponse(TalentInDB):
    """人才响应模型"""
    department_name: Optional[str] = Field(None, description="所属部门名称（前端展示用）")


class TalentListResponse(BaseModel):
    """人才列表响应"""
    items: List[TalentResponse]
    total: int
    page: int
    page_size: int


class ResumeParseRequest(BaseModel):
    """简历解析请求"""
    file_id: str = Field(..., description="文件ID")
    file_name: str = Field(..., description="文件名")
    auto_create: bool = Field(default=True, description="是否自动创建人才档案")


class ResumeParseResponse(BaseModel):
    """简历解析响应"""
    talent_data: Optional[dict] = Field(None, description="解析的人才数据（原始抽取结果，字段可能不完整）")
    confidence: float = Field(..., description="解析置信度", ge=0, le=1)
    raw_text: Optional[str] = Field(None, description="原始文本")
    warnings: List[str] = Field(default=[], description="警告信息")
    created_talent_id: Optional[int] = Field(None, description="自动建档后的人才ID（未建档则为空）")
    merged_existing: bool = Field(False, description="手机号或邮箱冲突时是否已并入现有档案")
    merge_message: Optional[str] = Field(None, description="冲突并入时的提示信息")


class TalentSearchRequest(BaseModel):
    """人才搜索请求"""
    query: Optional[str] = Field(None, description="搜索关键词")
    tags: Optional[List[str]] = Field(None, description="标签过滤")
    education: Optional[EducationLevel] = Field(None, description="学历过滤")
    min_experience: Optional[int] = Field(None, ge=0, description="最小工作年限")
    max_experience: Optional[int] = Field(None, ge=0, description="最大工作年限")
    status: Optional[TalentStatus] = Field(None, description="状态过滤")
    department_id: Optional[int] = Field(None, description="部门过滤")
    use_vector_search: bool = Field(default=False, description="是否使用向量搜索")
    page: int = Field(default=1, ge=1, description="页码")
    page_size: int = Field(default=10, ge=1, le=100, description="每页大小")


# 移除遗留的 TalentTagCreate / TalentPoolCreate 等 schema：
# 这些关联的 ORM 模型（talent_tags / talent_pools）已不再使用，
# 改用 talents.tags JSON 字段存储。如未来需标签管理 UI 可重新启用。
