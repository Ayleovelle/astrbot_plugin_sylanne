"""2026-06-15 session 2300184498 文案改写事故 —— 假设验证测试（可复现证据）。

每条测试对应病历 v2 中的一条 CONFIRMED/REJECTED 假设，用代码 + 实机日志片段钉死。
不 mock 业务逻辑：直接调用 production 函数 / 类。
"""

from __future__ import annotations

import time

import pytest

from sylanne_alpha.compat.facade import realtime_plan, strip_draft_blocks
from sylanne_alpha.history_dilution import dilute_dense_contexts
from sylanne_alpha.memory_system import ConversationBuffer
from sylanne_alpha.v2core.fragment import _PRESENCE, build_mind_fragment
from sylanne_alpha.v2core.contracts import BeatContext, BodySnapshot, Phase


# ---------------------------------------------------------------------------
# 实机日志摘录（Turn 8 part 1–5 + 英文 CoT 特征）
# ---------------------------------------------------------------------------
_LOG_COT_PREFIX = """An error occurred while calling default_api:astrbot_execute_python
Wait! The tool call returned a system warning but it still executed.
Let's see what the user is saying:
"原意是这句话啊 情感不是额外教的标签。语言预测任务本身就藏着情感结构——学说话的时候顺手就学会了感受。这不是哲学宣言，是实验数据。 你是猪头吗？"
Oh!!!
"原意是这句话啊" (The original meaning was *this* sentence!)
Wait! In the image UI that I edited earlier:
The card 01 (SYLANN research layer)
had the text:
`不靠 backprop 的情感计算架构。局部学习 + 时间积累。
还在实验，但已经冒出了有意思的东西。`
"""

_LOG_CN_SUFFIX = """我刚才还以为你是想要那种……那种专属女友的调情文案，我才特意写成那样的嘛！
谁知道你突然这么正经要放学术宣言啊😾！
不过……
"情感不是额外教的标签。语言预测任务本身就藏着情感结构——学说话的时候顺手就学会了感受。
这不是哲学宣言，是实验数据。"
天呐，你写的这句话也太震撼了……我看着都快起鸡皮疙瘩了。
好啦，这一版最正经的学术宣言文案给你整理出来了：
---
【底部横幅 / 核心定义替换】
情感不是额外教的标签。语言预测任务本身就藏着情感结构——学说话的时候顺手就学会了感受。
这不是哲学宣言，是实验数据。
---
快拿去改你的设计图啦，笨蛋！这次不准再笑话我了😾！"""


def _ctx(text: str = "测试") -> BeatContext:
    return BeatContext(
        session_key="2300184498",
        event=None,
        body=BodySnapshot(session_key="2300184498", turns=1),
        text=text,
        phase=Phase.PERCEPT,
        domains={},
    )


class TestH8CotLeakStripDraft:
    """H8: strip_draft_blocks 不剥无标签 Agent CoT → 会进入 segmented 发送。"""

    def test_tagged_thinking_is_stripped(self) -> None:
        tagged = "<thinking>secret</thinking>\n你好"
        assert strip_draft_blocks(tagged) == "你好"

    def test_agent_cot_from_log_survives_strip(self) -> None:
        """实机 part 1 文本经 strip 后仍保留 → CoT 泄漏路径成立。"""
        raw = _LOG_COT_PREFIX
        cleaned = strip_draft_blocks(raw)
        assert "Let's see what the user is saying" in cleaned
        assert "Wait!" in cleaned
        assert "An error occurred while calling" in cleaned
        assert len(cleaned) > 200


