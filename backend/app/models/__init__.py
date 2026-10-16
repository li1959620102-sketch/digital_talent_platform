"""
模型导出
"""
from app.models.talent import (
    Talent,
    Organization,
    # 移除遗留表 talent_tags / talent_tag_relations（改用 talents.tags JSON 字段）
)
from app.models.position import (
    JobPosition,
    MatchRecord,
    # 移除遗留表 talent_pools / talent_pool_relations
)
from app.models.assessment import (
    Question, 
    TestPaper, 
    AssessmentTask, 
    AssessmentResult,
    QuestionType,
    AssessmentStatus,
    CapabilityLevel
)
from app.models.training import (
    Course, 
    TrainingPlan, 
    LearningRecord, 
    ExaminationRecord,
    CourseType,
    CourseCategory,
    TrainingStatus,
    LearningStatus
)
from app.models.permission import (
    User, 
    Role, 
    Permission, 
    UserRole, 
    RolePermission,
    AuditLog,
    DataPermission,
    UserStatus,
    PermissionType
)
from app.models.knowledge import (
    KnowledgeFile,
    KnowledgeChunk
)

__all__ = [
    # 人才
    "Talent",
    "Organization",

    # 岗位
    "JobPosition",
    "MatchRecord",
    
    # 测评
    "Question",
    "TestPaper",
    "AssessmentTask",
    "AssessmentResult",
    "QuestionType",
    "AssessmentStatus",
    "CapabilityLevel",
    
    # 培训
    "Course",
    "TrainingPlan",
    "LearningRecord",
    "ExaminationRecord",
    "CourseType",
    "CourseCategory",
    "TrainingStatus",
    "LearningStatus",
    
    # 权限
    "User",
    "Role",
    "Permission",
    "UserRole",
    "RolePermission",
    "AuditLog",
    "DataPermission",
    "UserStatus",
    "PermissionType",
    "KnowledgeFile",
    "KnowledgeChunk",
]
