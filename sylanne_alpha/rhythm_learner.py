"""Sylanne-Embodiment: 自适应节奏同步——刻意的双向步调调整。

真实关系中不存在被动镜像——双方都在刻意调整。
频率更高的一方在被忽略时会感到失落，刻意放慢
（同时语调也会变差），压力在沉默中积累直到爆发。

来自用户研究的关键洞察：
- 同步是刻意的（DELIBERATE），不是无意识的
- 更快的一方在被忽略时会放慢，且语调同步变差（耦合变化）
- 频率变化伴随语调变化（耦合的，不是解耦的）
- 长期频率不匹配会累积为虚空压力

与其他组件的关系：
- 被 body.py 在每条用户消息时调用 observe_user_message()
- get_rhythm_params() 输出供消息分段器使用
- 通过 engine_observation 与情感引擎耦合（亲密度门控）
"""

from __future__ import annotations

from collections import deque
from statistics import median
from typing import Any

_MAX_SAMPLES = 60  # 最大采样数
_MIN_SAMPLES_FOR_PROFILE = 8  # 生成有效画像所需的最少采样数
_DEFAULT_CHARS_PER_SECOND = 7.5  # 默认打字速度（字符/秒）
_DEFAULT_MAX_PART_CHARS = 48  # 默认单条消息最大字符数