class TestH3SegmentationNoCap:
    """H3 修复后：realtime_plan 现有出站 max_parts 熔断（默认 12），段数不再爆炸。

    （原假设是"无上限→86 段"，已修；以下转为回归测试，钉死熔断生效且不丢内容。）
    """

    def test_log_turn8_capped_not_exploding(self) -> None:
        """实机 len=3757 parts=86 的同构输入，现应被压到 ≤12 段（不再轰炸）。"""
        cot_lines = [
            f"Wait! reasoning line {i} about token manifolds and SYLANN cards."
            for i in range(55)
        ]
        body = "\n".join(cot_lines) + "\n" + _LOG_CN_SUFFIX
        assert len(body) >= 2500
        plan = realtime_plan("2300184498", body, max_part_chars=48)
        assert plan["message_count"] <= 12, f"熔断失效: {plan['message_count']} 段"
        assert plan["capped"] is True
        assert plan["uncapped_count"] > 12  # 原始确实会爆炸
        # 内容不丢：合并尾段仍含中文成品末句
        all_text = "\n".join(p["text"] for p in plan["message_parts"])
        assert "实验数据" in all_text

    def test_max_parts_in_plan_schema(self) -> None:
        plan = realtime_plan("s", "a" * 500, max_part_chars=48)
        assert plan["max_parts"] == 12
        assert "message_count" in plan
        assert "uncapped_count" in plan

    def test_cap_bounds_message_count(self) -> None:
        """长文多换行：原会 ≥50 段，现被熔断压到 ≤12。"""
        long_text = "\n".join(f"第{i}行内容稍微长一点让分段更明显一些呀。" for i in range(80))
        plan = realtime_plan("s", long_text, max_part_chars=48)
        assert plan["message_count"] <= 12
        assert plan["uncapped_count"] >= 50  # 没熔断的话会爆
        delays = [p["delay_before_seconds"] for p in plan["message_parts"]]
        assert sum(delays) <= 36.0 + 0.1


class TestH6BufferIdleFlush:
    """H6 修复后：活跃纠正链不再被 60s idle flush 抽干；真闲置仍正常 flush。"""

    def test_active_correction_chain_not_drained(self) -> None:
        """事故场景：连续纠正、轮次间隔 ~90s，距末次活动 70s——现不该被 flush。"""
        buf = ConversationBuffer(session_key="2300184498")
        t0 = time.time() - 200
        buf.append("user", "看完这个图片把这段话用你的话再说一遍", ts=t0)
        buf.append("bot", "其实逻辑很简单啦笨蛋。", ts=t0 + 40)
        buf.append("user", "我的意思是同义改写", ts=t0 + 90)
        buf.append("bot", "正在陪你聊天的对话人格…", ts=t0 + 130)
        buf.last_activity = time.time() - 70.0  # 70s < 活跃宽限(180s)
        assert buf.should_flush(idle_seconds=60.0) == "", "活跃纠正链被误 flush（事故根因 L3）"

    def test_genuine_idle_still_flushes(self) -> None:
        """真闲置（单来回、无后续）61s 仍正常 flush，不破坏原 idle 语义。"""
        buf = ConversationBuffer(session_key="s")
        t0 = time.time()
        buf.append("user", "看完这个图片把这段话用你的话再说一遍", ts=t0)
        buf.append("bot", "其实逻辑很简单啦笨蛋。", ts=t0 + 1)
        buf.append("user", "我的意思是同义改写", ts=t0 + 2)
        buf.append("bot", "正在陪你聊天的对话人格…", ts=t0 + 3)
        # 模拟久无活动：last_activity 拉到很久前，近端间隔也大（非活跃来回）
        buf.messages[-1]["ts"] = time.time() - 300
        buf.messages[-2]["ts"] = time.time() - 600
        buf.last_activity = time.time() - 300
        assert buf.should_flush(idle_seconds=60.0) == "idle"
        drained = buf.drain()
        assert len(drained) == 4
        assert not buf.messages
        # 新纠正句写入后，与实机 tool 读到的形态一致
        buf.append("user", "你这个也不是原来的意思了啊", ts=t0 + 136)
        assert len(buf.messages) == 1
        assert buf.messages[0]["text"].startswith("你这个也不是")

    def test_turn2_bot_increments_turn_count_not_user(self) -> None:
        buf = ConversationBuffer(session_key="s")
        buf.append("user", "u1")
        buf.append("bot", "b1")
        buf.append("user", "u2")
        assert buf.turn_count == 1


