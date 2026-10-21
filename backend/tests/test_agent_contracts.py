from app.agents.agent_contracts import (
    AgentContext,
    AgentResult,
    Capability,
    DomainAgentRegistry,
    RecoveryAction,
)


class FakeAgent:
    name = "fake"

    def capabilities(self):
        return [Capability("fake.echo", "回显输入")]

    def execute(self, capability, inputs, context):
        return AgentResult(success=True, data=inputs)

    def validate(self, result, context):
        return []

    def recover(self, error, context):
        return RecoveryAction(action="retry", reason=str(error))


def test_domain_agent_registry_contract():
    registry = DomainAgentRegistry()
    registry.register(FakeAgent())
    agent, capability = registry.resolve_capability("fake.echo")
    context = AgentContext.create(task_id="task-1", session_id="session-1")

    assert agent.name == "fake"
    assert capability.name == "fake.echo"
    assert agent.execute("fake.echo", {"value": 1}, context).data["value"] == 1
    assert registry.list_agents()[0]["capabilities"] == ["fake.echo"]
