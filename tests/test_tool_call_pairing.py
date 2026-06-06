"""Tests for sanitize_tool_call_pairing (fixes #18).

验证孤儿 tool_calls 清理：严格 provider（DeepSeek 等）要求每个带 tool_calls
的 assistant 消息后必须跟随对应每个 tool_call_id 的 tool 响应，否则 400。
sanitize_tool_call_pairing 在请求定型后移除破损配对，对所有模型生效。
"""

from __future__ import annotations

import sys
import unittest

from sylanne_alpha.llm_request_pipeline import sanitize_tool_call_pairing


def _roles(msgs):
    return [m.get("role") if isinstance(m, dict) else getattr(m, "role", None) for m in msgs]


class TestToolCallPairing(unittest.TestCase):
    def test_well_formed_single(self):
        ctx = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "tool_calls": [{"id": "c1"}]},
            {"role": "tool", "tool_call_id": "c1", "content": "r1"},
            {"role": "assistant", "content": "done"},
        ]
        self.assertEqual(sanitize_tool_call_pairing(ctx), ctx)

    def test_well_formed_multi_tool(self):
        ctx = [
            {"role": "assistant", "tool_calls": [{"id": "c1"}, {"id": "c2"}]},
            {"role": "tool", "tool_call_id": "c1", "content": "r1"},
            {"role": "tool", "tool_call_id": "c2", "content": "r2"},
        ]
        self.assertEqual(sanitize_tool_call_pairing(ctx), ctx)

    def test_forward_orphan_assistant_missing_tool(self):
        ctx = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "tool_calls": [{"id": "c1"}]},
            {"role": "assistant", "content": "final"},
        ]
        out = sanitize_tool_call_pairing(ctx)
        self.assertEqual(_roles(out), ["user", "assistant"])
        self.assertEqual(out[-1]["content"], "final")

    def test_reverse_orphan_lone_tool(self):
        ctx = [
            {"role": "tool", "tool_call_id": "x", "content": "r"},
            {"role": "user", "content": "hi"},
        ]
        self.assertEqual(_roles(sanitize_tool_call_pairing(ctx)), ["user"])

    def test_partial_response_dropped_entirely(self):
        # 两个 tool_call 仅一个有响应 → 整组（含已响应的 tool）清除
        ctx = [
            {"role": "assistant", "tool_calls": [{"id": "c1"}, {"id": "c2"}]},
            {"role": "tool", "tool_call_id": "c1", "content": "r1"},
            {"role": "assistant", "content": "x"},
        ]
        out = sanitize_tool_call_pairing(ctx)
        self.assertEqual(_roles(out), ["assistant"])
        self.assertEqual(out[0]["content"], "x")

    def test_order_independent(self):
        # tool 出现在 assistant 之前也能正确配对（三遍扫描保证）
        ctx = [
            {"role": "tool", "tool_call_id": "c1", "content": "r1"},
            {"role": "assistant", "tool_calls": [{"id": "c1"}]},
        ]
        self.assertEqual(sanitize_tool_call_pairing(ctx), ctx)

    def test_multi_turn_mixed(self):
        ctx = [
            {"role": "assistant", "tool_calls": [{"id": "a"}]},
            {"role": "tool", "tool_call_id": "a", "content": "ra"},
            {"role": "assistant", "content": "mid"},
            {"role": "assistant", "tool_calls": [{"id": "b"}]},  # 孤儿
            {"role": "assistant", "content": "end"},
        ]
        out = sanitize_tool_call_pairing(ctx)
        self.assertEqual(_roles(out), ["assistant", "tool", "assistant", "assistant"])
        self.assertEqual([m for m in out if m.get("tool_calls")][0]["tool_calls"][0]["id"], "a")

    def test_object_form_orphan(self):
        # 对象形态（getattr 分支）：带 tool_calls 的 assistant 对象缺 tool → 丢弃
        class _Msg:
            def __init__(self, role, tool_calls=None, tool_call_id=None, content=""):
                self.role = role
                self.tool_calls = tool_calls
                self.tool_call_id = tool_call_id
                self.content = content

        class _TC:
            def __init__(self, _id):
                self.id = _id

        ctx = [
            _Msg("user", content="hi"),
            _Msg("assistant", tool_calls=[_TC("c1")]),  # 孤儿
        ]
        out = sanitize_tool_call_pairing(ctx)
        self.assertEqual(_roles(out), ["user"])

    def test_edge_cases(self):
        self.assertEqual(sanitize_tool_call_pairing([]), [])
        self.assertIsNone(sanitize_tool_call_pairing(None))
        self.assertEqual(sanitize_tool_call_pairing("str"), "str")


class TestStreamingThinkingFilter(unittest.TestCase):
    """流式 thinking 剥离（修复流式模式 ResultDecorateStage 被跳过的泄露）。"""

    @staticmethod
    def _run(chunks):
        from sylanne_alpha.llm_request_pipeline import StreamingThinkingFilter

        f = StreamingThinkingFilter()
        out = "".join(f.feed(c) for c in chunks)
        return out + f.flush()

    def test_single_chunk(self):
        self.assertEqual(self._run(["<thinking>secret</thinking>你好"]), "你好")

    def test_tag_split_across_chunks(self):
        self.assertEqual(self._run(["<thin", "king>x</thi", "nking>答案"]), "答案")

    def test_pure_thinking_empty(self):
        self.assertEqual(self._run(["<thinking>", "只思考", "</thinking>"]), "")

    def test_unclosed_thinking_dropped(self):
        self.assertEqual(self._run(["可见<thinking>没闭合"]), "可见")

    def test_char_by_char(self):
        self.assertEqual(self._run(list("a<draft_notes>n</draft_notes>b")), "ab")

    def test_non_tag_angle_bracket(self):
        self.assertEqual(self._run(["1 < 2 and a<b"]), "1 < 2 and a<b")

    def test_multiple_blocks(self):
        self.assertEqual(
            self._run(["a<think>x</think>b<thinking>y</thinking>c"]), "abc"
        )

    def test_partial_tag_flushed(self):
        # 末尾半截看似标签但流结束 → 补发，不丢用户文本
        self.assertEqual(self._run(["答案ok<thi"]), "答案ok<thi")


if __name__ == "__main__":
    unittest.main()