class RhythmProfile:
    """从单个用户学习到的节奏特征画像。

    追踪用户的消息长度分布和消息间隔分布，
    从中推导出用户的"打字速度"和"偏好消息长度"。
    只有采样数足够时（≥8）才产生有效画像。
    """

    __slots__ = (
        "_msg_lengths",
        "_inter_msg_gaps",
        "_last_msg_time",
        "_chars_per_second",
        "_avg_part_chars",
        "_confidence",
    )

    def __init__(self):
        self._msg_lengths: deque[int] = deque(maxlen=_MAX_SAMPLES)  # 消息长度样本
        self._inter_msg_gaps: deque[float] = deque(maxlen=_MAX_SAMPLES)  # 消息间隔样本
        self._last_msg_time: float = 0.0  # 上条消息时间戳
        self._chars_per_second: float = _DEFAULT_CHARS_PER_SECOND  # 推断的打字速度
        self._avg_part_chars: float = _DEFAULT_MAX_PART_CHARS  # 推断的偏好消息长度
        self._confidence: float = 0.0  # 画像置信度 [0,1]

    def observe(self, text: str, timestamp: float) -> None:
        """记录一条用户消息，更新节奏画像。"""
        length = len(text.strip())
        if length < 1:
            return
        self._msg_lengths.append(length)

        if self._last_msg_time > 0 and timestamp > self._last_msg_time:
            gap = timestamp - self._last_msg_time
            if 0.3 < gap < 120.0:
                self._inter_msg_gaps.append(gap)
        self._last_msg_time = timestamp

        self._recompute()

    def _recompute(self) -> None:
        """重新计算画像参数（置信度、偏好长度、打字速度）。"""
        n = len(self._msg_lengths)
        if n < _MIN_SAMPLES_FOR_PROFILE:
            self._confidence = 0.0
            return

        # 置信度随采样数线性增长
        self._confidence = min(
            1.0,
            (n - _MIN_SAMPLES_FOR_PROFILE) / (_MAX_SAMPLES - _MIN_SAMPLES_FOR_PROFILE),
        )

        # 偏好消息长度：取中位数（比均值更抗噪声）
        sorted_lengths = sorted(self._msg_lengths)
        p50_idx = len(sorted_lengths) // 2
        self._avg_part_chars = float(sorted_lengths[p50_idx])

        # 打字速度：中位长度 / 中位间隔
        if len(self._inter_msg_gaps) >= 3:
            sorted_gaps = sorted(self._inter_msg_gaps)
            median_gap = sorted_gaps[len(sorted_gaps) // 2]
            median_len = self._avg_part_chars
            if median_gap > 0.1:
                self._chars_per_second = max(2.0, min(20.0, median_len / median_gap))

    @property
    def confidence(self) -> float:
        return self._confidence

    @property
    def avg_part_chars(self) -> float:
        return self._avg_part_chars

    @property
    def chars_per_second(self) -> float:
        return self._chars_per_second

    def modulate(
        self, default_max_part: int, default_cps: float, blend: float
    ) -> tuple[int, float]:
        """返回混合后的 (max_part_chars, chars_per_second)。

        参数:
            default_max_part: 默认最大分段字符数
            default_cps: 默认打字速度
            blend: 混合比例，0.0=纯默认，1.0=纯用户节奏

        实际混合比例还会乘以置信度（采样不足时不生效）。
        """
        effective_blend = blend * self._confidence
        if effective_blend < 0.05:
            return default_max_part, default_cps

        learned_part = max(12, min(120, int(self._avg_part_chars)))
        learned_cps = self._chars_per_second

        blended_part = int(
            default_max_part * (1 - effective_blend) + learned_part * effective_blend
        )
        blended_cps = (
            default_cps * (1 - effective_blend) + learned_cps * effective_blend
        )

        return max(12, min(120, blended_part)), max(2.0, min(20.0, blended_cps))

    def to_dict(self) -> dict[str, Any]:
        """序列化画像状态。"""
        return {
            "msg_lengths": list(self._msg_lengths),
            "inter_msg_gaps": list(self._inter_msg_gaps),
            "last_msg_time": self._last_msg_time,
            "chars_per_second": self._chars_per_second,
            "avg_part_chars": self._avg_part_chars,
            "confidence": self._confidence,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RhythmProfile":
        """从字典恢复画像。"""
        p = cls()
        for v in data.get("msg_lengths", []):
            p._msg_lengths.append(int(v))
        for v in data.get("inter_msg_gaps", []):
            p._inter_msg_gaps.append(float(v))
        p._last_msg_time = float(data.get("last_msg_time", 0.0))
        p._chars_per_second = float(
            data.get("chars_per_second", _DEFAULT_CHARS_PER_SECOND)
        )
        p._avg_part_chars = float(data.get("avg_part_chars", _DEFAULT_MAX_PART_CHARS))
        p._confidence = float(data.get("confidence", 0.0))
        return p


class RhythmLearner:
    """按会话的节奏学习器，带亲密度门控。

    只有当关系达到足够亲密度时才开始学习用户节奏——
    这是"刻意同步"的体现：不是对所有人都调整，
    而是对亲密的人才愿意调整自己的节奏。

    与其他组件的关系：
    - 被 body.py 在每条用户消息时调用
    - 亲密度判断依赖情感引擎的 observation
    - 输出的节奏参数供消息分段器使用
    """

    __slots__ = (
        "_profiles",
        "_intimacy_threshold",
        "_default_blend",
        "_tempo_timestamps",
        "_last_tempo",
        "_tempo_shift",
    )

    def __init__(self, intimacy_threshold: float = 0.6):
        self._profiles: dict[str, RhythmProfile] = {}  # session_key → 节奏画像
        self._intimacy_threshold = intimacy_threshold  # 开始学习的亲密度阈值
        self._default_blend = 0.6  # 默认混合比例
        self._tempo_timestamps: dict[str, deque] = {}  # session_key → 时间戳窗口
        self._last_tempo: dict[str, float] = {}  # session_key → 上次 tempo
        self._tempo_shift: dict[str, bool] = {}  # session_key → 是否突变

    def set_personality_params(self, intimacy_threshold: float, blend_rate: float):
        """设置人格驱动的节奏学习参数。"""
        self._intimacy_threshold = intimacy_threshold
        self._default_blend = blend_rate

    def is_intimate(self, engine_observation: dict[str, float]) -> bool:
        """判断当前关系状态是否达到高亲密度（门控条件）。"""
        warmth = engine_observation.get("warmth", 0.0)
        coherence = engine_observation.get("coherence", 1.0)
        tension = engine_observation.get("tension", 0.0)
        combined = warmth * 0.5 + coherence * 0.3 + (1.0 - tension) * 0.2
        return combined >= self._intimacy_threshold

    def observe_user_message(
        self,
        session_key: str,
        text: str,
        timestamp: float,
        engine_observation: dict[str, float],
    ) -> None:
        """观察一条用户消息。只有亲密度足够时才学习。"""
        # 始终记录 tempo（不受亲密度门控）
        self._record_tempo(session_key, timestamp)

        if not self.is_intimate(engine_observation):
            return
        if session_key not in self._profiles:
            if len(self._profiles) >= 200:
                oldest_key = next(iter(self._profiles))
                del self._profiles[oldest_key]
            self._profiles[session_key] = RhythmProfile()
        self._profiles[session_key].observe(text, timestamp)

    def observe_voice_message(
        self,
        session_key: str,
        duration_seconds: float,
    ) -> None:
        """观察一条语音消息，按时长换算为等效字符数后记录。

        语音消息按 1 秒 ≈ 5 个字符的信息量换算，
        生成等效文本长度后调用 observe_user_message 的核心逻辑更新节奏画像。

        Args:
            session_key: 会话标识。
            duration_seconds: 语音消息时长（秒）。
        """
        if duration_seconds <= 0:
            return
        # 1 秒 ≈ 5 个字符的信息量
        equivalent_chars = int(duration_seconds * 5)
        # 直接更新 RhythmProfile 的 _msg_lengths（绕过亲密度门控和 tempo 记录，
        # 因为语音消息的节奏适配是独立于文本消息的补充数据源）
        if session_key not in self._profiles:
            if len(self._profiles) >= 200:
                oldest_key = next(iter(self._profiles))
                del self._profiles[oldest_key]
            self._profiles[session_key] = RhythmProfile()
        profile = self._profiles[session_key]
        # 将等效字符数追加到消息长度列表
        if equivalent_chars >= 1:
            profile._msg_lengths.append(equivalent_chars)
            profile._recompute()

    def get_rhythm_params(
        self,
        session_key: str,
        default_max_part: int = 48,
        default_cps: float = 7.5,
        blend: float = 0.6,
        expression_drive: float = 0.5,
        recent_ignored_rate: float = 0.0,
    ) -> tuple[int, float]:
        """获取调制后的分段参数——刻意同步。

        与被动学习不同，这是一个有意识的决策：
        - 高 expression_drive → 主动加速向用户节奏靠拢
        - 高 ignored_rate → 刻意放慢（退缩）
        - blend 被驱力（想同步）和退缩（被忽略）共同调制

        参数:
            session_key: 会话标识
            default_max_part: 默认最大分段字符数
            default_cps: 默认打字速度
            blend: 基础混合比例
            expression_drive: 表达驱力（来自人格系统）
            recent_ignored_rate: 近期被忽略率

        返回:
            (max_part_chars, chars_per_second) 元组
        """
        profile = self._profiles.get(session_key)
        if profile is None or profile.confidence < 0.1:
            return default_max_part, default_cps

        # 刻意调整：驱力推向同步，被忽略则退缩
        drive_factor = min(1.0, expression_drive * 1.5)
        withdrawal_factor = min(0.8, recent_ignored_rate * 2.0)

        # 净同步意图：正值=想同步，负值=在退缩
        sync_intent = drive_factor - withdrawal_factor
        effective_blend = max(0.0, blend * profile.confidence * max(0.1, sync_intent))

        if effective_blend < 0.05:
            # 退缩模式：使用比默认更慢的节奏
            slowdown = 1.0 + withdrawal_factor * 0.5
            return int(default_max_part * slowdown), default_cps / slowdown

        learned_part = max(12, min(120, int(profile.avg_part_chars)))
        learned_cps = profile.chars_per_second

        blended_part = int(
            default_max_part * (1 - effective_blend) + learned_part * effective_blend
        )
        blended_cps = (
            default_cps * (1 - effective_blend) + learned_cps * effective_blend
        )

        return max(12, min(120, blended_part)), max(2.0, min(20.0, blended_cps))

    def profile(self, session_key: str) -> RhythmProfile | None:
        return self._profiles.get(session_key)

    # ------------------------------------------------------------------
    # Item 79: 回复长度自适应控制器
    # ------------------------------------------------------------------

    def get_reply_length_factor(self, session_key: str) -> float:
        """统计用户近 20 条消息的平均字符长度，返回回复长度倍率因子。

        规则：
        - 用户消息短（<30 字）→ 0.7（回复精炼）
        - 用户消息长（>200 字）→ 1.5（回复详尽）
        - 中间线性插值，最终 clamp 到 [0.5, 2.0]
        """
        profile = self._profiles.get(session_key)
        if profile is None or len(profile._msg_lengths) == 0:
            return 1.0

        # 取最近 20 条
        recent = list(profile._msg_lengths)[-20:]
        avg_len = sum(recent) / len(recent)

        # 线性插值：30 → 0.7, 200 → 1.5
        if avg_len <= 30.0:
            factor = 0.7
        elif avg_len >= 200.0:
            factor = 1.5
        else:
            # 线性插值 [30, 200] → [0.7, 1.5]
            factor = 0.7 + (avg_len - 30.0) / (200.0 - 30.0) * (1.5 - 0.7)

        return max(0.5, min(2.0, factor))

    # ------------------------------------------------------------------
    # Item 122: 呼吸节奏的快慢时钟
    # ------------------------------------------------------------------

    def _record_tempo(self, session_key: str, timestamp: float) -> None:
        """记录一次交互时间戳并更新 tempo 状态。"""
        if session_key not in self._tempo_timestamps:
            self._tempo_timestamps[session_key] = deque(maxlen=300)
        self._tempo_timestamps[session_key].append(timestamp)
        new_tempo = self._session_tempo(session_key)
        last = self._last_tempo.get(session_key, 0.0)
        if last > 0.0 and new_tempo > 0.0:
            ratio = new_tempo / last
            self._tempo_shift[session_key] = ratio > 2.0 or ratio < 0.5
        else:
            self._tempo_shift[session_key] = False
        if new_tempo > 0.0:
            self._last_tempo[session_key] = new_tempo

    def _session_tempo(self, session_key: str) -> float:
        """指定会话最近 5 分钟内的交互频率（次/分钟）。"""
        timestamps = self._tempo_timestamps.get(session_key)
        if not timestamps:
            return 0.0
        now = timestamps[-1]
        window_start = now - 300.0
        count = sum(1 for t in timestamps if t >= window_start)
        if count <= 1:
            return 0.0
        earliest_in_window = min(t for t in timestamps if t >= window_start)
        span_minutes = (now - earliest_in_window) / 60.0
        if span_minutes < 0.01:
            return 0.0
        return count / span_minutes

    @property
    def tempo(self) -> float:
        """全局 tempo（兼容旧接口，返回最近活跃会话的 tempo）。"""
        if not self._last_tempo:
            return 0.0
        best_key = max(self._last_tempo, key=self._last_tempo.get)
        return self._session_tempo(best_key)

    def session_tempo(self, session_key: str) -> float:
        """获取指定会话的 tempo。"""
        return self._session_tempo(session_key)

    @property
    def tempo_shift(self) -> bool:
        """任一会话是否发生 tempo 突变（兼容旧接口）。"""
        return any(self._tempo_shift.values()) if self._tempo_shift else False

    def session_tempo_shift(self, session_key: str) -> bool:
        """指定会话是否发生 tempo 突变。"""
        return self._tempo_shift.get(session_key, False)

    # ------------------------------------------------------------------
    # Item 129: 对话呼吸的"屏息"检测
    # ------------------------------------------------------------------

    def detect_breath_hold(self, last_message_time: float, now: float, session_key: str = "") -> bool:
        """当用户停顿超过正常间隔 2 倍时返回 True。

        正常间隔从 tempo_clock 的历史中位数计算。
        如果历史数据不足（<2 条时间戳），返回 False。
        """
        timestamps = self._tempo_timestamps.get(session_key) if session_key else None
        if not timestamps:
            all_ts = [t for dq in self._tempo_timestamps.values() for t in dq]
            if len(all_ts) < 2:
                return False
            timestamps = sorted(all_ts)
        else:
            if len(timestamps) < 2:
                return False
            timestamps = sorted(timestamps)
        gaps = [
            timestamps[i + 1] - timestamps[i]
            for i in range(len(timestamps) - 1)
            if timestamps[i + 1] - timestamps[i] > 0.1
        ]
        if not gaps:
            return False

        normal_interval = median(gaps)
        current_gap = now - last_message_time
        return current_gap > normal_interval * 2.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "intimacy_threshold": self._intimacy_threshold,
            "profiles": {k: v.to_dict() for k, v in self._profiles.items()},
        }

    @classmethod
    def from_dict(
        cls, data: dict[str, Any], intimacy_threshold: float = 0.6
    ) -> "RhythmLearner":
        threshold = float(data.get("intimacy_threshold", intimacy_threshold))
        learner = cls(intimacy_threshold=threshold)
        profiles = data.get("profiles", data)
        for k, v in profiles.items():
            if k == "intimacy_threshold":
                continue
            if isinstance(v, dict):
                learner._profiles[k] = RhythmProfile.from_dict(v)
        return learner
