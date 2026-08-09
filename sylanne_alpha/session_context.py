"""会话管理模块。

提供 SessionContext 类，封装 Sylanne 插件的会话生命周期管理：
- session key 派生（从事件对象提取唯一会话标识）
- 每会话锁（防止同一会话并发处理）
- host 实例管理（LRU 缓存 + 懒加载 + 编码器共享）
- 记忆系统注水（从持久化 traces 恢复记忆状态）
- 离线消息缓冲与重连摘要
- 时区感知与作息推断

所有方法通过 self._plugin 委托访问插件实例的属性和方法。
"""

from __future__ import annotations

import asyncio
import datetime
import hashlib
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

try:
    from astrbot.api import logger  # type: ignore
except ImportError:
    import logging as _logging

    logger = _logging.getLogger("astrbot_plugin_sylanne")  # type: ignore

    def get_astrbot_data_path() -> Path:  # type: ignore
        return Path.home()


from sylanne_alpha.infra import resolve_data_root
from sylanne_alpha.host import SylanneAlphaHost
from sylanne_alpha.memory_system import ConversationBuffer, MemorySystem
from sylanne_alpha.observation_history import (
    DEFAULT_MAX_BYTES,
    ObservationHistoryStore,
)
from sylanne_alpha.scope_repository import ScopedPersistenceGateway
from sylanne_alpha.scope_contracts import VerifiedSubjectInput
from sylanne_alpha.scope_runtime import FirstImpression, RelationRuntime, get_relationship_stage

if TYPE_CHECKING:
    from sylanne_alpha.protocols import PluginHost


# 时区感知：固定中国时区 UTC+8——time.localtime()/datetime.fromtimestamp() 不带 tz
# 会读宿主系统时区，境外/UTC 服务器上会把凌晨的"早安"仪式误判成"深夜"（8 小时偏移）。
# 与 v2core/capabilities/ignition.py 的 _CHINA_TZ 同一常量定义，仪式判断口径对齐。
_CHINA_TZ = datetime.timezone(datetime.timedelta(hours=8))


# ---------------------------------------------------------------------------
# T2-06④：早安/晚安兜底关键词识别
#
# 设计原打算读 sylanne_core 后台 assessor（_engine/sylanne_core/assessor.py）的
# greeting/farewell 分类 flag，但当前运行时没有启用这条 SDK assessor 分类路径；实际驱动
# valence/arousal 的是完全独立的 sylanne_alpha/assessor_async.py（自有 v/a/i/w
# 极简 prompt，不含 flags/greeting/farewell）。也就是说 sylanne_core.assessor 的
# flags 分类在插件当前运行时路径下不可达——因此这里按卡片指示退化为关键词兜底
# （小集合、模块级、可扩展），并在实现报告中记录这一偏差。
# ---------------------------------------------------------------------------

_MORNING_GREETING_KW = ("早安", "早上好")
_NIGHT_FAREWELL_KW = ("晚安",)


def _detect_greeting_ritual_pattern(text: str) -> str | None:
    """从消息文本粗判是否命中早安问候/晚安告别模式。"""
    if not text:
        return None
    if any(kw in text for kw in _MORNING_GREETING_KW):
        return "morning_greeting"
    if any(kw in text for kw in _NIGHT_FAREWELL_KW):
        return "night_farewell"
    return None


_DEVICE_CATEGORIES = frozenset({"mobile", "desktop", "other"})


@dataclass(slots=True)
class ScopedDeviceContext:
    """Frozen session-owned device signal with no raw User-Agent persistence."""

    gateway: ScopedPersistenceGateway
    _generation: int = 0
    _digest: str | None = None
    _category: str | None = None

    def __post_init__(self) -> None:
        if type(self.gateway) is not ScopedPersistenceGateway:
            raise ValueError("gateway must be a ScopedPersistenceGateway")
        snapshot = self.gateway.load("device-context")
        if snapshot is None:
            return
        self._generation = snapshot.generation
        payload = snapshot.payload
        if type(payload) is not dict:
            return
        digest = payload.get("digest")
        category = payload.get("category")
        if (
            type(digest) is str
            and len(digest) == 40
            and all(char in "0123456789abcdef" for char in digest)
            and type(category) is str
            and category in _DEVICE_CATEGORIES
        ):
            self._digest = digest
            self._category = category

    @staticmethod
    def _category_for(user_agent: str) -> str:
        lowered = user_agent.lower()
        if any(marker in lowered for marker in ("mobile", "android", "iphone", "ipad")):
            return "mobile"
        if any(marker in lowered for marker in ("windows", "macintosh", "x11", "linux")):
            return "desktop"
        return "other"

    def _digest_for(self, user_agent: str) -> str:
        key = hashlib.sha256(self.gateway.scope.storage_token.encode("utf-8")).digest()
        return hashlib.blake2b(
            user_agent.encode("utf-8"),
            key=key,
            digest_size=20,
        ).hexdigest()

    def last_device_category(self) -> str | None:
        return self._category

    def detect_change(self, user_agent: str) -> str | None:
        """Persist the current opaque signal and return a coarse transition hint."""

        if type(user_agent) is not str:
            return None
        digest = self._digest_for(user_agent)
        category = self._category_for(user_agent)
        previous_digest = self._digest
        previous_category = self._category
        if previous_digest == digest:
            return None
        next_generation = self.gateway.save(
            "device-context",
            expected_generation=self._generation,
            payload={"digest": digest, "category": category},
        )
        self._generation = next_generation
        self._digest = digest
        self._category = category
        if previous_digest is None or previous_category == category:
            return None
        if category == "mobile" and previous_category != "mobile":
            return "换到手机了？我简短些。"
        if category == "desktop" and previous_category == "mobile":
            return "回到电脑了，可以聊详细点。"
        return None


# ---------------------------------------------------------------------------
# OfflineBuffer -- 离线消息队列（Item 107）
# ---------------------------------------------------------------------------


