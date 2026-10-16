"""
岗位管理API路由
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any

from app.core.database import get_mysql_session
from app.schemas.common import ResponseModel, PageModel
from app.services.position_service import PositionService
from app.core.rbac import PermCode, require_permission_or_403
from app.models.position import PositionStatus, PositionLevel
from app.models.talent import Organization

router = APIRouter()
AUTH_POSITION_VIEW = require_permission_or_403(PermCode.POSITION_VIEW)
AUTH_POSITION_MANAGE = require_permission_or_403(PermCode.POSITION_MANAGE)


@router.get("/organizations", response_model=ResponseModel, summary="组织/部门列表（下拉用）")
async def list_organizations(
    db: Session = Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_POSITION_VIEW)
):
    """返回组织架构列表，供岗位/人才表单的「所属部门」下拉选择"""
    try:
        orgs = db.query(Organization).filter(
            Organization.status == "active"
        ).order_by(Organization.id).all()
        items = [{
            "id": o.id,
            "org_code": o.org_code,
            "org_name": o.org_name,
            "org_type": o.org_type,
        } for o in orgs]
        return ResponseModel(code=200, message="获取成功", data=items)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取组织列表失败: {str(e)}")


@router.post("", response_model=ResponseModel, summary="创建岗位")
async def create_position(
    position_data: Dict[str, Any],
    db: Session = Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_POSITION_MANAGE)
):
    """创建岗位"""
    try:
        service = PositionService(db)
        position = service.create_position(position_data, current_user.id)

        return ResponseModel(
            code=200,
            message="创建岗位成功",
            data={
                "id": position.id,
                "position_code": position.position_code,
                "position_name": position.position_name,
                "status": position.status.value if position.status else None
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建岗位失败: {str(e)}")


@router.get("/{position_id}", response_model=ResponseModel, summary="获取岗位详情")
async def get_position(
    position_id: int,
    db: Session = Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_POSITION_VIEW)
):
    """获取岗位详情"""
    try:
        service = PositionService(db)
        position = service.get_position(position_id)

        if not position:
            raise HTTPException(status_code=404, detail="岗位不存在")

        return ResponseModel(
            code=200,
            message="获取成功",
            data={
                "id": position.id,
                "position_code": position.position_code,
                "position_name": position.position_name,
                "department_id": position.department_id,
                "position_category": position.position_category,
                "position_level": position.position_level.value if position.position_level else None,
                "position_type": position.position_type,
                "headcount": position.headcount,
                "filled_count": position.filled_count,
                "salary_min": position.salary_min,
                "salary_max": position.salary_max,
                "work_location": position.work_location,
                "education_requirement": position.education_requirement,
                "experience_requirement": position.experience_requirement,
                "skill_requirements": position.skill_requirements,
                "capability_requirements": position.capability_requirements,
                "job_description": position.job_description,
                "job_responsibilities": position.job_responsibilities,
                "tags": position.tags,
                "status": position.status.value if position.status else None,
                "publish_date": position.publish_date.isoformat() if position.publish_date else None,
                "deadline": position.deadline.isoformat() if position.deadline else None,
                "created_at": position.created_at.isoformat() if position.created_at else None
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取岗位失败: {str(e)}")


@router.put("/{position_id}", response_model=ResponseModel, summary="更新岗位信息")
async def update_position(
    position_id: int,
    position_data: Dict[str, Any],
    db: Session = Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_POSITION_MANAGE)
):
    """更新岗位信息"""
    try:
        service = PositionService(db)
        position = service.update_position(position_id, position_data, current_user.id)

        if not position:
            raise HTTPException(status_code=404, detail="岗位不存在")

        return ResponseModel(
            code=200,
            message="更新成功",
            data={
                "id": position.id,
                "position_code": position.position_code,
                "position_name": position.position_name
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新岗位失败: {str(e)}")


@router.delete("/{position_id}", response_model=ResponseModel, summary="删除岗位")
async def delete_position(
    position_id: int,
    db: Session = Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_POSITION_MANAGE)
):
    """删除岗位"""
    try:
        service = PositionService(db)
        success = service.delete_position(position_id)

        if not success:
            raise HTTPException(status_code=404, detail="岗位不存在")

        return ResponseModel(
            code=200,
            message="删除成功",
            data={"position_id": position_id}
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除岗位失败: {str(e)}")


@router.post("/batch-delete", response_model=ResponseModel, summary="批量删除岗位")
async def batch_delete_positions(
    payload: Dict[str, Any],
    db: Session = Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_POSITION_MANAGE)
):
    """批量删除岗位（整页删除）"""
    position_ids = payload.get("ids") or payload.get("position_ids") or []
    if not position_ids:
        raise HTTPException(status_code=400, detail="ids 必填")
    try:
        service = PositionService(db)
        result = service.batch_delete_positions([int(i) for i in position_ids])
        return ResponseModel(
            code=200,
            message=f"批量删除完成：成功 {result['deleted']} 条",
            data=result
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"批量删除失败: {str(e)}")


@router.get("", response_model=ResponseModel, summary="岗位列表")
async def list_positions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    department_id: Optional[int] = None,
    status: Optional[str] = None,
    position_level: Optional[str] = None,
    keyword: Optional[str] = None,
    db: Session = Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_POSITION_VIEW)
):
    """获取岗位列表（支持按状态、层级、关键词筛选）"""
    try:
        # 转换status参数
        status_enum = None
        if status:
            try:
                status_enum = PositionStatus(status)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"无效的状态值: {status}")

        # 转换position_level参数
        level_enum = None
        if position_level:
            try:
                level_enum = PositionLevel(position_level)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"无效的层级值: {position_level}")

        service = PositionService(db)

        # 过滤条件下推到数据库，避免上万级岗位时把全量数据加载到进程内。
        result = service.get_positions(
            page=page,
            page_size=page_size,
            department_id=department_id,
            status=status_enum,
            position_level=level_enum,
            keyword=keyword
        )
        paged_items = result["items"]
        total = result["total"]

        # 转换结果
        items = [
            {
                "id": p.id,
                "position_code": p.position_code,
                "position_name": p.position_name,
                "department_id": p.department_id,
                "position_category": p.position_category,
                "position_level": p.position_level.value if p.position_level else None,
                "headcount": p.headcount,
                "filled_count": p.filled_count,
                "status": p.status.value if p.status else None,
                "education_requirement": p.education_requirement,
                "experience_requirement": p.experience_requirement,
                "publish_date": p.publish_date.isoformat() if p.publish_date else None
            }
            for p in paged_items
        ]

        total_pages = (total + page_size - 1) // page_size
        return ResponseModel(
            code=200,
            message="获取成功",
            data={
                "items": items,
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取岗位列表失败: {str(e)}")


@router.post("/search", response_model=ResponseModel, summary="岗位搜索")
async def search_positions(
    query_text: str,
    top_k: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_POSITION_VIEW)
):
    """岗位搜索（向量搜索）"""
    try:
        service = PositionService(db)
        results = service.search_positions(
            query_text=query_text,
            top_k=top_k
        )

        return ResponseModel(
            code=200,
            message="搜索成功",
            data=results
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"岗位搜索失败: {str(e)}")
