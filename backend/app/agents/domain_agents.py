"""将现有五个业务 Agent 适配到统一 DomainAgent 协议。"""
from __future__ import annotations

from typing import Any, Dict, List

from app.agents.agent_contracts import (
    AgentContext,
    AgentResult,
    Capability,
    DomainAgent,
    RecoveryAction,
    domain_registry,
)
from app.agents.resume_parser_agent import resume_parser_agent
from app.agents.assessment_agent import AssessmentAnalysisAgent
from app.agents.matching_agent import MatchingAgent
from app.agents.training_agent import training_agent
from app.agents.data_decision_agent import data_decision_agent


class _BaseDomainAgent:
    name = ""

    def capabilities(self) -> List[Capability]:
        return []

    def _result(self, value: Any, context: AgentContext) -> AgentResult:
        if isinstance(value, dict):
            success = value.get("success", True) is not False
            data = value
        else:
            success = True
            data = {"value": value}
        return AgentResult(
            success=success,
            data=data,
            evidence=[{"source": self.name, "task_id": context.task_id}],
            errors=[str(value.get("error"))] if isinstance(value, dict) and value.get("error") else [],
            metadata={"agent": self.name, "session_id": context.session_id},
        )

    def validate(self, result: AgentResult, context: AgentContext) -> List[str]:
        errors = list(result.errors)
        if not result.success and not errors:
            errors.append(f"{self.name} 返回失败但未提供错误原因")
        return errors

    def recover(self, error: Exception, context: AgentContext) -> RecoveryAction:
        return RecoveryAction(action="retry", reason=str(error), retry_after_seconds=1)


class ResumeDomainAgent(_BaseDomainAgent):
    name = "resume"

    def capabilities(self) -> List[Capability]:
        return [Capability("resume.parse_and_profile", "解析简历并生成结构化档案、标签和画像", permission="talent:parse_resume", risk_level="medium")]

    def execute(self, capability: str, inputs: Dict[str, Any], context: AgentContext) -> AgentResult:
        if capability != "resume.parse_and_profile":
            raise KeyError(f"resume Agent 不支持能力: {capability}")
        file_path = inputs.get("file_path")
        file_name = inputs.get("file_name", "resume")
        if not file_path:
            raise ValueError("resume.parse_and_profile 需要 file_path")
        return self._result(resume_parser_agent.parse_resume(file_path, file_name), context)


class AssessmentDomainAgent(_BaseDomainAgent):
    name = "assessment"

    def capabilities(self) -> List[Capability]:
        return [Capability("assessment.analyze_result", "分析测评结果并生成能力画像与发展建议", permission="assessment:execute", risk_level="low")]

    def execute(self, capability: str, inputs: Dict[str, Any], context: AgentContext) -> AgentResult:
        if capability != "assessment.analyze_result":
            raise KeyError(f"assessment Agent 不支持能力: {capability}")
        result_id = inputs.get("result_id") or inputs.get("assessment_result_id")
        if not result_id:
            raise ValueError("assessment.analyze_result 需要 result_id")
        return self._result(AssessmentAnalysisAgent().analyze(int(result_id)), context)


class MatchingDomainAgent(_BaseDomainAgent):
    name = "matching"

    def capabilities(self) -> List[Capability]:
        return [
            Capability("matching.position_to_talents", "为岗位检索和排序候选人", permission="matching:execute", risk_level="medium"),
            Capability("matching.talent_to_positions", "为人才检索和排序适配岗位", permission="matching:execute", risk_level="medium"),
        ]

    def execute(self, capability: str, inputs: Dict[str, Any], context: AgentContext) -> AgentResult:
        agent = MatchingAgent()
        if capability == "matching.position_to_talents":
            if not inputs.get("position_id"):
                raise ValueError("matching.position_to_talents 需要 position_id")
            value = agent.match_position_to_talents(int(inputs["position_id"]))
        elif capability == "matching.talent_to_positions":
            if not inputs.get("talent_id"):
                raise ValueError("matching.talent_to_positions 需要 talent_id")
            value = agent.match_talent_to_positions(int(inputs["talent_id"]))
        else:
            raise KeyError(f"matching Agent 不支持能力: {capability}")
        return self._result(value, context)


class TrainingDomainAgent(_BaseDomainAgent):
    name = "training"

    def capabilities(self) -> List[Capability]:
        return [Capability("training.recommend_path", "诊断能力缺口并生成课程和学习路径", permission="training:execute", risk_level="low")]

    def execute(self, capability: str, inputs: Dict[str, Any], context: AgentContext) -> AgentResult:
        if capability != "training.recommend_path":
            raise KeyError(f"training Agent 不支持能力: {capability}")
        if not inputs.get("talent_id"):
            raise ValueError("training.recommend_path 需要 talent_id")
        value = training_agent.analyze(int(inputs["talent_id"]), int(inputs["position_id"]) if inputs.get("position_id") else None)
        return self._result(value, context)


class DataDecisionDomainAgent(_BaseDomainAgent):
    name = "data_decision"

    def capabilities(self) -> List[Capability]:
        return [
            Capability("data.structure", "分析人才结构", permission="dashboard:view", risk_level="low"),
            Capability("data.trend", "分析人才趋势", permission="dashboard:view", risk_level="low"),
            Capability("data.anomaly", "分析人才异常", permission="dashboard:view", risk_level="low"),
            Capability("data.nl2sql", "生成并执行只读自然语言查询", permission="dashboard:view", risk_level="medium"),
        ]

    def execute(self, capability: str, inputs: Dict[str, Any], context: AgentContext) -> AgentResult:
        mapping = {
            "data.structure": "structure",
            "data.trend": "trend",
            "data.anomaly": "anomaly",
            "data.nl2sql": "nl2sql",
        }
        analysis_type = mapping.get(capability)
        if not analysis_type:
            raise KeyError(f"data_decision Agent 不支持能力: {capability}")
        kwargs: Dict[str, Any] = {"analysis_type": analysis_type}
        if analysis_type == "nl2sql":
            kwargs["nl2sql_question"] = inputs.get("question")
        return self._result(data_decision_agent.analyze(**kwargs), context)


def register_builtin_domain_agents() -> None:
    """幂等注册五个领域 Agent。"""
    if domain_registry.list_agents():
        return
    for agent in (ResumeDomainAgent(), AssessmentDomainAgent(), MatchingDomainAgent(), TrainingDomainAgent(), DataDecisionDomainAgent()):
        domain_registry.register(agent)


register_builtin_domain_agents()
