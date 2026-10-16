"""
Skills 可编排技能组件库 API 路由（考核模块三③）

提供：
- 组件清单查询（供前端编排画布拖拽）
- 组件启停
- 技能编排（流水线）的创建/查询/复制/删除/执行/启停
- 触发机制登记（定时/事件/手动/接口）
"""
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException

from app.core.database import get_mysql_session
from app.schemas.common import ResponseModel
from app.core.rbac import PermCode, require_permission_or_403
from app.services.skill_engine import (
    registry, pipeline_store, SkillPipeline, TriggerType
)
from app.services import skill_registry_builtin  # noqa: F401 确保内置组件已注册

router = APIRouter()
AUTH_SKILL_MANAGE = require_permission_or_403(PermCode.SKILL_MANAGE)


@router.get("/components", response_model=ResponseModel, summary="技能组件清单")
async def list_components(
    category: Optional[str] = None,
    db=Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_SKILL_MANAGE)
):
    """返回全部可编排技能组件（供画布拖拽）。"""
    items = registry.list(category=category)
    return ResponseModel(code=200, message="ok", data={"components": items, "total": len(items)})


@router.post("/components/{key}/toggle", response_model=ResponseModel, summary="组件启停")
async def toggle_component(
    key: str,
    payload: Dict[str, Any],
    db=Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_SKILL_MANAGE)
):
    """启用/停用指定技能组件。"""
    enabled = bool(payload.get("enabled", True))
    ok = registry.set_enabled(key, enabled)
    if not ok:
        raise HTTPException(status_code=404, detail=f"组件不存在: {key}")
    return ResponseModel(code=200, message="ok", data={"key": key, "enabled": enabled})


@router.post("/components/{key}/execute", response_model=ResponseModel, summary="组件单次执行")
async def execute_component(
    key: str,
    payload: Dict[str, Any],
    db=Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_SKILL_MANAGE)
):
    """手动执行单个技能组件（触发机制：手动）。"""
    params = payload.get("params", {})
    result = registry.execute(key, params, {"user": current_user})
    return ResponseModel(code=200, message="ok", data=result)


@router.post("/pipelines", response_model=ResponseModel, summary="创建技能编排")
async def create_pipeline(
    payload: Dict[str, Any],
    db=Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_SKILL_MANAGE)
):
    """创建技能编排流水线（可视化画布保存）。"""
    pipeline_id = payload.get("pipeline_id")
    name = payload.get("name")
    steps = payload.get("steps", [])
    if not pipeline_id or not name or not steps:
        raise HTTPException(status_code=400, detail="pipeline_id / name / steps 必填")

    trigger_type = payload.get("trigger_type", TriggerType.MANUAL)
    if trigger_type not in (TriggerType.CRON, TriggerType.EVENT, TriggerType.MANUAL, TriggerType.API):
        raise HTTPException(status_code=400, detail=f"非法触发类型: {trigger_type}")

    pipeline = SkillPipeline(
        pipeline_id=pipeline_id,
        name=name,
        description=payload.get("description", ""),
        steps=steps,
        trigger_type=trigger_type,
        trigger_config=payload.get("trigger_config", {}),
        enabled=payload.get("enabled", True),
    )
    pipeline_store.save(pipeline)
    return ResponseModel(code=200, message="编排已保存", data=pipeline.to_dict())


@router.get("/pipelines", response_model=ResponseModel, summary="技能编排清单")
async def list_pipelines(
    db=Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_SKILL_MANAGE)
):
    """返回全部技能编排流水线。"""
    return ResponseModel(code=200, message="ok", data={"pipelines": pipeline_store.list()})


@router.post("/pipelines/{pipeline_id}/execute", response_model=ResponseModel, summary="执行技能编排")
async def execute_pipeline(
    pipeline_id: str,
    payload: Dict[str, Any],
    db=Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_SKILL_MANAGE)
):
    """执行技能编排流水线（触发机制：手动/接口）。"""
    pipeline = pipeline_store.get(pipeline_id)
    if not pipeline:
        raise HTTPException(status_code=404, detail=f"编排不存在: {pipeline_id}")
    input_params = payload.get("input", {})
    result = pipeline.execute(input_params)
    return ResponseModel(code=200, message="ok", data=result)


@router.post("/pipelines/{pipeline_id}/duplicate", response_model=ResponseModel, summary="复制技能编排")
async def duplicate_pipeline(
    pipeline_id: str,
    payload: Dict[str, Any],
    db=Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_SKILL_MANAGE)
):
    """复制技能编排（复用能力）。"""
    new_id = payload.get("new_pipeline_id")
    if not new_id:
        raise HTTPException(status_code=400, detail="new_pipeline_id 必填")
    result = pipeline_store.duplicate(pipeline_id, new_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"编排不存在: {pipeline_id}")
    return ResponseModel(code=200, message="编排已复制", data=result)


@router.post("/pipelines/{pipeline_id}/toggle", response_model=ResponseModel, summary="编排启停")
async def toggle_pipeline(
    pipeline_id: str,
    payload: Dict[str, Any],
    db=Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_SKILL_MANAGE)
):
    """启用/停用技能编排流水线。"""
    pipeline = pipeline_store.get(pipeline_id)
    if not pipeline:
        raise HTTPException(status_code=404, detail=f"编排不存在: {pipeline_id}")
    pipeline.enabled = bool(payload.get("enabled", True))
    return ResponseModel(code=200, message="ok", data=pipeline.to_dict())


@router.delete("/pipelines/{pipeline_id}", response_model=ResponseModel, summary="删除技能编排")
async def delete_pipeline(
    pipeline_id: str,
    db=Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_SKILL_MANAGE)
):
    """删除技能编排流水线。"""
    ok = pipeline_store.delete(pipeline_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"编排不存在: {pipeline_id}")
    return ResponseModel(code=200, message="已删除", data={"pipeline_id": pipeline_id})
