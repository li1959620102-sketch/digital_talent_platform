"""
数据看板API路由（P0：大数据可视化决策看板）
基于真实数据库聚合统计，支持大屏展示与多维分析。
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, case
from typing import Optional

from app.core.database import get_mysql_session
from app.schemas.common import ResponseModel
from app.models.talent import Talent, TalentStatus
from app.models.position import JobPosition, PositionStatus
from app.models.assessment import AssessmentResult, AssessmentTask
from app.models.training import Course, LearningRecord, ExaminationRecord
from app.models.position import MatchRecord
from app.models.permission import User
from app.core.rbac import PermCode, require_permission_or_403

router = APIRouter()

# ── P0 安全加固：看板承载核心经营统计，禁止匿名访问 ──
AUTH_DASHBOARD_VIEW = require_permission_or_403(PermCode.DASHBOARD_VIEW)


@router.get("/overview", response_model=ResponseModel, summary="数据概览")
async def get_overview(db: Session = Depends(get_mysql_session),
    current_user: User = Depends(AUTH_DASHBOARD_VIEW)):
    """总体概览：人才总量、岗位数、测评数、培训数、匹配数等"""
    total_talents = db.query(func.count(Talent.id)).scalar() or 0
    active_talents = db.query(func.count(Talent.id)).filter(
        Talent.status == TalentStatus.ACTIVE).scalar() or 0
    reserve_talents = db.query(func.count(Talent.id)).filter(
        Talent.status == TalentStatus.RESERVE).scalar() or 0
    total_positions = db.query(func.count(JobPosition.id)).scalar() or 0
    open_positions = db.query(func.count(JobPosition.id)).filter(
        JobPosition.status == PositionStatus.OPEN).scalar() or 0
    total_assessments = db.query(func.count(AssessmentResult.id)).scalar() or 0
    total_courses = db.query(func.count(Course.id)).scalar() or 0
    total_matches = db.query(func.count(MatchRecord.id)).scalar() or 0

    data = {
        "total_talents": total_talents,
        "active_talents": active_talents,
        "reserve_talents": reserve_talents,
        "total_positions": total_positions,
        "open_positions": open_positions,
        "total_assessments": total_assessments,
        "total_courses": total_courses,
        "total_matches": total_matches
    }
    return ResponseModel(code=200, message="获取成功", data=data)


@router.get("/talent-structure", response_model=ResponseModel, summary="人才结构分析")
async def get_talent_structure(db: Session = Depends(get_mysql_session),
    current_user: User = Depends(AUTH_DASHBOARD_VIEW)):
    """人才结构：按学历、状态、性别、工作年限分布"""
    by_status_raw = dict(
        (str(s[0].value if hasattr(s[0], 'value') else s[0] or '未知'), s[1]) for s in
        db.query(Talent.status, func.count(Talent.id)).group_by(Talent.status).all()
    )
    by_education_raw = dict(
        (str(e[0].value if hasattr(e[0], 'value') else e[0] or '未知'), e[1]) for e in
        db.query(Talent.education, func.count(Talent.id)).group_by(Talent.education).all()
    )
    by_gender_raw = dict(
        (str(g[0].value if hasattr(g[0], 'value') else g[0] or '未知'), g[1]) for g in
        db.query(Talent.gender, func.count(Talent.id)).group_by(Talent.gender).all()
    )

    # 工作年限分布在数据库端聚合，避免上万级人才记录全部加载到 API 进程。
    exp_bucket = case(
        (func.coalesce(Talent.experience_years, 0) <= 2, "0-2年"),
        (Talent.experience_years <= 5, "3-5年"),
        (Talent.experience_years <= 10, "6-10年"),
        else_="10年以上",
    )
    exp_buckets = {"0-2年": 0, "3-5年": 0, "6-10年": 0, "10年以上": 0}
    for bucket, count in db.query(exp_bucket, func.count(Talent.id)).group_by(exp_bucket).all():
        exp_buckets[bucket] = count

    data = {
        "by_status": by_status_raw,
        "by_education": by_education_raw,
        "by_gender": by_gender_raw,
        "by_experience": exp_buckets,
    }
    return ResponseModel(code=200, message="获取成功", data=data)


@router.get("/skill-distribution", response_model=ResponseModel, summary="技能分布")
async def get_skill_distribution(db: Session = Depends(get_mysql_session),
    current_user: User = Depends(AUTH_DASHBOARD_VIEW)):
    """技能分布：聚合所有人才的技能标签"""
    talents = db.query(Talent.skills_certificates).all()
    skill_counter = {}
    for (skills,) in talents:
        if not skills:
            continue
        for s in skills:
            name = s.get("name") if isinstance(s, dict) else str(s)
            if name:
                skill_counter[name] = skill_counter.get(name, 0) + 1
    # 取前20
    top = sorted(skill_counter.items(), key=lambda x: x[1], reverse=True)[:20]
    data = {
        "skill_distribution": [{"skill": k, "count": v} for k, v in top],
        "total_skills": len(skill_counter)
    }
    return ResponseModel(code=200, message="获取成功", data=data)


@router.get("/assessment-statistics", response_model=ResponseModel, summary="测评统计")
async def get_assessment_statistics(db: Session = Depends(get_mysql_session),
    current_user: User = Depends(AUTH_DASHBOARD_VIEW)):
    """测评统计：测评次数、平均分、合格率（合格 = 分数 >= 60）"""
    total = db.query(func.count(AssessmentResult.id)).scalar() or 0
    avg_score = db.query(func.avg(AssessmentResult.total_score)).scalar()
    avg_score = float(avg_score) if avg_score is not None else 0.0
    # 合格以分数 >= 60 判定（status 字段历史值可能是 completed/passed/failed，统一用分数）
    passed = db.query(func.count(AssessmentResult.id)).filter(
        AssessmentResult.total_score >= 60).scalar() or 0
    pass_rate = (passed / total * 100) if total else 0.0
    data = {
        "total_assessments": total,
        "average_score": round(avg_score, 2),
        "passed_count": passed,
        "pass_rate": round(pass_rate, 2)
    }
    return ResponseModel(code=200, message="获取成功", data=data)


@router.get("/training-statistics", response_model=ResponseModel, summary="培训统计")
async def get_training_statistics(db: Session = Depends(get_mysql_session),
    current_user: User = Depends(AUTH_DASHBOARD_VIEW)):
    """培训统计：课程数、学习完成率、考核通过率"""
    total_courses = db.query(func.count(Course.id)).scalar() or 0
    total_learning = db.query(func.count(LearningRecord.id)).scalar() or 0
    completed_learning = db.query(func.count(LearningRecord.id)).filter(
        LearningRecord.status == "completed").scalar() or 0
    completion_rate = (completed_learning / total_learning * 100) if total_learning else 0.0
    total_exam = db.query(func.count(ExaminationRecord.id)).scalar() or 0
    passed_exam = db.query(func.count(ExaminationRecord.id)).filter(
        ExaminationRecord.passed == True).scalar() or 0
    exam_pass_rate = (passed_exam / total_exam * 100) if total_exam else 0.0
    data = {
        "total_courses": total_courses,
        "total_learning": total_learning,
        "completed_learning": completed_learning,
        "completion_rate": round(completion_rate, 2),
        "total_examinations": total_exam,
        "exam_pass_rate": round(exam_pass_rate, 2)
    }
    return ResponseModel(code=200, message="获取成功", data=data)


@router.get("/matching-statistics", response_model=ResponseModel, summary="匹配统计")
async def get_matching_statistics(db: Session = Depends(get_mysql_session),
    current_user: User = Depends(AUTH_DASHBOARD_VIEW)):
    """匹配统计：匹配次数、平均匹配度"""
    total = db.query(func.count(MatchRecord.id)).scalar() or 0
    avg_score = db.query(func.avg(MatchRecord.match_score)).scalar()
    avg_score = float(avg_score) if avg_score is not None else 0.0
    high_match = db.query(func.count(MatchRecord.id)).filter(
        MatchRecord.match_score >= 85).scalar() or 0
    data = {
        "total_matches": total,
        "average_match_score": round(avg_score, 2),
        "high_match_count": high_match
    }
    return ResponseModel(code=200, message="获取成功", data=data)


@router.get("/alerts", response_model=ResponseModel, summary="智能预警")
async def get_alerts(db: Session = Depends(get_mysql_session),
    current_user: User = Depends(AUTH_DASHBOARD_VIEW)):
    """智能预警：岗位缺口、培训滞后、测评异常——统一返回 alerts 数组(供前端列表渲染)"""
    from datetime import datetime, timedelta

    alerts: list = []
    now = datetime.now()

    # 1. 岗位缺口：招聘中但未满编（按缺口大小分级）
    open_positions = db.query(JobPosition).filter(
        JobPosition.status == PositionStatus.OPEN).all()
    for p in open_positions:
        gap = (p.headcount or 0) - (p.filled_count or 0)
        if gap > 0:
            level = "critical" if gap >= 5 else ("warning" if gap >= 2 else "info")
            alerts.append({
                "level": level,
                "type": "position_gap",
                "title": "岗位缺口预警",
                "detail": f"【{p.position_name}】招聘缺口 {gap} 人（计划 {p.headcount} / 已招 {p.filled_count}）",
                "position_id": p.id,
                "gap": gap,
                "created_at": (now - timedelta(hours=2, minutes=alerts.__len__())).strftime("%Y-%m-%d %H:%M"),
            })

    # 2. 培训滞后：学习计划未开始
    pending_count = db.query(func.count(LearningRecord.id)).filter(
        LearningRecord.status == "not_started").scalar() or 0
    if pending_count > 0:
        alerts.append({
            "level": "warning",
            "type": "training_lag",
            "title": "培训滞后预警",
            "detail": f"当前有 {pending_count} 条学习记录处于「未开始」状态，请及时跟进",
            "created_at": now.strftime("%Y-%m-%d %H:%M"),
        })

    # 3. 测评异常：不合格率高（合格 = 分数 >= 60）
    total_assess = db.query(func.count(AssessmentResult.id)).scalar() or 0
    passed_assess = db.query(func.count(AssessmentResult.id)).filter(
        AssessmentResult.total_score >= 60).scalar() or 0
    if total_assess > 0:
        fail_rate = round((1 - passed_assess / total_assess) * 100, 1) if total_assess else 0
        if fail_rate >= 40:
            alerts.append({
                "level": "critical",
                "type": "assessment_anomaly",
                "title": "测评异常预警",
                "detail": f"测评不合格率达 {fail_rate}%（{total_assess - passed_assess}/{total_assess}），建议优化试题或加强培训",
                "created_at": now.strftime("%Y-%m-%d %H:%M"),
            })

    # 按级别排序：critical > warning > info
    level_order = {"critical": 0, "warning": 1, "info": 2}
    alerts.sort(key=lambda x: level_order.get(x.get("level", "info"), 3))

    data = {
        "alerts": alerts,
        "total": len(alerts),
        "critical_count": sum(1 for a in alerts if a["level"] == "critical"),
        "warning_count": sum(1 for a in alerts if a["level"] == "warning"),
        "info_count": sum(1 for a in alerts if a["level"] == "info"),
    }
    return ResponseModel(code=200, message="获取成功", data=data)
