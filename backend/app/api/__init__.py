"""
AI数字化人才平台 - API路由注册
"""
from fastapi import APIRouter
from app.api.v1 import auth, talent, position, assessment, training, matching, dashboard, knowledge, agent, user, skills, me

api_router = APIRouter()

# 注册各模块路由
api_router.include_router(auth.router, prefix="/auth", tags=["认证"])
api_router.include_router(user.router, prefix="/users", tags=["用户管理"])
api_router.include_router(talent.router, prefix="/talents", tags=["人才档案"])
api_router.include_router(position.router, prefix="/positions", tags=["岗位管理"])
api_router.include_router(assessment.router, prefix="/assessments", tags=["测评管理"])
api_router.include_router(training.router, prefix="/training", tags=["培训赋能"])
api_router.include_router(matching.router, prefix="/matching", tags=["岗位匹配"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["数据看板"])
api_router.include_router(knowledge.router, prefix="/knowledge", tags=["知识库"])
api_router.include_router(agent.router, prefix="/agents", tags=["AI智能体"])
api_router.include_router(skills.router, prefix="/skills", tags=["技能编排"])
api_router.include_router(me.router, prefix="/me", tags=["员工自助"])

__all__ = ["api_router"]
