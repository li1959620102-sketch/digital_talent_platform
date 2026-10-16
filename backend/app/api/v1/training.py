"""
培训管理API路由（P0：数字化培训赋能）
实现课程管理、学习计划、在线学习记录、课后考核。
"""
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional, Dict, Any

from app.core.database import get_mysql_session
from app.schemas.common import ResponseModel
from app.core.rbac import PermCode, require_permission_or_403
from app.models.training import Course, TrainingPlan, LearningRecord, ExaminationRecord

router = APIRouter()
AUTH_TRAINING_VIEW = require_permission_or_403(PermCode.TRAINING_VIEW)
AUTH_TRAINING_MANAGE = require_permission_or_403(PermCode.TRAINING_MANAGE)


def _gen_code(prefix: str) -> str:
    return f"{prefix}{int(datetime.now().timestamp()*1000)}{uuid.uuid4().hex[:6].upper()}"


# ── 课程枚举翻译：把存储的英文 key 翻成中文给前端展示 ──────────────
_COURSE_CATEGORY_CN = {
    "position": "按岗位", "skill": "按技能", "level": "按层级", "profession": "按专业",
}
_COURSE_TYPE_CN = {
    "text_image": "图文", "video": "视频", "document": "文档",
    "courseware": "课件", "live": "直播", "exam": "考试",
}
_COURSE_STATUS_CN = {
    "draft": "草稿", "published": "已发布", "in_progress": "进行中",
    "completed": "已完成", "cancelled": "已取消", "active": "已上架",
    "offline": "已下架",
}

def _course_category_label(v):
    return _COURSE_CATEGORY_CN.get(v or "", v or "-")

def _course_type_label(v):
    return _COURSE_TYPE_CN.get(v or "", v or "-")

def _course_status_label(v):
    return _COURSE_STATUS_CN.get(v or "", v or "-")


@router.get("/courses", response_model=ResponseModel, summary="课程列表")
async def list_courses(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    course_category: Optional[str] = None,
    db: Session = Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_TRAINING_VIEW)
):
    """课程列表（支持按分类过滤）"""
    query = db.query(Course)
    if course_category:
        query = query.filter(Course.course_category == course_category)
    total = query.count()
    items = query.order_by(Course.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    data = [{
        "id": c.id, "course_code": c.course_code, "course_name": c.course_name,
        "course_category": c.course_category,
        "course_category_label": _course_category_label(c.course_category),
        "course_type": c.course_type,
        "course_type_label": _course_type_label(c.course_type),
        "duration_minutes": c.duration_minutes, "instructor": c.instructor,
        "tags": c.tags, "status": c.status,
        "status_label": _course_status_label(c.status),
        "rating": float(c.rating) if c.rating is not None else None,
        "rating_count": c.rating_count
    } for c in items]
    total_pages = (total + page_size - 1) // page_size
    return ResponseModel(code=200, message="获取成功", data={
        "items": data, "total": total, "page": page, "page_size": page_size, "total_pages": total_pages
    })


@router.get("/plans", response_model=ResponseModel, summary="学习计划列表")
async def list_training_plans(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_TRAINING_VIEW)
):
    """学习计划列表"""
    query = db.query(TrainingPlan)
    total = query.count()
    items = query.order_by(TrainingPlan.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    data = [{
        "id": p.id, "plan_code": p.plan_code, "plan_name": p.plan_name,
        "target_type": p.target_type, "target_talents": p.target_talents,
        "courses": p.courses, "start_time": p.start_time, "end_time": p.end_time,
        "examination_required": p.examination_required, "status": p.status
    } for p in items]
    total_pages = (total + page_size - 1) // page_size
    return ResponseModel(code=200, message="获取成功", data={
        "items": data, "total": total, "page": page, "page_size": page_size, "total_pages": total_pages
    })


@router.post("/courses", response_model=ResponseModel, summary="创建课程")
async def create_course(
    payload: Dict[str, Any],
    db: Session = Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_TRAINING_MANAGE)
):
    """创建培训课程"""
    name = payload.get("course_name")
    if not name:
        raise HTTPException(status_code=400, detail="course_name 必填")
    course = Course(
        course_code=_gen_code("C"),
        course_name=name,
        course_category=payload.get("course_category"),
        course_type=payload.get("course_type"),
        course_content=payload.get("course_content"),
        course_url=payload.get("course_url"),
        duration_minutes=payload.get("duration_minutes", 0),
        instructor=payload.get("instructor"),
        tags=payload.get("tags", []),
        status=payload.get("status", "published")
    )
    db.add(course)
    db.commit()
    db.refresh(course)
    return ResponseModel(code=200, message="创建成功", data={"id": course.id, "course_code": course.course_code})


