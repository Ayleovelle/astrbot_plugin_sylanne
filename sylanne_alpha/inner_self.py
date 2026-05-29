"""Sylanne-Embodiment: 内在自我系统。

整合秘密状态层、自我叙事引擎、矛盾检测三个子系统。
这些组件共同构成 Sylanne 的内在自我意识。
"""
from __future__ import annotations

import random
import time
from collections import deque
from dataclasses import dataclass, field


# ======================================================================
# 秘密状态层
# ======================================================================


@dataclass
class Secret:
    name: str
    description: str
    created_at: float = field(default_factory=time.time)
    ttl: float = 3600
    leak_probability: float = 0.1
    intensity: float = 0.5


class HiddenStateManager:
    def __init__(self, max_secrets: int = 10):
        self._secrets: list[Secret] = []
        self._max = max_secrets

    def add_secret(
        self,
        name: str,
        description: str,
        ttl: float = 3600,
        leak_prob: float = 0.1,
        intensity: float = 0.5,
    ):
        if len(self._secrets) >= self._max:
            self._secrets.pop(0)
        self._secrets.append(
            Secret(name, description, time.time(), max(ttl, 1.0), leak_prob, intensity)
        )

    def tick(self) -> list[str]:
        """移除过期秘密，返回本轮泄露的秘密描述列表。"""
        now = time.time()
        self._secrets = [s for s in self._secrets if now - s.created_at < s.ttl]
        leaked = []
        for s in self._secrets:
            if random.random() < s.leak_probability:
                leaked.append(s.description)
                s.leak_probability *= 0.3
        return leaked

    def get_bias_vector(self) -> dict[str, float]:
        if not self._secrets:
            return {}
        return {
            "hidden_tension": sum(s.intensity for s in self._secrets)
            / len(self._secrets)
        }

    def active_count(self) -> int:
        return len(self._secrets)

    def check_self_awareness(self) -> str | None:
        now = time.time()
        for s in self._secrets:
            age_ratio = (now - s.created_at) / max(s.ttl, 1.0)
            if age_ratio > 0.8:
                return "有些想法已经在心里很久了，也许该找个机会表达"
        return None

    def to_dict(self) -> list[dict]:
        return [
            {
                "name": s.name,
                "description": s.description,
                "created_at": s.created_at,
                "ttl": s.ttl,
                "leak_probability": s.leak_probability,
                "intensity": s.intensity,
            }
            for s in self._secrets
        ]

    @classmethod
    def from_dict(cls, data: list[dict]) -> "HiddenStateManager":
        mgr = cls()
        for d in data:
            mgr._secrets.append(
                Secret(
                    d["name"],
                    d.get("description", ""),
                    d["created_at"],
                    max(d.get("ttl", 3600), 1.0),
                    d.get("leak_probability", 0.1),
                    d.get("intensity", 0.5),
                )
            )
        return mgr


# ======================================================================
# 自我叙事引擎
# ======================================================================


@dataclass
class NarrativeFragment:
    content: str
    confidence: float = 0.5
    formed_at: float = field(default_factory=time.time)
    last_reinforced: float = field(default_factory=time.time)