class OfflineBuffer:
    """离线消息缓冲区。

    当用户长时间不在线时，缓存生活模拟产生的想法/事件。
    重连时生成一句摘要（取最近 N 条拼接），让用户感知 Sylanne 的"离线生活"。

    设计要点：
    - 每个 session 独立缓冲区
    - 容量上限 50 条，超出时丢弃最早的
    - 重连摘要取最近 3 条拼接，保持简洁
    """

    _MAX_ITEMS = 50
    _SUMMARY_COUNT = 3

    def __init__(self) -> None:
        self.buffer: list[str] = []
        self.last_push_ts: float = 0.0

    def push(self, thought: str) -> None:
        """缓存一条离线想法。

        Args:
            thought: 生活模拟产生的想法文本。
        """
        text = (thought or "").strip()
        if not text:
            return
        self.buffer.append(text)
        self.last_push_ts = time.time()
        # 超出容量时丢弃最早的
        if len(self.buffer) > self._MAX_ITEMS:
            self.buffer = self.buffer[-self._MAX_ITEMS :]

    def drain_summary(self) -> str:
        """取出缓冲区内容并生成重连摘要。

        取最近 3 条拼接为一句话，清空缓冲区。
        如果缓冲区为空，返回空字符串。

        Returns:
            重连摘要文本，或空字符串。
        """
        if not self.buffer:
            return ""
        # 取最近 N 条
        recent = self.buffer[-self._SUMMARY_COUNT :]
        self.buffer.clear()
        self.last_push_ts = 0.0
        # 拼接为摘要
        if len(recent) == 1:
            return f"（你不在的时候，我{recent[0]}）"
        return "（你不在的时候，我" + "；".join(recent) + "）"

    @property
    def pending_count(self) -> int:
        """当前缓冲区中的待处理消息数。"""
        return len(self.buffer)

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典。"""
        return {
            "buffer": self.buffer[:],
            "last_push_ts": self.last_push_ts,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OfflineBuffer":
        """从字典恢复。"""
        ob = cls()
        ob.buffer = list(data.get("buffer", []))
        ob.last_push_ts = float(data.get("last_push_ts", 0.0))
        return ob


def validate_session_isolation(hosts: dict) -> list[str]:
    """诊断会话隔离：检查不同 session_key 的 host 是否共享了同一个 memory_system 或 kernel 实例。

    通过 id() 比较对象身份，发现违规共享时返回描述列表。
    空列表表示所有会话完全隔离，通过审计。

    可被 /api/diagnostic_report 调用。

    Args:
        hosts: session_key → host 实例的字典。

    Returns:
        违规描述列表（空列表 = 通过）。
    """
    violations: list[str] = []
    if not hosts or not isinstance(hosts, dict):
        return violations

    # 收集所有 host 的 kernel 和 memory_system 的 id
    kernel_ids: dict[int, list[str]] = {}  # id(kernel) → [session_keys]
    memory_ids: dict[int, list[str]] = {}  # id(memory_system) → [session_keys]

    for session_key, host in hosts.items():
        # 检查 kernel 共享
        kernel = getattr(host, "kernel", None)
        if kernel is not None:
            kid = id(kernel)
            kernel_ids.setdefault(kid, []).append(session_key)

        # 检查 memory_system 共享（多种获取路径）
        mem_sys = None
        # 路径1: host.kernel.body.memory.get("_memory_system") 是序列化数据，不算共享
        # 路径2: 通过 plugin._memory_systems 字典（但这里只检查 host 级别）
        # 路径3: host 上直接挂载的 memory_system
        mem_sys = getattr(host, "memory_system", None)
        if mem_sys is None and kernel is not None:
            # 尝试从 kernel 的 body 获取
            body = getattr(kernel, "body", None)
            mem_sys = getattr(body, "_memory_system", None)
        if mem_sys is not None:
            mid = id(mem_sys)
            memory_ids.setdefault(mid, []).append(session_key)

    # 检测共享违规
    for kid, sessions in kernel_ids.items():
        if len(sessions) > 1:
            violations.append(f"kernel 实例共享违规: id={kid:#x}, 涉及会话: {sessions}")

    for mid, sessions in memory_ids.items():
        if len(sessions) > 1:
            violations.append(f"memory_system 实例共享违规: id={mid:#x}, 涉及会话: {sessions}")

    return violations


class SessionContext:
    """封装 Sylanne 插件的会话管理逻辑。

    作为插件实例的委托层，将会话相关的复杂逻辑（key 派生、锁管理、
    host 生命周期、记忆系统初始化）从主插件类中解耦出来。
    """

    def __init__(self, plugin: PluginHost) -> None:
        """初始化会话上下文。

        Args:
            plugin: Sylanne 插件实例，通过 self._plugin 访问其内部状态。
            services: 只读服务容器（可选，为 None 时从 plugin 构建）。
            session_state: 集中式可变状态容器（可选，为 None 时回退到 self._plugin 属性）。
        """
        self._p = plugin
        cfg = self._p.config if hasattr(self._p, "_config") else getattr(self._p, "config", {}) or {}
        registry = getattr(self._p, "_scope_runtime_registry", None)
        repository = getattr(registry, "repository", None)
        self._observation_history_store: ObservationHistoryStore | None = None
        self._observation_history_repository = repository
        if registry is None:
            # Explicit registry-free compatibility for old test hosts and
            # legacy deployments.  Scoped production never enters this branch.
            self._observation_history_store = ObservationHistoryStore(
                Path(resolve_data_root(cfg)) / "observation-history",
                self._observation_history_limit_bytes,
            )
        elif repository is not None:
            self._observation_history_store = ObservationHistoryStore.from_scope_repository(
                repository,
                self._observation_history_limit_bytes,
            )
        self._observation_sink = (
            None
            if self._observation_history_store is None
            else self._observation_history_store.append_snapshot
        )
        try:
            hosts = getattr(getattr(self._p, "_store", None), "hosts", None)
        except Exception:
            hosts = None
        snapshot_items = getattr(hosts, "snapshot_items", None)
        if callable(snapshot_items):
            for _, host in snapshot_items():
                self._bind_observation_sink(host)

    @property
    def observation_history_store(self) -> ObservationHistoryStore:
        """Return the legacy or repository-owned observation history store."""

        registry = getattr(self._p, "_scope_runtime_registry", None)
        repository = getattr(registry, "repository", None)
        if repository is not None:
            if (
                self._observation_history_store is None
                or not self._observation_history_store.scoped
                or self._observation_history_repository is not repository
            ):
                self._observation_history_store = ObservationHistoryStore.from_scope_repository(
                    repository,
                    self._observation_history_limit_bytes,
                )
                self._observation_history_repository = repository
            return self._observation_history_store
        if self._observation_history_store is None:
            raise RuntimeError("scoped observation history repository is unavailable")
        return self._observation_history_store

    def _observation_history_limit_bytes(self) -> int:
        """动态读取历史存储预算；负值按 128 MiB 默认值处理。"""
        cfg = self._p.config if hasattr(self._p, "_config") else getattr(self._p, "config", {}) or {}
        getter = getattr(cfg, "get", None)
        raw_value = getter("sylanne_webui_history_storage_limit_mb", 128) if callable(getter) else 128
        try:
            megabytes = int(raw_value)
        except (TypeError, ValueError, OverflowError):
            return DEFAULT_MAX_BYTES
        if megabytes < 0:
            return DEFAULT_MAX_BYTES
        return megabytes * 1024 * 1024

    def _bind_observation_sink(self, host: Any) -> None:
        """Bind a legacy or exact-scope observation sink to one host runtime."""
        setter = getattr(getattr(host, "runtime", None), "set_observation_sink", None)
        if not callable(setter):
            return
        runtime = getattr(host, "runtime", None)
        persistence = getattr(runtime, "persistence", None)
        scope = getattr(persistence, "scope", None)
        if scope is not None and getattr(scope, "storage_token", None):
            store = self.observation_history_store

            def scoped_sink(_session_key: str, snapshot: dict[str, Any], *, _scope=scope, _store=store) -> None:
                _store.append(_scope, snapshot)

            setter(scoped_sink)
            return
        if self._observation_sink is not None:
            setter(self._observation_sink)

    def _uses_scope_runtime(self) -> bool:
        return hasattr(self._p, "_scope_runtime_registry")

    def _active_relation_runtime(self) -> Any | None:
        getter = getattr(self._p, "_active_relation_runtime", None)
        if not callable(getter):
            return None
        try:
            return getter()
        except Exception:
            return None

    def _active_session_runtime(self) -> Any | None:
        getter = getattr(self._p, "_active_scoped_session_runtime", None)
        if not callable(getter):
            return None
        try:
            return getter()
        except Exception:
            return None

    # ------------------------------------------------------------------
    # 关系年龄（Item 125 / Item 130）
    # ------------------------------------------------------------------

    def first_interaction_time(self, session_key: str) -> float:
        """Return the active relation's first interaction, never a session bucket."""

        del session_key
        relation = self._active_relation_runtime()
        if type(relation) is RelationRuntime:
            return relation.ensure_first_interaction_time()
        # A missing authenticated relation is a no-op.  Preserve the legacy
        # return shape for display callers without materialising anonymous state.
        return time.time()

    def set_first_interaction_time(self, session_key: str, ts: float) -> None:
        """Set state only on an already authenticated relation owner."""

        del session_key
        relation = self._active_relation_runtime()
        if type(relation) is RelationRuntime:
            relation.set_first_interaction_time(ts)

    def relationship_stage(self, session_key: str) -> str:
        """Expose a display-safe relationship stage without a fallback bucket."""

        relation = self._active_relation_runtime()
        if type(relation) is RelationRuntime:
            stage = relation.relationship_stage()
            if stage is not None:
                return stage
        return get_relationship_stage(self.first_interaction_time(session_key))

    def accelerate_relationship(self, session_key: str, intensity: float) -> None:
        """Apply acceleration only to an already authenticated relation owner."""

        del session_key
        relation = self._active_relation_runtime()
        if type(relation) is RelationRuntime:
            relation.accelerate_relationship(intensity)

    # ------------------------------------------------------------------
    # Item 103: 设备切换感知问候
    # ------------------------------------------------------------------

    def detect_device_change(self, session_key: str, current_ua: str) -> str | None:
        """Registry-free compatibility seam; scoped callers must use the owner."""

        del session_key, current_ua
        # This old shape is intentionally unable to select a live scoped session.
        # Production receives ``ScopedDeviceContext`` from the exact runtime view.
        return None

    # ------------------------------------------------------------------
    # 第一印象锚定（Item 141 / Item 142）
    # ------------------------------------------------------------------

    def record_first_impression(
        self,
        session_key: str,
        valence: float,
        topic_type: str,
        user_style: str,
        quality: float,
    ) -> None:
        """Record only through the active authenticated relation owner."""

        del session_key
        relation = self._active_relation_runtime()
        if type(relation) is RelationRuntime:
            relation.record_first_impression(
                valence=valence,
                topic_type=topic_type,
                user_style=user_style,
                quality=quality,
            )

    def get_impression_anchor(self, session_key: str) -> tuple[FirstImpression | None, float]:
        """Return an anchor only from the active authenticated relation owner."""

        del session_key
        relation = self._active_relation_runtime()
        if type(relation) is not RelationRuntime:
            return (None, 0.0)
        impression = relation.first_impression()
        first = relation.first_interaction_time()
        if impression is None or first is None:
            return (None, 0.0)
        age_days = max(0.0, (time.time() - first) / 86_400)
        return (impression, impression.anchor_weight(age_days))

    # ------------------------------------------------------------------
    # Session key 派生
    # ------------------------------------------------------------------

    def raw_bucket_sender_id(self, event: Any) -> str:
        """session_key() 塌缩判定专用的 sender 解析口径：只读裸属性
        `sender_id` / `user_id`，**不回退** `event.get_sender_id()`。

        与下面 `session_key()` 的塌缩后缀判定共用同一段逻辑（此方法即从那里
        抽出），保证"session_key 是否塌缩"与"这个口径是否解析出 sender"两件
        事恒为同一次求值——`session_key()` 的桶派生本身依赖这一点，本方法
        因此保留、不删除。

        **历史修正（v2.5.0 slice-1b）**：本方法**曾经**被 v2.5.0 P0 B1 暂存层
        （`session_state_store` 的已认证 sender 暂存）直接复用，理由是"与
        `session_key()` 同口径、塌缩桶天然拿不到值"。但真实 AstrBot 事件只
        暴露 `get_sender_id()` 方法、从不设 `sender_id`/`user_id` 裸属性——
        本方法在生产事件上对**所有**事件（不分塌缩桶还是正常私聊/unique-on
        群）恒返回空串，导致 B1 暂存层在生产上恒为空、货架写点因此永久 SKIP
        （含本该天生 per-user 的私聊）。真正的哑火根因是"把裸属性判空"当成
        了"塌缩判定"的代理，而生产事件裸属性本就不存在，两者被巧合掩盖。

        B1 暂存层现已改用 `resolve_authenticated_identity`（见下）——那里用
        `get_sender_id()` + `get_message_type()` + `get_group_id()` +
        `session_id` 的组合矩阵直接判定"是否 per-user"，不再借道本方法这个
        裸属性代理。本方法自身职责收窄回**只服务 `session_key()` 的桶派生**，
        不再是其他调用方的"身份解析"入口。
        """
        return str(getattr(event, "sender_id", "") or getattr(event, "user_id", "") or "")

    def resolve_authenticated_identity(
        self,
        event: Any,
    ) -> VerifiedSubjectInput | dict[str, str] | None:
        """跨群记忆三写点（货架写 / profile 软同步 / 出生播种）身份解析主判据。

        design: docs/architecture/v250-cross-group-memory-design.md §8 B1
        （slice-1b 全矩阵扎实版修正）。

        与 `raw_bucket_sender_id`/`session_key()` 的塌缩判定口径【不同】——
        本方法只用 event 的**公开方法**（`get_sender_id()` /
        `get_message_type()` / `get_group_id()` / `session_id` /
        `unified_msg_origin`），绝不读裸属性 `sender_id`/`user_id`（真实
        AstrBot 事件从不设这两个属性，读它们在生产上恒空——这正是本方法要
        修的哑火根因，见 `raw_bucket_sender_id` 文档字符串的历史修正）。
        不解析 `session_key` 反推、不读 `rel_register` 钉住值——这两条路都
        已被 design §8 证明不安全。

        判定矩阵（design "per_user_matrix"）：
        - `get_sender_id()` 为空 → None（认不出发言人，SKIP）。
        - 平台（`get_platform_id()`，回退 `unified_msg_origin` 首段）解不出
          → None（拒绝构造无平台的身份记录）。
        - `message_type == FRIEND_MESSAGE`（私聊）→ 天生 per-user，放行；
          `origin_id` = 本会话的 `session_key()`（与写点历史行为一致）。
        - `message_type == GROUP_MESSAGE` 且 `group_id` 非空 且
          `event.session_id != group_id`（unique_session ON——框架
          WakingCheckStage 在插件 handler 之前已把 session_id 改写成
          `f"{sender}_{group}"`，见 stage_order.py / waking_check/stage.py）
          → per-user，放行；`origin_id` = `f"group:{group_id}"`。
        - `message_type == GROUP_MESSAGE` 且 `session_id == group_id`
          （unique_session OFF，共享桶——多人共享同一 session_id，B1 红线
          场景）或 `group_id` 解不出 → None（首条消息即可确定性判定，
          不依赖任何历史/一致性积累，无冷启动洞）。
        - `OTHER_MESSAGE` / 未知类型 → None（保守，不放行）。

        Returns:
            None：调用方（on_message）本次不应暂存任何身份。
            非 None：身份记录 `{"sender_id","platform","origin_scope",
            "origin_id"}`，货架写点直接消费这四个字段——platform/origin
            由此确定性算出，写点不再自行反解析 session_key（一并修正
            MINOR#3 的写读键三段分叉）。
        """
        sid = ""
        try:
            if hasattr(event, "get_sender_id"):
                sid = str(event.get_sender_id() or "")
        except Exception:
            sid = ""
        if not sid:
            return None

        platform = ""
        try:
            get_platform_id = getattr(event, "get_platform_id", None)
            if callable(get_platform_id):
                platform = str(get_platform_id() or "")
        except Exception:
            platform = ""
        if not platform:
            umo = str(getattr(event, "unified_msg_origin", "") or "")
            platform = umo.split(":", 1)[0] if umo else ""
        if not platform:
            return None

        mt_name = ""
        try:
            get_mt = getattr(event, "get_message_type", None)
            if callable(get_mt):
                mt_name = str(getattr(get_mt(), "name", "") or "")
        except Exception:
            mt_name = ""

        if mt_name == "FRIEND_MESSAGE":
            if self._uses_scope_runtime():
                return VerifiedSubjectInput(
                    platform_realm=platform,
                    subject_id=sid,
                )
            return {
                "sender_id": sid,
                "platform": platform,
                "origin_scope": "private",
                "origin_id": self.session_key(event),
            }

        if mt_name == "GROUP_MESSAGE":
            gid = ""
            try:
                get_gid = getattr(event, "get_group_id", None)
                if callable(get_gid):
                    gid = str(get_gid() or "")
            except Exception:
                gid = ""
            if not gid:
                return None  # 群号解不出 → 保守 SKIP
            evt_session_id = str(getattr(event, "session_id", "") or "")
            if evt_session_id and evt_session_id != gid:
                # unique_session ON：session_id 已被框架改写为 per-sender 形态
                if self._uses_scope_runtime():
                    return VerifiedSubjectInput(
                        platform_realm=platform,
                        subject_id=sid,
                    )
                return {
                    "sender_id": sid,
                    "platform": platform,
                    "origin_scope": "group",
                    "origin_id": f"group:{gid}",
                }
            return None  # session_id == group_id：unique_session OFF 共享桶，SKIP

        return None  # OTHER_MESSAGE / 未知类型：保守不放行

    def session_key(self, event: Any = None, session_key: str = "") -> str:
        """从事件对象派生会话标识。

        派生规则：
        1. 显式传入 session_key 时直接使用
        2. 从 event 中提取 session_id / unified_msg_origin
        3. 群聊场景下追加 sender_id，确保每个用户独立的计算脊柱

        Args:
            event: AstrBot 事件对象。
            session_key: 显式指定的会话键（优先级最高）。

        Returns:
            派生出的会话标识字符串。
        """
        if self._uses_scope_runtime():
            runtime = self._active_session_runtime()
            if runtime is None:
                raise ValueError("scoped session key requires a frozen runtime")
            if session_key and session_key != runtime.storage_token:
                raise ValueError("scoped session key does not match frozen storage_token")
            return runtime.storage_token
        if session_key:
            return session_key
        if event is not None:
            base = str(getattr(event, "session_id", "") or getattr(event, "unified_msg_origin", "") or "default")
            # 群聊中追加 sender_id，使每个用户拥有独立的 host/kernel/计算脊柱。
            # 与 raw_bucket_sender_id() 共用同一口径（见该方法文档字符串）。
            sender_id = self.raw_bucket_sender_id(event)
            if sender_id and base != "default":
                return f"{base}:{sender_id}"
            return base
        return "default"

    # ------------------------------------------------------------------
    # 每会话锁
    # ------------------------------------------------------------------

    def session_lock(self, session_key: str) -> asyncio.Lock:
        """获取指定会话的异步锁（懒创建）。

        当锁字典超过 500 个条目时，清理未锁定的旧条目到 400 以下，
        防止长期运行时内存泄漏。

        Args:
            session_key: 会话标识。

        Returns:
            该会话对应的 asyncio.Lock 实例。
        """
        locks = self._p._store.session_locks
        if not locks.has(session_key):
            locks.set(session_key, asyncio.Lock())
            # 锁字典过大时清理未使用的旧锁，防止内存泄漏
            if len(locks) > 500:
                to_remove = []
                for k, lock in locks.snapshot_items():
                    if k != session_key and not lock.locked():
                        to_remove.append(k)
                    if len(locks) - len(to_remove) <= 400:
                        break
                for k in to_remove:
                    locks.pop(k, None)
        return locks.get(session_key)

    # ------------------------------------------------------------------
    # 文件系统安全的 session key
    # ------------------------------------------------------------------

    def safe_session_key(self, session_key: str) -> str:
        """将 session_key 转换为文件系统安全的字符串。

        移除 <>:"|?* 等不安全字符，将 / \\ 替换为 _，
        截断到 200 字符防止路径过长。结果会被缓存。

        Args:
            session_key: 原始会话标识。

        Returns:
            文件系统安全的会话标识。
        """
        if self._session_state is not None:
            cache = self._session_state.safe_session_key_cache
        else:
            cache = {}
        if session_key in cache:
            return cache[session_key]
        # 移除文件系统不安全字符
        unsafe = '<>:"|?*\x00'
        safe = session_key.replace("/", "_").replace("\\", "_")
        for ch in unsafe:
            safe = safe.replace(ch, "_")
        # 截断防止路径过长
        if len(safe) > 200:
            safe = safe[:200]
        cache[session_key] = safe
        # 缓存过大时全量清空（简单策略，避免复杂 LRU）
        if len(cache) > 512:
            cache.clear()
        return safe

    # ------------------------------------------------------------------
    # 公共 session key 解析（用于 WebUI 等外部接口）
    # ------------------------------------------------------------------

    def resolve_public_session_key(self, event: Any = None, *, request: Any = None, session_key: str = "") -> str:
        """解析公共会话标识，用于 WebUI 等外部接口。

        与 session_key() 不同，此方法不追加 sender_id，返回的是
        "公共"级别的会话标识（如群聊的 unified_msg_origin）。

        Args:
            event: 事件对象或字符串。
            request: 请求对象（备选来源）。
            session_key: 显式指定的会话键。

        Returns:
            仅 legacy 模式可从传输数据导出公共会话标识；scoped 模式只返回
            当前已绑定的 storage token。
        """
        if self._uses_scope_runtime():
            runtime = self._active_session_runtime()
            storage_token = getattr(runtime, "storage_token", None)
            if not isinstance(storage_token, str) or not storage_token:
                raise ValueError("scoped public session lookup requires a live binding")
            if session_key and session_key != storage_token:
                raise ValueError("raw public session key does not match the bound scope")
            return storage_token

        # Registry-free compatibility reader only.  Production hooks and HTTP
        # routes resolve an authenticated SessionScope before they reach here.
        if session_key:
            return session_key
        if event is not None:
            if isinstance(event, str):
                return event
            umo = getattr(event, "unified_msg_origin", None)
            if umo:
                return str(umo)
        if request is not None:
            sid = getattr(request, "session_id", None)
            if sid:
                return str(sid)
        return "global"

    # ------------------------------------------------------------------
    # Item 153 / T2-06：关系仪式观察
    # ------------------------------------------------------------------

    def observe_ritual_pattern(
        self,
        session_key: str,
        hour: int,
        pattern: str,
        *,
        observed_at: float | None = None,
    ) -> None:
        """Route a pattern to the already-bound relation owner, or skip it."""

        del session_key
        relation = self._active_relation_runtime()
        if type(relation) is RelationRuntime:
            ritual = relation.observe_ritual(
                hour=hour,
                pattern=pattern,
                observed_at=observed_at,
            )
            session_runtime = self._active_session_runtime()
            scheduler = getattr(session_runtime, "proactive_scheduler", None)
            register = getattr(scheduler, "register_ritual", None)
            if ritual is not None and callable(register):
                register(
                    relation.scope.relation_ref.token,
                    str(ritual["pattern"]),
                    int(ritual["hour_start"]),
                    int(ritual["hour_end"]),
                )

    def detect_and_observe_ritual_from_text(self, session_key: str, text: str, now: float | None = None) -> None:
        """T2-06④：message ingest 钩子——从原始用户文本识别早安/晚安模式。

        识别方式与偏差说明见模块级 `_detect_greeting_ritual_pattern` 的注释
        （assessor 的 greeting/farewell flag 在插件运行时路径不可达，退化为
        关键词兜底）。命中才调用 observe_ritual_pattern，未命中零开销。

        Args:
            session_key: 会话标识。
            text: 原始用户消息文本。
            now: 当前时间戳，默认为 time.time()。
        """
        pattern = _detect_greeting_ritual_pattern(text)
        if not pattern:
            return
        ts = now if now is not None else time.time()
        # 中国时区读取小时（非 time.localtime 的系统时区），避免境外/UTC 部署把凌晨
        # 早安仪式误判成深夜（8 小时偏移）。
        hour = datetime.datetime.fromtimestamp(ts, tz=_CHINA_TZ).hour
        self.observe_ritual_pattern(
            session_key,
            hour,
            pattern,
            observed_at=ts,
        )

    # ------------------------------------------------------------------
    # 记忆系统辅助方法
    # ------------------------------------------------------------------

    def memory_system_for_session(self, session_key: str) -> MemorySystem:
        """获取指定会话的记忆系统实例（懒创建）。

        MEM-02①：本方法是冻结的同步契约（外部消费方按同步 API 调用），不能改成
        async——但 chat 路径重启后 body 通道恢复不到真实内容（CP1 起
        AlphaBodyState.to_dict 白名单 memory 到 {relationship, shadow,
        recent_texts}，_memory_system 键从未落进去），首次为某 session 懒创建的
        MemorySystem 永远是空的。这里在懒创建的同一拍，把"从 KV 归档补水"调度成
        后台 fire-and-forget 任务（仓库既有的 anchored 后台任务模式），不阻塞、
        不改变本方法的同步返回契约；真正的合并逻辑在
        StatePersistence.hydrate_memory_system 里非破坏性地原地合并（不是整层替换），
        避免补水任务完成前活体已经写入的新内容被覆盖。

        Args:
            session_key: 会话标识。

        Returns:
            该会话对应的 MemorySystem 实例。
        """
        if self._uses_scope_runtime():
            runtime = self._active_session_runtime()
            if runtime is None:
                raise ValueError("scoped memory lookup requires a frozen runtime")
            if session_key != runtime.storage_token:
                raise ValueError(
                    "scoped memory lookup does not match frozen storage_token"
                )
            memory = runtime.memory_system
            if not isinstance(memory, MemorySystem):
                raise ValueError("scoped session runtime has no loaded memory owner")
            return memory
        if not session_key:
            if self._uses_scope_runtime():
                raise ValueError("scoped memory lookup requires storage_token")
            session_key = "default"
        systems = self._p._store.memory_systems
        if not systems.has(session_key):
            # 召回引擎灰度模式：插件配置 sylanne_alpha_recall_mode 优先，
            # 缺省时 MemorySystem 内部会回退到环境变量 SYLANNE_RECALL_MODE / LEGACY。
            cfg = getattr(self._p, "config", None) or {}
            recall_mode = cfg.get("sylanne_alpha_recall_mode") or None
            systems.set(session_key, MemorySystem(recall_mode=recall_mode))
            # MEM-03 PR-1：懒创建即盖化身印章（同步、无 await，不破坏本 accessor 的
            # 冻结同步契约）。PR-1 惰性（纪元恒 0，印章恒 0）；PR-2 删除臂 bump 后即生效
            # ——让"删除后新建的活体"带新纪元、旧引用携旧印章被咽喉验章丢弃。
            sp = getattr(self._p, "_state_persistence", None)
            throat = getattr(sp, "_throat", None) if sp is not None else None
            if throat is not None:
                throat.stamp(systems.get(session_key), session_key)
            self._schedule_memory_hydration(session_key)
        return systems.get(session_key)

    def _schedule_memory_hydration(self, session_key: str) -> None:
        """MEM-02①：懒创建 MemorySystem 后台补水的调度点（幂等，失败静默降级）。

        `StatePersistence.hydrate_memory_system` 自己会检查 `_hydrated` 标记，
        重复调度（例如同一 session 短时间内多次懒创建，理论上不该发生但防御一下）
        不会重复合并——第二次进去时活体已经 `_hydrated=True`，直接 no-op 返回。

        MEM-03 PR-2（design §3 臂③ / §8 PR-2 行）：改经单写咽喉提交
        （kind="hydrate"），不再直接 `safe_ensure_future`。若本次懒创建之后、hydrate
        真正执行之前该 session 被删（三条删除类壳之一 bump 了纪元），入队时捕获的
        token 与执行时的当前纪元不再相等，咽喉会把这个陈旧 hydrate op 直接丢弃、
        不合并那份已经注定被删的归档——闭合 F3 的 hydrate 复活臂。同一 session 的
        hydrate 与 save/delete 现在共享同一条 FIFO 队列，天然按提交序串行，不再是
        与其他记忆写路径完全独立、时序不确定的后台任务。

        本方法自身依然不 await（`memory_system_for_session` 冻结同步契约不变）；
        `throat.submit` 本身就是同步调用，返回的 Future 用 done_callback 消费掉
        异常/取消（与 `_on_memory_system_evicted` 同款 MINOR-1 模式一致），避免
        "Future exception was never retrieved" 噪音。若拿不到咽喉实例（旧/测试环境
        降级），回退到原 fire-and-forget 调度，保持行为不倒退。
        """
        state_persistence = getattr(self._p, "_state_persistence", None)
        hydrate = getattr(state_persistence, "hydrate_memory_system", None)
        if not callable(hydrate):
            return
        throat = getattr(state_persistence, "_throat", None)
        if throat is None:
            try:
                from sylanne_alpha.utils import safe_ensure_future

                safe_ensure_future(
                    hydrate(session_key),
                    name=f"memory_hydrate_{session_key}",
                    task_list=getattr(self._p, "_background_tasks", None),
                )
            except Exception as e:
                logger.debug(f"Sylanne memory hydration scheduling skipped: {e}")
            return
        try:
            fut = throat.submit(
                session_key,
                lambda: hydrate(session_key),
                kind="hydrate",
                state=None,
            )
        except Exception as e:
            logger.debug(f"Sylanne memory hydration scheduling skipped: {e}")
            return
        if fut is not None:
            fut.add_done_callback(lambda f: f.cancelled() or f.exception())

    def memory_system_has_content(self, memory_system: Any) -> bool:
        """检查记忆系统是否包含有效内容（L1/L2/L3 任一非空）。

        Args:
            memory_system: MemorySystem 实例。

        Returns:
            True 表示至少有一层包含数据。
        """
        if memory_system is None:
            return False
        return bool(
            list(getattr(memory_system, "_l1", []) or [])
            or list(getattr(memory_system, "_l2", []) or [])
            or dict(getattr(memory_system, "_l3_nodes", {}) or {})
            or list(getattr(memory_system, "_l3_edges", []) or [])
        )

    def hydrate_memory_system_from_body_traces(
        self, session_key: str, memory_system: MemorySystem, traces: Any
    ) -> None:
        """从 body.memory.traces 注水记忆系统。

        当记忆系统为空但 kernel body 中存有历史 traces 时，
        将最近 50 条 trace 写入记忆系统以恢复状态。

        Args:
            session_key: 会话标识。
            memory_system: 目标记忆系统实例。
            traces: body.memory["traces"] 列表。
        """
        if self.memory_system_has_content(memory_system):
            return
        # 只取最近 50 条，避免冷启动时大量写入
        for trace in list(traces or [])[-50:]:
            if not isinstance(trace, dict):
                continue
            text = str(trace.get("text") or "").strip()
            if not text:
                continue
            try:
                temperature = float(trace.get("temperature", trace.get("warmth", 0.5)) or 0.5)
            except (TypeError, ValueError):
                temperature = 0.5
            memory_system.write(
                text=text,
                embedding=trace.get("embedding"),
                temperature=max(0.0, min(1.0, temperature)),
            )
            # 恢复原始权重和创建时间
            if memory_system._l1:
                item = memory_system._l1[-1]
                try:
                    item.weight = max(0.0, min(1.0, float(trace.get("weight", 1.0) or 1.0)))
                except (TypeError, ValueError):
                    item.weight = 1.0
                try:
                    created_at = float(trace.get("created_at", trace.get("updated_at", 0.0)) or 0.0)
                    if created_at > 0:
                        item.created_at = created_at
                except (TypeError, ValueError):
                    pass

    # ------------------------------------------------------------------
    # 已知 WebUI 会话列表
    # ------------------------------------------------------------------

    def known_webui_sessions(self, requested: str = "") -> list[str]:
        """收集所有已知的会话标识，用于 WebUI 会话列表展示。

        从多个来源聚合：hosts 缓存、memory_systems、memory_cache、
        runtime 导出数据、磁盘 .alpha.json 文件。

        Args:
            requested: 当前请求的会话标识（确保包含在结果中）。

        Returns:
            去重后的会话标识列表。
        """
        if self._uses_scope_runtime():
            # WebUI calls have no authenticated scope in Task 5; never select or
            # enumerate a default/recent session as a substitute.
            return []
        sessions: list[str] = []

        def add(value: Any) -> None:
            text = str(value or "").strip()
            if text and text not in sessions:
                sessions.append(text)

        add(requested)
        if self._session_state is not None:
            hosts_dict = self._session_state.hosts
            memory_dict = self._session_state.memory_systems
        else:
            hosts_dict = {}
            memory_dict = {}
        for key in hosts_dict.keys():
            add(key)
        for key in memory_dict.keys():
            add(key)
        cache = getattr(self._plugin, "_sylanne_memory_cache", {}) or {}
        if isinstance(cache, dict):
            for key in cache.keys():
                add(key)
        # 从 runtime 导出中提取持久化过的 session
        for host in list(hosts_dict.values()):
            runtime = getattr(host, "runtime", None)
            export_all = getattr(runtime, "export_all", None)
            if not callable(export_all):
                continue
            try:
                exported = export_all()
            except Exception:
                continue
            persisted = exported.get("sessions", {}) if isinstance(exported, dict) else {}
            if isinstance(persisted, dict):
                for key in persisted.keys():
                    add(key)
        # 从磁盘文件名中提取 session key
        try:
            cfg = self._services.config or {}
            root = Path(resolve_data_root(cfg))
            if root.exists():
                for path in root.glob("*.alpha.json"):
                    add(path.name[: -len(".alpha.json")])
        except Exception as e:
            logger.debug(f"Sylanne skip: {e}")
        return sessions

    # ------------------------------------------------------------------
    # Host 管理
    # ------------------------------------------------------------------

    def host(self, session_key: str) -> SylanneAlphaHost:
        """获取指定会话的 Host 实例（懒加载 + LRU 缓存）。

        首次访问时创建 Host 并执行以下初始化：
        1. LRU 驱逐：超过 _MAX_HOSTS 时持久化并移除最旧的 host
        2. 编码器共享：所有 host 共用同一个 encoder 实例节省内存
        3. 人格驱动记忆参数：从 personality 派生记忆系统参数
        4. 记忆恢复：从持久化数据或 body traces 恢复记忆状态
        5. 对话缓冲区恢复：从文件加载历史对话缓冲

        Args:
            session_key: 会话标识。

        Returns:
            该会话对应的 SylanneAlphaHost 实例。
        """
        if self._uses_scope_runtime():
            runtime = self._active_session_runtime()
            if runtime is None:
                raise ValueError("scoped host lookup requires a frozen runtime")
            if session_key != runtime.storage_token:
                raise ValueError(
                    "scoped host lookup does not match frozen storage_token"
                )
            host = runtime.host
            if not isinstance(host, SylanneAlphaHost):
                raise ValueError("scoped session runtime has no gateway-bound host")
            self._bind_observation_sink(host)
            return host
        if not session_key:
            if self._uses_scope_runtime():
                raise ValueError("scoped host lookup requires storage_token")
            session_key = "default"
        hosts = self._p._store.hosts
        # 用 .get() 单次取值：BoundedDict 的 __contains__ 不查 TTL 而
        # __getitem__/pop 查，二者不一致会导致 `not in`→`.pop()` 的 TOCTOU
        # KeyError（并发驱逐/TTL 过期时）。miss 即走创建分支重建，幂等安全。
        existing_host = hosts.get(session_key)
        if existing_host is None:
            # LRU 驱逐：超容量时持久化并移除最旧的 host
            if len(hosts) >= self._p._MAX_HOSTS:
                oldest_key = next(iter(hosts.keys()))
                old_host = hosts.pop(oldest_key)
                from sylanne_alpha.utils import safe_ensure_future

                safe_ensure_future(
                    self._services.state_persistence.persist_kernel(oldest_key, old_host),
                    name=f"lru_evict_{oldest_key}",
                )
                # CP8-P6：驱逐前先把进化档案落盘（否则未巩固的反射/反思偏置随驱逐丢失），
                # 再清进化层 per-session 状态。尤其 _restored 守卫必须清——否则同 key
                # 后续重建时不会再从 KV 恢复，已落盘学习成果静默丢失。
                self._persist_and_forget_evolution(oldest_key)
            cfg = self._p.config if hasattr(self._p, "_config") else getattr(self._p, "config", {}) or {}
            root = resolve_data_root(cfg)
            host = SylanneAlphaHost(root=root, session_key=session_key)
            self._bind_observation_sink(host)
            # v2.5.0 跨群记忆出生播种（design §3/§4.1，与关系计数/Sylanne Six
            # 播种同点同档门）。**必须在此刻（第一次调用 `_personality()` 之前）
            # 判断"是否真正首次出生"**——`kernel._personality()` 有惰性初始化
            # 副作用（personality.py:482-485），一旦下面 :1176 调用过，
            # `host.kernel.personality` 就不再是空 dict，"是否首次出生"这个天然
            # 信号会被自己的读操作污染掉。真正首次出生（`self.personality` 为
            # 空 dict）与 LRU 驱逐重建（`runtime.load` 从磁盘读回非空
            # personality）在这里天然可辨——见 `host.py`/`kernel.py:140-157
            # boot()`。
            _is_true_birth = not host.kernel.personality
            self._schedule_person_profile_seed(session_key, host, is_true_birth=_is_true_birth)
            # 编码器共享：避免每个 host 各持有一份无状态 HDC encoder。
            comp = host.kernel.computation
            plugin_cls = type(self._p)
            if plugin_cls._shared_encoder is None:
                plugin_cls._shared_encoder = comp.encoder
            else:
                comp.replace_encoder(plugin_cls._shared_encoder)
            # 从人格状态派生记忆系统参数（人格驱动全参数）
            personality = host.kernel._personality() if hasattr(host.kernel, "_personality") else {}
            memory_system = self.memory_system_for_session(session_key)
            if personality and isinstance(personality, dict):
                memory_system.derive_params(personality)
            # 从持久化数据恢复记忆系统状态
            mem_data = host.kernel.body.memory.get("_memory_system")
            if mem_data and isinstance(mem_data, dict):
                memory_system.from_dict(mem_data)
            # 若记忆系统仍为空，尝试从 body traces 注水
            if not self.memory_system_has_content(memory_system):
                self.hydrate_memory_system_from_body_traces(
                    session_key,
                    memory_system,
                    host.kernel.body.memory.get("traces", []),
                )
                # MEM-03 PR-5（存储解耦）：trace 注水出的内容留在活体占位者里，由下一次
                # 周期 KV save 落盘（sylanne_memory_state 唯一真源）——删掉原来写
                # body.memory["_memory_system"] 死档 + persist_kernel 那对：AlphaBodyState
                # 白名单丢弃该键、从未在 kernel 快照往返幸存，persist_kernel 只落这份死写，
                # durability 上等于没落盘（真档一直靠周期 KV save）。故删之无损。
            hosts.set(session_key, host)
            # 恢复对话缓冲区（文件回退；KV 保持同步）
            if not self._p._store.conversation_buffers.has(session_key):
                buf_data = host.runtime.load_buffer(session_key)
                if buf_data and isinstance(buf_data, dict):
                    self._p._store.conversation_buffers.set(session_key, ConversationBuffer.from_dict(buf_data))
        else:
            # 已存在：重新写入以刷新 LRU 顺序（set→__setitem__ 会 move_to_end）
            host = existing_host
            self._bind_observation_sink(host)
            hosts.set(session_key, host)
        return host

    # ------------------------------------------------------------------
    # v2.5.0 跨群记忆出生播种（design §3 关系+人格 / §4.1 transient / §8 B3）
    # ------------------------------------------------------------------

    def _schedule_person_profile_seed(self, session_key: str, host: SylanneAlphaHost, *, is_true_birth: bool) -> None:
        """`host()` 内的同步守门 + 调度入口。

        真正的 KV 读写是异步的（`get_kv_data`/`put_kv_data`），而 `host()` 本身
        是同步方法——这里只做零成本的同步前置检查（开关全关 / 认不出身份时
        直接 return，不产生任何调度），检查通过才 `safe_ensure_future` 一个
        后台任务。**已知限制**：该后台任务与本次 `host()` 调用是异步的，
        本次调用内 :1176 附近的 `memory_system.derive_params(personality)`
        仍会用到播种前的（默认）人格值——这与 design §3"播种只在出生一瞬"
        的既定"最终一致"容忍度同类：下一次真正读取
        `host.kernel._personality()`（同一 host 对象，同一进程内）时已是
        播种后的值，只有出生那一次 `derive_params` 调用用的是旧值。
        """
        # A scoped request already owns a frozen RelationRuntime.  Do not turn
        # its opaque subject into a legacy platform/sender KV lookup here: that
        # would bypass the relation gateway and let a mutable session cache
        # choose identity downstream.  The scoped ingress path supplies the
        # relation-owned state directly instead.
        if self._uses_scope_runtime():
            return
        settings_mod = None
        try:
            from sylanne_alpha.cross_session_config import cross_session_settings

            settings_mod = cross_session_settings(self._p)
        except Exception:
            return
        if not settings_mod.enabled:
            # mode="off"：§7 "停读停写旁挂层"——即便某个 bool 开关已被提前拧开，
            # 主档位仍是 off 时整段出生播种（含 shadow 观测计算）都不应调度。
            return
        if not (settings_mod.cross_relationship or settings_mod.cross_personality):
            return

        identity = None
        try:
            identity = self._p._store.get_authenticated_identity(session_key)
        except Exception:
            identity = None
        if not identity:
            return
        platform = str(identity.get("platform", "") or "")
        sender_id = str(identity.get("sender_id", "") or "")
        if not platform or not sender_id:
            return

        kernel_last_activity = 0.0
        try:
            kernel_last_activity = float(host.kernel.last_event.get("now") or 0.0)
        except Exception:
            kernel_last_activity = 0.0

        from sylanne_alpha.utils import safe_ensure_future

        safe_ensure_future(
            self._seed_person_profile_async(
                session_key,
                host,
                platform=platform,
                sender_id=sender_id,
                is_true_birth=is_true_birth,
                kernel_last_activity=kernel_last_activity,
            ),
            name=f"person_profile_seed_{session_key}",
        )

    async def _seed_person_profile_async(
        self,
        session_key: str,
        host: SylanneAlphaHost,
        *,
        platform: str,
        sender_id: str,
        is_true_birth: bool,
        kernel_last_activity: float,
    ) -> None:
        """后台任务真身：读 profile，按档位把关系计数/Sylanne Six/transient
        播种进【同一个】`host.kernel` 对象（引用不变，`hosts.set` 已在
        `host()` 里同步完成，本任务只是稍后原地修改同一份 kernel 状态）。

        关系计数 / Sylanne Six 只在 `is_true_birth` 时播种（LRU 驱逐重建时
        `host.kernel` 已从磁盘恢复出该 session 组织累积/漂移过的真实值，
        重新播种会用 profile 里可能更旧的快照覆盖掉，是数据倒退，不是"跨群
        记得"）。transient 走独立守卫（`seed_transient_delta` 内部的
        `profile.last_interaction_ts > kernel_last_activity`），不受
        `is_true_birth` 限制——LRU 重建后仍可能有"来自别处的新情绪"需要补种，
        这正是 design §4.3 明确要求覆盖的场景。

        `mode=="shadow"` 与 `mode=="on"` 的区别只在这里体现——外层
        `_schedule_person_profile_seed` 只保证 `mode!="off"`：shadow 档只
        计算"若施加会怎样"并落观测日志，绝不真的改动 `host.kernel`（design
        §4.3"shadow 观测：播种点在 shadow 档落一条…不施加"）；只有
        `mode=="on"` 才真正写入 kernel/回写 `last_applied_*` 锚点。
        """
        # Defense in depth for a task queued before a runtime mode transition.
        # Scoped mode must never fall back to raw platform/sender persistence.
        if self._uses_scope_runtime():
            return
        from sylanne_alpha.cross_session_config import cross_session_settings
        from sylanne_alpha.person_profile import load_person_profile, seed_transient_delta
        from sylanne_alpha.person_shelf import register_person_shelf_origin

        settings = cross_session_settings(self._p)
        state_persistence = getattr(self._p, "_state_persistence", None)
        get_lock = getattr(state_persistence, "_get_person_profile_lock", None)
        lock = get_lock(platform, sender_id) if callable(get_lock) else None

        async def _run() -> None:
            safe_key = None
            get_safe = getattr(state_persistence, "_safe_session_key", None)
            if callable(get_safe):
                try:
                    safe_key = get_safe(session_key)
                except Exception:
                    safe_key = None
            if safe_key:
                # 同货架写侧一致的"先登记再动"次序——出生播种同样会在 kernel
                # 里留下可能需要 purge 反查的痕迹（transient 施加），登记失败
                # 则本轮整体跳过（fail-closed，不产生孤儿）。
                try:
                    registered = await register_person_shelf_origin(self._p, safe_key, platform, sender_id, "")
                except Exception:
                    registered = False
                if not registered:
                    return

            try:
                profile = await load_person_profile(self._p, platform, sender_id)
            except Exception as exc:
                logger.debug(f"Sylanne person profile seed: load failed: {exc}")
                return

            apply_live = settings.mode == "on"

            if is_true_birth:
                if settings.cross_personality and profile.six_snapshot:
                    if apply_live:
                        try:
                            from sylanne_alpha._engine.sylanne_core.compute.personality import (
                                _voice,
                                initial_personality,
                            )

                            seeded = initial_personality(session_key)
                            seeded["traits"] = dict(profile.six_snapshot)
                            seeded["voice"] = _voice(seeded["traits"])
                            host.kernel.personality = seeded
                        except Exception as exc:
                            logger.debug(f"Sylanne person profile seed: Six seed failed: {exc}")
                    else:
                        logger.debug(
                            "Sylanne person profile seed (shadow, would-apply): "
                            f"person={platform}:{sender_id} would_seed_six={profile.six_snapshot}"
                        )

                if settings.cross_relationship and (
                    profile.preference_count or profile.boundary_count or profile.progress_count or profile.repair_count
                ):
                    if apply_live:
                        try:
                            relationship = host.kernel.body.memory.setdefault("relationship", {})
                            relationship["signals"] = {
                                "preference_count": profile.preference_count,
                                "boundary_count": profile.boundary_count,
                                "progress_count": profile.progress_count,
                                "repair_count": profile.repair_count,
                            }
                        except Exception as exc:
                            logger.debug(f"Sylanne person profile seed: relationship seed failed: {exc}")
                    else:
                        logger.debug(
                            "Sylanne person profile seed (shadow, would-apply): "
                            f"person={platform}:{sender_id} would_seed_relationship_counts="
                            f"pref={profile.preference_count} bound={profile.boundary_count} "
                            f"prog={profile.progress_count} repair={profile.repair_count}"
                        )

            if settings.cross_relationship:
                now = time.time()
                delta_t = now - (profile.last_interaction_ts or now)
                try:
                    result = seed_transient_delta(profile, now, kernel_last_activity)
                except Exception as exc:
                    logger.debug(f"Sylanne person profile seed: transient calc failed: {exc}")
                    result = None
                if result is not None:
                    delta, new_last_applied, new_last_applied_volatility = result
                    if apply_live:
                        try:
                            if delta:
                                host.kernel.body.apply_vector_delta(delta, now=now)
                            if (
                                new_last_applied != profile.last_applied_transient
                                or new_last_applied_volatility != profile.last_applied_volatility_transient
                            ):
                                from sylanne_alpha.person_profile import save_person_profile

                                updated = replace(
                                    profile,
                                    last_applied_transient=new_last_applied,
                                    last_applied_volatility_transient=new_last_applied_volatility,
                                )
                                await save_person_profile(self._p, platform, sender_id, updated)
                        except Exception as exc:
                            logger.debug(f"Sylanne person profile seed: transient apply failed: {exc}")
                    else:
                        # shadow：只落"若施加会怎样"的观测日志（person_hash 由
                        # debug 日志自身的 platform:sender_id 承担，Δt/衰减前后
                        # 值/would-apply delta 见 design §4.3），绝不碰 host.kernel、
                        # 也绝不回写 `last_applied_*` 锚点（锚点只在真正施加后推进）。
                        logger.debug(
                            "Sylanne person profile seed (shadow, would-apply): "
                            f"person={platform}:{sender_id} delta_t={delta_t:.1f}s "
                            f"warmth_transient_before={profile.warmth_transient:.4f} "
                            f"volatility_transient_before={profile.volatility_transient:.4f} "
                            f"would_apply_delta={delta} "
                            f"would_last_applied_warmth={new_last_applied:.4f} "
                            f"would_last_applied_volatility={new_last_applied_volatility:.4f}"
                        )

        if lock is not None:
            async with lock:
                await _run()
        else:
            await _run()

    def _persist_and_forget_evolution(self, session_key: str) -> None:
        """LRU 驱逐时：先同步取进化档案快照并异步落盘 KV，再清进化层 per-session 状态。

        关键时序：必须**同步**先取 evo_to_dict 快照，再调 forget 清容器，最后让落盘
        协程写入快照——否则 forget 先清空，落盘协程跑时只会写到空档案，未巩固的
        反射/反思偏置静默丢失。
        """
        p = self._p
        sched = getattr(p, "_autonomy_scheduler", None)
        consol = getattr(sched, "_consolidation", None)
        sc = getattr(p, "_self_core", None)
        snapshot = None
        if sc is not None and hasattr(sc, "evo_to_dict"):
            try:
                snapshot = sc.evo_to_dict(session_key)
            except Exception:
                snapshot = None
        if snapshot and consol is not None and hasattr(consol, "_write_evolution"):
            from sylanne_alpha.utils import safe_ensure_future

            safe_ensure_future(
                consol._write_evolution(session_key, snapshot),
                name=f"evo_persist_evict_{session_key}",
            )
        forget = getattr(p, "_forget_evolution_session", None)
        if callable(forget):
            try:
                forget(session_key)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # 离线消息缓冲（Item 107）
    # ------------------------------------------------------------------

    def offline_buffer_for_session(self, session_key: str) -> OfflineBuffer:
        """获取指定会话的离线缓冲区（懒创建）。

        Args:
            session_key: 会话标识。

        Returns:
            该会话对应的 OfflineBuffer 实例。
        """
        if not session_key:
            if self._uses_scope_runtime():
                raise ValueError("scoped offline buffer requires storage_token")
            session_key = "default"
        if self._session_state is not None:
            buffers = self._session_state.offline_buffers
        else:
            buffers = {}
        if session_key not in buffers:
            buffers[session_key] = OfflineBuffer()
        return buffers[session_key]

    def push_offline_thought(self, session_key: str, thought: str) -> None:
        """向指定会话的离线缓冲区推送一条想法。

        由生活模拟模块在用户不在线时调用。

        Args:
            session_key: 会话标识。
            thought: 生活模拟产生的想法文本。
        """
        buf = self.offline_buffer_for_session(session_key)
        buf.push(thought)

    def drain_reconnect_summary(self, session_key: str) -> str:
        """用户重连时，取出离线缓冲区内容并生成摘要。

        如果缓冲区为空，返回空字符串（不注入任何内容）。

        Args:
            session_key: 会话标识。

        Returns:
            重连摘要文本，或空字符串。
        """
        buf = self.offline_buffer_for_session(session_key)
        return buf.drain_summary()


