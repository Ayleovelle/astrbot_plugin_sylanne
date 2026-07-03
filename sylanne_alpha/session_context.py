"""会话管理模块。

提供 SessionContext 类，封装 Sylanne 插件的会话生命周期管理：
- session key 派生（从事件对象提取唯一会话标识）
- 每会话锁（防止同一会话并发处理）
- host 实例管理（LRU 缓存 + 懒加载 + 编码器共享）
- 记忆系统注水（从持久化 traces 恢复记忆状态）
- 离线消息缓冲与重连摘要
- 时区感知与作息推断

所有方法通过 self._p 委托访问插件实例的属性和方法。
"""

from __future__ import annotations

import asyncio
import datetime
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

try:
    from astrbot.api import logger  # type: ignore
    from astrbot.core.utils.astrbot_path import get_astrbot_data_path  # type: ignore
except ImportError:
    import logging as _logging

    logger = _logging.getLogger("astrbot_plugin_sylanne")  # type: ignore

    def get_astrbot_data_path() -> Path:  # type: ignore
        return Path.home()

from sylanne_alpha.infra import resolve_data_root


from sylanne_alpha.host import SylanneAlphaHost
from sylanne_alpha.memory_system import ConversationBuffer, MemorySystem

if TYPE_CHECKING:
    from sylanne_alpha.protocols import PluginHost


# 时区感知：固定中国时区 UTC+8——time.localtime()/datetime.fromtimestamp() 不带 tz
# 会读宿主系统时区，境外/UTC 服务器上会把凌晨的"早安"仪式误判成"深夜"（8 小时偏移）。
# 与 v2core/capabilities/ignition.py 的 _CHINA_TZ 同一常量定义，仪式判断口径对齐。
_CHINA_TZ = datetime.timezone(datetime.timedelta(hours=8))


# ---------------------------------------------------------------------------
# Item 153: 关系仪式注册表（RitualRegistry）
# ---------------------------------------------------------------------------


