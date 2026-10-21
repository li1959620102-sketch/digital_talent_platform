from app.agents.supervisor import supervisor_planner


def test_supervisor_builds_cross_domain_plan():
    plan = supervisor_planner.plan(
        "为 Java 岗位筛选候选人并生成培训建议",
        {"position_id": 10, "talent_id": 20},
        use_llm=False,
    )

    names = [step["capability"] for step in plan["steps"]]
    assert plan["source"] == "rules"
    assert "matching.position_to_talents" in names
    assert "training.recommend_path" in names
    assert plan["validation"]["valid"] is True
    assert plan["steps"][1]["depends_on"] == [plan["steps"][0]["step_id"]]


def test_supervisor_has_safe_fallback_for_ambiguous_goal():
    plan = supervisor_planner.plan("请给我一个人才数据概览", {}, use_llm=False)
    assert plan["steps"]
    assert plan["steps"][0]["capability"] == "data.structure"
