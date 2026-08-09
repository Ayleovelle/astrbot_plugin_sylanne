"""流式抢发 thinking 泄漏根治测试（2026-06-13 用户诊断推动）。

bug 链：on_llm_stream_chunk 旧版在【裸 delta buffer】上跑 _extract_first_sentence，
模型流式【先吐 thinking】时——很多推理模型如此——buffer 第一个句末标点落在
<thinking> 段内 → 抢发了思维链碎片（泄漏 thinking 给用户）+ 存进 stream_first_sent
污染 on_llm_response 的 remainder 匹配，连锁触发 stripped_to_empty 兜底怪话。

修复：抢发前先经 _visible_stream_prefix 取可见前缀——剥已闭合隐藏块 + 在未闭合
thinking open 标签处截断 + 切掉末尾半截标签。本文件钉死该行为，任何重写不得复发。
"""

from __future__ import annotations

from sylanne_alpha.llm_response_pipeline import LLMResponsePipeline


def _pipe() -> LLMResponsePipeline:
    """最小实例：_visible_stream_prefix/_extract_first_sentence 是纯方法，不碰 plugin。"""
    return LLMResponsePipeline(plugin=object())  # type: ignore[arg-type]


# ===========================================================================
# 核心 bug：流式先吐 thinking，其句号不得被当正文抢发
# ===========================================================================

def test_unclosed_thinking_prefix_is_empty() -> None:
    """未闭合 thinking 流式中：可见前缀为空 → 不抢发（thinking 句号不泄漏）。"""
    p = _pipe()
    buf = "<thinking>用户问的是世界杯赛程。我先搜一下。"
    visible = p._visible_stream_prefix(buf)
    assert visible == "", f"未闭合 thinking 应整体 pending，实得 {visible!r}"
    # 抢发判定连锁结果：首句为空
    assert p._extract_first_sentence(visible) == ""


def test_thinking_sentence_not_extracted_as_first() -> None:
    """thinking 段里的句末标点绝不被抽成首句（核心泄漏点）。"""
    p = _pipe()
    buf = "<thinking>这是我的推理。还要继续想。</thinking>"
    visible = p._visible_stream_prefix(buf)
    # 闭合 thinking 被整段剥掉 → 可见为空 → 无首句
    assert "推理" not in visible
    assert p._extract_first_sentence(visible) == ""


def test_visible_text_after_closed_thinking() -> None:
    """thinking 闭合后真正文到达：抽到正文首句，绝不含 thinking 内容。"""
    p = _pipe()
    buf = "<thinking>先想想怎么答。</thinking>世界杯今晚有巴西对摩洛哥。还有别的。"
    visible = p._visible_stream_prefix(buf)
    first = p._extract_first_sentence(visible)
    assert "想想" not in first, f"首句不得含 thinking: {first!r}"
    assert first == "世界杯今晚有巴西对摩洛哥。", f"实得 {first!r}"


def test_half_tag_at_buffer_end_truncated() -> None:
    """末尾半截标签（流式把 <thinking> 切在两 chunk 间）→ 切掉，等下个 chunk。"""
    p = _pipe()
    # 正文 + 半截开标签
    buf = "好的我在。<thi"
    visible = p._visible_stream_prefix(buf)
    assert visible == "好的我在。", f"半截标签应切掉，实得 {visible!r}"
    # 这种情况首句已可抢发（正文部分完整）
    assert p._extract_first_sentence(visible) == "好的我在。"


# ===========================================================================
# 回归保护：无 thinking 的正常流式不受影响
# ===========================================================================

def test_plain_text_unaffected() -> None:
    """无任何隐藏标签的正常正文：可见前缀=原文，首句照常抽（不误伤正路）。"""
    p = _pipe()
    buf = "今晚有巴西对摩洛哥的比赛。要看吗？"
    visible = p._visible_stream_prefix(buf)
    assert visible == buf
    assert p._extract_first_sentence(visible) == "今晚有巴西对摩洛哥的比赛。"


def test_empty_buffer_safe() -> None:
    """空 buffer：可见前缀空，不抛。"""
    p = _pipe()
    assert p._visible_stream_prefix("") == ""


def test_think_short_tag_variant() -> None:
    """<think>（短标签变体）同样被识别为隐藏块。"""
    p = _pipe()
    buf = "<think>短标签也算。</think>真正回复在这。"
    visible = p._visible_stream_prefix(buf)
    assert "短标签" not in visible
    assert p._extract_first_sentence(visible) == "真正回复在这。"


def test_multiline_thinking_stripped() -> None:
    """跨行 thinking（流式累积多行）整段剥离，可见部分干净。"""
    p = _pipe()
    buf = "<thinking>\n第一行推理。\n第二行推理。\n</thinking>\n这才是答案。"
    visible = p._visible_stream_prefix(buf)
    assert "推理" not in visible
    assert "这才是答案。" in visible


def test_text_before_unclosed_thinking_survives() -> None:
    """未闭合 thinking 【之前】的正文要保留（边想边说场景：先答一句再思考）。"""
    p = _pipe()
    buf = "我先说一句。<thinking>然后我开始想"
    visible = p._visible_stream_prefix(buf)
    assert visible == "我先说一句。", f"thinking 前的正文应保留，实得 {visible!r}"
    assert p._extract_first_sentence(visible) == "我先说一句。"