@router.get("/courses/{course_id}", response_model=ResponseModel, summary="获取课程详情")
async def get_course(
    course_id: int,
    db: Session = Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_TRAINING_VIEW)
):
    """获取课程详情"""
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")
    return ResponseModel(code=200, message="获取成功", data={
        "id": course.id,
        "course_code": course.course_code,
        "course_name": course.course_name,
        "course_category": course.course_category,
        "course_type": course.course_type,
        "duration_minutes": course.duration_minutes,
        "instructor": course.instructor,
        "tags": course.tags,
        "status": course.status,
        "rating": float(course.rating) if course.rating is not None else None,
        "rating_count": course.rating_count
    })


@router.delete("/courses/{course_id}", response_model=ResponseModel, summary="删除课程")
async def delete_course(
    course_id: int,
    db: Session = Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_TRAINING_MANAGE)
):
    """删除课程"""
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")
    try:
        db.delete(course)
        db.commit()
        return ResponseModel(code=200, message="删除成功", data={"course_id": course_id})
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"删除课程失败: {str(e)}")


@router.post("/courses/batch-delete", response_model=ResponseModel, summary="批量删除课程")
async def batch_delete_courses(
    payload: Dict[str, Any],
    db: Session = Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_TRAINING_MANAGE),
):
    """批量删除课程（整页/跨页删除）"""
    ids = payload.get("ids") or payload.get("course_ids") or []
    if not ids:
        raise HTTPException(status_code=400, detail="ids 必填")
    try:
        deleted = db.query(Course).filter(Course.id.in_([int(i) for i in ids])).delete(synchronize_session=False)
        db.commit()
        return ResponseModel(code=200, message=f"批量删除成功：共删除 {deleted} 条", data={"deleted": deleted})
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"批量删除课程失败: {str(e)}")


@router.delete("/plans/{plan_id}", response_model=ResponseModel, summary="删除学习计划")
async def delete_training_plan(
    plan_id: int,
    db: Session = Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_TRAINING_MANAGE)
):
    """删除学习计划"""
    plan = db.query(TrainingPlan).filter(TrainingPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="学习计划不存在")
    try:
        db.delete(plan)
        db.commit()
        return ResponseModel(code=200, message="删除成功", data={"plan_id": plan_id})
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"删除学习计划失败: {str(e)}")


@router.post("/plans/batch-delete", response_model=ResponseModel, summary="批量删除学习计划")
async def batch_delete_training_plans(
    payload: Dict[str, Any],
    db: Session = Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_TRAINING_MANAGE),
):
    """批量删除学习计划"""
    ids = payload.get("ids") or payload.get("plan_ids") or []
    if not ids:
        raise HTTPException(status_code=400, detail="ids 必填")
    try:
        deleted = db.query(TrainingPlan).filter(TrainingPlan.id.in_([int(i) for i in ids])).delete(synchronize_session=False)
        db.commit()
        return ResponseModel(code=200, message=f"批量删除成功：共删除 {deleted} 条", data={"deleted": deleted})
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"批量删除学习计划失败: {str(e)}")


