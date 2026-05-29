"""Sylanne-Embodiment: 对话智能系统。

整合风格镜像引擎和话题重力场。
风格镜像分析用户语言风格并决定回复风格；
话题重力场追踪话题讨论深度，高深度话题对对话产生引力。
"""
from __future__ import annotations

import math
import time
from collections import OrderedDict, deque
from dataclasses import dataclass, field


# ======================================================================
# 风格镜像引擎
# ======================================================================

_EMOJI_RANGES = (
    (0x2600, 0x27BF),
    (0x1F300, 0x1F5FF),
    (0x1F600, 0x1F64F),
    (0x1F680, 0x1F6FF),
    (0x1F900, 0x1F9FF),
    (0x1FA00, 0x1FA6F),
    (0x1FA70, 0x1FAFF),
    (0x2702, 0x27B0),
    (0xFE00, 0xFE0F),
)

_INFORMAL_WORDS = ("哈", "嘿", "嗯", "啊", "呢", "吧", "呀", "哦", "噢", "嘻")


def _is_emoji(c: str) -> bool:
    cp = ord(c)
    return any(lo <= cp <= hi for lo, hi in _EMOJI_RANGES)


class StyleMirror:
    def __init__(self):
        self._user_samples: deque[dict] = deque(maxlen=20)

    def observe(self, text: str):
        sentence_ends = (
            text.count("。") + text.count(".") + text.count("！") + text.count("？")
        )
        text_len = max(len(text), 1)
        emoji_count = sum(1 for c in text if _is_emoji(c))
        informal_count = sum(text.count(w) for w in _INFORMAL_WORDS)

        features = {
            "avg_sentence_len": text_len / max(sentence_ends, 1),
            "emoji_density": emoji_count / text_len,
            "punctuation_density": sum(
                1 for c in text if c in "，。！？、；：…—"
            ) / text_len,
            "informal_ratio": min(1.0, informal_count / text_len * 5),
        }
        self._user_samples.append(features)

    def get_style_profile(self) -> dict[str, float]:
        if not self._user_samples:
            return {
                "avg_sentence_len": 20,
                "emoji_density": 0,
                "punctuation_density": 0.05,
                "informal_ratio": 0.3,
            }
        keys = self._user_samples[0].keys()
        return {
            k: sum(s[k] for s in self._user_samples) / len(self._user_samples)
            for k in keys
        }

    def get_mirror_hint(self, mirror_degree: float = 0.5) -> str:
        profile = self.get_style_profile()
        hints = []
        if mirror_degree > 0.5:
            if profile["informal_ratio"] > 0.3:
                hints.append("语气轻松口语化")
            if profile["avg_sentence_len"] < 15:
                hints.append("用短句回复")
            elif profile["avg_sentence_len"] > 40:
                hints.append("可以展开详细说")
        else:
            hints.append("保持自己的表达风格")
        return "；".join(hints) if hints else ""

    def get_contrast_hint(self, user_valence: float) -> str:
        if user_valence < -0.4:
            return "用更明快温暖的语气，带一点轻松感"
        elif user_valence > 0.7:
            return "保持沉稳，不要过度附和兴奋"
        return ""


# ======================================================================
# 话题重力场
# ======================================================================


@dataclass
class TopicNode:
    name: str
    mass: float = 0.0
    last_active: float = field(default_factory=time.time)
    visit_count: int = 0
    emotional_peak: float = 0.0


class TopicGravityField:
    def __init__(self, max_topics: int = 20, half_life: float = 7200):
        self._topics: OrderedDict[str, TopicNode] = OrderedDict()
        self._max = max_topics
        self._half_life = half_life

    def observe(self, topic: str, depth: float, emotion_intensity: float):
        if topic not in self._topics:
            if len(self._topics) >= self._max:
                min_topic = min(self._topics, key=lambda k: self._topics[k].mass)
                del self._topics[min_topic]
            self._topics[topic] = TopicNode(topic)
        node = self._topics[topic]
        node.mass += depth * emotion_intensity
        node.last_active = time.time()
        node.visit_count += 1
        node.emotional_peak = max(node.emotional_peak, emotion_intensity)

    def get_gravity_pull(self) -> list[tuple[str, float]]:
        now = time.time()
        pulls: list[tuple[str, float]] = []
        for name, node in self._topics.items():
            age = now - node.last_active
            decay = math.exp(-age * math.log(2) / self._half_life)
            pull = node.mass * decay
            if pull > 0.01:
                pulls.append((name, pull))
        pulls.sort(key=lambda x: x[1], reverse=True)
        return pulls

    def strongest_pull(self) -> tuple[str, float] | None:
        pulls = self.get_gravity_pull()
        return pulls[0] if pulls else None

    def apply_repulsion(self, topic: str, strength: float = 0.5):
        if topic in self._topics:
            self._topics[topic].mass *= 1 - strength

    def to_dict(self) -> list[dict]:
        return [
            {
                "name": n.name,
                "mass": n.mass,
                "last_active": n.last_active,
                "visits": n.visit_count,
                "peak": n.emotional_peak,
            }
            for n in self._topics.values()
        ]

    @classmethod
    def from_dict(cls, data: list[dict], **kwargs) -> "TopicGravityField":
        gf = cls(**kwargs)
        for d in data:
            node = TopicNode(
                d["name"],
                d["mass"],
                d["last_active"],
                d.get("visits", 0),
                d.get("peak", 0),
            )
            gf._topics[d["name"]] = node
        return gf
