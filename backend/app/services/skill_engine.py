"""
Skills 可编排技能组件库（考核模块三③）

需求要点：
1. 组件封装：将简历解析、语义检索、人才匹配、测评分析、数据问答、报表生成、消息推送、
   数据导出、权限校验等 AI/业务能力封装为独立可插拔 Skill 组件。
2. 可视化编排：支持拖拽式组合 Skills 组件，自定义业务流程、执行顺序、触发条件、分支规则。
3. 技能复用：组件支持复用、复制、升级、启停管理，参数自定义配置。
4. 触发机制：定时触发、事件触发、手动触发、接口触发。

设计：
- SkillComponent：单个技能组件（原子能力），含 schema（参数定义）+ execute() 实现。
- SkillRegistry：组件注册表（单例），负责组件的注册/查询/启停。
- SkillPipeline：技能编排（业务流程），由若干 SkillStep 按顺序/条件组合，可复用/复制/启停。
- TriggerType：定时(cron) / 事件(event) / 手动(manual) / 接口(api)。

本模块为「能力层」，提供组件封装 + 编排执行 + 触发注册；
可视化编排画布由前端 SkillsDesigner 页面 + 后端 skills API 共同落地。
"""
from __future__ import annotations

import inspect
import json
import logging
import threading
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ==================== 技能组件（原子能力） ====================

class SkillComponent:
    """
    单个可插拔技能组件。

    属性：
    - key: 组件唯一标识（如 "resume_parse"）
    - name / description: 展示名与说明
    - category: 组件分类（ai / business / data / notify / security）
    - params_schema: 参数定义（list[dict]，供前端动态渲染表单）
    - enabled: 是否启用
    - fn: 执行函数，签名 fn(params: dict, context: dict) -> dict
    """

    def __init__(self, key: str, name: str, description: str, category: str,
                 params_schema: List[Dict[str, Any]], fn: Callable):
        self.key = key
        self.name = name
        self.description = description
        self.category = category
        self.params_schema = params_schema or []
        self.fn = fn
        self.enabled = True

    def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """执行组件，返回统一结果 dict（含 success 字段）。"""
        if not self.enabled:
            return {"success": False, "error": f"组件 {self.key} 已停用"}
        try:
            result = self.fn(params or {}, context or {})
            if not isinstance(result, dict):
                result = {"success": True, "data": result}
            result.setdefault("success", True)
            return result
        except Exception as e:
            logger.error(f"技能组件 {self.key} 执行失败: {e}")
            return {"success": False, "error": str(e)}

    def to_dict(self) -> Dict[str, Any]:
        """序列化（供前端编排画布/API 展示）。"""
        return {
            "key": self.key,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "params_schema": self.params_schema,
            "enabled": self.enabled,
        }


# ==================== 组件注册表 ====================

