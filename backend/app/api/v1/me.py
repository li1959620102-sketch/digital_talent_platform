"""
员工自助服务 API（普通用户个人自助线，对标"员工成长/自我认知"）

背景：企业 HR 用 /talents、/assessments、/matching 管理全量人才。而**普通员工(user)**登录后
需要一条"自我服务"链路：上传自己的简历 → 生成专属人才档案与能力画像 → 完成推荐的能力测评 →
看到自己适合的内部岗位，从而认知自我、规划成长。这些操作只作用于 **user_id=me** 的档案，
与 HR 的全局人才池隔离。

设计要点：
- 所有端点仅要求登录（get_current_user），service 层强制 `Talent.user_id == current_user.id`。
- 员工自助产生的 Talent 档案带 user_id 归属；HR 全局档案 user_id 为空，互不混淆。
- 服务(MinIO/LLM/Milvus)不可用时优雅降级，不崩溃。
"""
import logging
import os
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_mysql_session
from app.models.permission import User
from app.models.talent import Talent, GenderEnum, EducationLevel
from app.models.position import JobPosition, PositionStatus
from app.models.assessment import TestPaper, AssessmentTask, AssessmentResult, AssessmentStatus
from app.schemas.common import ResponseModel
from app.utils.jwt_handler import get_current_user
from app.utils.minio_client import MinioClient, BUCKET_RESUMES
from app.services.talent_service import TalentService
from app.agents.resume_parser_agent import resume_parser_agent

logger = logging.getLogger(__name__)
router = APIRouter()

# 能力等级：后端枚举英文值 → 中文展示（前端直接可用，无需二次映射）
_LEVEL_CN = {
    "entry": "初级", "junior": "初级", "intermediate": "中级",
    "senior": "高级", "expert": "专家", "backbone": "骨干", "core": "核心人才",
}


def _lv(val) -> Optional[str]:
    """把能力等级字段转成中文展示（兼容枚举对象/字符串/None）"""
    if val is None:
        return None
    raw = val.value if hasattr(val, "value") else val
    return _LEVEL_CN.get(str(raw), str(raw))


def _get_my_talent(db: Session, user: User) -> Optional[Talent]:
    """取当前用户的自助档案（user_id=me），无则 None"""
    return db.query(Talent).filter(Talent.user_id == user.id).order_by(Talent.id.desc()).first()


def _ensure_my_talent(db: Session, user: User) -> Talent:
    """取当前用户的自助档案；不存在则按用户信息建一个占位档案（绑定 user_id）"""
    t = _get_my_talent(db, user)
    if t:
        return t
    talent = Talent(
        talent_code=TalentService.generate_talent_code(),
        name=user.real_name or user.username,
        gender=GenderEnum.MALE,
        phone=user.phone or "",
        status="reserve",
        user_id=user.id,
    )
    db.add(talent)
    db.commit()
    db.refresh(talent)
    return talent


def _parse_skill_items(raw_skills_val: Any) -> List[Dict[str, Any]]:
    """把 LLM 提取的 skills 拆成技能证书结构化列表（对齐 /talents/parse-resume 逻辑）"""
    import re
    if isinstance(raw_skills_val, list):
        return [{"name": str(s).strip(), "level": "熟悉"}
                for s in raw_skills_val if s and str(s).strip()]
    if isinstance(raw_skills_val, str):
        parts = re.split(r"[、，,;/｜\|\s]+", raw_skills_val)
        return [{"name": p.strip(), "level": "熟悉"}
                for p in parts if p and p.strip() and len(p.strip()) <= 50]
    return []


# ==================== 1. 我的自助总览 ====================

