"""
测评管理API路由
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any

from app.core.database import get_mysql_session
from app.schemas.common import ResponseModel, PageModel
from app.services.assessment_service import AssessmentService
from app.core.rbac import PermCode, require_permission_or_403
from app.models.assessment import AssessmentTask, AssessmentResult
from app.models.talent import Talent

router = APIRouter()
AUTH_ASSESSMENT_MANAGE = require_permission_or_403(PermCode.ASSESSMENT_MANAGE)


# ==================== 题库管理 ====================

@router.post("/questions", response_model=ResponseModel, summary="创建题目")
async def create_question(
    question_data: Dict[str, Any],
    db: Session = Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_ASSESSMENT_MANAGE)
):
    """创建题目"""
    try:
        service = AssessmentService(db)
        question = service.create_question(question_data, current_user.id)

        return ResponseModel(
            code=200,
            message="创建题目成功",
            data={
                "id": question.id,
                "question_type": question.question_type.value,
                "question_content": question.question_content,
                "difficulty": question.difficulty
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建题目失败: {str(e)}")


@router.get("/questions", response_model=ResponseModel, summary="题目列表")
async def list_questions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    question_type: Optional[str] = None,
    category: Optional[str] = None,
    difficulty: Optional[str] = None,
    db: Session = Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_ASSESSMENT_MANAGE)
):
    """获取题目列表"""
    try:
        service = AssessmentService(db)
        # 空字符串视为 None（前端可能传 "" 表示不筛选）
        diff_int = int(difficulty) if difficulty and difficulty.strip() else None
        result = service.get_questions(
            page=page,
            page_size=page_size,
            question_type=question_type if question_type and question_type.strip() else None,
            category=category if category and category.strip() else None,
            difficulty=diff_int
        )

        items = [
            {
                "id": q.id,
                "question_type": q.question_type.value,
                "question_content": q.question_content,
                "difficulty": q.difficulty,
                "category": q.question_category,
                "score": q.score_value
            }
            for q in result["items"]
        ]

        total_pages = (result["total"] + result["page_size"] - 1) // result["page_size"]
        return ResponseModel(
            code=200,
            message="获取成功",
            data={
                "items": items,
                "total": result["total"],
                "page": result["page"],
                "page_size": result["page_size"],
                "total_pages": total_pages
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取题目列表失败: {str(e)}")


@router.post("/questions/batch-delete", response_model=ResponseModel, summary="批量删除题目")
async def batch_delete_questions(
    payload: Dict[str, Any],
    db: Session = Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_ASSESSMENT_MANAGE)
):
    """批量删除题目（同时清理引用了该题目的试卷）"""
    from app.models.assessment import Question, TestPaper
    try:
        ids = payload.get("ids") or []
        if not ids or not isinstance(ids, list):
            raise HTTPException(status_code=400, detail="ids 不能为空且必须是数组")
        # 先扫试卷移除引用（避免试题 id 指向已删题目）
        affected_papers = db.query(TestPaper).all()
        id_set = set(int(i) for i in ids)
        for p in affected_papers:
            new_qs = [q for q in (p.questions or [])
                      if (q.get("question_id") if isinstance(q, dict) else None) not in id_set]
            if len(new_qs) != len(p.questions or []):
                p.questions = new_qs
        deleted = db.query(Question).filter(Question.id.in_(ids)).delete(synchronize_session=False)
        db.commit()
        return ResponseModel(code=200, message=f"已删除 {deleted} 道题目", data={"deleted": deleted})
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"批量删除失败: {str(e)}")


@router.post("/papers/batch-delete", response_model=ResponseModel, summary="批量删除试卷")
async def batch_delete_papers(
    payload: Dict[str, Any],
    db: Session = Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_ASSESSMENT_MANAGE)
):
    """批量删除试卷"""
    from app.models.assessment import TestPaper
    try:
        ids = payload.get("ids") or []
        if not ids or not isinstance(ids, list):
            raise HTTPException(status_code=400, detail="ids 不能为空且必须是数组")
        deleted = db.query(TestPaper).filter(TestPaper.id.in_(ids)).delete(synchronize_session=False)
        db.commit()
        return ResponseModel(code=200, message=f"已删除 {deleted} 份试卷", data={"deleted": deleted})
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"批量删除失败: {str(e)}")


# ==================== 试卷管理 ====================

@router.post("/papers", response_model=ResponseModel, summary="创建试卷")
async def create_paper(
    paper_data: Dict[str, Any],
    db: Session = Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_ASSESSMENT_MANAGE)
):
    """创建试卷"""
    try:
        service = AssessmentService(db)
        paper = service.create_paper(paper_data, current_user.id)

        return ResponseModel(
            code=200,
            message="创建试卷成功",
            data={
                "id": paper.id,
                "paper_code": paper.paper_code,
                "paper_name": paper.paper_name,
                "total_score": paper.total_score,
                "status": paper.status
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建试卷失败: {str(e)}")


@router.post("/papers/auto-generate", response_model=ResponseModel, summary="自动组卷")
async def auto_generate_paper(
    paper_data: Dict[str, Any],
    db: Session = Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_ASSESSMENT_MANAGE)
):
    """根据题库已有题目自动拼接生成完整试卷（按题型/难度/分类随机抽题）。"""
    try:
        service = AssessmentService(db)
        paper = service.auto_generate_paper(paper_data, current_user.id)
        return ResponseModel(
            code=200,
            message="自动组卷成功",
            data={
                "id": paper.id,
                "paper_code": paper.paper_code,
                "paper_name": paper.paper_name,
                "paper_type": paper.paper_type,
                "total_score": float(paper.total_score),
                "question_count": len(paper.questions or []),
                "status": paper.status
            }
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"自动组卷失败: {str(e)}")


@router.post("/papers/{paper_id}/simulate", response_model=ResponseModel, summary="模拟答题")
async def simulate_answer(
    paper_id: int,
    payload: Dict[str, Any],
    db: Session = Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_ASSESSMENT_MANAGE)
):
    """对指定试卷模拟答题（按正确率自动生成答案并评分）。"""
    try:
        service = AssessmentService(db)
        talent_id = payload.get("talent_id", 1)
        correct_rate = float(payload.get("correct_rate", 0.8))
        result = service.simulate_answer(paper_id, talent_id, correct_rate)
        return ResponseModel(code=200, message="模拟答题完成", data=result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"模拟答题失败: {str(e)}")


@router.post("/papers/{paper_id}/grade", response_model=ResponseModel, summary="真实答题评分(员工提交答卷)")
async def grade_real_answer(
    paper_id: int,
    payload: Dict[str, Any],
    db: Session = Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_ASSESSMENT_MANAGE)
):
    """员工对试卷真实作答后提交，根据真实答案逐题判分，返回能力报告。"""
    from app.models.assessment import TestPaper, Question, QuestionType
    import json as _json
    try:
        paper = db.query(TestPaper).filter(TestPaper.id == paper_id).first()
        if not paper:
            raise HTTPException(status_code=404, detail=f"试卷 {paper_id} 不存在")
        raw_talent_id = payload.get("talent_id")
        if raw_talent_id is None or raw_talent_id == "":
            raise HTTPException(status_code=400, detail="talent_id 必填")
        try:
            talent_id = int(raw_talent_id)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="talent_id 必须是正整数")
        if talent_id <= 0:
            raise HTTPException(status_code=400, detail="talent_id 必须是正整数")
        from app.models.talent import Talent
        if not db.query(Talent).filter(Talent.id == talent_id).first():
            raise HTTPException(status_code=404, detail=f"人才 {talent_id} 不存在")
        answers = payload.get("answers") or []  # [{question_id, answer}]
        ans_map = {str(a.get("question_id")): (a.get("answer") or "") for a in answers if a.get("question_id") is not None}

        qid_with_score = paper.questions or []
        qids = [q.get("question_id") for q in qid_with_score if isinstance(q, dict)]
        qs = db.query(Question).filter(Question.id.in_(qids)).all() if qids else []
        qmap = {q.id: q for q in qs}

        total_score = 0.0
        correct_score = 0.0
        correct_count = 0
        wrong_count = 0
        per_question = []
        for entry in qid_with_score:
            qid = entry.get("question_id") if isinstance(entry, dict) else None
            q = qmap.get(qid)
            if not q:
                continue
            q_score = float(entry.get("score", 1.0))
            total_score += q_score
            user_ans = ans_map.get(str(qid), "").strip()
            correct_ans = (q.correct_answer or "").strip()
            # 客观题严格判分；简答题做相似度（这里用包含匹配近似）
            qtype = q.question_type.value if hasattr(q.question_type, "value") else str(q.question_type)
            is_correct = False
            if qtype in ("single_choice", "true_false"):
                is_correct = user_ans.upper() == correct_ans.upper()
            elif qtype == "multiple_choice":
                u = {s.strip().upper() for s in user_ans.replace(" ", "").split(",") if s.strip()}
                c = {s.strip().upper() for s in correct_ans.replace(" ", "").split(",") if s.strip()}
                is_correct = u == c and len(u) > 0
            elif qtype == "fill_blank":
                # 填空题允许按 | 分隔的多答案任一命中
                parts = [p.strip() for p in correct_ans.split("|") if p.strip()]
                is_correct = user_ans in parts
            else:  # short_answer/essay 简化：用关键词匹配
                keywords = [k for k in correct_ans.split("|") if len(k.strip()) >= 2]
                if keywords:
                    is_correct = any(k.strip() in user_ans for k in keywords)
                else:
                    is_correct = user_ans == correct_ans
            if is_correct:
                correct_score += q_score
                correct_count += 1
            else:
                wrong_count += 1
            per_question.append({
                "question_id": qid,
                "user_answer": user_ans,
                "correct": is_correct,
                "score": q_score if is_correct else 0.0,
                "max_score": q_score,
            })
        accuracy = (correct_score / total_score * 100) if total_score > 0 else 0.0
        # 能力等级（与 AssessmentAgent 同源）
        if accuracy >= 90: level = "core"; level_label = "核心人才"
        elif accuracy >= 75: level = "backbone"; level_label = "骨干"
        elif accuracy >= 60: level = "senior"; level_label = "高级"
        elif accuracy >= 40: level = "intermediate"; level_label = "中级"
        else: level = "entry"; level_label = "初级"
        return ResponseModel(
            code=200,
            message="ok",
            data={
                "paper_id": paper_id,
                "paper_name": paper.paper_name,
                "talent_id": talent_id,
                "total_score": round(total_score, 2),
                "correct_score": round(correct_score, 2),
                "correct_count": correct_count,
                "wrong_count": wrong_count,
                "accuracy": round(accuracy, 1),
                "ability_level": level,
                "ability_level_label": level_label,
                "per_question": per_question,
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"答题评分失败: {str(e)}")


@router.post("/papers/{paper_id}/publish", response_model=ResponseModel, summary="发布试卷")
async def publish_paper(
    paper_id: int,
    db: Session = Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_ASSESSMENT_MANAGE)
):
    """发布试卷"""
    try:
        service = AssessmentService(db)
        paper = service.publish_paper(paper_id, current_user.id)

        if not paper:
            raise HTTPException(status_code=404, detail="试卷不存在")

        return ResponseModel(
            code=200,
            message="发布成功",
            data={
                "id": paper.id,
                "paper_code": paper.paper_code,
                "status": paper.status
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"发布试卷失败: {str(e)}")


@router.get("/papers", response_model=ResponseModel, summary="试卷列表")
async def list_papers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    paper_type: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_ASSESSMENT_MANAGE)
):
    """获取试卷列表"""
    try:
        service = AssessmentService(db)
        result = service.get_papers(
            page=page,
            page_size=page_size,
            paper_type=paper_type,
            status=status
        )

        items = [
            {
                "id": p.id,
                "paper_code": p.paper_code,
                "paper_name": p.paper_name,
                "paper_type": p.paper_type,
                "total_score": p.total_score,
                "duration": p.duration_minutes,
                "status": getattr(p.status, "value", p.status),
                "created_at": p.created_at.isoformat() if p.created_at else None
            }
            for p in result["items"]
        ]

        total_pages = (result["total"] + result["page_size"] - 1) // result["page_size"]
        return ResponseModel(
            code=200,
            message="获取成功",
            data={
                "items": items,
                "total": result["total"],
                "page": result["page"],
                "page_size": result["page_size"],
                "total_pages": total_pages
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取试卷列表失败: {str(e)}")


@router.get("/papers/{paper_id}/questions", response_model=ResponseModel, summary="试卷题目详情(用于模拟答题)")
async def get_paper_questions(
    paper_id: int,
    include_answer: bool = Query(False, description="是否返回正确答案（管理员/HR 鉴权）"),
    db: Session = Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_ASSESSMENT_MANAGE)
):
    """返回试卷完整题目（题干、选项、分值），供前端真实答题弹框使用。

    - 默认不返回正确答案/解析（员工答题）
    - include_answer=true 时返回（管理侧/答题回顾用）
    """
    from app.models.assessment import TestPaper, Question
    try:
        paper = db.query(TestPaper).filter(TestPaper.id == paper_id).first()
        if not paper:
            raise HTTPException(status_code=404, detail=f"试卷 {paper_id} 不存在")
        qid_with_score = paper.questions or []  # [{question_id, score}]
        qids = [q.get("question_id") for q in qid_with_score if isinstance(q, dict) and q.get("question_id")]
        qs = db.query(Question).filter(Question.id.in_(qids)).all() if qids else []
        qmap = {q.id: q for q in qs}
        items = []
        for entry in qid_with_score:
            qid = entry.get("question_id") if isinstance(entry, dict) else None
            q = qmap.get(qid)
            if not q:
                continue
            qtype = q.question_type.value if hasattr(q.question_type, "value") else str(q.question_type)
            items.append({
                "id": q.id,
                "question_code": q.question_code,
                "question_content": q.question_content,
                "question_type": qtype,
                "question_category": q.question_category,
                "options": q.options or [],
                "score": float(entry.get("score", 0)) if isinstance(entry, dict) else float(q.score_value or 0),
                "difficulty": q.difficulty,
                "capability_dimension": q.capability_dimension,
                "tags": q.tags or [],
            })
            if include_answer:
                items[-1]["correct_answer"] = q.correct_answer
                items[-1]["answer_analysis"] = q.answer_analysis
        return ResponseModel(
            code=200,
            message="ok",
            data={
                "paper_id": paper.id,
                "paper_name": paper.paper_name,
                "total_score": float(paper.total_score or 0),
                "duration_minutes": paper.duration_minutes or 0,
                "items": items,
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取试卷题目失败: {str(e)}")


# ==================== 测评任务 ====================

@router.get("/tasks", response_model=ResponseModel, summary="测评任务列表")
async def list_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    db: Session = Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_ASSESSMENT_MANAGE)
):
    """获取测评任务列表"""
    try:
        query = db.query(AssessmentTask)
        if status:
            query = query.filter(AssessmentTask.status == status)

        total = query.count()
        tasks = query.order_by(AssessmentTask.id.desc()).offset((page - 1) * page_size).limit(page_size).all()

        # 构建 talent_id -> name 映射
        all_tids = set()
        for t in tasks:
            all_tids.update(t.target_talents or [])
        talent_names = {}
        if all_tids:
            talents = db.query(Talent.id, Talent.name).filter(Talent.id.in_(all_tids)).all()
            talent_names = {t.id: t.name for t in talents}

        items = [
            {
                "id": t.id,
                "task_code": t.task_code,
                "task_name": t.task_name,
                "paper_id": t.paper_id,
                "status": t.status,
                "target_type": t.target_type,
                "target_talents": t.target_talents or [],
                "talent_count": len(t.target_talents or []),
                "talent_names": [talent_names.get(tid, f"人才#{tid}") for tid in (t.target_talents or [])],
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in tasks
        ]

        total_pages = (total + page_size - 1) // page_size
        return ResponseModel(
            code=200,
            message="获取成功",
            data={"items": items, "total": total, "page": page, "page_size": page_size, "total_pages": total_pages}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取测评任务列表失败: {str(e)}")


@router.delete("/tasks/{task_id}", response_model=ResponseModel, summary="删除测评任务")
async def delete_assessment_task(
    task_id: int,
    db: Session = Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_ASSESSMENT_MANAGE)
):
    """删除单个测评任务（同时清理关联结果，避免悬空数据）"""
    try:
        task = db.query(AssessmentTask).filter(AssessmentTask.id == task_id).first()
        if not task:
            raise HTTPException(status_code=404, detail="测评任务不存在")
        db.query(AssessmentResult).filter(AssessmentResult.task_id == task_id).delete(synchronize_session=False)
        db.delete(task)
        db.commit()
        return ResponseModel(code=200, message="删除成功", data={"task_id": task_id})
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"删除测评任务失败: {str(e)}")


@router.post("/tasks/batch-delete", response_model=ResponseModel, summary="批量删除测评任务")
async def batch_delete_assessment_tasks(
    payload: Dict[str, Any],
    db: Session = Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_ASSESSMENT_MANAGE)
):
    """批量删除测评任务（同时清理关联的测评结果，避免悬空数据）"""
    ids = payload.get("ids") or payload.get("task_ids") or []
    if not ids:
        raise HTTPException(status_code=400, detail="ids 必填")
    try:
        from app.models.assessment import AssessmentResult
        ids_int = [int(i) for i in ids]
        # 先清理关联测评结果
        db.query(AssessmentResult).filter(AssessmentResult.task_id.in_(ids_int)).delete(synchronize_session=False)
        deleted = db.query(AssessmentTask).filter(AssessmentTask.id.in_(ids_int)).delete(synchronize_session=False)
        db.commit()
        return ResponseModel(code=200, message=f"批量删除成功：共删除 {deleted} 条任务", data={"deleted": deleted})
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"批量删除测评任务失败: {str(e)}")


@router.post("/tasks", response_model=ResponseModel, summary="创建测评任务")
async def create_assessment_task(
    task_data: Dict[str, Any],
    db: Session = Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_ASSESSMENT_MANAGE)
):
    """创建测评任务"""
    try:
        service = AssessmentService(db)
        task = service.create_task(task_data, current_user.id)

        return ResponseModel(
            code=200,
            message="创建测评任务成功",
            data={
                "id": task.id,
                "task_name": task.task_name,
                "paper_id": task.paper_id,
                "talent_count": len(task.target_talents)
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建测评任务失败: {str(e)}")


@router.post("/tasks/{task_id}/submit", response_model=ResponseModel, summary="提交测评")
async def submit_assessment(
    task_id: int,
    submit_data: Dict[str, Any],
    db: Session = Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_ASSESSMENT_MANAGE)
):
    """提交测评"""
    try:
        service = AssessmentService(db)

        talent_id = submit_data.get("talent_id")
        answers = submit_data.get("answers", [])

        result = service.submit_assessment(task_id, talent_id, answers)

        return ResponseModel(
            code=200,
            message="提交成功",
            data={
                "result_id": result.id,
                "total_score": float(result.total_score),
                "correct_count": result.correct_count,
                "total_count": result.correct_count + result.wrong_count + result.unanswered_count,
                "correct_rate": (result.correct_count / (result.correct_count + result.wrong_count + result.unanswered_count) * 100) if (result.correct_count + result.wrong_count + result.unanswered_count) > 0 else 0
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"提交测评失败: {str(e)}")


# ==================== 测评结果 ====================

@router.get("/results", response_model=ResponseModel, summary="测评结果列表")
async def list_results(
    talent_id: Optional[int] = None,
    task_id: Optional[int] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_ASSESSMENT_MANAGE)
):
    """获取测评结果列表"""
    try:
        service = AssessmentService(db)
        result = service.get_results(
            talent_id=talent_id,
            task_id=task_id,
            page=page,
            page_size=page_size
        )

        # 构建 talent_id -> name 映射
        talent_names = {}
        if result["items"]:
            tids = {r.talent_id for r in result["items"]}
            talents = db.query(Talent.id, Talent.name).filter(Talent.id.in_(tids)).all()
            talent_names = {t.id: t.name for t in talents}

        items = [
            {
                "id": r.id,
                "task_id": r.task_id,
                "talent_id": r.talent_id,
                "talent_name": talent_names.get(r.talent_id, f"人才#{r.talent_id}"),
                "total_score": float(r.total_score),
                "correct_count": r.correct_count,
                "wrong_count": r.wrong_count,
                "unanswered_count": r.unanswered_count,
                "total_count": r.correct_count + r.wrong_count + r.unanswered_count,
                "capability_level": r.capability_level.value if r.capability_level else None,
                "submitted_at": r.submit_time.isoformat() if r.submit_time else None
            }
            for r in result["items"]
        ]

        total_pages = (result["total"] + result["page_size"] - 1) // result["page_size"]
        return ResponseModel(
            code=200,
            message="获取成功",
            data={
                "items": items,
                "total": result["total"],
                "page": result["page"],
                "page_size": result["page_size"],
                "total_pages": total_pages
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取测评结果失败: {str(e)}")


@router.get("/results/{result_id}/radar-chart", response_model=ResponseModel, summary="获取能力雷达图")
async def get_radar_chart(
    result_id: int,
    db: Session = Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_ASSESSMENT_MANAGE)
):
    """获取能力雷达图"""
    try:
        service = AssessmentService(db)
        radar_data = service.generate_radar_chart(result_id)

        return ResponseModel(
            code=200,
            message="获取成功",
            data=radar_data
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取雷达图失败: {str(e)}")
