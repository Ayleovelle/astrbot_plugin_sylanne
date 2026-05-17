from interpretation_engine import interpret_user_text, classify_memory_gate


def test_typo_correction_pattern_yields_candidate_without_memorizing():
    result = interpret_user_text("我打错了，不是桥粱，是桥梁。")

    assert result["candidates"][0]["kind"] == "typo"
    assert result["candidates"][0]["raw_text"] == "桥粱"
    assert result["candidates"][0]["candidate"] == "桥梁"
    assert result["candidates"][0]["should_memorize"] is False


def test_homophone_joke_is_common_ground_not_hard_fact():
    result = interpret_user_text("这个插件真是记亿犹新，谐音梗啦")
    gate = classify_memory_gate(result["candidates"][0])

    assert result["candidates"][0]["kind"] == "homophone"
    assert result["candidates"][0]["humor_likelihood"] >= 0.5
    assert gate["layer"] == "joke_or_bit"
    assert gate["allow_long_term_fact"] is False