class SelfNarrative:
    def __init__(self, max_fragments: int = 10):
        self._fragments: list[NarrativeFragment] = []
        self._max = max_fragments
        self._identity_core: str = ""

    def set_identity_core(self, core: str):
        self._identity_core = core

    def add_fragment(self, content: str, confidence: float = 0.5):
        for f in self._fragments:
            if self._is_contradictory(f.content, content):
                f.confidence *= 0.7
        if len(self._fragments) >= self._max:
            self._fragments.sort(key=lambda f: f.confidence)
            self._fragments.pop(0)
        self._fragments.append(NarrativeFragment(content, confidence))

    def reinforce(self, content_keyword: str):
        for f in self._fragments:
            if content_keyword in f.content:
                f.confidence = min(1.0, f.confidence + 0.1)
                f.last_reinforced = time.time()

    def get_active_narrative(self) -> str:
        active = sorted(
            [f for f in self._fragments if f.confidence > 0.3],
            key=lambda f: -f.confidence,
        )[:3]
        parts = [self._identity_core] if self._identity_core else []
        parts.extend(f.content for f in active)
        return "；".join(parts) if parts else ""

    def _is_contradictory(self, a: str, b: str) -> bool:
        opposites = [
            ("容易", "不容易"),
            ("喜欢", "讨厌"),
            ("主动", "被动"),
            ("外向", "内向"),
            ("信任", "不信任"),
        ]
        for pos, neg in opposites:
            if (pos in a and neg not in a and neg in b) or (
                neg in a and pos in b and neg not in b
            ):
                return True
        return False

    def to_dict(self) -> dict:
        return {
            "identity_core": self._identity_core,
            "fragments": [
                {
                    "content": f.content,
                    "confidence": f.confidence,
                    "formed_at": f.formed_at,
                    "last_reinforced": f.last_reinforced,
                }
                for f in self._fragments
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SelfNarrative":
        sn = cls()
        sn._identity_core = data.get("identity_core", "")
        for fd in data.get("fragments", []):
            sn._fragments.append(
                NarrativeFragment(
                    fd["content"],
                    fd["confidence"],
                    fd.get("formed_at", time.time()),
                    fd.get("last_reinforced", time.time()),
                )
            )
        return sn


# ======================================================================
# 矛盾检测
# ======================================================================


@dataclass
class Stance:
    timestamp: float
    topic: str
    position: str
    valence: float


class ContradictionCandidate:
    def __init__(
        self,
        current: str,
        historical: Stance,
        severity: float,
        contradiction_type: str,
    ):
        self.current = current
        self.historical = historical
        self.severity = severity
        self.type = contradiction_type


class ContradictionDetector:
    MIN_TOPIC_LEN = 2

    def __init__(self, history_size: int = 50):
        self._stance_history: deque[Stance] = deque(maxlen=history_size)

    def record_stance(self, topic: str, position: str, valence: float):
        self._stance_history.append(Stance(time.time(), topic, position, valence))

    def check(
        self, current_text: str, current_valence: float
    ) -> ContradictionCandidate | None:
        for stance in reversed(list(self._stance_history)):
            if len(stance.topic) < self.MIN_TOPIC_LEN:
                continue
            if stance.topic in current_text:
                valence_diff = abs(current_valence - stance.valence)
                if valence_diff > 0.6:
                    severity = min(1.0, valence_diff)
                    c_type = (
                        "emotional" if abs(stance.valence) > 0.3 else "behavioral"
                    )
                    return ContradictionCandidate(
                        current_text[:50], stance, severity, c_type
                    )
        return None

    def is_playful_inconsistency(self, text: str, mode: str) -> bool:
        playful_markers = (
            "哈哈", "开玩笑", "逗你", "才怪", "反正",
            "just kidding", "jk", "lol",
        )
        if mode in ("playful", "curious"):
            return True
        return any(m in text for m in playful_markers)

    def to_dict(self) -> list[dict]:
        return [
            {
                "timestamp": s.timestamp,
                "topic": s.topic,
                "position": s.position,
                "valence": s.valence,
            }
            for s in self._stance_history
        ]

    @classmethod
    def from_dict(cls, data: list[dict]) -> "ContradictionDetector":
        det = cls()
        for d in data:
            det._stance_history.append(
                Stance(d["timestamp"], d["topic"], d["position"], d["valence"])
            )
        return det


def get_correction_strategy(
    candidate: ContradictionCandidate, tolerance: float
) -> str | None:
    if candidate.severity < tolerance * 0.5:
        return None
    elif candidate.severity < tolerance:
        return "silent_adjust"
    elif candidate.severity < tolerance * 1.5:
        return "natural_transition"
    else:
        return "acknowledge"
