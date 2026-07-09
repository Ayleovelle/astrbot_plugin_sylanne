"""T3 回归：LLM completion 是 content-parts 列表/repr 时不再把结构原样漏进正文。

根因（对抗审查 workflow w6iyrrw5k 定）：某些 OpenAI 兼容 provider（含 OpenAI 兼容
Gemini 端点）走完 tool 轮后把 assistant content 返成 `[{'type':'text','text':...}]`
列表，或返回它已被 str() 成的单引号 repr（流式拼接还可能截断没闭合）。Sylanne 三个读
边界（v2core/integration.py:482、llm_response_pipeline.py:115/142）原本裸 str()，把
这串结构原样当正文，渲染器再粘 "嗯……" 前缀、分段切成 48 字气泡 → 用户看到
`嗯……[{'type': 'text', 'text': '啊啊啊啊对不起对不起！`。

修复：共享 helper normalize_completion_text 在三个边界 str() 之前归一。本组直测 helper。
"""

from sylanne_alpha.message_dispatch import normalize_completion_text as norm

_APOLOGY = "啊啊啊啊对不起对不起！"


def test_live_content_parts_list():
    assert norm([{"type": "text", "text": _APOLOGY}]) == _APOLOGY


def test_truncated_repr_string():
    """流式截断的 repr（没闭合）也要救回——AstrBot 自己的归一只修完整数组，截断漏过。"""
    assert norm("[{'type': 'text', 'text': '" + _APOLOGY) == _APOLOGY


def test_complete_repr_string():
    assert norm("[{'type': 'text', 'text': '" + _APOLOGY + "'}]") == _APOLOGY


def test_multiline_repr():
    assert norm("[{'type': 'text', 'text': '嗯\\n第二行'}]") == "嗯\n第二行"


def test_multiple_text_parts_joined():
    assert norm([{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]) == "a\nb"


def test_non_text_parts_dropped():
    parts = [{"type": "text", "text": "hi"}, {"type": "image_url", "image_url": {"url": "x"}}]
    assert norm(parts) == "hi"


def test_list_of_plain_strings():
    assert norm(["p1", "p2"]) == "p1\np2"


def test_plain_text_unchanged():
    assert norm("嗯……没喝就好啦！") == "嗯……没喝就好啦！"


def test_plain_text_with_bracket_not_touched():
    """正文里恰好出现 [1,2,3] 之类不应被误判为 content-parts。"""
    assert norm("看这个 [1,2,3] 数组") == "看这个 [1,2,3] 数组"


def test_empty_and_none():
    assert norm([]) == ""
    assert norm(None) == ""
    assert norm("") == ""


def test_no_repr_leak_marker_in_output():
    """任何形态归一后，正文里都不应残留 content-parts 的结构标记。"""
    for inp in (
        [{"type": "text", "text": _APOLOGY}],
        "[{'type': 'text', 'text': '" + _APOLOGY,
        "[{'type': 'text', 'text': '" + _APOLOGY + "'}]",
    ):
        out = norm(inp)
        assert "'type'" not in out and "[{" not in out
        assert _APOLOGY in out


# ── 复审 CLUSTER B 防回归：绝不吃掉 / 截断 / 串味正经内容 ──

def test_fp_non_content_parts_list_repr_preserved():
    """正经回复恰好是 [{'type':'object',...}]（讲 JSON schema）不能被吃成空。"""
    s = "[{'type': 'object', 'properties': {}}]"
    assert norm(s) == s


def test_fp_content_parts_followed_by_prose_preserved():
    """content-parts 形状后还接了散文（模型在讲解）→ 整条原样保留，不丢尾巴。"""
    s = "[{'type': 'text', 'text': 'hi'}] 然后我想说点别的"
    assert norm(s) == s


def test_fp_image_only_nested_text_not_leaked():
    """image part 里嵌套的 'text'（alt）不能被误抽出来当正文。"""
    s = "[{'type': 'image_url', 'image_url': {'text': 'alt'}}]"
    assert norm(s) == s


def test_fp_malformed_repr_preserved_not_corrupted():
    """畸形/不可解析的 repr → 原样保留（安全），绝不截断成半截。"""
    s = "[{'type': 'text', 'text': '啊'}对'}]"  # 内引号未转义=畸形
    assert norm(s) == s  # 不 corrupt 成 '啊'


def test_properly_escaped_quote_recovers():
    """正经转义的 repr（provider str() 会转义内引号）能正确恢复整段文本。"""
    s = "[{'type': 'text', 'text': '啊\\'}对'}]"  # \\' = 转义引号, 文本=啊'}对
    assert norm(s) == "啊'}对"


def test_list_non_content_parts_not_eaten():
    """completion_text 是个不像 content-parts 的 list（如 [1,2,3]）→ 不吃，原样 str。"""
    assert norm([1, 2, 3]) == "[1, 2, 3]"


def test_list_image_only_genuine_empty():
    """真 content-parts 但只有 image part（无 text）→ 空串是正确的（确无正文）。"""
    assert norm([{"type": "image_url", "image_url": {"url": "x"}}]) == ""


def test_fp_truncated_on_backslash_no_raw_leak():
    """流式截断恰好落在转义反斜杠上 → 去掉悬空 \\ 后仍能恢复前缀，绝不漏 raw repr。"""
    cut = "[{'type': 'text', 'text': 'line1\\"  # 截在 \\n 的反斜杠上（末尾一个反斜杠）
    out = norm(cut)
    assert "'type'" not in out and "[{" not in out, "不得漏出 content-parts 结构"
    assert out == "line1"


def test_deeply_nested_untrusted_input_no_crash():
    """不可信 provider 输出深度嵌套（通过 [{...'type'... 守卫）→ literal_eval 在 Py3.10/3.11
    可能抛 RecursionError、Py3.12+ 抛 SyntaxError，两者都须兜住 → 退回原文，绝不让畸形
    输入打挂回复管线（gemini PR #45 review 提的 RecursionError 面）。"""
    evil = "[{'type':'text','text':" + "[" * 5000 + "]" * 5000 + "}]"
    out = norm(evil)  # 不得抛 RecursionError/SyntaxError
    assert out == evil  # 解析失败 → 原样退回，绝不吃/截断/串味
