"""多智能体认知架构基础设施（CP8-P3a）。

设计总纲（详见作战文档 G:\\claude-data\\plans\\cp8-multiagent-warplan.md §3）：
- 共振场黑板：SDK kernel 是单一真相源，agent 把意图融合成单个 host event 喂进
  kernel.tick，产出 surface 广播全队。强来自结构（单一收敛点 + 人格门控），
  不来自通讯带宽。
- 两层自适应：门控层（perceive→gate，纯算术人格函数，高频零 LLM）+ 执行层
  （act 仅在门控放行时调 LLM/工具）。
- 防死锁：tick 串行收口，agent 间消息 fire-forget 不 await 回执。

本模块定义 worker 的契约（AgentIntent / CognitiveAgent / 档位常量 / 合法 flag 集）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sylanne_alpha.agents.event_bus import EventBus
    from sylanne_alpha.protocols import PluginHost

# ── SDK kernel 真正识别的合法 flag 集（实证 body.py:406-409 / kernel.py 决策层）──
# agent 贡献的 flag 经 SelfCore._compose 按此过滤，非法 flag 静默丢弃避免污染计算。
VALID_FLAGS: frozenset[str] = frozenset({
    "safe", "hurt", "boundary", "repair", "idle",
    "pause", "resume", "reset", "proactive", "tool",
    "task", "group", "fallibility", "interrupt", "interruption",
})

# ── 决策档位：门控 gate() 的返回值 ──
SKIP = "skip"   # 这轮不动（绝大多数 agent 的默认）
RULE = "rule"   # 用廉价规则处理，零 LLM
LLM = "llm"     # 够格升级到 LLM + 工具（低频，受全局预算闸约束）

# ── 编排时点：四时点模型 ──
# PRE：请求发出前，agent act 产意图影响本轮计算输入（flags/confidence/values）。
# POST：host 计算完出新 surface 后（请求侧），agent 消化本轮结果（节奏/记忆/主动）。
# RESPONSE_POST：bot 回复后（响应侧），agent 消化回复结果（社交通知/回复观测）。
# AUTONOMOUS：无用户消息的自驱时点（AutonomyScheduler 驱动），agent 自主演化
#   （作息/情绪漂移/空闲主动开口）。让她"没人说话也活着"。
PRE = "pre"
POST = "post"
RESPONSE_POST = "response_post"
AUTONOMOUS = "autonomous"


@dataclass(slots=True)
class AgentIntent:
    """worker 投给 SelfCore 的一份意图贡献。

    SelfCore._compose 把多份 AgentIntent 融合成单个 host event 的输入：
    - flags → body.apply 事件向量（safe/hurt/boundary/repair...）
    - confidence_hint → 事件向量置信轴
    - affect → values（hot_pool 相变）+ assessment（Void-Scar resonance）双通道
    - group_heat → values["group_heat"]（tick 唯一消费的 values 键）
    - payload → SDK 吃不下的高层意图（哪段回忆/措辞策略），SelfCore 托管进 surface
    - priority → 冲突仲裁权重（SDK 不认，SelfCore 加权融合用）
    """

    source: str
    flags: list[str] = field(default_factory=list)
    confidence_hint: float | None = None
    affect: dict[str, float] = field(default_factory=dict)
    group_heat: float | None = None
    priority: float = 0.5
    payload: dict[str, Any] = field(default_factory=dict)


class CognitiveAgent:
    """认知 worker 基类：感知-决策-行动（perceive / gate / act）。

    纪律（防死锁 + 防成本爆炸）：
    - perceive：只读 surface 快照，不写任何状态（并行安全）。
    - gate：纯算术人格门控，微秒级，零 LLM，返回 SKIP/RULE/LLM 档位。
    - act：按档位行动产出 AgentIntent；RULE 走廉价逻辑，LLM 才调工具；
      可经 emit() 发 fire-forget 消息给别的 agent，绝不 await tick 或回执。
    """

    name: str = "base"
    # agent 在哪些时点参与：PRE（影响计算输入）/ POST（消化计算结果）。
    # 子类覆盖，多数 worker 只在一个时点活跃。
    phases: tuple[str, ...] = (POST,)

    def __init__(self, plugin: PluginHost, bus: EventBus) -> None:
        self._p = plugin
        self._bus = bus

    def perceive(self, surface: dict[str, Any]) -> dict[str, Any]:
        """从 surface 抽取本 agent 关心的信号（只读）。子类覆盖。"""
        return {}

    def gate(self, perceived: dict[str, Any]) -> str:
        """人格门控：返回 SKIP/RULE/LLM。纯算术，阈值是人格函数。子类覆盖。"""
        return SKIP

    async def act(
        self, session_key: str, mode: str, perceived: dict[str, Any], phase: str = POST
    ) -> AgentIntent | None:
        """按档位 mode、时点 phase 行动，产出意图贡献（或 None）。

        PRE 时点：产意图影响本轮计算（返回的 AgentIntent 被融合进 host event）。
        POST 时点：消化本轮 surface 结果、更新自身状态（通常返回 None，副作用即收编的业务）。
        子类覆盖。
        """
        return None

    def emit(self, event: Any) -> None:
        """发 fire-forget 消息给订阅的别的 agent（不 await 回执，防死锁）。"""
        self._bus.publish(event)