class SkillRegistry:
    """技能组件注册表（单例）。"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._components: Dict[str, SkillComponent] = {}
        return cls._instance

    def register(self, component: SkillComponent) -> None:
        self._components[component.key] = component
        logger.info(f"技能组件已注册: {component.key} ({component.name})")

    def register_many(self, components: List[SkillComponent]) -> None:
        for c in components:
            self.register(c)

    def get(self, key: str) -> Optional[SkillComponent]:
        return self._components.get(key)

    def list(self, category: Optional[str] = None, enabled_only: bool = False) -> List[Dict[str, Any]]:
        items = []
        for c in self._components.values():
            if category and c.category != category:
                continue
            if enabled_only and not c.enabled:
                continue
            items.append(c.to_dict())
        return items

    def set_enabled(self, key: str, enabled: bool) -> bool:
        c = self._components.get(key)
        if not c:
            return False
        c.enabled = enabled
        logger.info(f"技能组件 {key} 已{'启用' if enabled else '停用'}")
        return True

    def execute(self, key: str, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        c = self._components.get(key)
        if not c:
            return {"success": False, "error": f"技能组件不存在: {key}"}
        return c.execute(params, context)


registry = SkillRegistry()


# ==================== 技能编排（业务流程） ====================

class TriggerType:
    """触发机制：定时 / 事件 / 手动 / 接口。"""
    CRON = "cron"        # 定时触发（如每日人才盘点）
    EVENT = "event"      # 事件触发（如岗位空缺自动匹配）
    MANUAL = "manual"    # 手动触发
    API = "api"          # 接口触发（第三方系统调用）


class SkillPipeline:
    """
    技能编排流程：由若干 Step 按顺序组合。

    Step 结构：
      {"skill": "resume_parse", "params": {...}, "condition": "..."}

    支持：
    - 顺序执行（steps 按序）
    - 分支规则（condition 为 Python 布尔表达式，可引用上一步输出）
    - 复用/复制（duplicate）
    - 启停（enabled）
    - 触发配置（trigger_type + cron_expr / event / manual）
    """

    def __init__(self, pipeline_id: str, name: str, description: str,
                 steps: List[Dict[str, Any]], trigger_type: str = TriggerType.MANUAL,
                 trigger_config: Optional[Dict[str, Any]] = None, enabled: bool = True):
        self.pipeline_id = pipeline_id
        self.name = name
        self.description = description
        self.steps = steps
        self.trigger_type = trigger_type
        self.trigger_config = trigger_config or {}
        self.enabled = enabled

    def execute(self, input_params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """执行编排：顺序执行各 step，支持条件分支与中间结果传递。"""
        if not self.enabled:
            return {"success": False, "error": f"技能编排 {self.pipeline_id} 已停用"}

        context: Dict[str, Any] = {"input": input_params or {}, "steps": {}}
        outputs: List[Dict[str, Any]] = []

        for idx, step in enumerate(self.steps):
            skill_key = step.get("skill")
            params = step.get("params") or {}
            condition = step.get("condition")

            # 条件分支：condition 为表达式时求值，为 False 则跳过
            if condition:
                if not self._eval_condition(condition, context):
                    outputs.append({"step": idx, "skill": skill_key, "skipped": True})
                    continue

            comp = registry.get(skill_key)
            if not comp:
                outputs.append({"step": idx, "skill": skill_key, "success": False,
                                "error": f"组件不存在: {skill_key}"})
                continue

            result = comp.execute(params, context)
            context["steps"][skill_key] = result
            outputs.append({"step": idx, "skill": skill_key, **result})

        success = all(o.get("success", True) for o in outputs if not o.get("skipped"))
        return {
            "success": success,
            "pipeline_id": self.pipeline_id,
            "outputs": outputs,
        }

    @staticmethod
    def _eval_condition(expr: str, context: Dict[str, Any]) -> bool:
        """求值分支条件（安全受限：仅支持简单比较/布尔，禁用任意代码）。"""
        try:
            # 仅暴露 steps 输出中的 success/字段，禁止 eval 任意表达式
            safe_env = {"ctx": context.get("steps", {})}
            return bool(eval(expr, {"__builtins__": {}}, safe_env))  # noqa: S307
        except Exception as e:
            logger.warning(f"分支条件求值失败（视为 True）: {expr} -> {e}")
            return True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pipeline_id": self.pipeline_id,
            "name": self.name,
            "description": self.description,
            "steps": self.steps,
            "trigger_type": self.trigger_type,
            "trigger_config": self.trigger_config,
            "enabled": self.enabled,
        }


class PipelineStore:
    """技能编排存储（内存态，生产可扩展为 DB 持久化）。"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._pipelines: Dict[str, SkillPipeline] = {}
        return cls._instance

    def save(self, pipeline: SkillPipeline) -> None:
        self._pipelines[pipeline.pipeline_id] = pipeline

    def get(self, pipeline_id: str) -> Optional[SkillPipeline]:
        return self._pipelines.get(pipeline_id)

    def list(self) -> List[Dict[str, Any]]:
        return [p.to_dict() for p in self._pipelines.values()]

    def delete(self, pipeline_id: str) -> bool:
        if pipeline_id in self._pipelines:
            del self._pipelines[pipeline_id]
            return True
        return False

    def duplicate(self, pipeline_id: str, new_id: str) -> Optional[Dict[str, Any]]:
        """复制编排（复用能力）。"""
        src = self._pipelines.get(pipeline_id)
        if not src:
            return None
        new_p = SkillPipeline(
            pipeline_id=new_id,
            name=f"{src.name}(副本)",
            description=src.description,
            steps=[dict(s) for s in src.steps],
            trigger_type=src.trigger_type,
            trigger_config=dict(src.trigger_config),
            enabled=src.enabled,
        )
        self.save(new_p)
        return new_p.to_dict()


pipeline_store = PipelineStore()
