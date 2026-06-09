"""深睡巩固引擎（CP8-P4-D 层次3，真·零 LLM）。

会话进入 RETIRED（深睡）前跑一次，把"白天的经验"沉淀掉，对应人类深睡记忆固化：
- 记忆衰减推进（tick_decay，纯数值运算，无 LLM）。
- 进化档案落盘（反应式学习累积的门控偏置持久化，跨重启不丢）。

⚠️ 语义巩固（判断哪些记忆值得长期保留、L1→L2 下沉）由现有 _consolidation_loop
在每天 6:00/18:00 用 LLM 负责，此处不重复触发——深睡只做零 LLM 的纯计算沉淀，
避免重复烧 token（严控 token 红线）。

全程零 LLM、纯计算。由 AutonomyScheduler 在 RETIRED 分支调用，每会话只跑一次
（last_consolidated_at 守卫，避免重复）。
"""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger("astrbot_plugin_sylanne")


class ConsolidationEngine:
    """深睡巩固：记忆固化 + 进化档案落盘。零 LLM。"""

    def __init__(self, plugin: Any) -> None:
        self._p = plugin
        # 每会话上次巩固时间（守卫，避免 RETIRED 期反复巩固）
        self._last_consolidated: dict[str, float] = {}
        # 同一会话两次巩固的最小间隔（秒）
        self._min_interval = 1800.0
        # 已从 KV 恢复进化档案的会话（一次性守卫，避免重复 IO + 覆盖运行时学习）
        self._restored: set[str] = set()

    async def ensure_restored(self, session_key: str) -> None:
        """会话首次活跃时从 KV 恢复一次进化档案（跨重启累积学习）。

        host() 为同步方法、无法 await，故恢复挪到异步入口（reactive 首次 observe）。
        一次性守卫：只在该会话首次调用时恢复，之后由运行时反应式学习接管，
        避免后续覆盖已在内存里自校准的门控偏置。
        """
        if session_key in self._restored:
            return
        self._restored.add(session_key)
        await self.restore_evolution(session_key)

    def needs_consolidation(self, session_key: str, now: float) -> bool:
        last = self._last_consolidated.get(session_key, 0.0)
        return (now - last) >= self._min_interval

    async def consolidate(self, session_key: str, now: float) -> None:
        """对一个会话跑一次深睡巩固（真·零 LLM）。

        内部 = 同步巩固（取快照）+ 异步落盘。供 terminate 等无锁上下文直接 await。
        持锁的自驱路径应改用 consolidate_sync + _write_evolution 锁舞（见 scheduler）。
        """
        snapshot = self.consolidate_sync(session_key, now)
        try:
            await self._write_evolution(session_key, snapshot)
        except Exception as exc:
            logger.debug("Sylanne consolidate evolution [%s]: %s", session_key, exc)

    def consolidate_sync(self, session_key: str, now: float) -> dict:
        """深睡巩固的同步部分（零 LLM、零 IO）：记忆衰减 + 反思回归，返回待落盘快照。

        CP8-P6：与 KV 落盘拆开，使自驱路径可在 session_lock 内只跑这段同步计算，
        把 put_kv_data 移到锁外（避免 IO 长占会话锁、阻塞唤醒）。
        """
        self._last_consolidated[session_key] = now
        p = self._p
        # 1. 记忆衰减推进（纯数值运算）。语义巩固（L1→L2，需 LLM）交给现有
        #    _consolidation_loop 在 6:00/18:00 负责，此处不触发以免重复烧 token。
        try:
            ms = p._memory_system_for_session(session_key)
            if ms is not None:
                ms.tick_decay()
        except Exception as exc:
            logger.debug("Sylanne consolidate memory [%s]: %s", session_key, exc)
        # 1.5 反思偏置缓慢回归（CP8-P6）：深睡时朝 0 衰减一步，无新反思则自动复位，
        #     防 reflection_bias 单向锁死（反射 delta 已有自回归，此处补反思路）。
        try:
            sc = getattr(p, "_self_core", None)
            store = sc._evo_stores.get(session_key) if sc is not None else None
            if store is not None and hasattr(store, "decay_reflection_all"):
                store.decay_reflection_all()
        except Exception as exc:
            logger.debug("Sylanne consolidate reflection decay [%s]: %s", session_key, exc)
        # 2. 取进化档案快照（落盘交给锁外的 _write_evolution）
        try:
            sc = getattr(p, "_self_core", None)
            return sc.evo_to_dict(session_key) if sc is not None else {}
        except Exception:
            return {}

    async def _persist_evolution(self, session_key: str) -> None:
        """把该会话的进化档案存进 KV（深睡低频写，省 IO）。"""
        p = self._p
        sc = getattr(p, "_self_core", None)
        if sc is None or not getattr(p, "_has_kv_api", lambda: False)():
            return
        data = sc.evo_to_dict(session_key)
        await self._write_evolution(session_key, data)

    async def _write_evolution(self, session_key: str, data: dict) -> None:
        """把给定进化档案快照写入 KV（供驱逐时先取快照再落盘，避免与 forget 竞争）。"""
        p = self._p
        if not data or not getattr(p, "_has_kv_api", lambda: False)():
            return
        safe = p._safe_session_key(session_key) if hasattr(p, "_safe_session_key") else session_key
        await p.put_kv_data(f"sylanne_evolution_{safe}", data)

    async def restore_evolution(self, session_key: str) -> None:
        """会话首次建立时从 KV 恢复进化档案（跨重启累积学习）。"""
        p = self._p
        sc = getattr(p, "_self_core", None)
        if sc is None or not getattr(p, "_has_kv_api", lambda: False)():
            return
        try:
            safe = p._safe_session_key(session_key) if hasattr(p, "_safe_session_key") else session_key
            data = await p.get_kv_data(f"sylanne_evolution_{safe}", None)
            if data and isinstance(data, dict):
                sc.evo_load(session_key, data)
        except Exception as exc:
            logger.debug("Sylanne restore evolution [%s]: %s", session_key, exc)

    def forget_session(self, session_key: str) -> None:
        self._last_consolidated.pop(session_key, None)
        self._restored.discard(session_key)
