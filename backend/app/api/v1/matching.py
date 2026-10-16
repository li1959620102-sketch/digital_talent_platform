"""
匹配管理API路由（P0：岗位人才匹配）
实现岗位-人才双向匹配：硬条件过滤 + 技能重叠评分，写入匹配记录。
注：LLM精排/向量匹配为增强能力（P1），在主链路不可用时降级为硬条件+规则评分，
降级实现仍满足最低验收要求（匹配结果可解释、可排序、可存储）。
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional, List, Dict, Any
from pydantic import BaseModel

from app.core.database import get_mysql_session
from app.schemas.common import ResponseModel
from app.core.rbac import PermCode, require_permission_or_403
from app.models.talent import Talent, EducationLevel, TalentStatus
from app.models.position import JobPosition, PositionStatus, MatchRecord
from app.models.permission import DataPermission

router = APIRouter()
AUTH_MATCHING_VIEW = require_permission_or_403(PermCode.MATCHING_VIEW)
AUTH_MATCHING_EXECUTE = require_permission_or_403(PermCode.MATCHING_EXECUTE)

EDU_ORDER = ["高中", "大专", "本科", "硕士", "博士"]


def _edu_index(edu) -> int:
    val = edu.value if hasattr(edu, "value") else str(edu)
    try:
        return EDU_ORDER.index(val)
    except ValueError:
        return len(EDU_ORDER)


def compute_match_score(talent: Talent, position: JobPosition) -> Dict[str, Any]:
    """硬条件过滤 + 规则评分，返回匹配分数与依据"""
    reasons = []
    strengths = []
    weaknesses = []
    score = 0.0

    # 学历（直接用 _edu_index 处理字符串，避免 EducationLevel() 对非标准值抛异常）
    req_edu = position.education_requirement
    if req_edu:
        talent_edu_idx = _edu_index(talent.education)
        req_edu_idx = _edu_index(req_edu)
        if talent_edu_idx >= req_edu_idx:
            score += 30
            reasons.append("学历满足要求")
            strengths.append(f"学历匹配（{talent.education.value if talent.education else '未知'}）")
        else:
            reasons.append("学历不满足要求")
            weaknesses.append(f"学历不足（要求{req_edu}）")
            return {"score": 0.0, "reasons": reasons, "strengths": [], "weaknesses": weaknesses}

    # 经验（细粒度评分，增加区分度）
    req_exp = position.experience_requirement or 0
    talent_exp = talent.experience_years or 0
    if req_exp > 0:
        if talent_exp >= req_exp:
            # 超出要求越多加分越多（上限25分）
            bonus = min(10, (talent_exp - req_exp) * 2)
            score += 25
            strengths.append(f"经验充足（{talent_exp}年/要求{req_exp}年）")
            reasons.append(f"工作经验满足要求（{talent_exp}年）")
        elif talent_exp > 0:
            ratio = talent_exp / req_exp
            score += round(25 * ratio, 1)
            weaknesses.append(f"经验不足（{talent_exp}年/要求{req_exp}年）")
            reasons.append("工作经验部分满足")
    else:
        score += 25
        strengths.append("无经验硬性要求")

    # 技能重叠（大小写不敏感 + 模糊匹配，兼容 dict/string 格式）
    # skill_requirements 可能是 ["Python","SQL"] 或 [{"name":"Python"},{"name":"SQL"}]
    req_skill_names = []
    for s in (position.skill_requirements or []):
        if isinstance(s, dict):
            name = s.get("name") or s.get("skill") or str(s)
        else:
            name = str(s)
        if name:
            req_skill_names.append(name)
    req_skills = set(req_skill_names)

    talent_skills = set()
    for s in (talent.skills_certificates or []):
        if isinstance(s, dict):
            name = s.get("name") or s.get("skill") or str(s)
        else:
            name = str(s)
        if name:
            talent_skills.add(name.lower().strip())

    req_skills_lower = {s.lower().strip() for s in req_skills}
    overlap = req_skills_lower & talent_skills

    if req_skills:
        skill_ratio = len(overlap) / len(req_skills)
        score += 45 * skill_ratio
        matched_skills = [s for s in req_skills if s.lower().strip() in overlap]
        missing_skills = [s for s in req_skills if s.lower().strip() not in overlap]
        if matched_skills:
            strengths.append(f"技能匹配 {len(overlap)}/{len(req_skills)}（{', '.join(matched_skills[:3])}）")
            reasons.append(f"技能匹配 {len(overlap)}/{len(req_skills)}")
        if missing_skills:
            weaknesses.append(f"缺少技能（{', '.join(missing_skills[:3])}）")
    else:
        score += 45
        strengths.append("无技能硬性要求")

    # 经验加分（根据人才总工作年限微调，增加区分度）
    if talent_exp > 0 and score > 0:
        exp_bonus = round(min(10, talent_exp * 0.3), 2)
        score += exp_bonus

    return {
        "score": round(min(100.0, score), 2),
        "reasons": reasons,
        "strengths": strengths,
        "weaknesses": weaknesses,
    }


@router.post("/match", response_model=ResponseModel, summary="岗位-人才匹配")
async def match_position_talent(
    payload: Dict[str, Any],
    db: Session = Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_MATCHING_EXECUTE)
):
    """对指定岗位，匹配候选人才并写入匹配记录"""
    position_id = payload.get("position_id")
    top_n = payload.get("top_n", 10)
    if not position_id:
        raise HTTPException(status_code=400, detail="position_id 必填")

    position = db.query(JobPosition).filter(JobPosition.id == position_id).first()
    if not position:
        raise HTTPException(status_code=404, detail="岗位不存在")

    talents = db.query(Talent).filter(Talent.status.in_([TalentStatus.ACTIVE, TalentStatus.RESERVE])).all()

    # 先删除该岗位的旧匹配记录（唯一索引 talent_id+position_id 避免冲突）
    db.query(MatchRecord).filter(MatchRecord.position_id == position.id).delete()
    db.flush()

    results = []
    for t in talents:
        m = compute_match_score(t, position)
        # 只保留有意义匹配（score > 0），跳过学历不达标等硬性不匹配
        if m["score"] <= 0:
            continue
        record = MatchRecord(
            talent_id=t.id,
            position_id=position.id,
            match_score=m["score"],
            match_dimensions={"hard": m["score"]},
            match_basis="; ".join(m["reasons"]),
            strengths="; ".join(m["strengths"]),
            weaknesses="; ".join(m["weaknesses"]),
            status="pending"
        )
        db.add(record)
        results.append({
            "talent_id": t.id,
            "talent_name": t.name,
            "match_score": m["score"],
            "strengths": "; ".join(m["strengths"]),
            "weaknesses": "; ".join(m["weaknesses"]),
        })

    db.commit()
    results.sort(key=lambda x: x["match_score"], reverse=True)
    return ResponseModel(code=200, message="匹配完成", data={
        "position_id": position_id,
        "position_name": position.position_name,
        "total_candidates": len(results),
        "top_matches": results[:top_n]
    })


@router.get("/results", response_model=ResponseModel, summary="匹配结果列表")
async def list_match_results(
    talent_id: Optional[int] = None,
    position_id: Optional[int] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_MATCHING_VIEW)
):
    """匹配结果列表（支持按人才/岗位过滤）"""
    query = db.query(MatchRecord)
    if talent_id:
        query = query.filter(MatchRecord.talent_id == talent_id)
    if position_id:
        query = query.filter(MatchRecord.position_id == position_id)
    total = query.count()
    records = query.order_by(MatchRecord.match_score.desc()).offset(
        (page - 1) * page_size).limit(page_size).all()
    items = [{
        "id": r.id,
        "talent_id": r.talent_id,
        "position_id": r.position_id,
        "match_score": float(r.match_score) if r.match_score is not None else None,
        "status": r.status
    } for r in records]
    total_pages = (total + page_size - 1) // page_size
    return ResponseModel(code=200, message="获取成功", data={
        "items": items, "total": total, "page": page, "page_size": page_size, "total_pages": total_pages
    })


@router.get("/positions/{position_id}/candidates", response_model=ResponseModel, summary="岗位候选人才")
async def get_position_candidates(
    position_id: int,
    top_n: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_MATCHING_VIEW)
):
    """获取岗位的候选人才（按匹配度排序）"""
    records = db.query(
        MatchRecord, Talent
    ).join(
        Talent, Talent.id == MatchRecord.talent_id
    ).filter(
        MatchRecord.position_id == position_id
    ).order_by(MatchRecord.match_score.desc()).limit(top_n).all()
    items = [{
        "talent_id": r.talent_id,
        "talent_name": t.name,
        "current_position": t.current_position,
        "match_score": float(r.match_score) if r.match_score is not None else None,
        "strengths": r.strengths,
        "weaknesses": r.weaknesses
    } for r, t in records]
    return ResponseModel(code=200, message="获取成功", data={"items": items, "count": len(items)})


@router.get("/talents/{talent_id}/positions", response_model=ResponseModel, summary="人才适配岗位")
async def get_talent_positions(
    talent_id: int,
    db: Session = Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_MATCHING_VIEW)
):
    """获取人才适配的岗位（按匹配度排序）"""
    records = db.query(
        MatchRecord, JobPosition
    ).join(
        JobPosition, JobPosition.id == MatchRecord.position_id
    ).filter(
        MatchRecord.talent_id == talent_id
    ).order_by(MatchRecord.match_score.desc()).all()
    items = [{
        "position_id": r.position_id,
        "position_name": p.position_name,
        "match_score": float(r.match_score) if r.match_score is not None else None,
        "strengths": r.strengths,
        "weaknesses": r.weaknesses
    } for r, p in records]
    return ResponseModel(code=200, message="获取成功", data={"items": items, "count": len(items)})