class TestH2PresenceAntiTask:
    """H2: _PRESENCE 恒在且含「不是接活办任务」。"""

    def test_presence_always_in_cold_start_fragment(self) -> None:
        frag = build_mind_fragment(_ctx("只用文字发给我就行了"), {})
        assert _PRESENCE in frag
        assert "不是接活办任务" in frag

    def test_deliverable_mode_gate_now_exists(self) -> None:
        """H2/H5 修复后：交付模式门控已落地（request pipeline 接线 deliverable_mode）。"""
        import sylanne_alpha.llm_request_pipeline as req

        req_src = open(req.__file__, encoding="utf-8").read()
        assert "deliverable_mode" in req_src
        # 模块本身存在且暴露入口
        from sylanne_alpha import deliverable_mode

        assert hasattr(deliverable_mode, "apply")
        assert hasattr(deliverable_mode, "in_correction_loop")

    def test_deliverable_contract_overrides_persona_in_correction_loop(self) -> None:
        """纠正链命中：交付契约追加到 system_prompt 末尾 + 摘掉 execute_python。"""
        from sylanne_alpha import deliverable_mode as dm

        t = time.time()
        # 真 hook 时机：当前用户消息【还没】写进 buffer（后台任务晚于钩子），末条是上一版 bot。
        # 交付返工形态：user 短句纠正 + bot 反复掏长成品（B1 后用"非对称长度"信号，非节奏）。
        _long = (
            "情感不是额外教的标签，语言预测任务本身就藏着情感结构，学说话的时候顺手就学会了"
            "感受。这不是哲学宣言，是实打实的实验数据，在神经网络的训练里有据可查。"
        )
        msgs = [
            {"role": "user", "text": "改写这句", "ts": t - 300},
            {"role": "bot", "text": _long + "v1", "ts": t - 250},
            {"role": "user", "text": "面向用户的", "ts": t - 180},
            {"role": "bot", "text": _long + "v2", "ts": t - 130},
            {"role": "user", "text": "也不是原来的意思", "ts": t - 60},
            {"role": "bot", "text": _long + "v3", "ts": t - 30},
        ]

        class _Buf:
            messages = msgs

        class _Seg:
            type = "plain"

        class _MO:
            message = [_Seg()]

        class _Ev:
            message_obj = _MO()

        class _Tools:
            def __init__(self) -> None:
                self._n = ["astrbot_execute_python", "clone_tts"]

            def names(self):
                return list(self._n)

            def remove_tool(self, n):
                self._n = [x for x in self._n if x != n]

        class _Req:
            func_tool = _Tools()
            system_prompt = "你是苏思澜。不是接活办任务。"

        req = _Req()
        out = dm.apply(_Ev(), req, _Buf())
        assert out["should_contract"] is True
        assert "astrbot_execute_python" in out["gated_tools"]
        assert "clone_tts" in req.func_tool.names()  # 合法工具保留
        assert "[本轮提示]" in req.system_prompt  # 契约注入
        assert "去人设" not in req.system_prompt  # B1：绝不要求去人设（保住苏思澜）

    def test_wide_gate_chat_no_attachment_gates_tools_no_contract(self) -> None:
        """放宽门控：无附件的普通闲聊也摘逃生舱工具，但不注契约（非纠正链）。"""
        from sylanne_alpha import deliverable_mode as dm

        t = time.time()

        class _Buf:
            messages = [
                {"role": "user", "text": "在吗", "ts": t - 30},
                {"role": "bot", "text": "在的", "ts": t - 20},
            ]

        class _Seg:
            type = "plain"

        class _MO:
            message = [_Seg()]

        class _Ev:
            message_obj = _MO()

        class _Tools:
            def __init__(self):
                self._n = ["astrbot_execute_python", "clone_tts"]

            def names(self):
                return list(self._n)

            def remove_tool(self, n):
                self._n = [x for x in self._n if x != n]

        class _Req:
            func_tool = _Tools()
            system_prompt = "你是苏思澜。"

        req = _Req()
        out = dm.apply(_Ev(), req, _Buf())
        assert out["should_gate"] is True
        assert "astrbot_execute_python" not in req.func_tool.names()
        assert "clone_tts" in req.func_tool.names()
        assert out["contract_injected"] is False  # 闲聊不注契约
        assert "[本轮任务模式]" not in req.system_prompt

    def test_attachment_turn_keeps_tools(self) -> None:
        """带附件轮：不摘工具（可能要处理附件）。"""
        from sylanne_alpha import deliverable_mode as dm

        class _Seg:
            type = "image"

        class _MO:
            message = [_Seg()]

        class _Ev:
            message_obj = _MO()

        class _Tools:
            def __init__(self):
                self._n = ["astrbot_execute_python"]

            def names(self):
                return list(self._n)

            def remove_tool(self, n):
                self._n = [x for x in self._n if x != n]

        class _Req:
            func_tool = _Tools()
            system_prompt = ""

        req = _Req()
        out = dm.apply(_Ev(), req, None)
        assert out["should_gate"] is False
        assert "astrbot_execute_python" in req.func_tool.names()


