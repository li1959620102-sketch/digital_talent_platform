"""Supervisor Agent：根据用户目标动态选择领域能力并生成可执行计划。"""
from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Any, Dict, Iterable, List, Optional

from app.agents.agent_contracts import AgentContext, PlanStep, domain_registry
# 导入内置适配器触发五个领域 Agent 注册。
from app.agents import domain_agents as _builtin_domain_agents  # noqa: F401

logger = logging.getLogger(__name__)


class SupervisorPlanner:
    """LLM 规划优先，规则规划兜底，并对计划做严格能力校验。"""

    _KEYWORDS = {
        "resume.parse_and_profile": ("简历", "档案", "解析", "履历"),
        "assessment.analyze_result": ("测评", "能力评估", "考试", "答题"),
        "matching.position_to_talents": ("岗位", "招聘", "候选人", "筛选", "匹配"),
        "matching.talent_to_positions": ("适合什么岗位", "人才匹配", "职业方向"),
        "training.recommend_path": ("培训", "课程", "学习路径", "能力缺口"),
        "data.structure": ("结构", "分布", "人员构成", "概览"),
        "data.trend": ("趋势", "变化", "增长"),
        "data.anomaly": ("异常", "风险", "离群"),
        "data.nl2sql": ("查询", "多少", "统计", "sql"),
    }

    def _allowed(self) -> set[str]:
        return {item["name"] for item in domain_registry.list_capabilities()}

    def _rule_plan(self, goal: str, inputs: Dict[str, Any]) -> List[PlanStep]:
        text = goal.lower()
        selected: List[str] = []
        for capability, keywords in self._KEYWORDS.items():
            if any(keyword.lower() in text for keyword in keywords):
                selected.append(capability)

        # 明确输入优先于自然语言猜测。
        if inputs.get("file_path") and "resume.parse_and_profile" not in selected:
            selected.insert(0, "resume.parse_and_profile")
        if inputs.get("result_id") and "assessment.analyze_result" not in selected:
            selected.append("assessment.analyze_result")
        if inputs.get("position_id") and "matching.position_to_talents" not in selected:
            selected.append("matching.position_to_talents")
        if inputs.get("talent_id") and "training.recommend_path" in selected:
            pass

        # 跨领域任务使用稳定的业务依赖顺序，避免结果依赖未完成步骤。
        order = [
            "resume.parse_and_profile", "data.nl2sql", "data.structure", "data.trend", "data.anomaly",
            "assessment.analyze_result", "matching.position_to_talents", "matching.talent_to_positions",
            "training.recommend_path",
        ]
        selected = [name for name in order if name in selected]
        if not selected:
            selected = ["data.nl2sql"] if inputs.get("question") else ["data.structure"]

        steps: List[PlanStep] = []
        for index, capability in enumerate(selected, start=1):
            depends = [steps[-1].step_id] if steps else []
            steps.append(PlanStep(
                step_id=f"step_{index}_{uuid.uuid4().hex[:6]}",
                capability=capability,
                inputs=dict(inputs),
                depends_on=depends,
                rationale="根据目标关键词和输入字段选择",
            ))
        return steps

    def _llm_plan(self, goal: str, inputs: Dict[str, Any]) -> Optional[List[PlanStep]]:
        try:
            from app.core.llm_factory import get_agent_llm
            from app.utils.json_utils import extract_json

            catalog = domain_registry.list_capabilities()
            prompt = (
                "你是企业人才平台的 Supervisor。请根据用户目标生成最少且必要的执行步骤。"
                "只能从能力目录中选择，返回 JSON："
                '{"steps":[{"capability":"能力名","depends_on":[],"rationale":"原因"}]}。'
                f"\n用户目标：{goal}\n输入字段：{sorted(inputs.keys())}\n能力目录：{json.dumps(catalog, ensure_ascii=False)}"
            )
            response = get_agent_llm(temperature=0).invoke(prompt)
            parsed = extract_json(getattr(response, "content", str(response))) or {}
            allowed = self._allowed()
            steps: List[PlanStep] = []
            for index, item in enumerate(parsed.get("steps", []), start=1):
                if not isinstance(item, dict) or item.get("capability") not in allowed:
                    continue
                # 统一使用已经生成的前置步骤 ID，避免 LLM 伪造不存在的 ID。
                deps = [steps[-1].step_id] if steps else []
                steps.append(PlanStep(
                    step_id=f"step_{index}_{uuid.uuid4().hex[:6]}",
                    capability=item["capability"],
                    inputs=dict(inputs),
                    depends_on=deps,
                    rationale=str(item.get("rationale", "")),
                ))
            return steps or None
        except Exception as exc:
            logger.warning("Supervisor LLM 规划失败，回退规则规划: %s", exc)
            return None

    def validate(self, steps: Iterable[PlanStep]) -> List[str]:
        errors: List[str] = []
        allowed = self._allowed()
        seen: set[str] = set()
        steps = list(steps)
        step_ids = {step.step_id for step in steps}
        for step in steps:
            if step.capability not in allowed:
                errors.append(f"未知能力: {step.capability}")
            if step.step_id in seen:
                errors.append(f"重复步骤 ID: {step.step_id}")
            seen.add(step.step_id)
            if step.step_id in step.depends_on:
                errors.append(f"步骤不能依赖自身: {step.step_id}")
            for dependency in step.depends_on:
                if dependency not in step_ids:
                    errors.append(f"依赖步骤不存在: {dependency}")
        return errors

    def plan(self, goal: str, inputs: Optional[Dict[str, Any]] = None, *, context: Optional[AgentContext] = None, use_llm: Optional[bool] = None) -> Dict[str, Any]:
        inputs = inputs or {}
        use_llm = use_llm if use_llm is not None else os.getenv("AGENT_SUPERVISOR_LLM", "false").lower() in {"1", "true", "yes"}
        steps = self._llm_plan(goal, inputs) if use_llm else None
        source = "llm" if steps else "rules"
        steps = steps or self._rule_plan(goal, inputs)
        errors = self.validate(steps)
        if errors:
            raise ValueError("Supervisor 计划校验失败: " + "; ".join(errors))
        return {
            "plan_id": "sup_" + uuid.uuid4().hex[:16],
            "goal": goal,
            "source": source,
            "session_id": context.session_id if context else None,
            "steps": [step.__dict__ for step in steps],
            "completion": "所有步骤成功执行并通过结果校验",
            "validation": {"valid": True, "errors": []},
        }


supervisor_planner = SupervisorPlanner()
