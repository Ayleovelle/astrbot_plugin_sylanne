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
    last_applied_volatility_transient: float = 0.0

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
        self.last_applied_volatility_transient = _clamp(
            _finite_float(self.last_applied_volatility_transient, 0.0), -_APPLY_CAP, _APPLY_CAP
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
            "last_applied_volatility_transient": self.last_applied_volatility_transient,
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
            last_applied_volatility_transient=d.get("last_applied_volatility_transient", 0.0),
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
# Task-6 inactive relation persistence.  These helpers deliberately sit beside
# the legacy KV API rather than replacing it: ingress has not switched yet.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RelationPersonProfileState:
    """One profile value plus the CAS generation of its relation component."""

    profile: PersonProfile
    generation: int

    def __post_init__(self) -> None:
        if type(self.profile) is not PersonProfile:
            raise ValueError("profile must be a PersonProfile")
        if type(self.generation) is not int or self.generation < 0:
            raise ValueError("generation must be a non-negative int")


# Short alias for callers that describe this as a relation profile snapshot.
RelationProfileState = RelationPersonProfileState


def _require_relation_profile_gateway(gateway: object):
    from .scope_repository import RelationScopedPersistenceGateway

    if type(gateway) is not RelationScopedPersistenceGateway:
        raise ValueError("gateway must be a RelationScopedPersistenceGateway")
    return gateway


def load_relation_person_profile(gateway: object) -> RelationPersonProfileState:
    """Load only the profile component from an exact frozen relation gateway."""

    persistence = _require_relation_profile_gateway(gateway)
    snapshot = persistence.load("profile")
    if snapshot is None or type(snapshot.payload) is not dict:
        return RelationPersonProfileState(profile=PersonProfile(), generation=0)
    try:
        profile = PersonProfile.from_dict(snapshot.payload)
    except Exception:
        profile = PersonProfile()
    return RelationPersonProfileState(profile=profile, generation=snapshot.generation)


def save_relation_person_profile(
    gateway: object,
    profile: PersonProfile,
    *,
    expected_generation: int,
) -> int:
    """CAS-save one profile through its captured relation gateway only."""

    persistence = _require_relation_profile_gateway(gateway)
    if type(profile) is not PersonProfile:
        raise ValueError("profile must be a PersonProfile")
    if type(expected_generation) is not int or expected_generation < 0:
        raise ValueError("expected_generation must be a non-negative int")
    return persistence.save(
        "profile",
        expected_generation=expected_generation,
        payload=profile.to_dict(),
    )


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


_SIX_MIX_ALPHA = 0.3
_WARMTH_BASELINE_ALPHA = 0.1
_TRANSIENT_MIX_ALPHA = 0.5


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


# ---------------------------------------------------------------------------
# 落盘软同步（§3 关系+人格 / §4.1 transient 写入点）—— persist_kernel 钩子消费的
# 纯合并函数。不读写 KV、不碰 host/kernel，可脱离 plugin 独立单测。
# ---------------------------------------------------------------------------


def _phase_from_counts(
    preference_count: int, boundary_count: int, progress_count: int, repair_count: int
) -> str:
    """与 body.py:524-530 `relationship_memory()` 同一套阈值公式，供
    PersonProfile.phase 字段在落盘合并后同步刷新（不是必需字段——货架/播种只
    读四计数本身，phase 只是展示性冗余——但保持一致，避免两处口径分叉）。
    """
    event_count = preference_count + boundary_count + progress_count + repair_count
    weight = event_count / 12.0
    if weight >= 0.6:
        return "active_continuity"
    if weight >= 0.25:
        return "forming_continuity"
    return "low_signal"


def mix_six_snapshot(
    old: dict[str, float], new: dict[str, float], alpha: float = _SIX_MIX_ALPHA
) -> dict[str, float]:
    """Sylanne Six 指数混合（design §3(2)）。

    - 键同时存在于新旧快照：`old*(1-alpha) + new*alpha`（慢混合，α 未在
      design 定死，本实现取 0.3——单次落盘不会把画像拉一半，需要多次落盘才能
      靠近新观测，与 warmth_transient 的"单次对话最多拉一半"不同调）。
    - 键只在新快照：直接采纳（首次观测，没有旧锚点可混，不应隐式当作
      "旧值=0" 参与混合，否则会把新特质硬拉向 0）。
    - 键只在旧快照：保留旧值（本次落盘没有新观测，不应凭空归零）。
    - 结果经 `_normalize_six_snapshot` 二次夹紧 [0,1] 并过滤非法键（防御性，
      调用方通常已保证输入合法）。
    """
    merged: dict[str, float] = dict(old)
    for key in _SIX_TRAIT_KEYS:
        if key in new:
            if key in old:
                merged[key] = old[key] * (1.0 - alpha) + new[key] * alpha
            else:
                merged[key] = new[key]
    return _normalize_six_snapshot(merged)


def merge_relationship_counts(
    profile: PersonProfile, counts: dict[str, int] | None
) -> tuple[int, int, int, int, str]:
    """关系四计数 element-wise max 合并（design §3(1)）。

    `counts` 为 None 或空 dict → 原样返回 profile 现有四计数（无新观测，
    不应回退清零）。返回值末尾附带按合并后计数重算的 phase。
    """
    if not counts:
        return (
            profile.preference_count,
            profile.boundary_count,
            profile.progress_count,
            profile.repair_count,
            profile.phase,
        )
    pref = max(profile.preference_count, _finite_nonneg_int(counts.get("preference_count", 0)))
    bound = max(profile.boundary_count, _finite_nonneg_int(counts.get("boundary_count", 0)))
    prog = max(profile.progress_count, _finite_nonneg_int(counts.get("progress_count", 0)))
    repair = max(profile.repair_count, _finite_nonneg_int(counts.get("repair_count", 0)))
    return pref, bound, prog, repair, _phase_from_counts(pref, bound, prog, repair)


def apply_flush_observation(
    profile: PersonProfile,
    *,
    now: float,
    current_warmth: float,
    current_volatility: float,
    relationship_counts: dict[str, int] | None = None,
    six_observed: dict[str, float] | None = None,
    valence: float | None = None,
    arousal: float | None = None,
    tension: float | None = None,
    update_relationship_affect: bool = True,
) -> PersonProfile:
    """`persist_kernel` 落盘钩子的合并入口（design §3 / §4.1，§8 B4 顺序冻结）。

    纯函数：不修改入参 `profile`，返回新实例。**顺序在此冻结，不得调换**
    （B4 明文"必须定义 flush 内 transient 计算与 baseline 计算的先后顺序并冻结"）：

    1. 关系四计数：element-wise max 合并（不依赖顺序，放前面纯粹为了函数
       内可读性）。
    2. Sylanne Six：指数混合。
    3. transient：先把旧 transient 按墙钟衰减到 `now`；`warmth_transient`
       的新观测值用【旧】`warmth_baseline`（本步骤更新前的基线）算
       `current_warmth - old_baseline - profile.last_applied_transient`
       （同 baseline 采样点一样剔除已跨群施加的锚点值——否则跨群播种注入
       的种子会被当作"这次会话自己观测到的偏离"重新计入 transient，
       种子自己的回声会在下一次落盘时又被读回，永不衰减到零），与衰减后
       的旧值做 EMA 混合，重新钳 ±0.3 存储帽；`volatility_transient` 同理，
       新观测直接取 `current_volatility`（无基线概念可减）。
    4. `warmth_baseline`：**最后一步**才更新，采样点＝
       `current_warmth - profile.last_applied_transient`（B4："剔除已施加
       的 transient"——用的是【已施加锚点】而非上一步刚算出的"观测 transient"，
       两者含义不同：后者是"当前偏离基线多少"，前者是"这个 kernel 因跨群
       播种被注入了多少"，基线要减去的是后者），与旧基线做慢 EMA（α=0.1）。
    5. `last_interaction_ts` 推进到 `now`（写侧职责——见
       `decay_profile_transient` 文档字符串，读时衰减不推进锚点）。
    6. `valence`/`arousal`/`tension`：仅当调用方传入非 None 时覆盖（"只存
       不施加"的最新快照，无定义动力学，直接采纳最新观测；§4.4/§8 B5）。

    `update_relationship_affect=False`（对应 `cross_relationship` 开关关闭，
    即便 `cross_personality` 单独开着）时，步骤 3/4/5 以及
    `valence`/`arousal`/`tension` 全部跳过、原样保留 profile 现有值——
    warmth 长期基线/transient/`last_interaction_ts` 全部挂在
    `cross_relationship` 这一个开关下（design §4.3 "开关归属"），不应该因为
    只开了 `cross_personality` 就被静默污染。

    所有产出的数值型字段都经由 `PersonProfile.__post_init__`（`replace()` 会
    重新触发）二次夹紧，不依赖本函数自行钳到位。
    """
    pref, bound, prog, repair, phase = merge_relationship_counts(profile, relationship_counts)

    new_six = mix_six_snapshot(profile.six_snapshot, six_observed or {})

    if not update_relationship_affect:
        return replace(
            profile,
            preference_count=pref,
            boundary_count=bound,
            progress_count=prog,
            repair_count=repair,
            phase=phase,
            six_snapshot=new_six,
        )

    decayed = decay_profile_transient(profile, now)

    old_baseline = profile.warmth_baseline
    # 与 baseline 采样点（下方 `baseline_sample`）一致地剔除 `last_applied_transient`：
    # 二者取自同一 `current_warmth`，若这里不去种而 baseline 去种，跨群播种的种子
    # 会被本函数当作"这次会话自己的新偏离"重新计入 transient，下次又原样播种回去，
    # 形成永不衰减的回声（详见本函数 docstring 步骤 3）。
    observed_warmth_transient = (
        _finite_float(current_warmth, old_baseline) - old_baseline - profile.last_applied_transient
    )
    new_warmth_transient = _clamp(
        decayed.warmth_transient * (1.0 - _TRANSIENT_MIX_ALPHA)
        + observed_warmth_transient * _TRANSIENT_MIX_ALPHA,
        -_TRANSIENT_STORAGE_CAP,
        _TRANSIENT_STORAGE_CAP,
    )

    observed_volatility = _finite_float(current_volatility, 0.0)
    new_volatility_transient = _clamp(
        decayed.volatility_transient * (1.0 - _TRANSIENT_MIX_ALPHA)
        + observed_volatility * _TRANSIENT_MIX_ALPHA,
        -_TRANSIENT_STORAGE_CAP,
        _TRANSIENT_STORAGE_CAP,
    )

    baseline_sample = _clamp(
        _finite_float(current_warmth, old_baseline) - profile.last_applied_transient, 0.0, 1.0
    )
    new_baseline = _clamp(
        old_baseline * (1.0 - _WARMTH_BASELINE_ALPHA) + baseline_sample * _WARMTH_BASELINE_ALPHA,
        0.0,
        1.0,
    )

    return replace(
        profile,
        preference_count=pref,
        boundary_count=bound,
        progress_count=prog,
        repair_count=repair,
        phase=phase,
        six_snapshot=new_six,
        warmth_baseline=new_baseline,
        warmth_transient=new_warmth_transient,
        volatility_transient=new_volatility_transient,
        valence=profile.valence if valence is None else valence,
        arousal=profile.arousal if arousal is None else arousal,
        tension=profile.tension if tension is None else tension,
        last_interaction_ts=now,
    )


def seed_transient_delta(
    profile: PersonProfile, now: float, kernel_last_activity: float
) -> tuple[dict[str, float], float] | None:
    """host 出生播种 / LRU 重建守卫过的 transient 施加计算（design §4.1/§4.3，
    §8 B3 幂等播种）。

    纯函数：不改 profile、不碰 kernel，调用方负责把返回的 delta 喂给
    `AlphaBodyState.apply_vector_delta`，并把返回的新锚点值回写进 profile 的
    `last_applied_transient`。

    Args:
        profile: 当前人格档案。
        now: 播种时刻的墙钟时间戳。
        kernel_last_activity: 该 session 已恢复 kernel 的最后活动时间戳
            （`host.kernel.last_event.get("now")`，真正首次出生传 0.0）。

    Returns:
        None：guard 不通过——`profile.last_interaction_ts` 为 `None`，或不晚于
        `kernel_last_activity`（该 kernel 自己的活动已经不早于 profile 记录的
        最近互动，说明没有"来自别处的新情绪"需要播种，直接跳过，防止 LRU
        驱逐重建把已经反映在 kernel 里的旧情绪重复叠加——design §4.3 "自激"
        坑的结构化解法）。
        `(delta, new_last_applied_transient, new_last_applied_volatility_transient)`：
        `delta` 的 key 只可能是 `"temperature.warmth"`/`"temperature.volatility"`
        的子集（可能为空 dict——目标值衰减到零时无需调用 `apply_vector_delta`，
        但两个锚点仍要推进），硬 assert 保证绝不含 `valence`/`arousal`/`tension`
        （§8 B5 物理拒绝播种，即便未来有人不慎在上游拼错 key 传进来）；两个
        `new_last_applied_*` 都是调用方应回写进 profile 的新锚点值。

    B3 语义："净施加恒等于当前衰减值，不是历史施加值的累加"——`temperature.warmth`
    与 `temperature.volatility` 在 `apply_vector_delta` 里都是【累加式】写入
    （body.py `self.temperature.volatility = _clamp(self.temperature.volatility +
    delta.get(...))`，与 warmth 同一形态，不是"设置为"），因此两者都必须走
    净施加：目标值先钳到锚点字段自身的存储上限（±0.15，即 `_APPLY_CAP`，与
    `PersonProfile.__post_init__` 同一把尺），再算
    `net = target - profile.last_applied_*` 作为本次实际注入 kernel 的增量。
    若 volatility 不做这层净施加（早期实现的简化），LRU 反复驱逐重建时
    （guard 允许——该人在别处持续活跃，`profile.last_interaction_ts` 始终晚于
    重建出的 kernel 活动时间）会把 `target_volatility` 逐次累加进已经播种过的
    kernel，击穿 ±0.15 单次施加帽、最终顶到 `apply_vector_delta` 的 [0,1] clamp
    上限——这不是"轻微累积"，是无界累积，必须与 warmth 同一套净施加语义。
    """
    if profile.last_interaction_ts is None:
        return None
    if not math.isfinite(kernel_last_activity):
        kernel_last_activity = 0.0
    if profile.last_interaction_ts <= kernel_last_activity:
        return None

    decayed = decay_profile_transient(profile, now)

    target_warmth = _clamp(decayed.warmth_transient, -_APPLY_CAP, _APPLY_CAP)
    net_warmth = target_warmth - profile.last_applied_transient
    target_volatility = _clamp(decayed.volatility_transient, -_APPLY_CAP, _APPLY_CAP)
    net_volatility = target_volatility - profile.last_applied_volatility_transient

    delta: dict[str, float] = {}
    if abs(net_warmth) >= _TRANSIENT_ZERO_EPS:
        delta["temperature.warmth"] = net_warmth
    if abs(net_volatility) >= _TRANSIENT_ZERO_EPS:
        delta["temperature.volatility"] = net_volatility

    # B5 硬闸：valence/arousal/tension 在 2.6.0 E 核落地前物理禁止进入任何播种
    # 路径。用运行期 RuntimeError 而非裸 assert——后者在 python -O / PYTHONOPTIMIZE
    # 下被整体剥离，"失败即崩溃"就落空。防止未来"顺手"接上播种而没人注意到这是
    # 语义翻转（只存不施加 → 存了就施加）。
    _forbidden = {"valence", "arousal", "tension"} & delta.keys()
    if _forbidden:
        raise RuntimeError(
            f"B5 违规：{sorted(_forbidden)} 禁止进入播种 delta"
            "（本期只存不施加，2.6.0 E 核落地前不得解除）"
        )

    return delta, target_warmth, target_volatility


async def reset_person_profile_transient(plugin: Any, platform: str, sender_id: str) -> None:
    """B5 purge 级联专用：只清空某人档案里"本次会话可能产生的瞬时/静态隐私面"
    字段（`transient_affect` 的 6 个字段 + 两个 B3 幂等播种锚
    `last_applied_transient`/`last_applied_volatility_transient`），
    保留关系四计数 / Sylanne Six / `warmth_baseline`——后者是跨会话长期状态，
    不属于"这次会话产生的"静态隐私面（design §7 purge 一致性 / §8 B5）。

    无 KV API / 键为空 / 档案本就是默认值（无需写入）均静默跳过。

    与 soft-sync 走【同一把 per-person 锁】串行化 load→clear→save：否则 purge
    与并发 soft-sync（同一人跨会话）交错时，soft-sync 的在途 merge 结果可能覆盖
    purge 刚清零的 transient/valence，令已删隐私面复活（§7 purge 一致性红线）。
    锁取自 plugin._state_persistence._get_person_profile_lock（与 soft-sync 同源）；
    取不到（如测试 fake 无该访问器）则退化为无锁，仅记忆语义降级、不改正确性。
    """
    sp = getattr(plugin, "_state_persistence", None)
    _getter = getattr(sp, "_get_person_profile_lock", None)
    lock = _getter(platform, sender_id) if callable(_getter) else None
    if lock is not None:
        await lock.acquire()
    try:
        profile = await load_person_profile(plugin, platform, sender_id)
        if (
            profile.warmth_transient == 0.0
            and profile.volatility_transient == 0.0
            and profile.valence == 0.0
            and profile.arousal == 0.0
            and profile.tension == 0.0
            and profile.last_interaction_ts is None
            and profile.last_applied_transient == 0.0
            and profile.last_applied_volatility_transient == 0.0
        ):
            return  # 已经是干净态，无需写入
        cleared = replace(
            profile,
            warmth_transient=0.0,
            volatility_transient=0.0,
            valence=0.0,
            arousal=0.0,
            tension=0.0,
            last_interaction_ts=None,
            last_applied_transient=0.0,
            last_applied_volatility_transient=0.0,
        )
        await save_person_profile(plugin, platform, sender_id, cleared)
    finally:
        if lock is not None:
            lock.release()