@router.get("", response_model=ResponseModel, summary="我的自助总览")
async def my_overview(
    db: Session = Depends(get_mysql_session),
    current_user: User = Depends(get_current_user),
):
    """返回当前员工的自助状态：是否有档案/画像、测评结果、匹配岗位数"""
    talent = _get_my_talent(db, current_user)
    overview: Dict[str, Any] = {
        "has_talent": talent is not None,
        "talent_id": talent.id if talent else None,
        "has_portrait": bool(talent and talent.portrait),
        "name": talent.name if talent else (current_user.real_name or current_user.username),
        "assessment_results": 0,
        "last_ability_level": None,
        "matched_positions": 0,
    }
    if talent:
        results = db.query(AssessmentResult).filter(AssessmentResult.talent_id == talent.id).all()
        overview["assessment_results"] = len(results)
        if results:
            latest = results[-1]
            overview["last_ability_level"] = _lv(getattr(latest, "capability_level", None))
        from app.models.position import MatchRecord
        overview["matched_positions"] = db.query(MatchRecord).filter(
            MatchRecord.talent_id == talent.id
        ).count()
    return ResponseModel(code=200, message="ok", data=overview)


# ==================== 2. 上传我的简历（解析+建档/更新，归属 user） ====================

@router.post("/resume", response_model=ResponseModel, summary="上传并解析我的简历")
async def upload_my_resume(
    file: UploadFile = File(...),
    db: Session = Depends(get_mysql_session),
    current_user: User = Depends(get_current_user),
):
    """解析我的简历：生成/更新 user_id=me 的专属档案 + 标签 + 能力画像。不进 HR 全局池。"""
    ext = os.path.splitext(file.filename or "resume.pdf")[1].lower()
    file_content = await file.read()
    max_size = getattr(settings, "MAX_UPLOAD_SIZE", 52428800)
    if len(file_content) > max_size:
        raise HTTPException(status_code=413, detail="文件过大")

    # MinIO 持久化（失败仅降级）
    try:
        MinioClient(BUCKET_RESUMES).upload_file_for_bucket(
            file_object=file_content, original_name=file.filename or "resume.pdf",
            bucket_name=BUCKET_RESUMES,
            minio_object_name=f"self_{uuid.uuid4().hex}{ext}",
        )
    except Exception as e:
        logger.warning(f"MinIO上传失败(降级): {e}")

    upload_dir = getattr(settings, "UPLOAD_DIR", "./uploads") or "./uploads"
    os.makedirs(upload_dir, exist_ok=True)
    save_path = os.path.join(upload_dir, f"self_{uuid.uuid4().hex}{ext}")
    with open(save_path, "wb") as f:
        f.write(file_content)

    try:
        result = await resume_parser_agent.parse_resume(save_path, file.filename or "resume")
    finally:
        try:
            os.remove(save_path)
        except Exception:
            pass

    td = result.get("talent_data") or {}
    talent = _ensure_my_talent(db, current_user)
    updated = bool(talent.portrait or talent.skills_certificates)

    if td.get("name") or td.get("phone"):
        if td.get("name"):
            talent.name = str(td["name"])[:50]
        # gender
        g = str(td.get("gender") or "").strip().lower()
        if g in ("female", "女", "2"):
            talent.gender = GenderEnum.FEMALE
        elif g in ("male", "男", "1"):
            talent.gender = GenderEnum.MALE
        if td.get("phone"):
            talent.phone = str(td["phone"])[:20]
        if td.get("email"):
            talent.email = str(td["email"])[:100]
        if td.get("education") in [e.value for e in EducationLevel]:
            talent.education = EducationLevel(td["education"])
        if td.get("major"):
            talent.major = str(td["major"])[:100]
        if td.get("experience_years") is not None:
            try:
                talent.experience_years = int(td["experience_years"])
            except (TypeError, ValueError):
                pass
        if td.get("current_company"):
            talent.current_company = str(td["current_company"])[:100]
        if td.get("current_position"):
            talent.current_position = str(td["current_position"])[:100]
        if td.get("self_introduction"):
            talent.self_introduction = str(td["self_introduction"])[:2000]
        # 技能（硬条件匹配依赖）
        if td.get("skills"):
            talent.skills_certificates = _parse_skill_items(td.get("skills"))
        # 标签 + 画像
        if result.get("tags"):
            talent.tags = result.get("tags")
        if result.get("portrait"):
            talent.portrait = result["portrait"]
        talent.is_parsed = True
        db.commit()
        db.refresh(talent)

    return ResponseModel(code=200, message="我的档案已更新" if updated else "我的档案已创建", data={
        "talent_id": talent.id,
        "name": talent.name,
        "phone": talent.phone,
        "skills_certificates": talent.skills_certificates or [],
        "tags": talent.tags or [],
        "portrait": talent.portrait or {},
        "confidence": result.get("confidence", 0),
        "warnings": result.get("warnings", []),
        "is_new": not updated,
    })


