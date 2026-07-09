"""Fable 重做版接线总验收 —— 每条新神经都有实弹断言。

覆盖（对应重做修复清单）：
- P-A 会话锁：response 阶段的 tick 在 plugin._session_lock 持有下发生。
- P-B 停机存档：drain_pending_saves + save_all_domains 真把状态送进 KV。
- D6 主动脉：request 阶段心象片段真进 system_prompt（有上限），认知影响言语。
- 双阶段续用：request 暂存的 PERCEPT ctx 在 response 阶段被复用（不重算）。
- 恰好一拍：realtime 拦截开（legacy 观测）→ v2core 不打 response tick；
  拦截关 → v2core 打。全局每轮恰好一次行动知觉。
- P-H 主动触达：憋话+超期 → consult_idle_reach 判 reach；
  ProactiveScheduler.get_speech_decision 升格 action=reach_out（真实消费链）。
"""

from __future__ import annotations

import asyncio
import tempfile

from sylanne_alpha._engine.sylanne_core.compute.host import SylanneAlphaHost
from sylanne_alpha.v2core import integration as ig


class _Resp:
    def __init__(self, t: str) -> None:
        self.completion_text = t


class _Req:
    system_prompt = ""


class _Ev:
    message_str = "我好想你呀❤️今天过得怎么样？"
    unified_msg_origin = "sess:fw"


class _RecLock:
    """可记录持有状态的异步锁。"""

    def __init__(self) -> None:
        self.depth = 0
        self.enter_count = 0

    async def __aenter__(self) -> "_RecLock":
        self.enter_count += 1
        self.depth += 1
        return self

    async def __aexit__(self, *a: object) -> None:
        self.depth -= 1


class _Plugin:
    def __init__(self, root: str, *, realtime_intercept: bool = False) -> None:
        self._config = {
            "sylanne_enable_v2core": True,
            "sylanne_alpha_realtime_chat_enabled": realtime_intercept,
            "sylanne_alpha_realtime_intercept_llm_response": realtime_intercept,
        }
        self._root = root
        self._h: dict = {}
        self._kv: dict = {}
        self.lock = _RecLock()

    def _session_key(self, _e: object) -> str:
        return "sess:fw"

    def _session_lock(self, _sk: str) -> _RecLock:
        return self.lock

    def _host(self, sk: str) -> SylanneAlphaHost:
        if sk not in self._h:
            self._h[sk] = SylanneAlphaHost(root=self._root, session_key=sk)
        return self._h[sk]

    async def get_kv_data(self, key, default=None):  # noqa: ANN001
        return self._kv.get(key, default)

    async def put_kv_data(self, key, value) -> None:  # noqa: ANN001
        self._kv[key] = value


def test_response_tick_under_session_lock() -> None:
    """P-A：response 阶段对宿主的 tick 必须发生在会话锁持有期间（S5 串行义务）。

    注：SylanneAlphaHost 是 slots dataclass，不能在实例上打补丁——改包 BodyPort.tick
    （v2core 对 SDK 的唯一写入口，正是 S5 约束的对象）。
    """
    p = _Plugin(tempfile.mkdtemp(prefix="fw_lock_"))
    rt = ig._runtime_for(p, "sess:fw")
    rt["loaded"] = True
    bp = rt["body_port"]
    held_at_tick: list[int] = []
    orig_tick = bp.tick

    def spy(event, assessment=None):  # noqa: ANN001
        held_at_tick.append(p.lock.depth)
        return orig_tick(event, assessment)

    bp.tick = spy  # type: ignore[method-assign]

    async def go() -> None:
        await ig.apply_v2core_response(p, _Ev(), _Resp("嗯，我也想你。"))

    asyncio.run(go())
    assert p.lock.enter_count >= 1, "response 阶段没拿会话锁"
    assert held_at_tick and all(d == 1 for d in held_at_tick), \
        f"tick 发生在锁外（depth={held_at_tick}）——并发双 tick 撕裂 kernel 的隐患"


def test_exactly_one_response_tick_per_turn() -> None:
    """恰好一拍：拦截关 → v2core 打 response tick（turns+1）；拦截开 → 不打（legacy 打）。"""
    def run(intercept: bool) -> int:
        p = _Plugin(tempfile.mkdtemp(prefix="fw_tick_"), realtime_intercept=intercept)
        host = p._host("sess:fw")
        before = int(host.diagnostics().get("turns") or 0)

        async def go() -> None:
            await ig.apply_v2core_response(p, _Ev(), _Resp("嗯嗯在的"))

        asyncio.run(go())
        return int(host.diagnostics().get("turns") or 0) - before

    assert run(intercept=False) == 1, "拦截关时 v2core 应自打 response tick"
    assert run(intercept=True) == 0, "拦截开时 legacy 会观测——v2core 不得重复打"


def test_mind_fragment_reaches_system_prompt() -> None:
    """D6 主动脉：request 阶段心象片段进 system_prompt 且有硬上限。"""
    p = _Plugin(tempfile.mkdtemp(prefix="fw_frag_"))
    req = _Req()

    async def go() -> None:
        await ig.apply_v2core_request(p, _Ev(), req)

    asyncio.run(go())
    assert "[心象" in req.system_prompt, "心象片段没注入——认知影响不了言语（主动脉断）"
    frag = req.system_prompt[req.system_prompt.index("[心象"):]
    # 上限 = header + STATE 预算(_MAX_CHARS) + PINNED 尾巴(_PRESENCE，Wave-L1/G2 新增
    # 文风纪律行后变长) + 分隔符余量；不是精确到字的快照，只钉"有硬上限"这条不变式。
    assert len(frag) <= 420, "心象片段必须有硬上限（不抢正文预算）"


