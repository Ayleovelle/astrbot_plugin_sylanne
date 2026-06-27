"""优先批修复回归（审计 wzwd8i0ta）：

- #10 assessor_async._parse_response 逐字段安全转换：单个坏字段（如 LLM 返 "v":"oops"）
  只丢自己，不再让裸 float() 抛错把整条评估丢成 {}。
- _clamp_float 助手行为。
"""

from sylanne_alpha.assessor_async import AsyncAssessor, _clamp_float


def _assessor() -> AsyncAssessor:
    # _parse_response 不依赖实例属性，绕开重 __init__ 直测
    return object.__new__(AsyncAssessor)


def test_clamp_float_safe_and_clamped():
    assert _clamp_float("0.5", -1.0, 1.0) == 0.5
    assert _clamp_float(0.5, -1.0, 1.0) == 0.5
    assert _clamp_float(None, -1.0, 1.0) is None
    assert _clamp_float("high", -1.0, 1.0) is None
    assert _clamp_float([1, 2], 0.0, 1.0) is None
    assert _clamp_float(9.9, 0.0, 1.0) == 1.0
    assert _clamp_float(-9.9, 0.0, 1.0) == 0.0


def test_parse_response_bad_field_drops_only_itself():
    a = _assessor()
    # valence 坏（非数字字符串），arousal/wound/intent 好
    r = a._parse_response('{"v":"oops","a":0.7,"w":0.3,"i":"share"}')
    assert "valence" not in r, "坏字段只丢自己"
    assert r.get("arousal") == 0.7, "好字段不被坏字段拖垮"
    assert r.get("wound_risk") == 0.3
    assert r.get("intent") == "share"


def test_parse_response_all_good():
    a = _assessor()
    r = a._parse_response('{"v":-0.4,"a":0.2,"w":0.1,"m":1}')
    assert r["valence"] == -0.4
    assert r["arousal"] == 0.2
    assert r["wound_risk"] == 0.1
    assert r["memorable"] is True


def test_parse_response_non_json_returns_empty():
    a = _assessor()
    assert a._parse_response("没有任何 JSON") == {}
    assert a._parse_response("") == {}
