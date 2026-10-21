"""领域 Agent 统一协议。

第一阶段只统一接口和能力描述，不改变现有五个 Agent 的业务算法。
后续 Supervisor、动态规划器和任务执行器都只依赖本模块。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Sequence, runtime_checkable
import uuid


@dataclass(frozen=True)
class Capability:
    """一个可被 Planner 选择的领域能力。"""

    name: str
    description: str
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    permission: str = "agent:execute"
    risk_level: str = "low"
    timeout_seconds: int = 120
    max_retries: int = 2


@dataclass
class AgentContext:
    """执行上下文；区分任务、会话、用户、记忆和工具结果。"""

    task_id: str
    session_id: str
    user_id: Optional[str] = None
    data_scope: Optional[str] = None
    memory: Dict[str, Any] = field(default_factory=dict)
    tool_results: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(cls, *, task_id: Optional[str] = None, session_id: Optional[str] = None, **kwargs: Any) -> "AgentContext":
        return cls(
            task_id=task_id or "task_" + uuid.uuid4().hex[:16],
            session_id=session_id or "session_" + uuid.uuid4().hex[:16],
            **kwargs,
        )


@dataclass
class PlanStep:
    """Planner 生成的一个可执行步骤。"""

    step_id: str
    capability: str
    inputs: Dict[str, Any] = field(default_factory=dict)
    depends_on: List[str] = field(default_factory=list)
    status: str = "pending"
    risk_level: str = "low"
    rationale: str = ""


@dataclass
class AgentResult:
    """所有领域 Agent 使用统一结果结构。"""

    success: bool
    data: Dict[str, Any] = field(default_factory=dict)
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    next_actions: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "evidence": self.evidence,
            "errors": self.errors,
            "next_actions": self.next_actions,
            "metadata": self.metadata,
        }


@dataclass
class RecoveryAction:
    action: str
    reason: str
    retry_after_seconds: int = 0
    requires_approval: bool = False


@runtime_checkable
class DomainAgent(Protocol):
    name: str

    def capabilities(self) -> Sequence[Capability]:
        ...

    def execute(self, capability: str, inputs: Dict[str, Any], context: AgentContext) -> AgentResult:
        ...

    def validate(self, result: AgentResult, context: AgentContext) -> List[str]:
        ...

    def recover(self, error: Exception, context: AgentContext) -> RecoveryAction:
        ...


class DomainAgentRegistry:
    """进程内能力注册表；后续可扩展为配置或数据库驱动。"""

    def __init__(self) -> None:
        self._agents: Dict[str, DomainAgent] = {}
        self._capabilities: Dict[str, tuple[str, Capability]] = {}

    def register(self, agent: DomainAgent) -> DomainAgent:
        if not isinstance(agent, DomainAgent):
            raise TypeError(f"对象不符合 DomainAgent 协议: {agent!r}")
        if agent.name in self._agents:
            raise ValueError(f"Agent 已注册: {agent.name}")
        self._agents[agent.name] = agent
        for capability in agent.capabilities():
            if capability.name in self._capabilities:
                raise ValueError(f"能力名称重复: {capability.name}")
            self._capabilities[capability.name] = (agent.name, capability)
        return agent

    def get(self, name: str) -> DomainAgent:
        try:
            return self._agents[name]
        except KeyError as exc:
            raise KeyError(f"未知领域 Agent: {name}") from exc

    def resolve_capability(self, name: str) -> tuple[DomainAgent, Capability]:
        try:
            agent_name, capability = self._capabilities[name]
        except KeyError as exc:
            raise KeyError(f"未知领域能力: {name}") from exc
        return self._agents[agent_name], capability

    def list_agents(self) -> List[Dict[str, Any]]:
        return [
            {"name": name, "capabilities": [c.name for c in agent.capabilities()]}
            for name, agent in self._agents.items()
        ]

    def list_capabilities(self) -> List[Dict[str, Any]]:
        return [
            {"agent": agent_name, "name": capability.name, "description": capability.description,
             "permission": capability.permission, "risk_level": capability.risk_level,
             "timeout_seconds": capability.timeout_seconds, "max_retries": capability.max_retries}
            for name, (agent_name, capability) in self._capabilities.items()
        ]


domain_registry = DomainAgentRegistry()