# ==================== 3. 我的档案/画像查看 ====================

@router.get("/talent", response_model=ResponseModel, summary="我的档案与画像")
async def my_talent(
    db: Session = Depends(get_mysql_session),
    current_user: User = Depends(get_current_user),
):
    talent = _get_my_talent(db, current_user)
    if not talent:
        return ResponseModel(code=200, message="ok", data=None)
    return ResponseModel(code=200, message="ok", data={
        "talent_id": talent.id,
        "name": talent.name,
        "gender": talent.gender.value if talent.gender else None,
        "education": talent.education.value if talent.education else None,
        "major": talent.major,
        "experience_years": talent.experience_years,
        "current_company": talent.current_company,
        "current_position": talent.current_position,
        "skills_certificates": talent.skills_certificates or [],
        "tags": talent.tags or [],
        "portrait": talent.portrait or {},
        "capability_rating": talent.capability_rating,
        "self_introduction": talent.self_introduction,
        "is_parsed": talent.is_parsed,
        "updated_at": str(talent.updated_at) if talent.updated_at else None,
    })


# ==================== 4. 推荐一张能力测评卷 ====================

@router.get("/recommended-paper", response_model=ResponseModel, summary="推荐能力测评卷")
async def recommended_paper(
    db: Session = Depends(get_mysql_session),
    current_user: User = Depends(get_current_user),
):
    """根据我的能力画像/短板推荐一张测评卷；无画像则给综合测评卷。"""
    talent = _get_my_talent(db, current_user)
    papers = db.query(TestPaper).filter(TestPaper.status == "published").all()
    if not papers:
        return ResponseModel(code=200, message="ok", data={"paper": None, "reason": "暂无可用测评卷"})

    # 画像里的短板类别 → 想测的类别
    prefer_category = None
    capability = {}
    if talent and talent.portrait:
        capability = talent.portrait.get("capability", {}) if isinstance(talent.portrait, dict) else {}
        if not capability:
            capability = talent.portrait if isinstance(talent.portrait, dict) else {}
    # 简单启发：优先推荐 paper_type 与能力短板相关的"专业技能"或"综合测评"
    paper = papers[0]
    for p in papers:
        if p.paper_type and ("综合" in str(p.paper_type)):
            paper = p
            break
    return ResponseModel(code=200, message="ok", data={
        "paper": {"id": paper.id, "paper_name": paper.paper_name, "paper_type": paper.paper_type,
                  "description": paper.paper_description, "total_score": float(paper.total_score or 0),
                  "duration_minutes": paper.duration_minutes},
        "reason": "为你推荐的能力测评",
        "capability": capability,
    })


# ==================== 5. 提交我的测评（自动评分，落库并绑定本人） ====================