@router.post("/plans", response_model=ResponseModel, summary="创建学习计划")
async def create_training_plan(
    payload: Dict[str, Any],
    db: Session = Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_TRAINING_MANAGE)
):
    """创建培训学习计划"""
    name = payload.get("plan_name")
    if not name:
        raise HTTPException(status_code=400, detail="plan_name 必填")
    plan = TrainingPlan(
        plan_code=_gen_code("P"),
        plan_name=name,
        target_type=payload.get("target_type", "batch"),
        target_talents=payload.get("target_talents", []),
        courses=payload.get("courses", []),
        start_time=payload.get("start_time"),
        end_time=payload.get("end_time"),
        learning_reminder=payload.get("learning_reminder", True),
        examination_required=payload.get("examination_required", False),
        status=payload.get("status", "published")
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return ResponseModel(code=200, message="创建成功", data={"id": plan.id, "plan_code": plan.plan_code})


@router.post("/learning/start", response_model=ResponseModel, summary="开始学习")
async def start_learning(
    payload: Dict[str, Any],
    db: Session = Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_TRAINING_MANAGE)
):
    """开始学习课程，创建学习记录"""
    talent_id = payload.get("talent_id")
    course_id = payload.get("course_id")
    if not talent_id or not course_id:
        raise HTTPException(status_code=400, detail="talent_id 与 course_id 必填")
    record = LearningRecord(
        record_code=_gen_code("L"),
        talent_id=talent_id,
        course_id=course_id,
        plan_id=payload.get("plan_id"),
        progress=0,
        status="in_progress",
        last_learning_time=datetime.now()
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return ResponseModel(code=200, message="开始学习", data={"id": record.id, "status": record.status})


@router.post("/learning/progress", response_model=ResponseModel, summary="更新学习进度")
async def update_learning_progress(
    payload: Dict[str, Any],
    db: Session = Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_TRAINING_MANAGE)
):
    """更新学习进度，进度100%标记完成"""
    record_id = payload.get("record_id")
    record = db.query(LearningRecord).filter(LearningRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="学习记录不存在")
    progress = payload.get("progress", record.progress)
    record.progress = progress
    if progress >= 100:
        record.status = "completed"
        record.completed_time = datetime.now()
    else:
        record.status = "in_progress"
    record.last_learning_time = datetime.now()
    db.commit()
    return ResponseModel(code=200, message="进度更新", data={"id": record.id, "progress": record.progress, "status": record.status})


@router.post("/examination/start", response_model=ResponseModel, summary="开始考核")
async def start_examination(
    payload: Dict[str, Any],
    db: Session = Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_TRAINING_MANAGE)
):
    """开始课后考核，创建考核记录"""
    talent_id = payload.get("talent_id")
    course_id = payload.get("course_id")
    if not talent_id or not course_id:
        raise HTTPException(status_code=400, detail="talent_id 与 course_id 必填")
    record = ExaminationRecord(
        record_code=_gen_code("E"),
        talent_id=talent_id,
        course_id=course_id,
        plan_id=payload.get("plan_id"),
        score=0,
        passed=False,
        start_time=datetime.now()
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return ResponseModel(code=200, message="开始考核", data={"id": record.id})


@router.post("/examination/submit", response_model=ResponseModel, summary="提交考核")
async def submit_examination(
    payload: Dict[str, Any],
    db: Session = Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_TRAINING_MANAGE)
):
    """提交考核，记录分数与是否通过"""
    record_id = payload.get("record_id")
    record = db.query(ExaminationRecord).filter(ExaminationRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="考核记录不存在")
    score = payload.get("score", 0)
    pass_line = payload.get("pass_line", 60)
    record.score = score
    record.passed = score >= pass_line
    record.submit_time = datetime.now()
    db.commit()
    return ResponseModel(code=200, message="考核提交", data={
        "id": record.id, "score": record.score, "passed": record.passed
    })
