"""SelfCore：自主生命周期与进化档案的宿主。

逐轮认知由 v2core 独占；本类只编排 AUTONOMOUS worker，并保存反射学习、
反思预算和会话进化档案。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from sylanne_alpha.agents.base import SKIP, CognitiveAgent

if TYPE_CHECKING:
    from sylanne_alpha.protocols import PluginHost

logger = logging.getLogger("astrbot_plugin_sylanne")

class SelfCore:
    """自主 worker 编排器与进化状态仓（全局单例）。"""

    def __init__(self, plugin: PluginHost) -> None:
        self._p = plugin
        self._agents: list[CognitiveAgent] = []
        # 自我进化（CP8-P4-C）：per-session 进化档案仓 + 反应式学习器
        self._evo_stores: dict[str, Any] = {}
        self._reflex = None  # 惰性建（ReflexLearner），见 _evo_store
        # CP8-P6：可观测行为信号——本会话上次 bot 回复时刻（自管，避免与
        # last_bot_expression_time 的更新时序耦合）。供 compute_behavior 算续聊/被忽略。
        self._last_bot_reply_time: dict[str, float] = {}
        # CP8-P6：反思预算元数据（per-session）随进化档案一同落盘/恢复，进程重启不清零。
        # 形如 {sk: {"daily": [date_str, count], "last_reflected": ts}}。由 ReflectionEngine 读写。
        self._reflection_meta: dict[str, dict] = {}

    def reflection_meta(self, session_key: str) -> dict:
        """取（或建）某会话的反思预算元数据（供 ReflectionEngine 读写 + 落盘）。"""
        m = self._reflection_meta.get(session_key)
        if m is None:
            m = {}
            self._reflection_meta[session_key] = m
        return m

    def _evo_store(self, session_key: str):
        """取（或建）某会话的进化档案仓。"""
        from sylanne_alpha.agents.learning import EvolutionStore, ReflexLearner
        if self._reflex is None:
            self._reflex = ReflexLearner(self._p)
        store = self._evo_stores.get(session_key)
        if store is None:
            store = EvolutionStore()
            self._evo_stores[session_key] = store
        return store

    def evo_delta(self, session_key: str, agent_name: str, key: str) -> float:
        """供 agent gate 读「学到的门控偏置」（叠加在人格函数基线上）。"""
        store = self._evo_stores.get(session_key)
        return store.get_delta(agent_name, key) if store is not None else 0.0

    # 可学习的门控参数清单（agent_name → param_key），ReflexLearner 据此微调
    _LEARNABLE = (
        ("memory", "intimacy_threshold"),
        ("proactive", "open_threshold"),
    )

    def reflex_learn(
        self, session_key: str, *, self_quality: float | None, behavior: float | None = None
    ) -> None:
        """层次1 反应式学习触发（零 LLM）：根据本轮效果微调可学习门控偏置。

        - self_quality：本轮 self_score 综合质量 [0,1]（弱信号，防 Goodhart 权重低）。
        - behavior：可观测行为信号 {-1 被忽略, 0 未知, +1 续聊}（强信号）。
          CP8-P6：传 None 时由 compute_behavior 自动从"用户续聊间隔"推断（接线强信号
          通道，此前恒传 0.0 导致 reward 全靠弱自评、易单向锁死）。
        当前由 v2core 回复结算阶段在确认可投递后触发。
        """
        import time as _time
        now = _time.time()
        if behavior is None:
            behavior = self.compute_behavior(session_key, now)
        store = self._evo_store(session_key)
        reflex = self._reflex
        if reflex is None:
            self.mark_bot_reply(session_key, now)
            return
        for agent_name, key in self._LEARNABLE:
            reflex.learn(
                store, agent_name, key,
                behavior=behavior, self_quality=self_quality,
            )
        # 顺手记一条聚合决策样本（供层次2 睡眠反思读，FM6：只存聚合不存逐条）
        store.record_decision(self_quality=self_quality, behavior=behavior, now=now)
        # 记录本次 bot 回复时刻，供下一轮 compute_behavior 算续聊间隔
        self.mark_bot_reply(session_key, now)

    def evo_to_dict(self, session_key: str) -> dict[str, Any]:
        store = self._evo_stores.get(session_key)
        data = store.to_dict() if store is not None else {}
        # CP8-P6：把反思预算元数据并入档案落盘（重启不丢配额计数）。用保留键避免与
        # agent_name 撞（agent 名都是小写标识，不含双下划线包裹）。
        meta = self._reflection_meta.get(session_key)
        if meta:
            data = dict(data)
            data["__reflection_meta__"] = dict(meta)
        return data

    def evo_load(self, session_key: str, data: dict[str, Any]) -> None:
        if not data:
            return
        meta = data.get("__reflection_meta__") if isinstance(data, dict) else None
        if isinstance(meta, dict):
            self._reflection_meta[session_key] = dict(meta)
            # 不要把保留键当成 agent 档案喂给 EvolutionStore.load_dict
            data = {k: v for k, v in data.items() if k != "__reflection_meta__"}
        if data:
            self._evo_store(session_key).load_dict(data)

    def compute_behavior(self, session_key: str, now: float) -> float:
        """可观测行为信号 ∈ {-1,0,+1}（CP8-P6 接线，防 Goodhart 的强信号通道）。

        以"用户对上一条 bot 回复的反应速度"为代理（强信号，比自评可信）：
        - 距上次 bot 回复 ≤ engaged 秒（默认 5min）→ 用户续聊，+1（当前策略有效）；
        - > ignored 秒（默认 2h）→ 上次像被晾着，-1（策略可能需收敛）；
        - 之间 / 无历史 → 0（未知，不驱动学习）。
        阈值取保守值，宁可判 0 不误判，避免噪声驱动漂移。
        """
        last = self._last_bot_reply_time.get(session_key, 0.0)
        if last <= 0.0:
            return 0.0
        gap = now - last
        if gap < 0:
            return 0.0
        engaged = self._cfg_float("sylanne_alpha_behavior_engaged_seconds", 300.0)
        ignored = self._cfg_float("sylanne_alpha_behavior_ignored_seconds", 7200.0)
        if gap <= engaged:
            return 1.0
        if gap >= ignored:
            return -1.0
        return 0.0

    def mark_bot_reply(self, session_key: str, now: float) -> None:
        """记录本会话最近一次 bot 回复时刻（供下轮 compute_behavior 算续聊间隔）。"""
        self._last_bot_reply_time[session_key] = now

    def forget_session(self, session_key: str) -> None:
        """释放某会话的进化档案仓（CP8-P6：接入会话删除/驱逐清理，防无界增长）。"""
        self._evo_stores.pop(session_key, None)
        self._last_bot_reply_time.pop(session_key, None)
        self._reflection_meta.pop(session_key, None)



    def register(self, agent: CognitiveAgent) -> None:
        self._agents.append(agent)

    # ------------------------------------------------------------------
    # 三态生命周期（CP8-P3b）：基于空闲时长判会话自驱活跃度
    # ------------------------------------------------------------------
    # AWAKE：刚互动过，每个自驱扫描拍都参与演化。
    # DROWSY：空闲数分钟，降频演化（N 拍才一次）。
    # RETIRED：空闲超阈值，移出自驱迭代，资源归零，等用户消息唤醒。
    AWAKE = "awake"
    DROWSY = "drowsy"
    RETIRED = "retired"

    def autonomy_phase(self, session_key: str, now: float) -> str:
        """按空闲时长（距上次用户消息）判会话三态。阈值是人格函数的占位实现，
        后续可随关系亲密度调（越在意的关系退休越慢）。"""
        try:
            last = float(
                self._p._store.last_user_message_time.get(session_key, 0.0) or 0.0
            )
        except Exception:
            last = 0.0
        idle = now - last
        drowsy_after = self._cfg_float("sylanne_alpha_autonomy_drowsy_after_seconds", 300.0)
        retire_after = self._cfg_float("sylanne_alpha_autonomy_retire_after_seconds", 1800.0)
        if idle < drowsy_after:
            return self.AWAKE
        if idle < retire_after:
            return self.DROWSY
        return self.RETIRED

    def _cfg_float(self, key: str, default: float) -> float:
        try:
            return float((self._p.config or {}).get(key, default))
        except Exception:
            return default

    async def run_autonomous_cycle(
        self, session_key: str, surface: dict[str, Any]
    ) -> None:
        """依次运行已注册的自主 worker；单个 worker 失败不会中断其余 worker。"""
        for agent in self._agents:
            try:
                perceived = agent.perceive(surface)
                mode = agent.gate(perceived)
            except Exception as exc:
                logger.warning("Sylanne agent %s perceive/gate failed: %s", agent.name, exc)
                continue
            if mode == SKIP:
                continue
            try:
                await agent.act(session_key, mode, perceived)
            except Exception as exc:
                logger.warning("Sylanne agent %s act failed: %s", agent.name, exc)