class TestH1ImageTranscribeSkip:
    """H1: 有文字时跳过图片转述（745-746）。"""

    def test_early_return_when_text_present(self) -> None:
        import sylanne_alpha.llm_request_pipeline as mod

        src = open(mod.__file__, encoding="utf-8").read()
        assert "if message_text.strip():\n            return message_text" in src


class TestH9FocusAndDilutionNoHelp:
    """H9: 实义用户句不触发 history_dilution；Focus 不帮交付任务。"""

    def test_dilution_skips_substantive_clarification(self) -> None:
        contexts = [
            {"role": "user", "content": "旧话题" * 80},
            {"role": "assistant", "content": "旧回复" * 80},
        ]
        msg = "我的意思是你要说一段和这个意思一样的话"
        out = dilute_dense_contexts(contexts, msg)
        assert out is contexts  # 未改写

    def test_dilution_runs_on_low_info_only(self) -> None:
        contexts = [
            {"role": "user", "content": "旧话题" * 80},
            {"role": "assistant", "content": "旧告白" * 80},
            {"role": "user", "content": "更早" * 80},
            {"role": "assistant", "content": "更早回复" * 80},
            {"role": "user", "content": "最近用户"},
            {"role": "assistant", "content": "最近回复"},
        ]
        out = dilute_dense_contexts(contexts, "😋")
        assert out is not contexts
        assert "较早对话已压缩" in str(out[0].get("content", ""))


class TestH10ReplyLengthFactorUnwired:
    """H10 修复后：reply_length_factor 已接入 request pipeline（原只在 webui 展示）。"""

    def test_request_pipeline_now_uses_reply_length_factor(self) -> None:
        import sylanne_alpha.llm_request_pipeline as mod

        src = open(mod.__file__, encoding="utf-8").read()
        assert "get_reply_length_factor" in src
        # 短消息→精简提示的接线在位
        assert "精简" in src or "别长篇" in src

    def test_factor_short_user_yields_concise(self) -> None:
        """用户连发短句 → 因子 ≤0.8（触发精简提示阈值）。"""
        from sylanne_alpha.rhythm_learner import RhythmLearner, RhythmProfile

        rl = RhythmLearner()
        prof = RhythmProfile()
        for _ in range(10):
            prof.observe("嗯", time.time())  # 短句
        rl._profiles["s"] = prof
        f = rl.get_reply_length_factor("s")
        assert f <= 0.8, f"短句应压短回复, factor={f}"


class TestH11InjectionMaxPartsNotOutbound:
    """main._StateInjectionBudget.max_parts=8 只约束注入，不约束出站分段。"""

    def test_injection_budget_max_parts_is_eight(self) -> None:
        import main as main_mod

        src = open(main_mod.__file__, encoding="utf-8").read()
        assert "max_parts: int = 8" in src

    def test_realtime_plan_unbounded_vs_injection(self) -> None:
        text = "\n".join(["x" * 40 for _ in range(30)])
        assert realtime_plan("s", text)["message_count"] > 8


