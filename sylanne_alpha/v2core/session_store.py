"""v2core 容器层：会话运行态的单一归属（设计 §3.1）。

本模块是"主链近窗 + 每轮只读打包 + 会话运行态 + 全局注册表"的容器实现。它不持有
任何认知逻辑（领域/能力 agent 的决策不在这里），只负责：
  1. RecentWindow —— 主链近窗的唯一真相源（D1 按 token 预算自适应驱逐）。
  2. CoreContext  —— 每 turn 一次的瘦只读打包（D4 frozen，goals 只读 view）。
  3. SessionLocks —— turn / evolve / persist 三把 asyncio 锁。
  4. SessionRuntime —— 一个会话的全部运行态容器（占位装配，M0 仅定形态）。
  5. SessionRegistry —— 全局单例 + LRU + 持久 session 注册表（P13：KV 无前缀枚举，
     冷会话靠注册表枚举，绝不靠 KV 扫描）。
  6. SessionFactory —— 装配 host/kernel/memory 的工厂协议签名。

铁律对齐：
  - 铁律2 无内部安全闸 —— 本层不做任何 clamp / 阈值闸；token 预算是【容量管理】而非
    情感封顶，floor/ceiling 只防极端 OOM，与情感浓度无关。
  - 铁律3 SDK 红线 —— 本层只持有 BodyPort（三动词门面），绝不下探 kernel。
  - 铁律4 存档无损 —— RecentWindow.from_dict 能吃旧 ConversationBuffer.messages 形态；
    缺字段=空起步，正交不破坏既有。
  - 铁律5 对外集成面冻结 —— 本层是纯内部容器，不暴露任何对外签名。

注（S1 修复）：本模块所有 dataclass 默认值提成模块常量。@dataclass(slots=True) 不保留
字段默认为类属性（slots 描述符顶掉同名类变量），故 from_dict 内绝不可用 cls.token_budget
取默认——那会抛 AttributeError、令每条旧存档恢复崩溃。
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from .contracts import BodyPort, BodySnapshot

# ---------------------------------------------------------------------------
# 默认值常量（S1：slots dataclass 不能用 cls.<field> 取默认，必须走模块常量）
# ---------------------------------------------------------------------------
_DEFAULT_TOKEN_BUDGET = 1600     # 近窗总 token 软预算（自适应主旋钮）
_DEFAULT_FLOOR = 4               # 最少保留条目数（防过度驱逐）
_DEFAULT_CEILING = 48            # 条目数硬上限（防极端爆炸）
_DEFAULT_MAX_SESSIONS = 200      # 注册表活体上限

# ---------------------------------------------------------------------------
# 占位类型别名（M0 仅定形态，下列子系统在后续里程碑落地，先以 Any 标注 + TODO）
# ---------------------------------------------------------------------------
SelfCoreT = Any            # TODO(M1): from .self_core import SelfCore
DomainAgentT = Any         # TODO(M2): 收窄到 contracts.DomainAgent
EvolutionArchiveT = Any    # TODO(M3): 进化档案（reflection_bias/outcome_ema）
ConversationBufferT = Any  # TODO: 旧 ConversationBuffer（迁移期共存）
GroupDomainT = Any         # TODO: from .group_domain import GroupDomain（P8）
GoalViewT = Any            # TODO: from .goals import GoalView（D3/D4）

# ===========================================================================
# RecentWindow —— 主链近窗的唯一真相源（D1：按 token 预算自适应驱逐）
# ===========================================================================

@dataclass(slots=True)
class WindowEntry:
    """近窗里的一条消息。

    role 沿用旧约定（user / bot / group_observed），text 为原文。pinned=True 的条目
    永不被预算驱逐。extra 收纳旧形态附加键（如群聊旁观的 sender_id），保证迁移无损。
    """

    role: str
    text: str
    ts: float = 0.0
    pinned: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"role": self.role, "text": self.text, "ts": self.ts}
        if self.pinned:
            d["pinned"] = True
        if self.extra:
            d.update(self.extra)
        return d


def _estimate_tokens(text: str) -> int:
    """极简 token 估算：len//2（CJK 约两字一 token），下限 1。

    D1 只要"对话密少留、稀多留"的相对排序成立即可，不追求精确分词。
    """
    return max(1, len(text or "") // 2)


@dataclass(slots=True)
class RecentWindow:
    """主链近窗：贯穿三拍的对话上下文唯一真相源（D1 自适应容量）。

    驱逐策略（容量管理，非情感闸）：ceiling 条目数硬上限；token_budget 软预算超则从最旧
    非 pinned 起丢、但不压到 floor 以下；pinned 免驱逐但仍计 token/ceiling。
    长文本更快吃预算 → 自然"短消息多留、长消息少留"。
    """

    session_key: str
    token_budget: int = _DEFAULT_TOKEN_BUDGET
    floor: int = _DEFAULT_FLOOR
    ceiling: int = _DEFAULT_CEILING
    entries: list[WindowEntry] = field(default_factory=list)

    def append(self, role: str, text: str, ts: float | None = None,
               *, pinned: bool = False, **extra: Any) -> None:
        """追加一条消息并立即按预算驱逐。ts 由调用方注入（容器不读时钟）。"""
        self.entries.append(
            WindowEntry(role=role, text=text or "", ts=ts or 0.0,
                        pinned=pinned, extra=dict(extra)),
        )
        self._evict()

    def pin(self, role: str, text: str, ts: float | None = None, **extra: Any) -> None:
        """追加一条 pinned 锚定消息（永不被预算驱逐）。"""
        self.append(role, text, ts, pinned=True, **extra)

    def clear(self) -> None:
        self.entries.clear()

    def as_context_lines(self, limit: int | None = None) -> list[str]:
        """投影为 prompt 注入用的 "role: text" 行；limit 取最近 N 行（None=全部）。纯只读。"""
        rows = self.entries if limit is None else self.entries[-limit:]
        return [f"{e.role}: {e.text}" for e in rows]

    @property
    def total_tokens(self) -> int:
        return sum(_estimate_tokens(e.text) for e in self.entries)

    def __len__(self) -> int:
        return len(self.entries)

    def _evict(self) -> None:
        while len(self.entries) > self.ceiling:
            if not self._drop_oldest_unpinned():
                break
        while self.total_tokens > self.token_budget and len(self.entries) > self.floor:
            if not self._drop_oldest_unpinned():
                break

    def _drop_oldest_unpinned(self) -> bool:
        for i, e in enumerate(self.entries):
            if not e.pinned:
                del self.entries[i]
                return True
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_key": self.session_key,
            "token_budget": self.token_budget,
            "floor": self.floor,
            "ceiling": self.ceiling,
            "entries": [e.to_dict() for e in self.entries],
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any], *,
                  token_budget: int | None = None,
                  floor: int | None = None,
                  ceiling: int | None = None) -> RecentWindow:
        """从持久化恢复，兼容【新 entries 形态】与【旧 ConversationBuffer.messages 形态】。

        S1 修复：默认值取模块常量 _DEFAULT_*，绝不用 cls.<field>（slots dataclass 上抛
        AttributeError）。显式传参 > 存档值 > 模块常量。
        """
        session_key = str(d.get("session_key", ""))
        win = cls(
            session_key=session_key,
            token_budget=token_budget if token_budget is not None
            else int(d.get("token_budget", _DEFAULT_TOKEN_BUDGET)),
            floor=floor if floor is not None else int(d.get("floor", _DEFAULT_FLOOR)),
            ceiling=ceiling if ceiling is not None else int(d.get("ceiling", _DEFAULT_CEILING)),
        )
        raw_entries = d.get("entries")
        raw_messages = d.get("messages")  # 旧 ConversationBuffer 形态
        source = raw_entries if raw_entries is not None else (raw_messages or [])
        known = {"role", "text", "ts", "pinned"}
        for m in source:
            if not isinstance(m, Mapping):
                continue
            extra = {k: v for k, v in m.items() if k not in known}
            win.entries.append(
                WindowEntry(
                    role=str(m.get("role", "")),
                    text=str(m.get("text", "")),
                    ts=float(m.get("ts", 0.0) or 0.0),
                    pinned=bool(m.get("pinned", False)),
                    extra=extra,
                ),
            )
        win._evict()  # 旧档可能超新预算 → 恢复后驱逐到合规（近窗是易失工作集，长期记忆在三层KV）
        return win

# ===========================================================================
# CoreContext —— 每 turn 一次的瘦只读打包（D4：frozen，goals 只读 view）
# ===========================================================================

@dataclass(frozen=True, slots=True)
class CoreContext:
    """一轮主链开场时打包一次的【只读】上下文聚合。

    与 contracts.BeatContext 分工：CoreContext 是"这一轮能看到的世界"的冻结快照，turn
    内不变；BeatContext 是"这一轮在写什么"的可变工作区。frozen + 只读视图 → 能力 agent
    无法经 ctx 反向穿透改领域状态。

    S6 备注：ports 由编排器在 build 时注入（body/storage/llm 工具表），不归 SessionRuntime
    持有；goals 来自 IntentionDomain 的只读投影。M1 写 SelfCore 时据此装配。
    """

    session_key: str
    body: BodySnapshot
    window_lines: tuple[str, ...]
    domains: Mapping[str, DomainAgentT]
    groups: GroupDomainT | None
    ports: Mapping[str, Any]
    goals: tuple[GoalViewT, ...] = ()

    @classmethod
    def build(cls, *, session_key: str, body: BodySnapshot,
              window: RecentWindow, domains: Mapping[str, DomainAgentT],
              ports: Mapping[str, Any], groups: GroupDomainT | None = None,
              goals: Sequence[GoalViewT] = (),
              window_limit: int | None = None) -> CoreContext:
        return cls(
            session_key=session_key,
            body=body,
            window_lines=tuple(window.as_context_lines(window_limit)),
            domains=MappingProxyType(dict(domains)),
            groups=groups,
            ports=MappingProxyType(dict(ports)),
            goals=tuple(goals),
        )


# ===========================================================================
# SessionLocks —— turn / evolve / persist 三把 asyncio 锁
# ===========================================================================

@dataclass(slots=True)
class SessionLocks:
    """一个会话的三把互斥锁：turn（单轮主链串行）/ evolve（EVOLVE 唯一写相位写锁）/
    persist（落盘临界区）。

    S5 关键契约：BodyPort.tick 只能在 turn 锁持有下调用——v2 路径绕过 engine 自带
    per-session 锁，turn 锁是同会话唯一串行点；否则同会话并发双 tick 撕裂 kernel 状态。
    """

    turn: asyncio.Lock = field(default_factory=asyncio.Lock)
    evolve: asyncio.Lock = field(default_factory=asyncio.Lock)
    persist: asyncio.Lock = field(default_factory=asyncio.Lock)


# ===========================================================================
# SessionRuntime —— 一个会话的全部运行态容器（M0 仅定形态）
# ===========================================================================

@dataclass(slots=True)
class SessionRuntime:
    """单会话运行态归属容器。registry 按 key 持有它。M0 仅定形态，占位字段待后续里程碑收窄。"""

    session_key: str
    body_port: BodyPort
    window: RecentWindow
    locks: SessionLocks = field(default_factory=SessionLocks)
    # —— 占位形态 ——
    core: SelfCoreT | None = None                                  # TODO(M1)
    domains: dict[str, DomainAgentT] = field(default_factory=dict)  # TODO(M2)
    evo: EvolutionArchiveT | None = None                           # TODO(M3)
    buffers: ConversationBufferT | None = None
    groups: GroupDomainT | None = None
    ports: dict[str, Any] = field(default_factory=dict)            # S6: ports 归属在此
    # —— 元数据 ——
    migration_marker: str | None = None
    last_access: float = 0.0
    dirty: bool = False

    def touch(self, now: float) -> None:
        self.last_access = now

# ===========================================================================
# SessionFactory —— 装配 host/kernel/memory 的工厂协议
# ===========================================================================

@runtime_checkable
class SessionFactory(Protocol):
    """会话运行态装配工厂。registry 只认本协议，不关心底层怎么接 AstrBot/SDK。

    - build：为 session_key 装配完整 SessionRuntime（经 canonical SylanneEngine.shared()
      造 BodyPort 持 host、恢复进化档案 sylanne_evolution_{safe} 与近窗）。
      # TODO(D0): vendored 升级到 canonical（shared()）是前置依赖，M0 不实装升级。
    - persist：把 runtime 的 evo + window 落盘（LRU 驱逐前调，保证无损，铁律4）。
    - on_register：会话首见时登记到持久 session 注册表（P13，迁移器据此枚举，绝不扫 KV）。
      S2 关键：本钩子必须接到 migration.SessionRegistryStore.register，构造时注入同一实例。
    """

    async def build(self, session_key: str) -> SessionRuntime: ...
    async def persist(self, runtime: SessionRuntime) -> None: ...
    async def on_register(self, session_key: str) -> None: ...


# ===========================================================================
# SessionRegistry —— 全局单例 + LRU + 持久 session 注册表
# ===========================================================================

class SessionRegistry:
    """进程级会话运行态注册表（全局单例）。

    get：懒建 + LRU 触达，活体超 max_sessions 时驱逐最久未访问者（驱逐前落盘，铁律4）。
    known_sessions：持久注册表全集（P13 枚举唯一来源，迁移器据此遍历）。
    S2 关键：on_register 钩子必须接到持久 SessionRegistryStore；_known 仅内存镜像。
    """

    _instance: SessionRegistry | None = None

    def __init__(self, factory: SessionFactory, *, max_sessions: int = _DEFAULT_MAX_SESSIONS) -> None:
        self._factory: SessionFactory = factory
        self.max_sessions: int = max_sessions
        self._live: OrderedDict[str, SessionRuntime] = OrderedDict()
        self._known: set[str] = set()

    @classmethod
    def configure(cls, factory: SessionFactory, *,
                  max_sessions: int = _DEFAULT_MAX_SESSIONS) -> SessionRegistry:
        cls._instance = cls(factory, max_sessions=max_sessions)
        return cls._instance

    @classmethod
    def instance(cls) -> SessionRegistry:
        if cls._instance is None:
            raise RuntimeError("SessionRegistry 未 configure：请在插件初始化时先 configure(factory)")
        return cls._instance

    async def get(self, session_key: str, *, now: float = 0.0) -> SessionRuntime:
        """取（或懒建）会话运行态，维护 LRU 与持久注册表。now 由调用方注入（确定性影子）。"""
        rt = self._live.get(session_key)
        if rt is not None:
            self._live.move_to_end(session_key)
            rt.touch(now)
            return rt
        rt = await self._factory.build(session_key)
        rt.touch(now)
        self._live[session_key] = rt
        self._live.move_to_end(session_key)
        if session_key not in self._known:
            self._known.add(session_key)
            await self._factory.on_register(session_key)
        await self._evict_if_needed()
        return rt

    def peek(self, session_key: str) -> SessionRuntime | None:
        return self._live.get(session_key)

    async def release(self, session_key: str) -> None:
        rt = self._live.pop(session_key, None)
        if rt is not None:
            await self._persist(rt)

    def known_sessions(self) -> frozenset[str]:
        return frozenset(self._known)

    @property
    def live_count(self) -> int:
        return len(self._live)

    async def _evict_if_needed(self) -> None:
        while len(self._live) > self.max_sessions:
            _old_key, old_rt = self._live.popitem(last=False)
            await self._persist(old_rt)  # 仅移出活体，不删 _known（冷会话仍可枚举，P13）

    async def _persist(self, rt: SessionRuntime) -> None:
        async with rt.locks.persist:
            await self._factory.persist(rt)
            rt.dirty = False


__all__ = [
    "WindowEntry",
    "RecentWindow",
    "CoreContext",
    "SessionLocks",
    "SessionRuntime",
    "SessionFactory",
    "SessionRegistry",
]



