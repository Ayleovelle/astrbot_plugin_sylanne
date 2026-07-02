"""fix/context-integrity（contrib）：外部主动消息插件模板泄漏进历史 → 脱敏。

背景（review 发现，CONTRIB x2 之二）：外部插件 astrbot_plugin_proactive_chat
每次发主动消息后，都把私聊默认提示词模板（session_config['proactive_prompt']
的默认值，见该插件 `_conf_schema.json` friend_settings.proactive_prompt.default）
——完整的 "[系统任务：主动对话]\\n你被授权在私聊中发起一次..." 元指令文本——
当作一条"用户说的话"存进 conversation_manager 历史
（core/chat_flow.py._finalize_and_reschedule → add_message_pair 的
user_prompt 参数就是这段模板本身）。这条假用户话会在此后每一轮对话里被当成
"用户历史发言"原样喂回 LLM，逐轮累积、毒化后续所有上下文。

该插件是外部代码（不可编辑）；修复只能在我们自己读取 request.contexts 时，把
匹配这个精确签名前缀的 user 轮次替换成中性占位
"（她此前主动发来过一条消息）"——converting instruction-templates to
placeholders IMPROVES persisted history，且只做精确签名前缀匹配（不做宽松
包含匹配），真实用户文本几乎不可能恰好以这个字面量开头，正常轮次字节级不变。

覆盖：
  ① scrub_proactive_template_turns：命中模板签名的 user 轮次 → 替换为占位，
     其余字段（如自定义 key）原样保留。
  ② 正常轮次（含提及"主动""系统任务"字样但不是精确签名前缀的真实用户话）
     字节级不受影响。
  ③ 兼容纯字符串 content（legacy）与 Message.model_dump() 输出的内容块列表
     content（当前形态，见 core/agent/message.py TextPart）。
  ④ 无命中时返回同一个 contexts 对象引用（不做无意义拷贝）。
  ⑤ assistant/system 角色即便内容恰好命中签名也不触碰（这条模板只会以
     user 轮次的身份泄漏进历史，收窄匹配面）。
"""

from __future__ import annotations

from sylanne_alpha.llm_request_pipeline import (
    _PROACTIVE_TEMPLATE_PLACEHOLDER,
    _PROACTIVE_TEMPLATE_SIGNATURE,
    scrub_proactive_template_turns,
)

_TEMPLATE_TEXT = (
    "[系统任务：主动对话]\n"
    "你被授权在私聊中发起一次"
    "\"主动消息\"。你的回复必须完全符合你的人格设定。"
)


class TestScrubHitsStringContent:
    def test_matching_user_turn_replaced(self) -> None:
        contexts = [
            {"role": "user", "content": _TEMPLATE_TEXT},
            {"role": "assistant", "content": "在的呀"},
        ]
        out, n = scrub_proactive_template_turns(contexts)
        assert n == 1
        assert out[0]["content"] == _PROACTIVE_TEMPLATE_PLACEHOLDER
        assert out[0]["role"] == "user"
        # 未命中的轮次原样保留
        assert out[1] == {"role": "assistant", "content": "在的呀"}

    def test_preserves_other_fields_on_replaced_message(self) -> None:
        contexts = [
            {"role": "user", "content": _TEMPLATE_TEXT, "timestamp": 123, "name": "u1"},
        ]
        out, n = scrub_proactive_template_turns(contexts)
        assert n == 1
        assert out[0]["timestamp"] == 123
        assert out[0]["name"] == "u1"
        assert out[0]["content"] == _PROACTIVE_TEMPLATE_PLACEHOLDER


class TestScrubHitsListContent:
    """兼容 Message.model_dump() 输出的内容块列表形态。"""

    def test_matching_list_content_replaced_preserving_list_shape(self) -> None:
        contexts = [
            {
                "role": "user",
                "content": [{"type": "text", "text": _TEMPLATE_TEXT}],
            },
        ]
        out, n = scrub_proactive_template_turns(contexts)
        assert n == 1
        assert out[0]["content"] == [
            {"type": "text", "text": _PROACTIVE_TEMPLATE_PLACEHOLDER}
        ]

    def test_non_text_blocks_do_not_match(self) -> None:
        contexts = [
            {"role": "user", "content": [{"type": "image_url", "image_url": "x"}]},
        ]
        out, n = scrub_proactive_template_turns(contexts)
        assert n == 0
        assert out is contexts


class TestScrubLeavesNormalTurnsByteIdentical:
    def test_real_user_text_mentioning_similar_words_untouched(self) -> None:
        contexts = [
            {"role": "user", "content": "你今天怎么突然主动找我说话呀"},
            {"role": "user", "content": "刚才那个系统任务是啥呀"},
        ]
        out, n = scrub_proactive_template_turns(contexts)
        assert n == 0
        assert out is contexts
        assert out[0]["content"] == "你今天怎么突然主动找我说话呀"
        assert out[1]["content"] == "刚才那个系统任务是啥呀"

    def test_empty_contexts_passthrough(self) -> None:
        out, n = scrub_proactive_template_turns([])
        assert n == 0
        assert out == []

    def test_non_list_passthrough(self) -> None:
        out, n = scrub_proactive_template_turns(None)
        assert n == 0
        assert out is None


class TestScrubRoleGating:
    def test_assistant_role_with_matching_text_not_touched(self) -> None:
        """签名只应匹配 user 轮次——assistant/system 即便文本恰好命中也不碰。"""
        contexts = [
            {"role": "assistant", "content": _TEMPLATE_TEXT},
            {"role": "system", "content": _TEMPLATE_TEXT},
        ]
        out, n = scrub_proactive_template_turns(contexts)
        assert n == 0
        assert out is contexts

    def test_mixed_batch_only_user_replaced(self) -> None:
        contexts = [
            {"role": "user", "content": _TEMPLATE_TEXT},
            {"role": "assistant", "content": _TEMPLATE_TEXT},
        ]
        out, n = scrub_proactive_template_turns(contexts)
        assert n == 1
        assert out[0]["content"] == _PROACTIVE_TEMPLATE_PLACEHOLDER
        assert out[1]["content"] == _TEMPLATE_TEXT


def test_signature_constant_matches_real_plugin_default_prefix() -> None:
    """钉死签名常量本身，防止未来改动悄悄漂移导致再也匹配不上真实模板。"""
    assert _PROACTIVE_TEMPLATE_SIGNATURE == "[系统任务：主动对话]"
    assert _TEMPLATE_TEXT.startswith(_PROACTIVE_TEMPLATE_SIGNATURE)