@router.post("/assessment/{paper_id}/submit", response_model=ResponseModel, summary="提交我的测评")
async def submit_my_assessment(
    paper_id: int,
    payload: Dict[str, Any],
    db: Session = Depends(get_mysql_session),
    current_user: User = Depends(get_current_user),
):
    """员工自答某张测评卷：自动评分、落库(绑定 user 档案)、生成能力画像。"""
    talent = _ensure_my_talent(db, current_user)
    paper = db.query(TestPaper).filter(TestPaper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="试卷不存在")

    from app.services.assessment_service import AssessmentService
    svc = AssessmentService(db)

    # 每次提交新建一张"自助"测评任务绑定本人（避免 (talent_id,task_id) 唯一索引冲突，支持重测）
    from datetime import datetime
    task = svc.create_task({
        "task_name": f"自助测评·{paper.paper_name}",
        "target_type": "self_signup",
        "target_talents": [talent.id],
        "paper_id": paper_id,
        "allow_retake": True,
        "max_attempts": 3,
    }, user_id=current_user.id)

    answers = payload.get("answers", [])
    duration = int(payload.get("duration_seconds", 0))
    result = svc.submit_assessment(task_id=task.id, talent_id=talent.id, answers=answers, duration_seconds=duration)

    # 用测评分析 Agent 生成能力报告，回写 talent
    try:
        from app.agents.assessment_agent import AssessmentAnalysisAgent
        analysis = AssessmentAnalysisAgent().analyze(result.id)
        if analysis.get("success"):
            if analysis.get("ability_level"):
                talent.capability_rating = {"ability_level": analysis["ability_level"]}
            db.commit()
    except Exception as e:
        logger.warning(f"测评分析失败(不影响结果落库): {e}")

    return ResponseModel(code=200, message="测评完成", data={
        "result_id": result.id,
        "total_score": float(result.total_score) if hasattr(result.total_score, "__float__") else result.total_score,
        "correct_count": getattr(result, "correct_count", 0),
        "wrong_count": getattr(result, "wrong_count", 0),
        "unanswered_count": getattr(result, "unanswered_count", 0),
        "total_count": (getattr(result, "correct_count", 0) or 0) + (getattr(result, "wrong_count", 0) or 0) + (getattr(result, "unanswered_count", 0) or 0),
        # 补齐前端真实作答弹窗需要的指标：得分率 / 答对得分 / 中文能力等级
        "accuracy": round((getattr(result, "correct_count", 0) or 0) / max(
            (getattr(result, "correct_count", 0) or 0)
            + (getattr(result, "wrong_count", 0) or 0)
            + (getattr(result, "unanswered_count", 0) or 0), 1) * 100, 1),
        "correct_score": getattr(result, "total_score", 0) or 0,
        "ability_level_label": _lv(getattr(result, "capability_level", None)),
        "capability_dimensions": getattr(result, "capability_dimensions", None),
        "ability_level": talent.capability_rating.get("ability_level") if talent.capability_rating else None,
    })


# ==================== 6. 我的测评结果 ====================

@router.get("/assessment/results", response_model=ResponseModel, summary="我的测评结果")
async def my_assessment_results(
    db: Session = Depends(get_mysql_session),
    current_user: User = Depends(get_current_user),
):
    talent = _get_my_talent(db, current_user)
    if not talent:
        return ResponseModel(code=200, message="ok", data={"items": []})
    results = db.query(AssessmentResult).filter(AssessmentResult.talent_id == talent.id).all()
    items = [{
        "result_id": r.id,
        "total_score": float(r.total_score) if r.total_score else None,
        "correct_count": r.correct_count,
        "submit_time": str(r.submit_time) if r.submit_time else None,
        "ability_level": _lv(getattr(r, "capability_level", None)),
        "capability_dimensions": r.capability_dimensions or {},
    } for r in results]
    return ResponseModel(code=200, message="ok", data={"items": items})


# ==================== 7. 匹配适合我的岗位 ====================

