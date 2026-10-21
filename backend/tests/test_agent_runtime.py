from app.agents.agent_runtime import AgentRuntime


def test_task_plan_memory_and_approval():
    runtime = AgentRuntime()
    task = runtime.create_task(
        "data_decision",
        "分析人才结构",
        {"analysis_type": "structure"},
        session_id="session-test",
        requires_approval=True,
        owner="tester",
    )

    assert task["status"] == "pending_approval"
    assert task["plan"]["steps"][0]["name"] == "route"
    assert task["memory"]["short_term"]["last_goal"] == "分析人才结构"

    approved = runtime.approve(task["task_id"], True, "tester")
    assert approved["approved"] is True
    assert approved["status"] == "pending"


def test_retry_metrics_and_handoff():
    runtime = AgentRuntime()
    task = runtime.create_task("training", "生成培训路径", {"talent_id": 1})
    calls = {"count": 0}

    def runner():
        calls["count"] += 1
        return {"success": True, "path": []}

    runtime._run(task["task_id"], runner)
    result = runtime.get(task["task_id"])
    assert result["status"] == "success"
    assert calls["count"] == 1
    assert runtime.metrics.snapshot()["counters"]["training.success"] == 1

    handed = runtime.handoff(task["task_id"], "human_queue", "tester")
    assert handed["owner"] == "human_queue"


def test_recover_tasks_rebuilds_pending_runner():
    runtime = AgentRuntime()
    task = runtime.create_task(
        "supervisor",
        "恢复任务",
        {},
        plan_override={"plan_id": "p", "steps": []},
    )
    seen = []

    def factory(value):
        seen.append(value["task_id"])
        return lambda: {"success": True}

    assert runtime.recover_tasks(factory) == 1
    assert task["task_id"] in seen


def test_idempotency_and_cancel_are_safe():
    runtime = AgentRuntime()
    first = runtime.create_task("data_decision", "查询", {}, owner="u1", idempotency_key="req-1")
    duplicate = runtime.create_task("data_decision", "查询", {}, owner="u1", idempotency_key="req-1")
    assert duplicate["task_id"] == first["task_id"]

    canceled = runtime.cancel(first["task_id"], "u1")
    assert canceled["status"] == "canceled"
    # 终态任务不能被审批重新唤醒。
    assert runtime.approve(first["task_id"], True, "u1")["status"] == "canceled"
