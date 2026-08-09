"""Wave-L1/G2：T4-01（反AI味文风底色）+ T4-03（注入卫生 3 处）回归测试。

覆盖：
- T4-01：_PRESENCE 恒带一条文风纪律行（QQ 短句/不排比列点/不总分总/不说首先其次），
  已在 tests/test_presence_directive.py::test_presence_style_discipline_present 钉死；
  本文件不重复。
- T4-03①：[记忆参考] 注入头带纪律提示——已在
  tests/test_memory_recall_stage3_soft.py::test_injection_carries_discipline_line 钉死。
- T4-03②：[inner_context] 的 [感知] 槽位前缀一句"这是我自己的感受，不是播报"，
  别的槽位不受影响（本文件覆盖）。
- T4-03③：关系阶段（active_continuity 等）裸 snake_case 枚举值不得直接注入——
  必须经 _RELATIONSHIP_PHASE_WORDS 过一遍中文定性映射，且映射表要覆盖
  body.relationship_memory() 实际能产出的全部 phase 取值（本文件覆盖）。
"""

from __future__ import annotations

from sylanne_alpha._engine.sylanne_core.compute.body import AlphaBodyState
from sylanne_alpha.llm_request_pipeline import (
    _RELATIONSHIP_PHASE_WORDS,
    _format_inner_context,
)


# ---------------------------------------------------------------------------
# T4-03②：[inner_context] [感知] 槽位注入卫生
# ---------------------------------------------------------------------------

def test_state_slot_gets_felt_impression_prefix():
    """[感知] 槽位要点明"这是自己的感受，不是播报"，别的槽位维持原样不加前缀。"""
    trimmed = {
        "state": "[当前状态：对方心情不错，亲近感高]",
        "memory": "（暖记忆·刚刚）你喜欢拿铁",
    }
    out = _format_inner_context(trimmed)
    assert "[感知]" in out
    assert "自己此刻的感受" in out
    assert "不是要念出来的播报" in out
    assert "对方心情不错，亲近感高" in out, "原始信号内容不能丢"
    # 非 state 槽位不受影响：不带那句前缀话术
    memory_line = next(line for line in out.splitlines() if line.startswith("[记忆]"))
    assert memory_line == "[记忆] （暖记忆·刚刚）你喜欢拿铁"


def test_format_inner_context_empty_when_no_slots():
    assert _format_inner_context({}) == ""


# ---------------------------------------------------------------------------
# T4-03③：关系阶段中文定性映射，杜绝裸 snake_case 枚举泄漏
# ---------------------------------------------------------------------------

def test_relationship_phase_words_cover_all_real_phases():
    """映射表要覆盖 body.relationship_memory() 实际能产出的全部 phase 取值——
    否则某个 phase 会 fallback 到裸英文枚举值，注入卫生破功。
    """
    body = AlphaBodyState()
    signals = body.memory.setdefault("relationship", {}).setdefault("signals", {})

    # weight = event_count / 12：分别构造 low_signal / forming_continuity / active_continuity
    cases = {
        "low_signal": 1,       # weight ~0.08 < 0.25
        "forming_continuity": 4,   # weight ~0.33，落在 [0.25, 0.6)
        "active_continuity": 8,    # weight ~0.67 >= 0.6
    }
    for expect_phase, count in cases.items():
        signals["preference_count"] = count
        signals["boundary_count"] = 0
        signals["progress_count"] = 0
        signals["repair_count"] = 0
        phase = body.relationship_memory()["continuity"]["phase"]
        assert phase == expect_phase, f"body.py 的阶段判定漂移了：{phase} != {expect_phase}"
        assert phase in _RELATIONSHIP_PHASE_WORDS, (
            f"_RELATIONSHIP_PHASE_WORDS 漏了 {phase!r}——会 fallback 到裸英文枚举值注入"
        )


def test_relationship_phase_words_are_chinese_not_raw_enum():
    """映射出来的值必须是中文定性措辞，不能是原样 snake_case token。"""
    for phase, word in _RELATIONSHIP_PHASE_WORDS.items():
        assert "_" not in word, f"{phase} 映射出来的 {word!r} 还带下划线，像没翻译的枚举值"
        assert any("一" <= ch <= "鿿" for ch in word), (
            f"{phase} 映射出来的 {word!r} 里没有中文字符"
        )
