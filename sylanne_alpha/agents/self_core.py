"""SelfCore：共振场 leader / 主席 + 编排器（CP8-P3a）。

职责（作战文档 §3.0-3.1）：
- 状态权威 + 综合者：SDK kernel 是它的大脑（生理/情绪/人格计算）。
- 编排：每轮针对一个 session，依次跑 9 个 worker 的 perceive→gate→act，
  收集 AgentIntent，融合成单个 host event 输入（flags/confidence/values/
  assessment），交给 host.on_request/on_response 驱动 kernel.tick。
- 承载力闭合：SDK event 吃不下的高层意图（payload）由 SelfCore 托管进 surface。

全局单例（非每会话）：reactive 是无状态的一轮编排，会话态在 host/surface 里，
inbox 只是一轮临时收集。避免再引入 session-keyed 容器。

本阶段（P3a）只做 reactive 编排 + 计算注入参数（compose_inputs）。autonomy
自驱循环、全局 LLM 预算闸的完整仲裁留 P3b。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sylanne_alpha.agents.base import LLM, POST, SKIP, VALID_FLAGS, AgentIntent, CognitiveAgent
from sylanne_alpha.agents.event_bus import EventBus

if TYPE_CHECKING:
    from sylanne_alpha.protocols import PluginHost

logger = logging.getLogger("astrbot_plugin_sylanne")


@dataclass(slots=True)
class ComposedInputs:
    """_compose 的产物：喂给 host event 的融合输入 + 托管的高层意图。"""

    flags: list[str]
    confidence: float | None
    values: dict[str, float]
    assessment: dict[str, float]
    carried: dict[str, dict]  # source → payload，SelfCore 托管，拼回 surface


class SelfCore:
    """认知团队主席 + 编排器（全局单例）。"""

    def __init__(self, plugin: PluginHost, *, llm_budget: int = 3) -> None:
        self._p = plugin
        self.bus = EventBus()
        self._agents: list[CognitiveAgent] = []
        # 全局 LLM 预算闸：每轮 LLM 档 agent 数上限，超预算按优先级降级
        self._llm_budget = llm_budget
        # 预算仲裁优先级（用户拍板）：越靠前越优先拿到 LLM 档
        self._llm_priority = [
            "dialogue", "assessor", "emotion", "proactive", "memory", "persona",
        ]

    def register(self, agent: CognitiveAgent) -> None:
        self._agents.append(agent)

    # ------------------------------------------------------------------
    # 编排：一轮 perceive → gate → act → 收集意图
    # ------------------------------------------------------------------
    async def run_cycle(
        self, session_key: str, surface: dict[str, Any], phase: str = POST
    ) -> list[AgentIntent]:
        """针对一个 session 跑某时点(phase)的认知周期，返回意图贡献。

        双时点模型：
        - PRE：请求发出前，agent 产意图影响本轮计算输入（融合进 host event）。
        - POST：host 计算完出新 surface 后，agent 消化结果更新自身状态。
        仅 phase 在 agent.phases 内的 agent 参与本轮。

        perceive 全部先行（只读 surface，并行安全）；gate 决档；预算闸仲裁 LLM 档；
        act 产意图。
        """
        active = [a for a in self._agents if phase in a.phases]
        # 1. perceive + gate（纯算术，零 LLM）
        decisions: list[tuple[CognitiveAgent, str, dict]] = []
        for agent in active:
            perceived = agent.perceive(surface)
            mode = agent.gate(perceived)
            if mode != SKIP:
                decisions.append((agent, mode, perceived))

        # 2. 全局 LLM 预算闸：LLM 档超预算的按优先级降级为 RULE
        decisions = self._apply_llm_budget(decisions)

        # 3. act（RULE 廉价 / LLM 调工具），收集意图
        intents: list[AgentIntent] = []
        for agent, mode, perceived in decisions:
            try:
                intent = await agent.act(session_key, mode, perceived, phase=phase)
            except Exception as exc:
                logger.warning("Sylanne agent %s act failed: %s", agent.name, exc)
                continue
            if intent is not None:
                intents.append(intent)
        return intents

    def _apply_llm_budget(
        self, decisions: list[tuple[CognitiveAgent, str, dict]]
    ) -> list[tuple[CognitiveAgent, str, dict]]:
        """LLM 档 agent 超全局预算时，按优先级保留高优、其余降级 RULE。"""
        llm_ones = [d for d in decisions if d[1] == LLM]
        if len(llm_ones) <= self._llm_budget:
            return decisions
        rank = {name: i for i, name in enumerate(self._llm_priority)}
        llm_ones.sort(key=lambda d: rank.get(d[0].name, 999))
        keep = {id(d[0]) for d in llm_ones[: self._llm_budget]}
        out = []
        for agent, mode, perceived in decisions:
            if mode == LLM and id(agent) not in keep:
                mode = "rule"  # 降级
            out.append((agent, mode, perceived))
        return out

    # ------------------------------------------------------------------
    # 融合：N 份意图 → 单个 host event 的输入参数
    # ------------------------------------------------------------------
    def compose_inputs(self, intents: list[AgentIntent]) -> ComposedInputs:
        """把多份 AgentIntent 融合成喂给 host event 的 flags/confidence/values/
        assessment，并拎出 SDK 吃不下的高层意图（carried）。

        - flags：并集，过滤掉非 VALID_FLAGS 的（防污染计算）。
        - confidence：按 priority 加权平均（无贡献则 None，调用方用既有默认）。
        - affect：按 priority 加权累加，分流进 values（hot_pool）+ assessment
          （Void-Scar resonance）双通道。
        - group_heat：取各贡献最大值，写 values["group_heat"]。
        - carried：source→payload，SelfCore 托管，由调用方拼回 surface。
        """
        flags: set[str] = set()
        conf_weighted = 0.0
        conf_w = 0.0
        affect: dict[str, float] = {}
        group_heat: float | None = None
        carried: dict[str, dict] = {}

        for it in intents:
            flags |= {f for f in it.flags if f in VALID_FLAGS}
            if it.confidence_hint is not None:
                conf_weighted += it.confidence_hint * it.priority
                conf_w += it.priority
            for k, v in it.affect.items():
                affect[k] = affect.get(k, 0.0) + v * it.priority
            if it.group_heat is not None:
                group_heat = max(group_heat or 0.0, it.group_heat)
            if it.payload:
                carried[it.source] = it.payload

        confidence = (conf_weighted / conf_w) if conf_w else None
        values: dict[str, float] = dict(affect)  # hot_pool 通道
        if group_heat is not None:
            values["group_heat"] = group_heat
        assessment: dict[str, float] = dict(affect)  # Void-Scar 通道
        return ComposedInputs(
            flags=sorted(flags),
            confidence=confidence,
            values=values,
            assessment=assessment,
            carried=carried,
        )
