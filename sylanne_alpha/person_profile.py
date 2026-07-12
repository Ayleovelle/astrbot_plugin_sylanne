"""v2.5.0 跨群记忆：人格档案（PersonProfile）—— 旁挂人核 v2 的旁挂存储 (B)。

design: docs/architecture/v250-cross-group-memory-design.md §3（关系+人格）/ §4
（瞬时情绪 transient_affect）/ §8 B2（载入加固）/ B3（幂等播种）/ B4（基线不污染）。

**本模块本 slice（P0 slice 1）范围**：只有 `PersonProfile` dataclass + KV 读写 +
B2 载入加固 + 衰减纯函数（`decay_transient` / `decay_profile_transient`，可单元测，
不接任何持久化/播种调用点）。

**本 slice 明确不做**（留后续 slice，§8 B3/B4/B5 的落地接线）：
- 播种到 body（`apply_vector_delta`）——host 出生播种点本 slice 零改动。
- 关系计数 / Sylanne Six 的落盘合并（kernel 落盘钩子）——本 slice 零改动。
- purge 级联（B5）——`delete_sylanne_memory_state` 本 slice 零改动。
- `valence`/`arousal`/`tension`"只存不施加"的硬 assert（B5 第二段）——本 slice 连
  播种路径本身都不存在，无路径可 assert，留给接播种线的 slice 一并做。

键格式：`sylanne_person_profile:{platform}:{sender_id}`（platform 解析复用
`person_shelf.platform_from_umo`，同一套 UMO 首段规则，不重复定义）。
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field, replace
from typing import Any

try:
    from astrbot.api import logger  # type: ignore
except Exception:  # pragma: no cover
    logger = logging.getLogger("astrbot_plugin_sylanne")

# ---------------------------------------------------------------------------
# 合法取值集 / 归一目标（fail-closed）
# ---------------------------------------------------------------------------
_LEGAL_PHASES = frozenset({"low_signal", "forming_continuity", "active_continuity"})
_PHASE_FAILCLOSED = "low_signal"

# Sylanne Six trait 键名，逐字对齐 personality.py:37-42 / :706-711。
_SIX_TRAIT_KEYS = frozenset(
    {
        "warmth_bias",
        "edge",
        "curiosity",
        "patience",
        "intimacy_gravity",
        "sovereignty_guard",
    }
)

_KV_KEY_TEMPLATE = "sylanne_person_profile:{platform}:{sender_id}"

# warmth/volatility transient 的存储帽（design §4.3："|transient| 存储帽 ±0.3"）。
# 每一处"产出新 transient 值"的代码（载入 / EMA 混合 / 衰减）都要重新钳，不能只在
# 写入那一刻钳一次就假设后续计算维持不变量（§8 B2 明文）。
_TRANSIENT_STORAGE_CAP = 0.3

# 单次施加预算（design §4.1 "|delta| 硬帽 ±0.15"）。`last_applied_transient` 追踪的
# 是"已施加的净值"，语义上不应超过这个单次预算，载入时同样重新钳。
_APPLY_CAP = 0.15

# 衰减半衰期（design §4.2，量级是拍的，未经行为标定，shadow 期再定死）。
WARMTH_HALF_LIFE_SECONDS = 4 * 3600.0
VOLATILITY_HALF_LIFE_SECONDS = 90 * 60.0

# |transient| < eps 视为归零（design §4.2）。
_TRANSIENT_ZERO_EPS = 0.02


def _finite_float(value: Any, default: float) -> float:
    """载入侧消毒：转 float 失败或非有限（NaN/±inf）一律回落默认值。

    仿 archive.py:26 的 `_finite_float` 形态；design §8 B2 明令不许用 `_opt_float`
    （emotion.py:332，只挡 None、放行 NaN，会把档案永久钉在 warmth=0.0 最冷）。
    """
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    return v if math.isfinite(v) else default


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _finite_nonneg_int(value: Any, default: int = 0) -> int:
    try:
        v = int(value)
    except (TypeError, ValueError):
        return default
    return v if v >= 0 else default


def _normalize_phase(value: Any) -> str:
    sval = str(value) if value is not None else ""
    return sval if sval in _LEGAL_PHASES else _PHASE_FAILCLOSED


def _normalize_six_snapshot(value: Any) -> dict[str, float]:
    """只保留合法 trait 键名；值非有限则整键丢弃（不是归零——"没有这个 trait 的快照"
    比"这个 trait 快照是 0"更诚实，避免播种时把 0.0 当真实低值用）。合法值钳 [0,1]
    （personality.py 的 trait 计算值域）。
    """
    if not isinstance(value, dict):
        return {}
    out: dict[str, float] = {}
    for k, v in value.items():
        if k not in _SIX_TRAIT_KEYS:
            continue
        try:
            fv = float(v)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(fv):
            continue
        out[k] = _clamp(fv, 0.0, 1.0)
    return out


@dataclass(slots=True)
class PersonProfile:
    """某 (platform, sender_id) 的人格档案（KV 值的顶层形状）。

    分三块：
    - 关系四计数 + phase：镜像 body.py:519-530 `relationship_memory()` 的 signals 子集。
    - Sylanne Six 快照 + warmth 长期基线：镜像 personality.py 六个 trait 键名 +
      body.py:141 `temperature.warmth` 默认值。
    - `transient_affect`（§4.1）六字段 + B3 幂等播种锚 `last_applied_transient`。
    """

    # ---- 关系四计数 + phase ----
    preference_count: int = 0
    boundary_count: int = 0
    progress_count: int = 0
    repair_count: int = 0
    phase: str = "low_signal"

    # ---- Sylanne Six 快照 + warmth 长期基线 ----
    six_snapshot: dict[str, float] = field(default_factory=dict)
    warmth_baseline: float = 0.45

    # ---- transient_affect（§4.1）----
    warmth_transient: float = 0.0
    volatility_transient: float = 0.0
    valence: float = 0.0
    arousal: float = 0.0
    tension: float = 0.0
    last_interaction_ts: float | None = None

    # ---- B3 幂等播种锚 ----
    last_applied_transient: float = 0.0

    schema_ver: int = 1

    def __post_init__(self) -> None:
        self.preference_count = _finite_nonneg_int(self.preference_count, 0)
        self.boundary_count = _finite_nonneg_int(self.boundary_count, 0)
        self.progress_count = _finite_nonneg_int(self.progress_count, 0)
        self.repair_count = _finite_nonneg_int(self.repair_count, 0)
        self.phase = _normalize_phase(self.phase)

        self.six_snapshot = _normalize_six_snapshot(self.six_snapshot)
        self.warmth_baseline = _clamp(_finite_float(self.warmth_baseline, 0.45), 0.0, 1.0)

        self.warmth_transient = _clamp(
            _finite_float(self.warmth_transient, 0.0),
            -_TRANSIENT_STORAGE_CAP,
            _TRANSIENT_STORAGE_CAP,
        )
        self.volatility_transient = _clamp(
            _finite_float(self.volatility_transient, 0.0),
            -_TRANSIENT_STORAGE_CAP,
            _TRANSIENT_STORAGE_CAP,
        )
        # valence/arousal/tension：本期"只存不施加"（§4.4），未定义存储帽，只做
        # 非有限性消毒，不额外夹紧数值域（避免臆造一个 2.6.0 E 核尚未定义的边界）。
        self.valence = _finite_float(self.valence, 0.0)
        self.arousal = _finite_float(self.arousal, 0.0)
        self.tension = _finite_float(self.tension, 0.0)

        # last_interaction_ts：None 或非有限一律归 None（下游必须能安全跳过播种，
        # 不得因此抛 TypeError——见 decay_profile_transient）。
        if self.last_interaction_ts is not None:
            lit = _finite_float(self.last_interaction_ts, float("nan"))
            self.last_interaction_ts = lit if math.isfinite(lit) else None

        self.last_applied_transient = _clamp(
            _finite_float(self.last_applied_transient, 0.0), -_APPLY_CAP, _APPLY_CAP
        )

        try:
            self.schema_ver = int(self.schema_ver)
        except (TypeError, ValueError):
            self.schema_ver = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "preference_count": self.preference_count,
            "boundary_count": self.boundary_count,
            "progress_count": self.progress_count,
            "repair_count": self.repair_count,
            "phase": self.phase,
            "six_snapshot": dict(self.six_snapshot),
            "warmth_baseline": self.warmth_baseline,
            "warmth_transient": self.warmth_transient,
            "volatility_transient": self.volatility_transient,
            "valence": self.valence,
            "arousal": self.arousal,
            "tension": self.tension,
            "last_interaction_ts": self.last_interaction_ts,
            "last_applied_transient": self.last_applied_transient,
            "schema_ver": self.schema_ver,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PersonProfile":
        """FIELD_BACKFILL_DOCTRINE：一律 `d.get(key, default)`；数值/枚举归一统一在
        `__post_init__` 做（原样传入，避免 to_dict/from_dict/直接构造三条路径各自为政）。
        """
        return cls(
            preference_count=d.get("preference_count", 0),
            boundary_count=d.get("boundary_count", 0),
            progress_count=d.get("progress_count", 0),
            repair_count=d.get("repair_count", 0),
            phase=d.get("phase", "low_signal"),
            six_snapshot=d.get("six_snapshot", {}),
            warmth_baseline=d.get("warmth_baseline", 0.45),
            warmth_transient=d.get("warmth_transient", 0.0),
            volatility_transient=d.get("volatility_transient", 0.0),
            valence=d.get("valence", 0.0),
            arousal=d.get("arousal", 0.0),
            tension=d.get("tension", 0.0),
            last_interaction_ts=d.get("last_interaction_ts", None),
            last_applied_transient=d.get("last_applied_transient", 0.0),
            schema_ver=d.get("schema_ver", 1),
        )


def person_profile_kv_key(platform: str, sender_id: str) -> str:
    """生成 PersonProfile 的 KV 键。platform/sender_id 任一为空返回空串（拒绝构键）。"""
    if not platform or not sender_id:
        return ""
    return _KV_KEY_TEMPLATE.format(platform=platform, sender_id=sender_id)


async def load_person_profile(plugin: Any, platform: str, sender_id: str) -> PersonProfile:
    """读 KV 载入档案；无 KV API / 键为空 / 读取异常 / 非 dict 均 fail-closed 返回默认档案。

    本 slice 未被任何生产读侧调用（出生播种未接线），只是可独立测试的读接口。
    """
    key = person_profile_kv_key(platform, sender_id)
    if not key:
        return PersonProfile()
    get_fn = getattr(plugin, "get_kv_data", None)
    if not callable(get_fn):
        return PersonProfile()
    try:
        raw = await get_fn(key, None)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Sylanne person_profile: 载入失败 (fail-closed 默认档案): %s", exc)
        return PersonProfile()
    if not isinstance(raw, dict):
        return PersonProfile()
    try:
        return PersonProfile.from_dict(raw)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Sylanne person_profile: from_dict 失败 (fail-closed 默认档案): %s", exc)
        return PersonProfile()


async def save_person_profile(
    plugin: Any, platform: str, sender_id: str, profile: PersonProfile
) -> None:
    """写 KV 保存档案；无 KV API / 键为空 / 写入异常均静默跳过。

    本 slice 未被任何生产写侧调用（落盘钩子软同步未接线），只是可独立测试的写接口。
    """
    key = person_profile_kv_key(platform, sender_id)
    if not key:
        return
    put_fn = getattr(plugin, "put_kv_data", None)
    if not callable(put_fn):
        return
    try:
        await put_fn(key, profile.to_dict())
    except Exception as exc:  # noqa: BLE001
        logger.debug("Sylanne person_profile: 保存失败: %s", exc)


# ---------------------------------------------------------------------------
# 衰减纯函数（design §4.2）—— 本 slice 唯一涉及"计算"的部分，其余（播种/合并/purge）
# 留后续 slice。纯函数：不读写 KV、不改传入对象、无副作用，可直接单元测。
# ---------------------------------------------------------------------------


def compute_delta_t(now: float, last_interaction_ts: float | None) -> float | None:
    """计算 Δt = max(0, now - last_interaction_ts)。

    - `last_interaction_ts` 为 None → 返回 None（调用方须据此跳过播种/衰减，不得
      因此抛 TypeError——design §8 B2 明文）。
    - `now`/`last_interaction_ts` 非有限 → 同样返回 None（防御性；`PersonProfile`
      的 `__post_init__` 已保证 `last_interaction_ts` 若非 None 必为有限值，这里
      是双保险，不依赖调用方总是传经过规范化的 profile）。
    - Δt 下限截断至 0（防时钟回拨放大衰减结果）。
    """
    if last_interaction_ts is None:
        return None
    if not math.isfinite(now) or not math.isfinite(last_interaction_ts):
        return None
    return max(0.0, now - last_interaction_ts)


def _decay_factor(delta_t: float, half_life_seconds: float) -> float:
    """指数衰减因子 2^(-Δt/T½)。

    长停机（Δt 巨大）是安全的——浮点下溢趋近 0，不会像 2.4.1 的 rhythm_ema 那样炸
    （design §4.2 红队诚实纠正）。真正危险的只有 Δt<0（上游 `compute_delta_t` 已
    下限截断，这里仍防御性二次截断）与非有限值。
    """
    if half_life_seconds <= 0:
        return 0.0
    dt = max(0.0, delta_t)
    try:
        factor = 2.0 ** (-dt / half_life_seconds)
    except OverflowError:
        return 0.0
    return factor if math.isfinite(factor) else 0.0


def decay_transient(value: float, delta_t: float, half_life_seconds: float) -> float:
    """对单个 transient 标量做墙钟指数衰减，返回衰减后的值。

    B2 全护栏内建于此单一入口，不依赖调用方：
    - `value`/`delta_t` 非有限 → 显式判定归零（不能依赖 `abs(nan) < eps` 这类隐式
      判断——NaN 参与比较恒为 False，那种写法抓不住非有限值，必须先做
      `math.isfinite` 式的显式检查）。
    - Δt 下限截断至 0（`_decay_factor` 内已做，这里透传）。
    - `|结果| < _TRANSIENT_ZERO_EPS` 视为归零。
    - 结果重新钳 ±`_TRANSIENT_STORAGE_CAP`（存储帽）——不是只在写入时钳一次就假设
      后续计算维持不变量。
    """
    if not math.isfinite(value) or not math.isfinite(delta_t):
        return 0.0
    factor = _decay_factor(delta_t, half_life_seconds)
    decayed = value * factor
    if not math.isfinite(decayed):
        return 0.0
    if abs(decayed) < _TRANSIENT_ZERO_EPS:
        return 0.0
    return _clamp(decayed, -_TRANSIENT_STORAGE_CAP, _TRANSIENT_STORAGE_CAP)


def decay_profile_transient(profile: PersonProfile, now: float) -> PersonProfile:
    """返回 warmth_transient/volatility_transient 衰减到 `now` 后的 profile 副本（纯函数）。

    - 不修改入参 `profile`（用 `dataclasses.replace` 返回新实例）。
    - `profile.last_interaction_ts` 为 None（或经 `__post_init__` 已归一为 None 的
      非有限值）→ 原样返回（跳过播种/衰减，不抛异常）。
    - 只衰减 `warmth_transient`/`volatility_transient`——`valence`/`arousal`/`tension`
      本期"只存不施加"（§4.4），没有定义半衰期，本函数不动它们。
    - 不改写 `last_interaction_ts`：锚点的推进是"新观测写入"的职责，不是"读时衰减"
      的职责，两者本 slice 均未接线，此处只保证衰减计算本身纯粹、可测。
    """
    dt = compute_delta_t(now, profile.last_interaction_ts)
    if dt is None:
        return profile
    return replace(
        profile,
        warmth_transient=decay_transient(
            profile.warmth_transient, dt, WARMTH_HALF_LIFE_SECONDS
        ),
        volatility_transient=decay_transient(
            profile.volatility_transient, dt, VOLATILITY_HALF_LIFE_SECONDS
        ),
    )
