"""Phase G fixlist P0-7 测试：域状态持久化（REVIEW §P0-7）。

病：integration 全文无 to_dict/load_dict 调用，域只活在 _v2core_runtimes 内存 → 进程重启
UserModel 后验/Narrative 锚点/Emotion 积分/Distill 权重全蒸发，违铁律①（只跨轮不跨进程）。
修：域状态总键 sylanne_v2core_domains:{safe}；首轮 load，turn 末 fire-and-forget save；
memory 域只存 overlay。验收：喂数轮→落盘→清运行态重建→逐字段相等。
"""

from __future__ import annotations

import asyncio
import math
import tempfile

from sylanne_alpha._engine.sylanne_core.compute.host import SylanneAlphaHost
from sylanne_alpha.v2core import integration as ig


class _KVPlugin:
    """带内存 KV 的假 plugin（async get/put），复用真 host 装配 v2core 运行态。"""

    _config = {"sylanne_enable_v2core": True}

    def __init__(self, root: str) -> None:
        self._root = root
        self._h: dict = {}
        self._kv: dict = {}
        self._background_tasks: list = []

    def _session_key(self, event) -> str:  # noqa: ANN001
        return "sess:persist"

    def _host(self, sk):  # noqa: ANN001
        if sk not in self._h:
            self._h[sk] = SylanneAlphaHost(root=self._root, session_key=sk)
        return self._h[sk]

    class _Pipe:
        @staticmethod
        def _text(event):  # noqa: ANN001
            return "我超喜欢你呀❤️😊抱抱你"
    _llm_response_pipeline = _Pipe()

    async def get_kv_data(self, key: str, default=None):  # noqa: ANN001
        return self._kv.get(key, default)

    async def put_kv_data(self, key: str, value) -> None:  # noqa: ANN001
        self._kv[key] = value


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.completion_text = text


def test_domains_survive_restart() -> None:
    root = tempfile.mkdtemp(prefix="p07_")

    async def drive(plugin: _KVPlugin, turns: int) -> dict:
        for _ in range(turns):
            resp = _FakeResponse("嗯嗯我也好喜欢你~")
            await ig.apply_v2core_response(plugin, object(), resp)
        # 抽干 fire-and-forget 落盘任务，确保写入完成
        if plugin._background_tasks:
            await asyncio.gather(*plugin._background_tasks)
        rt = plugin._v2core_runtimes["sess:persist"]
        return {n: d for n, d in rt["domains"].items()}

    # —— 进程 1：喂 3 轮，落盘 ——
    p1 = _KVPlugin(root)
    doms1 = asyncio.run(drive(p1, 3))
    snap_um1 = doms1["usermodel"].to_dict()
    snap_distill1 = doms1["distill"].to_dict()
    snap_narr1 = doms1["narrative"].to_dict()
    # 确认确实学到了东西（非空起步）
    assert doms1["distill"]._samples == 3
    assert len(doms1["usermodel"].synchrony_trajectory()) == 3
    # KV 真写进去了
    assert any("v2core_domains" in k for k in p1._kv)

    # —— 进程 2：同 KV + 同 data_dir，清运行态重建 → 应从 KV 恢复 ——
    p2 = _KVPlugin(root)
    p2._kv = p1._kv                      # 模拟跨进程：同一份持久化 KV
    # 不喂新内容，只触发一次 turn 让它 load（draft 非空避免回落）
    doms2 = asyncio.run(drive(p2, 0)) if False else None

    async def reload_only(plugin: _KVPlugin) -> dict:
        rt = ig._runtime_for(plugin, "sess:persist")
        await ig._load_domains(plugin, "sess:persist", rt["domains"])
        return rt["domains"]

    doms2 = asyncio.run(reload_only(p2))
    # —— 逐字段相等（她"越来越懂你"跨重启还原）——
    assert doms2["distill"].to_dict() == snap_distill1, "Distill 权重未还原"
    assert doms2["usermodel"].to_dict() == snap_um1, "UserModel 后验/轨迹未还原"
    assert doms2["narrative"].to_dict() == snap_narr1, "Narrative 锚点/纪元未还原"
    assert doms2["distill"]._samples == 3


