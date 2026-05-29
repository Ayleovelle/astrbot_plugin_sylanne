"""Sylanne-Embodiment: 关系动力学系统。

整合关系弹性、修复策略、动态边界协商三个子系统。
这些组件共同管理 Sylanne 与用户之间的关系状态演化。
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass


# ======================================================================
# 关系弹性模型
# ======================================================================


class RelationalResilience:
    def __init__(self) -> None:
        self._base_resilience: float = 0.5
        self._repair_history: int = 0
        self._unresolved_strains: int = 0

    def resilience(self, relationship_age_days: float, trust: float) -> float:
        age_bonus = min(relationship_age_days / 90, 1.0) * 0.2
        repair_bonus = min(self._repair_history * 0.05, 0.3)
        strain_penalty = self._unresolved_strains * 0.08
        raw = (
            self._base_resilience
            + age_bonus
            + repair_bonus
            - strain_penalty
            + trust * 0.2
        )
        return max(0.1, min(1.0, raw))

    def can_absorb(
        self, impact: float, relationship_age_days: float, trust: float
    ) -> bool:
        return impact <= self.resilience(relationship_age_days, trust)

    def record_repair(self) -> None:
        self._repair_history += 1
        self._unresolved_strains = max(0, self._unresolved_strains - 1)

    def record_strain(self) -> None:
        self._unresolved_strains += 1

    def is_brittle(self) -> bool:
        return self._unresolved_strains >= 3

    def to_dict(self) -> dict:
        return {
            "base": self._base_resilience,
            "repairs": self._repair_history,
            "strains": self._unresolved_strains,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RelationalResilience":
        r = cls()
        r._base_resilience = float(data.get("base", 0.5))
        r._repair_history = int(data.get("repairs", 0))
        r._unresolved_strains = int(data.get("strains", 0))
        return r


# ======================================================================
# 修复策略
# ======================================================================


class RepairStrategy:
    STRATEGIES: dict[str, str] = {
        "soften": "主动示弱，承认自己可能表达不当",
        "recall_good": "回忆共同经历中的温暖时刻",
        "reduce_frequency": "降低主动发言频率，给对方空间",
        "direct_address": "直接但温和地询问是否有什么不对",
        "humor_defuse": "用轻松幽默化解紧张氛围",
    }

    def __init__(self, conflict_threshold: int = 3) -> None:
        self._consecutive_conflicts: int = 0
        self._threshold = conflict_threshold
        self._last_strategy: str = ""

    def observe_interaction(self, is_conflict: bool) -> None:
        if is_conflict:
            self._consecutive_conflicts += 1
        else:
            self._consecutive_conflicts = max(0, self._consecutive_conflicts - 1)

    def needs_repair(self) -> bool:
        return self._consecutive_conflicts >= self._threshold

    def suggest(self, relationship_age_days: float, resilience_brittle: bool) -> str:
        if resilience_brittle:
            return "reduce_frequency"
        if relationship_age_days < 7:
            return "soften"
        if self._last_strategy == "soften":
            strategy = "recall_good"
        else:
            strategy = "soften"
        self._last_strategy = strategy
        return strategy

    def get_hint(self, strategy: str) -> str:
        return self.STRATEGIES.get(strategy, "")

    def reset(self) -> None:
        self._consecutive_conflicts = 0

    def to_dict(self) -> dict:
        return {
            "consecutive_conflicts": self._consecutive_conflicts,
            "threshold": self._threshold,
            "last_strategy": self._last_strategy,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RepairStrategy":
        rs = cls(conflict_threshold=int(data.get("threshold", 3)))
        rs._consecutive_conflicts = int(data.get("consecutive_conflicts", 0))
        rs._last_strategy = str(data.get("last_strategy", ""))
        return rs


# ======================================================================
# 动态边界协商
# ======================================================================


@dataclass
class BoundaryProbe:
    timestamp: float
    dimension: str
    accepted: bool


class DynamicBoundary:
    DIMENSIONS = ("intimacy", "directness", "humor", "vulnerability")

    def __init__(self):
        self._levels: dict[str, float] = {d: 0.3 for d in self.DIMENSIONS}
        self._probe_history: deque[BoundaryProbe] = deque(maxlen=50)
        self._probe_cooldowns: dict[str, float] = {d: 0 for d in self.DIMENSIONS}

    def get_level(self, dimension: str) -> float:
        return self._levels.get(dimension, 0.3)

    def should_probe(self, dimension: str) -> bool:
        now = time.time()
        cooldown = self._probe_cooldowns.get(dimension, 0)
        return now > cooldown and self._levels.get(dimension, 0) < 0.9

    def record_probe_result(self, dimension: str, accepted: bool):
        now = time.time()
        self._probe_history.append(BoundaryProbe(now, dimension, accepted))
        if accepted:
            self._levels[dimension] = min(1.0, self._levels[dimension] + 0.05)
            self._probe_cooldowns[dimension] = now + 300
        else:
            self._levels[dimension] = max(0.0, self._levels[dimension] - 0.1)
            recent_rejects = sum(
                1
                for p in self._probe_history
                if p.dimension == dimension
                and not p.accepted
                and now - p.timestamp < 3600
            )
            self._probe_cooldowns[dimension] = now + 600 * (1 + recent_rejects)

    def get_probe_hint(self, dimension: str) -> str:
        hints = {
            "intimacy": "可以稍微更亲近一些，用更柔软的称呼或表达关心",
            "directness": "可以更直接地表达想法，减少委婉",
            "humor": "可以尝试轻松的玩笑或调侃",
            "vulnerability": "可以分享一些内心的脆弱或不确定",
        }
        return hints.get(dimension, "")

    def to_dict(self) -> dict:
        return {
            "levels": dict(self._levels),
            "cooldowns": dict(self._probe_cooldowns),
            "probes": [
                {"ts": p.timestamp, "dim": p.dimension, "ok": p.accepted}
                for p in self._probe_history
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DynamicBoundary":
        db = cls()
        db._levels = data.get("levels", {d: 0.3 for d in cls.DIMENSIONS})
        db._probe_cooldowns = data.get("cooldowns", {d: 0 for d in cls.DIMENSIONS})
        for p in data.get("probes", []):
            db._probe_history.append(
                BoundaryProbe(p["ts"], p["dim"], p["ok"])
            )
        return db
