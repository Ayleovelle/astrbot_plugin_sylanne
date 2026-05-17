from expression_policy import choose_expression_policy, build_expression_policy_prompt


def test_technical_question_prefers_tool_like_brief_answer():
    policy = choose_expression_policy(
        current_user_text="帮我提交并创建 release",
        interpretation_candidates=[],
        is_user_correction=False,
        is_low_signal=False,
    )

    assert policy["posture"] == "tool_like"
    assert policy["verbosity"] == "brief"
    assert "technical_or_workflow_request" in policy["reasons"]


def test_low_confidence_interpretation_prefers_clarify():
    policy = choose_expression_policy(
        current_user_text="这个记亿是什么",
        interpretation_candidates=[{"confidence": 0.42, "kind": "homophone", "candidate": "记忆"}],
        is_user_correction=False,
        is_low_signal=False,
    )

    assert policy["posture"] == "clarify"
    prompt = build_expression_policy_prompt(policy)
    assert "[sylanne_expression_policy]" in prompt
    assert "不要强行玩梗" in prompt