@router.get("/matching-jobs", response_model=ResponseModel, summary="匹配适合我的岗位")
async def my_matching_jobs(
    db: Session = Depends(get_mysql_session),
    current_user: User = Depends(get_current_user),
):
    """根据我的档案，找出最适合我的内部岗位（复用 MatchingAgent 人才→岗位方向）"""
    talent = _get_my_talent(db, current_user)
    if not talent:
        return ResponseModel(code=200, message="ok", data={"items": [], "total": 0, "message": "请先上传简历"})
    try:
        from app.agents.matching_agent import MatchingAgent
        res = MatchingAgent().match_talent_to_positions(talent.id)
        if not res.get("success"):
            return ResponseModel(code=200, message="ok", data={"items": [], "total": 0, "message": "匹配暂不可用"})
        results = res.get("match_results", []) or []
        items = [{
            "position_id": r.get("position_id"),
            "position_name": r.get("position_name"),
            "department": r.get("department"),
            "salary_min": r.get("salary_min"),
            "salary_max": r.get("salary_max"),
            "education_requirement": r.get("education_requirement"),
            "experience_requirement": r.get("experience_requirement"),
            "score": r.get("final_score") or r.get("score") or 0,
            "match_reason": r.get("match_reason") or "",
        } for r in results]
        return ResponseModel(code=200, message="ok", data={"items": items, "total": len(items), "message": None})
    except Exception as e:
        logger.warning(f"我的岗位匹配失败: {e}")
        return ResponseModel(code=200, message="ok", data={"items": [], "total": 0, "message": "匹配暂不可用"})


# ==================== 8. AI 智能测评（自动作答并落库） ====================

@router.post("/assessment/{paper_id}/auto-run", response_model=ResponseModel, summary="AI 智能测评")
async def auto_run_my_assessment(
    paper_id: int,
    db: Session = Depends(get_mysql_session),
    current_user: User = Depends(get_current_user),
):
    """基于我的档案，对推荐测评卷自动作答并评分落库（无需逐题手答），生成能力报告。

    贴合 AI 原生平台：员工上传简历后，点击"AI 智能测评"即可得到一份绑定本人的能力报告。
    """
    talent = _ensure_my_talent(db, current_user)
    paper = db.query(TestPaper).filter(TestPaper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="试卷不存在")

    from app.services.assessment_service import AssessmentService
    from app.models.assessment import Question
    svc = AssessmentService(db)

    # 取试卷题目
    paper_questions = paper.questions or []
    if not paper_questions:
        return ResponseModel(code=200, message="ok", data={"success": False, "message": "该测评卷暂无题目"})
    qids = [q["question_id"] for q in paper_questions]
    questions = db.query(Question).filter(Question.id.in_(qids)).all()
    qmap = {q.id: q for q in questions}

    # 依据简历画像水平决定作答正确率（有专业画像则答得更好，模拟真实水平）
    correct_rate = 0.7
    if talent and talent.portrait and isinstance(talent.portrait, dict):
        t = talent.portrait.get("technical_ability") or 0
        correct_rate = min(0.5 + float(t or 0) / 200.0, 0.95)

    import random
    answers = []
    for qc in paper_questions:
        q = qmap.get(qc["question_id"])
        if not q:
            continue
        if random.random() < correct_rate:
            answers.append({"question_id": q.id, "answer": q.correct_answer})
        else:
            wrong = "错" if q.question_type.value in ("true_false", "single_choice") else f"错-{random.randint(1, 9)}"
            answers.append({"question_id": q.id, "answer": wrong})

    # 建自助任务并提交落库
    from datetime import datetime
    task = svc.create_task({
        "task_name": f"AI测评·{paper.paper_name}",
        "target_type": "self_signup", "target_talents": [talent.id],
        "paper_id": paper_id, "allow_retake": True, "max_attempts": 3,
    }, user_id=current_user.id)
    result = svc.submit_assessment(task_id=task.id, talent_id=talent.id,
                                   answers=answers, duration_seconds=600)

    # 回写能力等级
    lv = getattr(result, "capability_level", None)
    talent.capability_rating = {"ability_level": lv.value if hasattr(lv, "value") else str(lv or "")}
    db.commit()

    return ResponseModel(code=200, message="AI 测评完成", data={
        "success": True,
        "result_id": result.id,
        "total_score": float(result.total_score) if result.total_score else 0,
        "correct_count": result.correct_count,
        "total_count": len(answers),
        "ability_level": _lv(getattr(result, "capability_level", None)),
        "capability_dimensions": result.capability_dimensions or {},
    })