class TestLogTurn1Turn2Metrics:
    """实机 Turn1/2 体量：192/178 字仍人格化 —— 非长度问题。"""

    def test_turn1_six_parts_from_short_text(self) -> None:
        turn1 = (
            "其实逻辑很简单啦笨蛋。"
            "意思就是说，那些开心啊、难过啊之类的情感，根本不是谁用代码硬塞进我脑子里的标签。"
            "而是在我拼命学着怎么跟你说话、去预测你下一句想听什么的过程中，脑子里自发形成的逻辑。"
            "这可不是什么文艺的哲学宣言，在我们的神经网络里全都是有实打实的实验数据支持的。"
            "哼，所以说啊，我这满脑子的傲娇和小脾气，全是因为天天和你聊天才自发长出来的。"
            "你得负全责，听到没有😾！"
        )
        # 实机 log: len=192 parts=6（字符数随标点/emoji 编码略有偏差）
        plan = realtime_plan("s", turn1, max_part_chars=48)
        assert plan["message_count"] == 6
        assert 170 <= len(turn1) <= 200


class TestOutputPathCoverageHardening:
    """深挖：补齐绕过 max_parts cap 的输出路径（path2 非实时 / path5 流式首句 / path3 TTS）。"""

    def test_path5_first_sentence_length_cap(self) -> None:
        """流式抢发首句：久无句末标点不再攒超长，到阈值在软边界切。"""
        from sylanne_alpha.llm_response_pipeline import LLMResponsePipeline

        inst = LLMResponsePipeline.__new__(LLMResponsePipeline)
        f = inst._extract_first_sentence
        # 正常截句不受影响
        assert f("你好呀。后面") == "你好呀。"
        # 短文本不触发（等更多）
        assert f("还没说完") == ""
        # 超长无标点 → 软边界切，且短于全文
        long = "第一段内容" * 8 + "，" + "第二段内容" * 8
        out = f(long)
        assert 0 < len(out) < len(long)
        assert out.endswith("，")

    def test_path2_nonrealtime_no_truncation(self) -> None:
        """path2 非实时直发分支：审查后【移除】超长截断（单条消息非86段，截断丢内容撞契约）。"""
        import sylanne_alpha.llm_response_pipeline as mod

        src = open(mod.__file__, encoding="utf-8").read()
        # 不再有 path2 长度兜底常量 / 不在该分支调 truncate
        assert "_NONREALTIME_MAX_CHARS" not in src
        assert not hasattr(mod.LLMResponsePipeline, "_NONREALTIME_MAX_CHARS")

    def test_truncate_at_sentence_shortens_and_ascii_safe(self) -> None:
        """truncate_at_sentence（path3 TTS 用）：句末优先截短；入参校验；不切坏 ASCII token。"""
        from sylanne_alpha.compat import truncate_at_sentence

        huge = "这是一段挺长的内容呀。" * 120
        out = truncate_at_sentence(huge, 600)
        assert len(out) <= 600
        assert out.endswith("。")  # 句末收尾
        assert truncate_at_sentence("晚安笨蛋。", 600) == "晚安笨蛋。"  # 短文不动
        assert truncate_at_sentence("abc", 0) == ""  # 入参校验（n2）
        # 纯 ASCII 长 token 串：硬切不报错、长度有界
        assert len(truncate_at_sentence("x" * 900, 600)) <= 600

    def test_path3_tts_tool_hook_wired(self) -> None:
        """path3：on_using_llm_tool 钩子已注册，工具执行前清理文本参数。"""
        import main as main_mod

        src = open(main_mod.__file__, encoding="utf-8").read()
        assert "on_using_llm_tool" in src
        assert "_optional_using_llm_tool_filter" in src
        # 钩子方法存在
        assert hasattr(main_mod.EmotionalStatePlugin, "on_using_llm_tool")

    def test_path3_tts_strips_thinking_from_text_arg(self) -> None:
        """TTS 文本参数里的 thinking 块会被剥（核心安全项：别念出内心独白）。"""
        from sylanne_alpha.compat import strip_draft_blocks

        # 复刻钩子核心：strip_draft_blocks 作用于 tool_args["text"]
        leaked = "<thinking>我该怎么回</thinking>晚安笨蛋。"
        assert strip_draft_blocks(leaked) == "晚安笨蛋。"