class RitualRegistry:
    """关系仪式注册表：自动从重复行为模式中识别并注册"仪式"。

    仪式是用户与 Sylanne 之间形成的固定互动模式（如每晚道晚安、
    每天早上打招呼等）。当同一模式被观察到 3 次以上时，自动注册为仪式。

    用途：
    - 识别用户的行为规律，增强关系连续性感知
    - 为主动联系提供时间窗口参考
    - 仪式缺失时可触发"想念"信号
    """

    def __init__(self) -> None:
        self._rituals: dict[str, dict] = {}  # name -> {hour_start, hour_end, pattern}
        self._observations: dict[str, list[float]] = {}  # name -> [timestamps]

    def observe_pattern(self, session_key: str, hour: int, pattern: str) -> None:
        """观察到重复行为时记录。

        当同一模式出现 3 次以上时，自动注册为仪式。

        Args:
            session_key: 会话标识。
            hour: 当前小时（0-23）。
            pattern: 行为模式描述（如 "greeting"、"goodnight"）。
        """
        key = f"{session_key}:{pattern}"
        if key not in self._observations:
            self._observations[key] = []
        self._observations[key].append(time.time())
        # 同一模式出现 3 次以上，自动注册为仪式
        if len(self._observations[key]) >= 3:
            self._rituals[key] = {
                "hour_start": hour,
                "hour_end": (hour + 1) % 24,
                "pattern": pattern,
            }
            # 仪式已注册，只保留最近 5 条观测（用于更新时间窗口）
            self._observations[key] = self._observations[key][-5:]

    def get_active_rituals(self, session_key: str) -> list[dict]:
        """获取指定会话的所有已注册仪式。

        Args:
            session_key: 会话标识。

        Returns:
            该会话的仪式列表，每个仪式包含 hour_start、hour_end、pattern。
        """
        return [v for k, v in self._rituals.items() if k.startswith(session_key)]

    def get_ritual(self, session_key: str, pattern: str) -> dict | None:
        """获取指定会话+模式的已注册仪式（未达自动注册阈值则 None）。

        Args:
            session_key: 会话标识。
            pattern: 行为模式描述（如 "morning_greeting"）。
        """
        return self._rituals.get(f"{session_key}:{pattern}")

    # ------------------------------------------------------------------
    # 序列化（T2-06⑤：随插件 KV 周期持久化，重启不丢已学到的仪式）
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """序列化为可 JSON 化的 dict。"""
        return {
            "rituals": dict(self._rituals),
            "observations": {k: list(v) for k, v in self._observations.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RitualRegistry":
        """从字典恢复（load-compat：坏/缺字段一律安全降级为空）。"""
        reg = cls()
        if not isinstance(data, dict):
            return reg
        rituals = data.get("rituals", {})
        if isinstance(rituals, dict):
            reg._rituals = {
                str(k): dict(v) for k, v in rituals.items() if isinstance(v, dict)
            }
        observations = data.get("observations", {})
        if isinstance(observations, dict):
            reg._observations = {
                str(k): [float(t) for t in v if isinstance(t, (int, float))]
                for k, v in observations.items()
                if isinstance(v, list)
            }
        return reg


# ---------------------------------------------------------------------------
# T2-06④：早安/晚安兜底关键词识别
#
# 设计原打算读 sylanne_core 后台 assessor（_engine/sylanne_core/assessor.py）的
# greeting/farewell 分类 flag，但审计确认：插件的 EngineFacade
# （engine_adapter.py::EngineFacade.__init__）构造 SDK 引擎时 assessor_enabled
# 默认为 False，且全仓没有任何调用点把它覆盖为 True；插件运行时实际驱动
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


_RITUAL_REGISTRY_KV_KEY = "sylanne_ritual_registry_state"


# ---------------------------------------------------------------------------
# 关系年龄计算器（Item 125）
# ---------------------------------------------------------------------------

RELATIONSHIP_STAGES = {
    "infant": (0, 3),       # 0-3 天：初识
    "young": (3, 14),       # 3-14 天：熟悉中
    "mature": (14, 90),     # 14-90 天：稳定关系
    "deep": (90, float('inf')),  # 90 天+：深层关系
}


def get_relationship_stage(first_interaction: float) -> str:
    """根据首次交互时间计算关系阶段。

    Args:
        first_interaction: 首次交互的 Unix 时间戳（秒）。

    Returns:
        关系阶段名称：infant / young / mature / deep。
    """
    age_days = (time.time() - first_interaction) / 86400
    for stage, (low, high) in RELATIONSHIP_STAGES.items():
        if low <= age_days < high:
            return stage
    return "deep"


# ---------------------------------------------------------------------------
# 第一印象锚定系统（Item 141 / Item 142）
# ---------------------------------------------------------------------------


@dataclass
class FirstImpression:
    """首次对话的印象锚定数据。

    第一印象在关系早期具有极高权重，随时间缓慢衰减但永不完全消失。
    这模拟了人类心理学中的"首因效应"——初始印象对后续判断的持久影响。
    """

    valence: float  # 首次对话情绪基调 (-1 ~ 1)
    topic_type: str  # 话题类型（casual/deep/conflict/playful）
    user_style: str  # 用户风格（brief/verbose/emotional/factual）
    quality: float  # 互动质量 0-1
    timestamp: float = field(default_factory=time.time)

    def anchor_weight(self, relationship_age_days: float) -> float:
        """锚定权重：前7天不衰减，7-30天缓慢衰减，30天后稳定在15-25%。

        Args:
            relationship_age_days: 关系年龄（天）。

        Returns:
            锚定权重，范围 0.15-1.0。
        """
        if relationship_age_days < 7:
            return 1.0
        elif relationship_age_days < 30:
            decay = (relationship_age_days - 7) / 23
            return 1.0 - decay * 0.75  # 1.0 → 0.25
        else:
            return 0.15 + self.quality * 0.1  # 15-25% 残留

    def to_dict(self) -> dict:
        """序列化为字典。"""
        return {
            "valence": self.valence,
            "topic_type": self.topic_type,
            "user_style": self.user_style,
            "quality": self.quality,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FirstImpression":
        """从字典恢复。"""
        return cls(
            valence=float(data.get("valence", 0.0)),
            topic_type=str(data.get("topic_type", "casual")),
            user_style=str(data.get("user_style", "brief")),
            quality=max(0.0, min(1.0, float(data.get("quality", 0.5)))),
            timestamp=float(data.get("timestamp", 0.0) or time.time()),
        )


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
            self.buffer = self.buffer[-self._MAX_ITEMS:]

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
        recent = self.buffer[-self._SUMMARY_COUNT:]
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
            violations.append(
                f"kernel 实例共享违规: id={kid:#x}, 涉及会话: {sessions}"
            )

    for mid, sessions in memory_ids.items():
        if len(sessions) > 1:
            violations.append(
                f"memory_system 实例共享违规: id={mid:#x}, 涉及会话: {sessions}"
            )

    return violations


class SessionContext:
    """封装 Sylanne 插件的会话管理逻辑。

    作为插件实例的委托层，将会话相关的复杂逻辑（key 派生、锁管理、
    host 生命周期、记忆系统初始化）从主插件类中解耦出来。
    """

    def __init__(self, plugin: PluginHost) -> None:
        """初始化会话上下文。

        Args:
            plugin: Sylanne 插件实例，通过 self._p 访问其内部状态。
        """
        self._p = plugin
        # 关系年龄追踪：session_key → 首次交互时间戳
        self._first_interaction_times: dict[str, float] = {}
        # Item 103: 设备指纹追踪：session_key → 上次 User-Agent
        self._device_fingerprints: dict[str, str] = {}
        # 第一印象锚定：session_key → FirstImpression
        self._first_impressions: dict[str, FirstImpression] = {}
        # Item 153: 关系仪式注册表
        self._ritual_registry = RitualRegistry()

    # ------------------------------------------------------------------
    # 关系年龄（Item 125 / Item 130）
    # ------------------------------------------------------------------

    def first_interaction_time(self, session_key: str) -> float:
        """获取指定会话的首次交互时间戳。

        如果尚未记录，以当前时间作为首次交互时间。

        Args:
            session_key: 会话标识。

        Returns:
            首次交互的 Unix 时间戳（秒）。
        """
        if session_key not in self._first_interaction_times:
            self._first_interaction_times[session_key] = time.time()
        return self._first_interaction_times[session_key]

    def set_first_interaction_time(self, session_key: str, ts: float) -> None:
        """显式设置首次交互时间（用于从持久化数据恢复）。

        Args:
            session_key: 会话标识。
            ts: Unix 时间戳（秒）。
        """
        self._first_interaction_times[session_key] = ts

    def relationship_stage(self, session_key: str) -> str:
        """获取指定会话的关系阶段。

        Args:
            session_key: 会话标识。

        Returns:
            关系阶段名称：infant / young / mature / deep。
        """
        return get_relationship_stage(self.first_interaction_time(session_key))

    def accelerate_relationship(self, session_key: str, intensity: float) -> None:
        """高强度互动加速关系年龄。

        每次高强度互动等效于 intensity * 24 小时的关系积累（最多 1 天）。
        通过回拨 first_interaction_time 实现，但不会超过真实首次交互前 30 天。

        Args:
            session_key: 会话标识。
            intensity: 互动强度，范围 0-1。
        """
        intensity = max(0.0, min(1.0, intensity))
        acceleration_hours = intensity * 24  # 最多等效 1 天
        # 确保 first_interaction_time 已初始化
        real_first = self.first_interaction_time(session_key)
        # 下界：不早于真实首次交互前 30 天
        floor = real_first - 30 * 86400
        new_time = self._first_interaction_times[session_key] - acceleration_hours * 3600
        self._first_interaction_times[session_key] = max(floor, new_time)

    # ------------------------------------------------------------------
    # Item 103: 设备切换感知问候
    # ------------------------------------------------------------------

    def detect_device_change(self, session_key: str, current_ua: str) -> str | None:
        """检测 User-Agent 变化，返回适配问候或 None。

        Args:
            session_key: 会话标识。
            current_ua: 当前请求的 User-Agent 字符串。

        Returns:
            设备切换问候语，或 None（无变化时）。
        """
        last_ua = self._device_fingerprints.get(session_key, "")
        self._device_fingerprints[session_key] = current_ua
        if not last_ua or last_ua == current_ua:
            return None
        # 简单判断：mobile vs desktop
        is_mobile = any(k in current_ua.lower() for k in ("mobile", "android", "iphone"))
        was_mobile = any(k in last_ua.lower() for k in ("mobile", "android", "iphone"))
        if is_mobile and not was_mobile:
            return "换到手机了？我简短些。"
        elif not is_mobile and was_mobile:
            return "回到电脑了，可以聊详细点。"
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
        """记录首次对话的第一印象。

        仅在该 session 尚无第一印象时记录（不可覆盖）。

        Args:
            session_key: 会话标识。
            valence: 情绪基调 (-1 ~ 1)。
            topic_type: 话题类型（casual/deep/conflict/playful）。
            user_style: 用户风格（brief/verbose/emotional/factual）。
            quality: 互动质量 0-1。
        """
        if session_key in self._first_impressions:
            return  # 第一印象不可覆盖
        self._first_impressions[session_key] = FirstImpression(
            valence=max(-1.0, min(1.0, valence)),
            topic_type=topic_type,
            user_style=user_style,
            quality=max(0.0, min(1.0, quality)),
        )

    def get_impression_anchor(self, session_key: str) -> tuple[FirstImpression | None, float]:
        """获取第一印象及其当前锚定权重。

        Args:
            session_key: 会话标识。

        Returns:
            (FirstImpression, anchor_weight) 元组。
            如果无第一印象记录，返回 (None, 0.0)。
        """
        impression = self._first_impressions.get(session_key)
        if impression is None:
            return (None, 0.0)
        first_ts = self.first_interaction_time(session_key)
        age_days = (time.time() - first_ts) / 86400
        return (impression, impression.anchor_weight(age_days))

    # ------------------------------------------------------------------
    # Session key 派生
    # ------------------------------------------------------------------

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
        if session_key:
            return session_key
        if event is not None:
            base = str(
                getattr(event, "session_id", "")
                or getattr(event, "unified_msg_origin", "")
                or "default"
            )
            # 群聊中追加 sender_id，使每个用户拥有独立的 host/kernel/计算脊柱
            sender_id = str(
                getattr(event, "sender_id", "") or getattr(event, "user_id", "") or ""
            )
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
        cache = getattr(self._p, "_safe_session_key_cache", None)
        if cache is None:
            self._p._safe_session_key_cache = {}
            cache = self._p._safe_session_key_cache
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

    def resolve_public_session_key(
        self, event: Any = None, *, request: Any = None, session_key: str = ""
    ) -> str:
        """解析公共会话标识，用于 WebUI 等外部接口。

        与 session_key() 不同，此方法不追加 sender_id，返回的是
        "公共"级别的会话标识（如群聊的 unified_msg_origin）。

        Args:
            event: 事件对象或字符串。
            request: 请求对象（备选来源）。
            session_key: 显式指定的会话键。

        Returns:
            公共会话标识，无法确定时返回 "global"。
        """
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
    # Item 153 / T2-06：关系仪式注册表——观察 + 接线到 ProactiveScheduler
    # ------------------------------------------------------------------

    def observe_ritual_pattern(self, session_key: str, hour: int, pattern: str) -> None:
        """观察到重复问候/告别模式时喂给 RitualRegistry。

        一旦 RitualRegistry 侧自动注册（≥3 次观测），同步登记进
        ProactiveScheduler 自己的仪式表（scheduler.register_ritual）——此前
        RitualRegistry 只是个孤立记录，没有任何调用方把它接到调度器的
        check_ritual_absence，reason_code='ritual' 因此从未真正可达
        （T2-06 审计发现的缺口）。命中即落盘（观测频率天然低，无需节流）。

        Args:
            session_key: 会话标识。
            hour: 当前小时（0-23）。
            pattern: 行为模式描述（如 "morning_greeting"、"night_farewell"）。
        """
        self._ritual_registry.observe_pattern(session_key, hour, pattern)
        ritual = self._ritual_registry.get_ritual(session_key, pattern)
        if not ritual:
            return
        scheduler = getattr(self._p, "_proactive_scheduler", None)
        register = getattr(scheduler, "register_ritual", None) if scheduler is not None else None
        if callable(register):
            try:
                register(
                    session_key,
                    str(ritual.get("pattern", pattern)),
                    int(ritual.get("hour_start", hour)),
                    int(ritual.get("hour_end", (hour + 1) % 24)),
                )
            except Exception as e:
                logger.debug(f"Sylanne ritual register_ritual skipped: {e}")
        if hasattr(self._p, "_has_kv_api") and self._p._has_kv_api():
            try:
                from sylanne_alpha.utils import safe_ensure_future

                safe_ensure_future(
                    self._p.put_kv_data(
                        _RITUAL_REGISTRY_KV_KEY, self._ritual_registry.to_dict()
                    ),
                    name=f"ritual_registry_save_{session_key}",
                )
            except Exception as e:
                logger.debug(f"Sylanne ritual registry save skipped: {e}")

    def detect_and_observe_ritual_from_text(
        self, session_key: str, text: str, now: float | None = None
    ) -> None:
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
        self.observe_ritual_pattern(session_key, hour, pattern)

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
        if not session_key:
            session_key = "default"
        systems = self._p._store.memory_systems
        if not systems.has(session_key):
            # 召回引擎灰度模式：插件配置 sylanne_alpha_recall_mode 优先，
            # 缺省时 MemorySystem 内部会回退到环境变量 SYLANNE_RECALL_MODE / LEGACY。
            cfg = getattr(self._p, "config", None) or {}
            recall_mode = cfg.get("sylanne_alpha_recall_mode") or None
            systems.set(session_key, MemorySystem(recall_mode=recall_mode))
            self._schedule_memory_hydration(session_key)
        return systems.get(session_key)

    def _schedule_memory_hydration(self, session_key: str) -> None:
        """MEM-02①：懒创建 MemorySystem 后台补水的调度点（幂等，失败静默降级）。

        `StatePersistence.hydrate_memory_system` 自己会检查 `_hydrated` 标记，
        重复调度（例如同一 session 短时间内多次懒创建，理论上不该发生但防御一下）
        不会重复合并——第二次进去时活体已经 `_hydrated=True`，直接 no-op 返回。
        """
        state_persistence = getattr(self._p, "_state_persistence", None)
        hydrate = getattr(state_persistence, "hydrate_memory_system", None)
        if not callable(hydrate):
            return
        try:
            from sylanne_alpha.utils import safe_ensure_future

            safe_ensure_future(
                hydrate(session_key),
                name=f"memory_hydrate_{session_key}",
                task_list=getattr(self._p, "_background_tasks", None),
            )
        except Exception as e:
            logger.debug(f"Sylanne memory hydration scheduling skipped: {e}")

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
                temperature = float(
                    trace.get("temperature", trace.get("warmth", 0.5)) or 0.5
                )
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
                    item.weight = max(
                        0.0, min(1.0, float(trace.get("weight", 1.0) or 1.0))
                    )
                except (TypeError, ValueError):
                    item.weight = 1.0
                try:
                    created_at = float(
                        trace.get("created_at", trace.get("updated_at", 0.0)) or 0.0
                    )
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
        sessions: list[str] = []

        def add(value: Any) -> None:
            text = str(value or "").strip()
            if text and text not in sessions:
                sessions.append(text)

        add(requested)
        for key in getattr(self._p, "_hosts", {}).keys():
            add(key)
        for key in getattr(self._p, "_memory_systems", {}).keys():
            add(key)
        cache = getattr(self._p, "_sylanne_memory_cache", {}) or {}
        if isinstance(cache, dict):
            for key in cache.keys():
                add(key)
        # 从 runtime 导出中提取持久化过的 session
        for host in list(getattr(self._p, "_hosts", {}).values()):
            runtime = getattr(host, "runtime", None)
            export_all = getattr(runtime, "export_all", None)
            if not callable(export_all):
                continue
            try:
                exported = export_all()
            except Exception:
                continue
            persisted = (
                exported.get("sessions", {}) if isinstance(exported, dict) else {}
            )
            if isinstance(persisted, dict):
                for key in persisted.keys():
                    add(key)
        # 从磁盘文件名中提取 session key
        try:
            cfg = getattr(self._p, "config", {}) or {}
            root = Path(resolve_data_root(cfg))
            if root.exists():
                for path in root.glob("*.alpha.json"):
                    add(path.name[: -len(".alpha.json")])
        except Exception as e:
            logger.debug(f"Sylanne skip: {e}")
        if not sessions:
            add("default")
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
        if not session_key:
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
                    self._p._state_persistence.persist_kernel(oldest_key, old_host),
                    name=f"lru_evict_{oldest_key}",
                )
                # CP8-P6：驱逐前先把进化档案落盘（否则未巩固的反射/反思偏置随驱逐丢失），
                # 再清进化层 per-session 状态。尤其 _restored 守卫必须清——否则同 key
                # 后续重建时不会再从 KV 恢复，已落盘学习成果静默丢失。
                self._persist_and_forget_evolution(oldest_key)
            cfg = (
                self._p.config
                if hasattr(self._p, "_config")
                else getattr(self._p, "config", {}) or {}
            )
            root = resolve_data_root(cfg)
            host = SylanneAlphaHost(root=root, session_key=session_key)
            # 编码器共享：避免每个 host 各持有一份 encoder 浪费内存。
            # 仅旧 ComputationSpine 暴露 encoder/replace_encoder；SDK 共振场
            # （ResonanceSpine）架构不同、无此属性，跳过共享（其编码自管）。
            comp = getattr(host.kernel, "computation", None)
            if comp is not None and hasattr(comp, "encoder") and hasattr(comp, "replace_encoder"):
                plugin_cls = type(self._p)
                if plugin_cls._shared_encoder is None:
                    plugin_cls._shared_encoder = comp.encoder
                else:
                    comp.replace_encoder(plugin_cls._shared_encoder)
            # 从人格状态派生记忆系统参数（人格驱动全参数）
            personality = (
                host.kernel._personality()
                if hasattr(host.kernel, "_personality")
                else {}
            )
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
                if self.memory_system_has_content(memory_system):
                    host.kernel.body.memory["_memory_system"] = memory_system.to_dict()
                    from sylanne_alpha.utils import safe_ensure_future
                    safe_ensure_future(
                        self._p._state_persistence.persist_kernel(session_key, host),
                        name=f"hydrate_persist_{session_key}",
                    )
            hosts.set(session_key, host)
            # 恢复对话缓冲区（文件回退；KV 保持同步）
            if not self._p._store.conversation_buffers.has(session_key):
                buf_data = host.runtime.load_buffer(session_key)
                if buf_data and isinstance(buf_data, dict):
                    self._p._store.conversation_buffers.set(
                        session_key, ConversationBuffer.from_dict(buf_data)
                    )
        else:
            # 已存在：重新写入以刷新 LRU 顺序（set→__setitem__ 会 move_to_end）
            host = existing_host
            hosts.set(session_key, host)
        return host

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
            session_key = "default"
        buffers = getattr(self._p, "_offline_buffers", None)
        if buffers is None:
            self._p._offline_buffers = {}
            buffers = self._p._offline_buffers
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


# ---------------------------------------------------------------------------
# Item 105: 用户画像长期演化追踪
# ---------------------------------------------------------------------------


class ProfileEvolution:
    """用户画像长期演化追踪：每周快照兴趣/情感基线/互动模式。"""

    def __init__(self, max_snapshots: int = 52) -> None:  # 最多保留一年
        self._snapshots: list[dict] = []
        self._max = max_snapshots

    def take_snapshot(
        self,
        session_key: str,
        interests: list[str],
        emotional_baseline: float,
        interaction_frequency: float,
    ) -> None:
        self._snapshots.append(
            {
                "timestamp": time.time(),
                "session_key": session_key,
                "interests": interests[:10],
                "emotional_baseline": emotional_baseline,
                "interaction_frequency": interaction_frequency,
            }
        )
        if len(self._snapshots) > self._max:
            self._snapshots.pop(0)

    def diff_profile(self, weeks_ago_a: int, weeks_ago_b: int) -> dict | None:
        """比较两个时间点的画像差异。"""
        now = time.time()
        snap_a = self._find_nearest(now - weeks_ago_a * 7 * 86400)
        snap_b = self._find_nearest(now - weeks_ago_b * 7 * 86400)
        if not snap_a or not snap_b:
            return None
        return {
            "emotional_shift": snap_b["emotional_baseline"] - snap_a["emotional_baseline"],
            "frequency_shift": snap_b["interaction_frequency"] - snap_a["interaction_frequency"],
            "new_interests": [i for i in snap_b["interests"] if i not in snap_a["interests"]],
            "lost_interests": [i for i in snap_a["interests"] if i not in snap_b["interests"]],
        }

    def _find_nearest(self, target_time: float) -> dict | None:
        if not self._snapshots:
            return None
        return min(self._snapshots, key=lambda s: abs(s["timestamp"] - target_time))

    def to_dict(self) -> list[dict]:
        return list(self._snapshots)

    @classmethod
    def from_dict(cls, data: list[dict]) -> "ProfileEvolution":
        pe = cls()
        pe._snapshots = data
        return pe


# ---------------------------------------------------------------------------
# 时区感知与作息推断
# ---------------------------------------------------------------------------


def infer_active_hours(timestamps: list[float]) -> tuple[int, int]:
    """根据历史消息时间戳拟合用户活跃窗口。

    算法：
    1. 将所有时间戳按小时分桶（0-23），统计每小时的消息数
    2. 找到消息数最多的连续活跃时段（允许跨午夜）
    3. 活跃时段定义为：包含总消息量 ≥ 70% 的最短连续小时区间

    参数:
        timestamps: Unix 时间戳列表（秒级）

    返回:
        (start_hour, end_hour) 元组，表示用户活跃窗口。
        start_hour 和 end_hour 均为 0-23 的整数。
        如果 start_hour > end_hour，表示跨午夜（如 22:00 - 06:00）。
        时间戳不足时返回默认值 (8, 23)。
    """
    if not timestamps or len(timestamps) < 3:
        return (8, 23)

    # 按小时分桶
    buckets = [0] * 24
    for ts in timestamps:
        try:
            hour = time.localtime(ts).tm_hour
            buckets[hour] += 1
        except (OSError, ValueError, OverflowError):
            continue

    total = sum(buckets)
    if total == 0:
        return (8, 23)

    # 找到包含 ≥ 70% 消息量的最短连续窗口
    threshold = total * 0.7
    best_start = 0
    best_length = 24  # 最差情况：全天

    for window_len in range(1, 25):
        for start in range(24):
            count = 0
            for offset in range(window_len):
                count += buckets[(start + offset) % 24]
            if count >= threshold and window_len < best_length:
                best_start = start
                best_length = window_len
        # 一旦找到满足阈值的最短窗口就停止
        if best_length <= window_len:
            break

    start_hour = best_start
    end_hour = (best_start + best_length - 1) % 24
    return (start_hour, end_hour)


# ---------------------------------------------------------------------------
# Item 63: 新手 30 天成长日志
# ---------------------------------------------------------------------------


class GrowthJournal:
    """新手 30 天成长日志：每日生成 Sylanne 变化摘要。

    在关系早期（infant/young 阶段），每天记录一条 Sylanne 的变化摘要，
    帮助用户感知 AI 伙伴的"成长"过程。支持序列化/反序列化以持久化。
    """

    def __init__(self) -> None:
        self._entries: dict[str, str] = {}  # "2026-05-28" -> "今天人格漂移了..."

    def record_daily(self, date_str: str, summary: str) -> None:
        """记录某天的成长摘要。

        Args:
            date_str: ISO 格式日期字符串，如 "2026-05-28"。
            summary: 当天的变化摘要文本。
        """
        self._entries[date_str] = summary

    def get_recent(self, days: int = 7) -> list[dict]:
        """获取最近 N 天的成长记录。

        Args:
            days: 回溯天数，默认 7。

        Returns:
            按日期倒序排列的记录列表，每条包含 date 和 summary。
        """
        import datetime

        today = datetime.date.today()
        results = []
        for i in range(days):
            d = (today - datetime.timedelta(days=i)).isoformat()
            if d in self._entries:
                results.append({"date": d, "summary": self._entries[d]})
        return results

    def to_dict(self) -> dict:
        """序列化为字典。"""
        return dict(self._entries)

    @classmethod
    def from_dict(cls, data: dict) -> "GrowthJournal":
        """从字典恢复。"""
        gj = cls()
        gj._entries = dict(data) if isinstance(data, dict) else {}
        return gj


# ---------------------------------------------------------------------------
# Item 108: 跨设备偏好继承与覆盖
# ---------------------------------------------------------------------------


class DeviceOverrides:
    """跨设备偏好覆盖层。

    允许为不同设备类型（mobile/desktop/tablet 等）设置独立的偏好覆盖值。
    查询时优先返回设备特定值，无覆盖时回退到基础值。

    典型用途：
    - 手机端使用更短的回复长度
    - 桌面端启用更详细的诊断信息
    - 平板端调整字体大小偏好
    """

    def __init__(self) -> None:
        self._overrides: dict[str, dict[str, Any]] = {}  # device_type -> {key: value}

    def set_override(self, device_type: str, key: str, value: Any) -> None:
        """为指定设备类型设置偏好覆盖。

        Args:
            device_type: 设备类型标识（如 "mobile"、"desktop"）。
            key: 偏好键名。
            value: 覆盖值。
        """
        if device_type not in self._overrides:
            self._overrides[device_type] = {}
        self._overrides[device_type][key] = value

    def get(self, device_type: str, key: str, default: Any = None) -> Any:
        """获取指定设备类型的偏好值。

        Args:
            device_type: 设备类型标识。
            key: 偏好键名。
            default: 无覆盖时的默认值。

        Returns:
            覆盖值，或 default。
        """
        return self._overrides.get(device_type, {}).get(key, default)

    def effective_value(self, device_type: str, key: str, base_value: Any) -> Any:
        """获取有效值：设备覆盖 > 基础值。

        Args:
            device_type: 设备类型标识。
            key: 偏好键名。
            base_value: 无覆盖时使用的基础值。

        Returns:
            设备覆盖值（如果存在且非 None），否则 base_value。
        """
        override = self.get(device_type, key)
        return override if override is not None else base_value
