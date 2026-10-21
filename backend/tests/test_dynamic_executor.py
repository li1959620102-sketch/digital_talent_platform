from app.agents.agent_contracts import AgentContext, AgentResult, Capability
from app.agents.dynamic_executor import DynamicPlanExecutor


class FakeCapabilityAgent:
    def capabilities(self):
        return []

    def execute(self, capability, inputs, context):
        return AgentResult(success=True, data={"capability": capability, "inputs": inputs})

    def validate(self, result, context):
        return []


def test_dynamic_executor_runs_dependency_order(monkeypatch):
    agent = FakeCapabilityAgent()
    capability = Capability("fake.step", "测试能力", max_retries=0)
    monkeypatch.setattr("app.agents.dynamic_executor.domain_registry.resolve_capability", lambda _: (agent, capability))
    plan = {
        "plan_id": "sup-test",
        "steps": [
            {"step_id": "step-1", "capability": "fake.step", "inputs": {"n": 1}, "depends_on": []},
            {"step_id": "step-2", "capability": "fake.step", "inputs": {"n": 2}, "depends_on": ["step-1"]},
        ],
    }

    result = DynamicPlanExecutor().execute(plan, AgentContext.create(task_id="t1", session_id="s1"))
    assert result["success"] is True
    assert [item["step_id"] for item in result["steps"]] == ["step-1", "step-2"]
    assert result["context"]["step-2"]["data"]["inputs"]["n"] == 2


def test_dynamic_executor_resolves_previous_result_reference(monkeypatch):
    agent = FakeCapabilityAgent()
    capability = Capability("fake.step", "测试能力", max_retries=0)
    monkeypatch.setattr("app.agents.dynamic_executor.domain_registry.resolve_capability", lambda _: (agent, capability))
    plan = {
        "plan_id": "sup-ref",
        "steps": [
            {"step_id": "step-1", "capability": "fake.step", "inputs": {"value": "first"}, "depends_on": []},
                {"step_id": "step-2", "capability": "fake.step", "inputs": {"previous": "$step-1.data.inputs.value"}, "depends_on": ["step-1"]},
        ],
    }
    result = DynamicPlanExecutor().execute(plan, AgentContext.create())
    assert result["success"] is True
    assert result["steps"][1]["result"]["data"]["inputs"]["previous"] == "first"


def test_dynamic_executor_replans_after_failure(monkeypatch):
    class ReplanAgent(FakeCapabilityAgent):
        def execute(self, capability, inputs, context):
            if capability == "fake.bad":
                return AgentResult(success=False, errors=["temporary failure"])
            return AgentResult(success=True, data={"ok": True})

    agent = ReplanAgent()
    monkeypatch.setattr(
        "app.agents.dynamic_executor.domain_registry.resolve_capability",
        lambda name: (agent, Capability(name, "测试能力", max_retries=0)),
    )
    plan = {"plan_id": "replan", "goal": "完成任务", "steps": [{"step_id": "bad", "capability": "fake.bad", "inputs": {}, "depends_on": []}]}

    def replan(goal, inputs, context):
        return {"plan_id": "replanned", "goal": goal, "steps": [{"step_id": "good", "capability": "fake.good", "inputs": {}, "depends_on": []}]}

    result = DynamicPlanExecutor().execute(plan, AgentContext.create(), replan_fn=replan)
    assert result["success"] is True
    assert result["replans"] == 1


def test_dynamic_executor_enforces_capability_permission(monkeypatch):
    agent = FakeCapabilityAgent()
    monkeypatch.setattr(
        "app.agents.dynamic_executor.domain_registry.resolve_capability",
        lambda _: (agent, Capability("secure.step", "受限能力", permission="secure:execute", max_retries=0)),
    )
    plan = {"plan_id": "permission", "steps": [{"step_id": "secure", "capability": "secure.step", "inputs": {}, "depends_on": []}]}
    context = AgentContext.create(metadata={"permissions": ["agent:execute"]})
    result = DynamicPlanExecutor().execute(plan, context)
    assert result["success"] is False
    assert result["steps"][0]["status"] == "permission_denied"