def test_behavior_last_fired_drops_nonfinite_ts() -> None:
    """sourcery review：NaN/±inf 不应期 ts 会废掉门控（NaN→门常开、+inf→永久压制）。

    读写两路都用 math.isfinite 过滤：落盘只留有限值，恢复也滤掉混入的非有限值。
    移除任一侧的 math.isfinite 时，对应断言 FAIL。
    """
    root = tempfile.mkdtemp(prefix="p07nan_")
    p = _KVPlugin(root)
    key = ig._DOMAIN_STATE_KEY_FMT.format(safe=ig._safe_session_key("sess:persist"))

    # 写路径：含 NaN/+inf/-inf 的不应期表落盘 → 只留有限项
    blf = {"laziness": float("nan"), "grudge": float("inf"),
           "jealousy": float("-inf"), "lying": 1234.5}
    asyncio.run(ig._save_domains(p, "sess:persist", {}, blf))
    stored = p._kv[key]["_behavior_last_fired"]
    assert stored == {"lying": 1234.5}, f"写路径未滤掉非有限 ts：{stored}"

    # 读路径：即便 KV 里混进 NaN，恢复出来也不带它（否则门控被废）
    p._kv[key]["_behavior_last_fired"] = {"x": float("nan"), "y": 99.0}
    out = asyncio.run(ig._load_domains(p, "sess:persist", {}))
    assert out == {"y": 99.0}, f"读路径未滤掉非有限 ts：{out}"
    assert all(math.isfinite(v) for v in out.values())


def test_load_tolerates_missing_key() -> None:
    """KV 无域状态键（全新会话）→ 空起步不崩（容缺，铁律④）。"""
    root = tempfile.mkdtemp(prefix="p07b_")
    p = _KVPlugin(root)

    async def go() -> None:
        rt = ig._runtime_for(p, "sess:persist")
        await ig._load_domains(p, "sess:persist", rt["domains"])   # KV 空
        assert rt["domains"]["distill"]._samples == 0              # 空起步

    asyncio.run(go())


def test_save_persists_without_background_tasks_attr() -> None:
    """skeptic P0-7：plugin 无 _background_tasks 时，落盘任务仍被模块级锚定，不被 GC 丢。

    构造一个【没有 _background_tasks 属性】的 plugin，跑一轮，强制 GC，再 await 模块级
    _PENDING_SAVES 抽干——KV 里必须真有域状态（不静默丢档）。
    """
    import gc as _gc

    root = tempfile.mkdtemp(prefix="p07c_")

    class _NoBucketPlugin:
        _config = {"sylanne_enable_v2core": True}
        def __init__(self) -> None:
            self._root = root; self._h = {}; self._kv = {}
        def _session_key(self, event):  # noqa: ANN001
            return "sess:nobucket"
        def _host(self, sk):  # noqa: ANN001
            if sk not in self._h:
                self._h[sk] = SylanneAlphaHost(root=self._root, session_key=sk)
            return self._h[sk]
        class _Pipe:
            @staticmethod
            def _text(event):  # noqa: ANN001
                return "你好呀❤️"
        _llm_response_pipeline = _Pipe()
        async def get_kv_data(self, key, default=None):  # noqa: ANN001
            return self._kv.get(key, default)
        async def put_kv_data(self, key, value) -> None:  # noqa: ANN001
            self._kv[key] = value

    p = _NoBucketPlugin()
    assert not hasattr(p, "_background_tasks")    # 关键：无 bucket

    async def go() -> None:
        await ig.apply_v2core_response(p, object(), _FakeResponse("嗨~"))
        _gc.collect()                              # 强制 GC：无锚定的话任务会被回收
        # 抽干模块级锚定的落盘任务
        if ig._PENDING_SAVES:
            await asyncio.gather(*list(ig._PENDING_SAVES))

    asyncio.run(go())
    assert any("v2core_domains" in k for k in p._kv), "无 _background_tasks 时存档被 GC 丢了"