def test_percept_ctx_reused_across_stages() -> None:
    """双阶段：request 暂存的 ctx 在 response 阶段被复用，PERCEPT 不重算。"""
    p = _Plugin(tempfile.mkdtemp(prefix="fw_reuse_"))

    async def go() -> None:
        await ig.apply_v2core_request(p, _Ev(), _Req())
        rt = p._v2core_runtimes["sess:fw"]
        stashed_ctx = rt["pending"]["ctx"]
        stashed_ctx.scratch["marker"] = "from_request_stage"
        await ig.apply_v2core_response(p, _Ev(), _Resp("在的呀"))
        # 复用证据：decision 阶段跑的是同一个 ctx（marker 仍在 / pending 被取走）
        assert stashed_ctx.scratch.get("render_outcome") is not None, "response 没续用暂存 ctx"
        assert rt["pending"] is None

    asyncio.run(go())


def test_terminate_path_saves_domains() -> None:
    """P-B：drain_pending_saves + save_all_domains 后 KV 里有域状态（停机不丢成长）。"""
    p = _Plugin(tempfile.mkdtemp(prefix="fw_term_"))

    async def go() -> None:
        await ig.apply_v2core_response(p, _Ev(), _Resp("嗯嗯"))
        # 模拟 main.terminate 的 v2core 段：先排干在途，再终扫
        await ig.drain_pending_saves()
        await ig.save_all_domains(p)

    asyncio.run(go())
    keys = [k for k in p._kv if "v2core_domains" in k]
    assert keys, "停机路径没把域状态送进 KV"
    blob = p._kv[keys[0]]
    assert "usermodel" in blob and "emotion" in blob


def test_idle_reach_wins_when_pent_up_and_overdue() -> None:
    """P-H：憋着话 + 按你节律已超期 → consult_idle_reach 判 reach。"""
    p = _Plugin(tempfile.mkdtemp(prefix="fw_reach_"))

    async def go() -> dict:
        rt = ig._runtime_for(p, "sess:fw")
        rt["loaded"] = True
        # 憋话（沉默期积累的未表达积分）+ 节律画像（上次你 1000s 前发言，平时 10s 一条）
        import time as _t
        rt["domains"]["emotion"].load_dict({"unexpressed": 3.0})
        rt["domains"]["usermodel"].load_dict({
            "rhythm_ema": 10.0, "last_user_ts": _t.time() - 1000.0,
        })
        return await ig.consult_idle_reach(p, "sess:fw")

    out = asyncio.run(go())
    assert out["reach"] is True, f"积累+超期应判 reach，得到 {out}"
    assert out["g_reach"] > 1.0


def test_idle_no_pressure_stays_quiet() -> None:
    """无积累无超期 → 空闲轮安静（不话痨、不误触发）。"""
    p = _Plugin(tempfile.mkdtemp(prefix="fw_quiet_"))

    async def go() -> dict:
        return await ig.consult_idle_reach(p, "sess:fw")

    out = asyncio.run(go())
    assert out["reach"] is False


def test_proactive_scheduler_consumes_reach() -> None:
    """真实消费链：get_speech_decision 在 reach 胜出时升格 action=reach_out。"""
    from sylanne_alpha.proactive_scheduler import ProactiveScheduler

    p = _Plugin(tempfile.mkdtemp(prefix="fw_sched_"))
    # 让一个真实 surface 存在（host 创建 + 一拍）
    p._host("sess:fw").on_request({"phase": "request", "text": "x", "now": 1.0})

    async def go() -> dict:
        rt = ig._runtime_for(p, "sess:fw")
        rt["loaded"] = True
        import time as _t
        rt["domains"]["emotion"].load_dict({"unexpressed": 3.0})
        rt["domains"]["usermodel"].load_dict({
            "rhythm_ema": 10.0, "last_user_ts": _t.time() - 1000.0,
        })
        sched = ProactiveScheduler(p)  # type: ignore[arg-type]
        return await sched.get_speech_decision(session_key="sess:fw")

    decision = asyncio.run(go())
    assert decision.get("v2core_reach", {}).get("reach") is True
    if decision.get("allowed", True):
        assert decision["action"] == "reach_out", "reach 胜出没升格主动决策（死信号）"


def test_cron_events_not_processed() -> None:
    """cron 内部总结不进认知：两个钩子都跳过（防污染用户模型/蒸馏学习流）。"""
    p = _Plugin(tempfile.mkdtemp(prefix="fw_cron_"))

    class _CronEv:
        message_str = "今日总结……"
        unified_msg_origin = "cron:daily"

    async def go() -> None:
        req = _Req()
        await ig.apply_v2core_request(p, _CronEv(), req)
        assert "[心象" not in req.system_prompt
        took = await ig.apply_v2core_response(p, _CronEv(), _Resp("总结内容"))
        assert took is False
        assert not getattr(p, "_v2core_runtimes", {}), "cron 轮不应建认知运行态"

    asyncio.run(go())
