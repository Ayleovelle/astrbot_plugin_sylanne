"""实机集成冒烟测试：在真实 Python 环境加载 Sylanne 插件 + 仿真大饼，
驱动完整主动发言链路。不需要 IM 平台，但用真插件对象（真计算栈）。

运行：PYTHONPATH=G:/Bugfinders/AstrBot python tests/manual_proactive_integration.py
"""
from __future__ import annotations

import asyncio
import os
import sys

# AstrBot 提供 astrbot.* 包；Sylanne 项目根需排在前面，否则 `import main` 撞 AstrBot 的 main.py
_SYLANNE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "G:/Bugfinders/AstrBot")
sys.path.insert(0, _SYLANNE_ROOT)

PASS, FAIL = [], []


def check(name, cond):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")


# ---- 仿真大饼：真实实现 override 存储 + check_and_chat 触发装饰钩子 ----
class RealishOverrideMgr:
    def __init__(self):
        self.store = {}

    def get_override(self, sid):
        return dict(self.store.get(sid, {}))

    async def set_override(self, sid, patch):
        self.store[sid] = dict(patch)

    async def delete_override(self, sid):
        self.store.pop(sid, None)

    def get_effective(self, sid, base):
        out = dict(base or {})
        out.update(self.store.get(sid, {}))
        return out


class FakeDaPing:
    """仿真大饼插件：check_and_chat 真实触发 OnDecoratingResultEvent 装饰钩子。"""

    def __init__(self, sylanne):
        self.session_override_manager = RealishOverrideMgr()
        self.timezone = None
        self._sylanne = sylanne
        self.sent = []
        self.scheduled = []
        self.chat_sids = []  # 记录 check_and_chat 实际收到的 sid（验证 origin 解析）

    def _get_session_config(self, sid):
        base = {"schedule_settings": {"min_interval_minutes": 30, "max_interval_minutes": 900},
                "segmented_reply_settings": {"enable": True}}
        return self.session_override_manager.get_effective(sid, base)

    async def check_and_chat(self, sid):
        self.chat_sids.append(sid)
        cfg = self._get_session_config(sid)
        text = cfg.get("proactive_prompt", "默认主动消息")
        try:
            from astrbot.core.message.components import Plain  # type: ignore
        except Exception:
            from astrbot.api.message_components import Plain  # type: ignore

        class _Res:
            def __init__(s, chain):
                s.chain = chain

        class _Evt:
            def __init__(s, umo, res):
                s.unified_msg_origin = umo
                s._res = res

            def get_result(s):
                return s._res

        res = _Res([Plain(text=text)])
        await self._sylanne.on_decorating_result(_Evt(sid, res))
        if not res.chain:
            return  # 空链 = 被 Sylanne 接管
        self.sent.append("".join(getattr(c, "text", "") for c in res.chain))

    async def _schedule_next_chat_and_save(self, sid):
        sched = self._get_session_config(sid).get("schedule_settings", {})
        self.scheduled.append((sched.get("min_interval_minutes"), sched.get("max_interval_minutes")))


class FakeMeta:
    def __init__(self, s):
        self.star_cls = s


class FakeContext:
    def __init__(self):
        self._daping = None

    def get_registered_star(self, name):
        return FakeMeta(self._daping) if name == "astrbot_plugin_proactive_chat" else None


async def main():
    print("\n=== 实机集成测试：Sylanne 主动发言全链路 ===\n")
    from main import EmotionalStatePlugin

    print("[1] 解死锁 + 插件实例化")
    ctx = FakeContext()
    config = {
        "sylanne_alpha_proactive_bridge_enabled": True,
        "sylanne_alpha_proactive_segment_takeover": True,
        "sylanne_alpha_proactive_hesitation": True,
        "sylanne_alpha_life_simulation_enabled": False,
        "sylanne_persona_name": "知花",
        "sylanne_webui_enabled": False,
    }
    plugin = EmotionalStatePlugin(context=ctx, config=config)
    check("插件实例化成功", plugin is not None)
    check("_background_tasks 是 list（承接#15）", isinstance(plugin._background_tasks, list))
    check("桥接器已挂载", getattr(plugin, "_proactive_bridge", None) is not None)

    daping = FakeDaPing(plugin)
    ctx._daping = daping
    check("大饼桥接可用 available()", plugin._proactive_bridge.available())

    await plugin.initialize()
    check("initialize() 不崩（解死锁路径）", True)

    sid = "aiocqhttp:GroupMessage:12345"

    print("\n[2] 桥接 dispatch + 分段接管")
    bridge = plugin._proactive_bridge
    motivation = bridge.build_motivation_text(
        "[life_event] 路过花店闻到栀子花", "温柔", reason_code="scar", session_key=sid
    )
    check("素材含人设名", "知花" in motivation)
    res = await bridge.dispatch(sid, motivation)
    check("dispatch 成功", res.get("dispatched") is True)
    check("分段接管生效（大饼未整段发）", len(daping.sent) == 0)
    check("override 用完已清理", sid not in daping.session_override_manager.store)
    await asyncio.sleep(0.2)

    print("\n[3] 拨动倒计时")
    r = await bridge.adjust_countdown(sid)
    check("adjust_countdown 返回字典", isinstance(r, dict) and "adjusted" in r)
    if r.get("adjusted"):
        check("大饼重排被调用（min=max）",
              len(daping.scheduled) > 0 and daping.scheduled[-1][0] == daping.scheduled[-1][1])

    print("\n[4] 犹豫强度计算")
    h_anxious = bridge.compute_hesitation(
        {"immunity": {"boundary_pressure": 0.9}, "needs": {}, "temperature": {"warmth": 0.0}})
    h_warm = bridge.compute_hesitation(
        {"needs": {"need_expression": 0.9}, "temperature": {"warmth": 0.9}})
    check("怕打扰→犹豫高", h_anxious > 0.6)
    check("想表达+熟悉→犹豫低", h_warm == 0.0)

    print("\n[5] P5: session_key→UMO 映射解析（带多发言人后缀）")
    # 模拟收消息时 pipeline 写入的映射：内部带后缀的 session_key → 真实 UMO
    internal_sk = "aiocqhttp:GroupMessage:99999::agent:userA"
    real_umo = "aiocqhttp:GroupMessage:99999"
    plugin._store.session_origins.set(internal_sk, real_umo)
    daping.chat_sids.clear()
    r5 = await bridge.dispatch(internal_sk, "带后缀会话的主动素材")
    check("带后缀会话 dispatch 成功", r5.get("dispatched") is True)
    # 关键：大饼收到的 sid 必须是映射的真实 UMO，而非剥后缀的猜测值
    check("check_and_chat 收到映射的真实 UMO（非回退猜测）",
          daping.chat_sids == [real_umo])
    # 无映射时仍能回退剥后缀（不回归）
    daping.chat_sids.clear()
    await bridge.dispatch("plat:Group:42::speaker:u9", "无映射回退")
    check("无映射 → 回退剥后缀仍工作", daping.chat_sids == ["plat:Group:42"])

    print("\n[6] terminate 清理")
    try:
        await plugin.terminate()
        check("terminate 不崩", True)
    except Exception as e:
        print("   terminate 异常:", e)
        check("terminate 不崩", False)

    print(f"\n=== 结果: {len(PASS)} PASS, {len(FAIL)} FAIL ===")
    if FAIL:
        print("失败项:", FAIL)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
