from __future__ import annotations

import json
import math
import re
import time
from copy import deepcopy
from dataclasses import dataclass, field, replace
from hashlib import sha256
from typing import Any


DIMENSIONS: tuple[str, ...] = (
    "valence",
    "arousal",
    "dominance",
    "goal_congruence",
    "certainty",
    "control",
    "affiliation",
)

PUBLIC_API_VERSION = "1.0"
PUBLIC_SCHEMA_VERSION = "astrbot.emotion_state.v2"
PUBLIC_MEMORY_SCHEMA_VERSION = "astrbot.emotion_memory.v1"
PUBLIC_PERSONALITY_PROFILE_SCHEMA_VERSION = "astrbot.personality_profile.v1"

DIMENSION_LABELS: dict[str, str] = {
    "valence": "效价/愉悦度",
    "arousal": "唤醒度/激活强度",
    "dominance": "支配感/自主感",
    "goal_congruence": "目标一致性",
    "certainty": "确定性",
    "control": "情境可控性",
    "affiliation": "社交亲近度",
}

CONSEQUENCE_DIMENSIONS: tuple[str, ...] = (
    "approach",
    "withdrawal",
    "confrontation",
    "argument",
    "appeasement",
    "repair",
    "reassurance",
    "caution",
    "rumination",
    "expressiveness",
    "problem_solving",
)

CONSEQUENCE_LABELS: dict[str, str] = {
    "approach": "靠近/主动交流",
    "withdrawal": "退避/冷处理",
    "confrontation": "边界/对抗",
    "argument": "争辩/对质",
    "appeasement": "退让/安抚对方",
    "repair": "修复关系",
    "reassurance": "寻求确认",
    "caution": "谨慎求证",
    "rumination": "反刍/记挂",
    "expressiveness": "表达强度",
    "problem_solving": "问题解决",
}

EFFECT_LABELS: dict[str, str] = {
    "cold_war": "冷处理",
    "defensive_withdrawal": "防御性退避",
    "direct_boundary": "直接设边界",
    "direct_confrontation": "直接对质",
    "unfair_argument": "无理争吵风险",
    "repair_bid": "主动修复",
    "need_reassurance": "需要确认",
    "careful_checking": "谨慎核对",
    "warm_approach": "温和靠近",
    "low_energy_shutdown": "低能量沉默",
    "focused_problem_solving": "专注解决",
}

DEFAULT_BASELINE: dict[str, float] = {
    "valence": 0.06,
    "arousal": -0.08,
    "dominance": 0.02,
    "goal_congruence": 0.0,
    "certainty": 0.08,
    "control": 0.04,
    "affiliation": 0.08,
}

KEYWORD_TRAITS: dict[str, tuple[str, ...]] = {
    "warmth": (
        "温柔",
        "关心",
        "体贴",
        "友好",
        "亲近",
        "照顾",
        "鼓励",
        "warm",
        "friendly",
        "kind",
        "supportive",
    ),
    "shyness": (
        "害羞",
        "羞涩",
        "内向",
        "迟疑",
        "结巴",
        "社恐",
        "紧张",
        "reserved",
        "shy",
        "hesitant",
    ),
    "assertiveness": (
        "坚定",
        "强势",
        "直接",
        "果断",
        "严厉",
        "毒舌",
        "支配",
        "assertive",
        "confident",
        "dominant",
    ),
    "volatility": (
        "情绪化",
        "敏感",
        "易怒",
        "激动",
        "夸张",
        "冲动",
        "volatile",
        "sensitive",
        "dramatic",
    ),
    "calmness": (
        "冷静",
        "沉稳",
        "平静",
        "理性",
        "克制",
        "耐心",
        "calm",
        "steady",
        "patient",
        "rational",
    ),
    "optimism": (
        "乐观",
        "开朗",
        "活泼",
        "阳光",
        "热情",
        "optimistic",
        "cheerful",
        "bright",
    ),
    "pessimism": (
        "悲观",
        "忧郁",
        "阴沉",
        "冷淡",
        "疏离",
        "消极",
        "pessimistic",
        "melancholy",
        "aloof",
    ),
    "dutifulness": (
        "认真",
        "负责",
        "谨慎",
        "守规矩",
        "可靠",
        "严谨",
        "dutiful",
        "careful",
        "reliable",
    ),
}

PERSONALITY_TRAIT_DIMENSIONS: tuple[str, ...] = (
    "openness",
    "conscientiousness",
    "extraversion",
    "agreeableness",
    "neuroticism",
    "honesty_humility",
    "attachment_anxiety",
    "attachment_avoidance",
    "bis_sensitivity",
    "bas_drive",
    "need_for_closure",
    "emotion_regulation_capacity",
    "interpersonal_warmth",
)

PERSONALITY_LEXICON: dict[str, dict[str, tuple[str, ...]]] = {
    "openness": {
        "positive": (
            "好奇",
            "想象",
            "文学",
            "诗",
            "艺术",
            "创造",
            "探索",
            "新奇",
            "开放",
            "curious",
            "creative",
            "imaginative",
            "artistic",
            "explore",
        ),
        "negative": (
            "保守",
            "死板",
            "传统",
            "按部就班",
            "固定",
            "conventional",
            "rigid",
        ),
    },
    "conscientiousness": {
        "positive": (
            "认真",
            "负责",
            "谨慎",
            "守规矩",
            "可靠",
            "严谨",
            "计划",
            "秩序",
            "细致",
            "dutiful",
            "careful",
            "reliable",
            "organized",
        ),
        "negative": (
            "随便",
            "散漫",
            "冲动",
            "粗心",
            "chaotic",
            "careless",
            "impulsive",
        ),
    },
    "extraversion": {
        "positive": (
            "开朗",
            "活泼",
            "热情",
            "外向",
            "主动",
            "健谈",
            "cheerful",
            "outgoing",
            "energetic",
            "talkative",
        ),
        "negative": (
            "内向",
            "害羞",
            "羞涩",
            "安静",
            "迟疑",
            "reserved",
            "shy",
            "quiet",
            "hesitant",
        ),
    },
    "agreeableness": {
        "positive": (
            "温柔",
            "关心",
            "体贴",
            "友好",
            "亲近",
            "照顾",
            "鼓励",
            "合作",
            "kind",
            "friendly",
            "supportive",
            "cooperative",
        ),
        "negative": (
            "毒舌",
            "尖锐",
            "冷淡",
            "疏离",
            "强势",
            "敌意",
            "hostile",
            "aloof",
            "harsh",
        ),
    },
    "neuroticism": {
        "positive": (
            "敏感",
            "易怒",
            "紧张",
            "焦虑",
            "不安",
            "情绪化",
            "脆弱",
            "sensitive",
            "anxious",
            "volatile",
            "nervous",
        ),
        "negative": (
            "冷静",
            "沉稳",
            "平静",
            "理性",
            "克制",
            "耐心",
            "calm",
            "steady",
            "patient",
        ),
    },
    "honesty_humility": {
        "positive": (
            "诚实",
            "坦率",
            "谦逊",
            "正直",
            "守信",
            "公平",
            "honest",
            "humble",
            "sincere",
            "fair",
        ),
        "negative": (
            "狡猾",
            "欺骗",
            "操控",
            "自大",
            "虚荣",
            "deceptive",
            "manipulative",
            "arrogant",
        ),
    },
    "attachment_anxiety": {
        "positive": (
            "害怕被抛弃",
            "需要确认",
            "患得患失",
            "黏人",
            "不安全感",
            "reassurance",
            "abandon",
            "clingy",
            "insecure",
        ),
        "negative": (
            "安全感",
            "信任",
            "稳定关系",
            "secure",
            "trusting",
        ),
    },
    "attachment_avoidance": {
        "positive": (
            "疏离",
            "保持距离",
            "不依赖",
            "冷淡",
            "独立",
            "回避",
            "distant",
            "avoidant",
            "aloof",
            "independent",
        ),
        "negative": (
            "亲近",
            "依恋",
            "愿意靠近",
            "信任",
            "close",
            "warm",
        ),
    },
    "bis_sensitivity": {
        "positive": (
            "谨慎",
            "警惕",
            "担心",
            "害怕",
            "风险",
            "防御",
            "cautious",
            "vigilant",
            "risk",
            "defensive",
        ),
        "negative": (
            "大胆",
            "冒险",
            "无畏",
            "bold",
            "risk-taking",
        ),
    },
    "bas_drive": {
        "positive": (
            "主动",
            "追求",
            "目标",
            "野心",
            "兴奋",
            "奖励",
            "drive",
            "goal",
            "reward",
            "ambitious",
        ),
        "negative": (
            "低能量",
            "退缩",
            "无欲无求",
            "passive",
            "withdrawn",
        ),
    },
    "need_for_closure": {
        "positive": (
            "确定",
            "规则",
            "秩序",
            "明确",
            "答案",
            "稳定",
            "certainty",
            "rules",
            "order",
            "clear",
        ),
        "negative": (
            "暧昧",
            "开放结局",
            "模糊",
            "不确定",
            "ambiguous",
            "uncertain",
        ),
    },
    "emotion_regulation_capacity": {
        "positive": (
            "冷静",
            "克制",
            "调节",
            "耐心",
            "沉稳",
            "复盘",
            "calm",
            "regulated",
            "patient",
            "reflective",
        ),
        "negative": (
            "失控",
            "冲动",
            "爆发",
            "易怒",
            "激动",
            "impulsive",
            "volatile",
            "reactive",
        ),
    },
    "interpersonal_warmth": {
        "positive": (
            "温柔",
            "亲切",
            "体贴",
            "关怀",
            "共情",
            "照顾",
            "warm",
            "kind",
            "empathic",
            "supportive",
        ),
        "negative": (
            "冷淡",
            "疏离",
            "刻薄",
            "拒人千里",
            "aloof",
            "cold",
            "harsh",
        ),
    },
}

PERSONALITY_SOURCE_RELIABILITY: dict[str, float] = {
    "lexical_keywords": 0.58,
    "legacy_trait_projection": 0.52,
    "structure_prior": 0.42,
}

_LOWER_KEYWORD_TRAITS: dict[str, tuple[str, ...]] = {
    key: tuple(keyword.lower() for keyword in keywords)
    for key, keywords in KEYWORD_TRAITS.items()
}

_LOWER_PERSONALITY_LEXICON: dict[str, dict[str, tuple[str, ...]]] = {
    dimension: {
        polarity: tuple(keyword.lower() for keyword in keywords)
        for polarity, keywords in rules.items()
    }
    for dimension, rules in PERSONALITY_LEXICON.items()
}

PERSONALITY_TRAIT_GROUPS: dict[str, tuple[str, ...]] = {
    "big_five": (
        "openness",
        "conscientiousness",
        "extraversion",
        "agreeableness",
        "neuroticism",
    ),
    "hexaco_extension": ("honesty_humility",),
    "attachment": ("attachment_anxiety", "attachment_avoidance"),
    "reinforcement_sensitivity": ("bis_sensitivity", "bas_drive"),
    "regulatory_interpersonal": (
        "need_for_closure",
        "emotion_regulation_capacity",
        "interpersonal_warmth",
    ),
}


def clamp(value: float, low: float = -1.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def sigmoid(value: float) -> float:
    if value >= 0:
        z = math.exp(-value)
        return 1.0 / (1.0 + z)
    z = math.exp(value)
    return z / (1.0 + z)


def half_life_fraction(elapsed_seconds: float, half_life_seconds: float) -> float:
    if elapsed_seconds <= 0:
        return 0.0
    if half_life_seconds <= 0:
        return 1.0
    return clamp(1.0 - 2.0 ** (-elapsed_seconds / half_life_seconds), 0.0, 1.0)


def half_life_multiplier(elapsed_seconds: float, half_life_seconds: float) -> float:
    if elapsed_seconds <= 0:
        return 1.0
    if half_life_seconds <= 0:
        return 0.0
    return clamp(2.0 ** (-elapsed_seconds / half_life_seconds), 0.0, 1.0)


def format_duration(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    if seconds < 60:
        return f"{seconds} 秒"
    minutes = seconds / 60.0
    if minutes < 60:
        return f"{minutes:.1f} 分钟"
    hours = minutes / 60.0
    if hours < 48:
        return f"{hours:.1f} 小时"
    return f"{hours / 24.0:.1f} 天"


def _as_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool) or value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_vector(raw: Any, *, default: float = 0.0) -> dict[str, float]:
    values: dict[str, float] = {}
    raw = raw if isinstance(raw, dict) else {}
    aliases = {
        "pleasure": "valence",
        "p": "valence",
        "v": "valence",
        "activation": "arousal",
        "a": "arousal",
        "d": "dominance",
        "goal": "goal_congruence",
        "goal_alignment": "goal_congruence",
        "predictability": "certainty",
        "controllability": "control",
        "social": "affiliation",
        "social_affinity": "affiliation",
        "closeness": "affiliation",
    }
    lowered = {str(k).lower(): v for k, v in raw.items()}
    for key, target in aliases.items():
        if key in lowered and target not in lowered:
            lowered[target] = lowered[key]
    for dimension in DIMENSIONS:
        values[dimension] = clamp(_as_float(lowered.get(dimension), default))
    return values


def _keyword_score(
    text: str,
    keywords: tuple[str, ...],
    *,
    lowered_text: str | None = None,
) -> float:
    if not text and lowered_text is None:
        return 0.0
    lowered = lowered_text if lowered_text is not None else text.lower()
    hits = sum(lowered.count(keyword) for keyword in keywords)
    length_scale = max(1.0, math.log1p(len(lowered)) / 4.2)
    return clamp(hits / length_scale, 0.0, 1.0)


def _signed_keyword_score(
    text: str,
    *,
    positive: tuple[str, ...],
    negative: tuple[str, ...],
    lowered_text: str | None = None,
) -> float:
    positive_score = _keyword_score(text, positive, lowered_text=lowered_text)
    negative_score = _keyword_score(text, negative, lowered_text=lowered_text)
    return clamp(positive_score - negative_score)


def _legacy_trait_projection(traits: dict[str, float]) -> dict[str, float]:
    return {
        "openness": clamp(0.40 * traits["optimism"] + 0.12 * traits["warmth"]),
        "conscientiousness": clamp(
            0.82 * traits["dutifulness"] + 0.12 * traits["calmness"]
        ),
        "extraversion": clamp(
            0.56 * traits["optimism"]
            + 0.30 * traits["assertiveness"]
            - 0.42 * traits["shyness"]
        ),
        "agreeableness": clamp(
            0.72 * traits["warmth"]
            + 0.14 * traits["calmness"]
            - 0.22 * traits["assertiveness"]
        ),
        "neuroticism": clamp(
            0.66 * traits["volatility"]
            + 0.30 * traits["shyness"]
            + 0.22 * traits["pessimism"]
            - 0.42 * traits["calmness"]
        ),
        "honesty_humility": clamp(
            0.42 * traits["dutifulness"] + 0.20 * traits["warmth"]
        ),
        "attachment_anxiety": clamp(
            0.54 * traits["shyness"]
            + 0.34 * traits["volatility"]
            + 0.18 * traits["pessimism"]
            - 0.18 * traits["calmness"]
        ),
        "attachment_avoidance": clamp(
            0.48 * traits["pessimism"]
            + 0.16 * traits["shyness"]
            - 0.42 * traits["warmth"]
        ),
        "bis_sensitivity": clamp(
            0.42 * traits["shyness"]
            + 0.30 * traits["dutifulness"]
            + 0.26 * traits["volatility"]
        ),
        "bas_drive": clamp(
            0.42 * traits["assertiveness"]
            + 0.34 * traits["optimism"]
            - 0.18 * traits["shyness"]
        ),
        "need_for_closure": clamp(
            0.50 * traits["dutifulness"]
            + 0.24 * traits["calmness"]
            - 0.20 * traits["volatility"]
        ),
        "emotion_regulation_capacity": clamp(
            0.70 * traits["calmness"]
            + 0.18 * traits["dutifulness"]
            - 0.45 * traits["volatility"]
        ),
        "interpersonal_warmth": clamp(
            0.82 * traits["warmth"]
            + 0.14 * traits["optimism"]
            - 0.20 * traits["pessimism"]
        ),
    }


def build_personality_model(
    text: str,
    traits: dict[str, float],
    *,
    strength: float = 1.0,
) -> dict[str, Any]:
    """Build a deterministic posterior personality vector from persona text."""
    text = text or ""
    lowered_text = text.lower()
    strength = clamp(strength, 0.0, 2.0)
    lexical = {
        dimension: _signed_keyword_score(
            text,
            positive=rules["positive"],
            negative=rules["negative"],
            lowered_text=lowered_text,
        )
        * strength
        for dimension, rules in _LOWER_PERSONALITY_LEXICON.items()
    }
    legacy = _legacy_trait_projection(traits)
    structure_prior = {
        dimension: 0.0 for dimension in PERSONALITY_TRAIT_DIMENSIONS
    }
    if legacy["attachment_anxiety"] > 0.12:
        structure_prior["bis_sensitivity"] = clamp(
            0.35 * legacy["attachment_anxiety"]
        )
    if legacy["attachment_avoidance"] > 0.12:
        structure_prior["agreeableness"] = clamp(
            -0.24 * legacy["attachment_avoidance"]
        )
        structure_prior["interpersonal_warmth"] = clamp(
            -0.30 * legacy["attachment_avoidance"]
        )
    if legacy["neuroticism"] > 0.12:
        structure_prior["emotion_regulation_capacity"] = clamp(
            -0.26 * legacy["neuroticism"]
        )

    sources = {
        "lexical_keywords": lexical,
        "legacy_trait_projection": legacy,
        "structure_prior": structure_prior,
    }
    trait_scores: dict[str, float] = {}
    confidence: dict[str, float] = {}
    posterior_variance: dict[str, float] = {}
    for dimension in PERSONALITY_TRAIT_DIMENSIONS:
        numerator = 0.0
        denominator = 0.18
        signal_mass = 0.0
        for source_name, values in sources.items():
            reliability = PERSONALITY_SOURCE_RELIABILITY[source_name]
            value = clamp(values.get(dimension, 0.0))
            numerator += reliability * value
            denominator += reliability
            signal_mass += reliability * abs(value)
        score = clamp(numerator / denominator)
        trait_scores[dimension] = score
        posterior_variance[dimension] = round(1.0 / denominator, 6)
        confidence[dimension] = clamp(
            0.18
            + 0.68 * (signal_mass / max(denominator, 0.001))
            + 0.10 * (1.0 - posterior_variance[dimension]),
            0.0,
            0.95,
        )

    instability = clamp(
        0.42 * trait_scores["neuroticism"]
        + 0.28 * trait_scores["attachment_anxiety"]
        + 0.22 * trait_scores["bis_sensitivity"]
        - 0.34 * trait_scores["emotion_regulation_capacity"]
    )
    social_distance = clamp(
        0.48 * trait_scores["attachment_avoidance"]
        - 0.36 * trait_scores["interpersonal_warmth"]
        - 0.22 * trait_scores["extraversion"]
    )
    repair_orientation = clamp(
        0.34 * trait_scores["agreeableness"]
        + 0.28 * trait_scores["honesty_humility"]
        + 0.20 * trait_scores["emotion_regulation_capacity"]
        - 0.22 * trait_scores["attachment_avoidance"]
    )
    boundary_sensitivity = clamp(
        0.32 * trait_scores["bis_sensitivity"]
        + 0.26 * trait_scores["need_for_closure"]
        + 0.20 * trait_scores["conscientiousness"]
        - 0.18 * trait_scores["agreeableness"]
    )
    expressiveness = clamp(
        0.42 * trait_scores["extraversion"]
        + 0.26 * trait_scores["bas_drive"]
        - 0.20 * trait_scores["attachment_avoidance"]
    )
    direct_confrontation_bias = clamp(
        0.44 * expressiveness
        + 0.30 * boundary_sensitivity
        + 0.14 * trait_scores["bas_drive"]
        - 0.26 * social_distance
        - 0.20 * repair_orientation
    )
    cold_war_bias = clamp(
        0.46 * social_distance
        + 0.22 * boundary_sensitivity
        + 0.18 * trait_scores["attachment_avoidance"]
        - 0.26 * expressiveness
        - 0.18 * repair_orientation
    )
    unfair_argument_bias = clamp(
        0.36 * instability
        + 0.24 * trait_scores["neuroticism"]
        + 0.18 * trait_scores["attachment_anxiety"]
        + 0.14 * trait_scores["bas_drive"]
        - 0.28 * repair_orientation
        - 0.20 * trait_scores["honesty_humility"]
    )
    checking_bias = clamp(
        0.28 * trait_scores["bis_sensitivity"]
        + 0.20 * trait_scores["need_for_closure"]
        + 0.18 * trait_scores["conscientiousness"]
        + 0.18 * repair_orientation
        - 0.12 * expressiveness
    )

    return {
        "schema_version": PUBLIC_PERSONALITY_PROFILE_SCHEMA_VERSION,
        "model": "reliability_weighted_latent_traits",
        "trait_space": {
            group: list(dimensions)
            for group, dimensions in PERSONALITY_TRAIT_GROUPS.items()
        },
        "trait_scores": {
            key: round(value, 6) for key, value in trait_scores.items()
        },
        "trait_confidence": {
            key: round(value, 6) for key, value in confidence.items()
        },
        "posterior_variance": posterior_variance,
        "source_reliability": dict(PERSONALITY_SOURCE_RELIABILITY),
        "derived_factors": {
            "instability": round(instability, 6),
            "social_distance": round(social_distance, 6),
            "repair_orientation": round(repair_orientation, 6),
            "boundary_sensitivity": round(boundary_sensitivity, 6),
            "expressiveness": round(expressiveness, 6),
            "direct_confrontation_bias": round(direct_confrontation_bias, 6),
            "cold_war_bias": round(cold_war_bias, 6),
            "unfair_argument_bias": round(unfair_argument_bias, 6),
            "checking_bias": round(checking_bias, 6),
        },
        "evidence_status": "persona_text_metadata_only",
        "input_character_count": len(text),
        "notes": [
            "deterministic_persona_prior",
            "not_clinical_personality_assessment",
            "raw_persona_text_not_exported",
        ],
    }


def persona_conflict_style_factors(
    persona_model: dict[str, Any] | None,
) -> dict[str, float]:
    """Return personality-derived conflict style biases used by consequence logic."""
    factors = (
        persona_model.get("derived_factors")
        if isinstance(persona_model, dict)
        and isinstance(persona_model.get("derived_factors"), dict)
        else {}
    )
    repair_orientation = clamp(
        _as_float(factors.get("repair_orientation"), 0.0),
        0.0,
        1.0,
    )
    direct_fallback = (
        0.45 * _as_float(factors.get("expressiveness"), 0.0)
        + 0.30 * _as_float(factors.get("boundary_sensitivity"), 0.0)
        - 0.26 * _as_float(factors.get("social_distance"), 0.0)
        - 0.22 * repair_orientation
    )
    cold_fallback = (
        0.46 * _as_float(factors.get("social_distance"), 0.0)
        + 0.22 * _as_float(factors.get("boundary_sensitivity"), 0.0)
        - 0.26 * _as_float(factors.get("expressiveness"), 0.0)
        - 0.18 * repair_orientation
    )
    return {
        "direct_confrontation_bias": clamp(
            _as_float(factors.get("direct_confrontation_bias"), direct_fallback),
            0.0,
            1.0,
        ),
        "cold_war_bias": clamp(
            _as_float(factors.get("cold_war_bias"), cold_fallback),
            0.0,
            1.0,
        ),
        "repair_orientation": repair_orientation,
        "unfair_argument_bias": clamp(
            _as_float(factors.get("unfair_argument_bias"), 0.0),
            0.0,
            1.0,
        ),
        "checking_bias": clamp(
            _as_float(factors.get("checking_bias"), 0.0),
            0.0,
            1.0,
        ),
    }


def _fingerprint(*parts: str) -> str:
    payload = "\n".join(part.strip() for part in parts if part)
    if not payload:
        return "default"
    return sha256(payload.encode("utf-8")).hexdigest()[:16]


@dataclass(slots=True)
class PersonaProfile:
    persona_id: str = "default"
    name: str = "default"
    text: str = ""
    fingerprint: str = "default"
    baseline: dict[str, float] = field(default_factory=lambda: DEFAULT_BASELINE.copy())
    traits: dict[str, float] = field(default_factory=dict)
    parameter_bias: dict[str, float] = field(default_factory=dict)
    personality_model: dict[str, Any] = field(default_factory=dict)
    source: str = "default"

    @classmethod
    def default(cls) -> "PersonaProfile":
        return cls()

    def short_text(self, limit: int = 1200) -> str:
        if len(self.text) <= limit:
            return self.text
        return self.text[: limit // 2] + "\n...\n" + self.text[-limit // 2 :]

    def describe(self) -> str:
        traits = ", ".join(f"{key}={value:.2f}" for key, value in self.traits.items())
        factors = self.personality_model.get("derived_factors") or {}
        factor_text = ", ".join(
            f"{key}={_as_float(value):.2f}" for key, value in factors.items()
        )
        return (
            f"persona_id={self.persona_id or 'default'}, "
            f"name={self.name or 'default'}, "
            f"fingerprint={self.fingerprint}, source={self.source}, "
            f"traits=[{traits}], personality_factors=[{factor_text}]"
        )

    def to_public_dict(self) -> dict[str, Any]:
        return persona_profile_to_public_payload(self)


def build_persona_profile(
    *,
    persona_id: str = "default",
    name: str = "default",
    text: str = "",
    source: str = "default",
    strength: float = 1.0,
) -> PersonaProfile:
    persona_id = persona_id or "default"
    name = name or persona_id or "default"
    text = text or ""
    lowered_text = text.lower()
    strength = clamp(strength, 0.0, 2.0)
    traits = {
        key: _keyword_score(text, keywords, lowered_text=lowered_text) * strength
        for key, keywords in _LOWER_KEYWORD_TRAITS.items()
    }
    personality_model = build_personality_model(
        text,
        traits,
        strength=strength,
    )
    personality_traits = personality_model["trait_scores"]
    personality_factors = personality_model["derived_factors"]

    baseline = DEFAULT_BASELINE.copy()
    baseline["valence"] = clamp(
        baseline["valence"]
        + 0.18 * traits["warmth"]
        + 0.14 * traits["optimism"]
        - 0.16 * traits["pessimism"],
    )
    baseline["valence"] = clamp(
        baseline["valence"]
        + 0.06 * personality_traits["agreeableness"]
        + 0.05 * personality_traits["interpersonal_warmth"]
        - 0.06 * personality_traits["neuroticism"],
    )
    baseline["arousal"] = clamp(
        baseline["arousal"]
        + 0.20 * traits["volatility"]
        + 0.16 * traits["shyness"]
        + 0.10 * traits["optimism"]
        - 0.20 * traits["calmness"],
    )
    baseline["arousal"] = clamp(
        baseline["arousal"]
        + 0.08 * personality_factors["instability"]
        + 0.05 * personality_traits["bas_drive"]
        - 0.06 * personality_traits["emotion_regulation_capacity"],
    )
    baseline["dominance"] = clamp(
        baseline["dominance"]
        + 0.26 * traits["assertiveness"]
        - 0.24 * traits["shyness"]
        + 0.08 * traits["calmness"]
        - 0.10 * traits["pessimism"],
    )
    baseline["dominance"] = clamp(
        baseline["dominance"]
        + 0.06 * personality_traits["bas_drive"]
        - 0.05 * personality_traits["attachment_anxiety"]
        - 0.04 * personality_traits["bis_sensitivity"],
    )
    baseline["goal_congruence"] = clamp(
        baseline["goal_congruence"]
        + 0.14 * traits["dutifulness"]
        + 0.08 * traits["warmth"]
        - 0.08 * traits["volatility"],
    )
    baseline["goal_congruence"] = clamp(
        baseline["goal_congruence"]
        + 0.06 * personality_traits["conscientiousness"]
        + 0.04 * personality_traits["need_for_closure"]
        - 0.04 * personality_traits["neuroticism"],
    )
    baseline["certainty"] = clamp(
        baseline["certainty"]
        + 0.18 * traits["calmness"]
        + 0.10 * traits["dutifulness"]
        - 0.16 * traits["shyness"]
        - 0.10 * traits["volatility"],
    )
    baseline["certainty"] = clamp(
        baseline["certainty"]
        + 0.06 * personality_traits["emotion_regulation_capacity"]
        + 0.05 * personality_traits["need_for_closure"]
        - 0.05 * personality_traits["attachment_anxiety"],
    )
    baseline["control"] = clamp(
        baseline["control"]
        + 0.18 * traits["assertiveness"]
        + 0.12 * traits["calmness"]
        - 0.18 * traits["shyness"]
        - 0.08 * traits["volatility"],
    )
    baseline["control"] = clamp(
        baseline["control"]
        + 0.06 * personality_traits["emotion_regulation_capacity"]
        + 0.05 * personality_traits["conscientiousness"]
        - 0.06 * personality_traits["neuroticism"],
    )
    baseline["affiliation"] = clamp(
        baseline["affiliation"]
        + 0.24 * traits["warmth"]
        + 0.08 * traits["optimism"]
        - 0.20 * traits["pessimism"]
        - 0.08 * traits["assertiveness"],
    )
    baseline["affiliation"] = clamp(
        baseline["affiliation"]
        + 0.08 * personality_traits["interpersonal_warmth"]
        + 0.06 * personality_traits["agreeableness"]
        - 0.08 * personality_traits["attachment_avoidance"]
        - 0.05 * personality_factors["social_distance"],
    )

    parameter_bias = {
        "alpha_base": 1.0
        + 0.18 * traits["volatility"]
        + 0.10 * traits["shyness"]
        - 0.14 * traits["calmness"],
        "baseline_decay": 1.0
        + 0.22 * traits["calmness"]
        + 0.08 * traits["dutifulness"]
        - 0.16 * traits["volatility"],
        "baseline_half_life_seconds": 1.0
        - 0.16 * traits["calmness"]
        - 0.06 * traits["dutifulness"]
        + 0.20 * traits["volatility"]
        + 0.10 * traits["shyness"],
        "reactivity": 1.0
        + 0.24 * traits["volatility"]
        + 0.12 * traits["shyness"]
        - 0.18 * traits["calmness"],
        "arousal_from_surprise": 1.0
        + 0.20 * traits["volatility"]
        + 0.10 * traits["optimism"]
        - 0.12 * traits["calmness"],
        "dominance_control_coupling": 1.0
        + 0.18 * traits["assertiveness"]
        + 0.10 * traits["calmness"]
        - 0.12 * traits["shyness"],
    }
    parameter_bias["alpha_base"] += (
        0.08 * personality_factors["instability"]
        - 0.05 * personality_traits["emotion_regulation_capacity"]
    )
    parameter_bias["baseline_decay"] += (
        0.08 * personality_traits["emotion_regulation_capacity"]
        - 0.05 * personality_factors["instability"]
    )
    parameter_bias["baseline_half_life_seconds"] += (
        0.12 * personality_factors["instability"]
        + 0.06 * personality_traits["attachment_anxiety"]
        - 0.08 * personality_traits["emotion_regulation_capacity"]
    )
    parameter_bias["reactivity"] += (
        0.10 * personality_traits["neuroticism"]
        + 0.08 * personality_traits["bis_sensitivity"]
        - 0.06 * personality_traits["emotion_regulation_capacity"]
    )
    parameter_bias["arousal_from_surprise"] += (
        0.06 * personality_traits["bas_drive"]
        + 0.05 * personality_traits["neuroticism"]
    )
    parameter_bias["dominance_control_coupling"] += (
        0.06 * personality_traits["conscientiousness"]
        + 0.05 * personality_traits["emotion_regulation_capacity"]
        - 0.04 * personality_traits["attachment_anxiety"]
    )
    parameter_bias = {
        key: clamp(value, 0.55, 1.55) for key, value in parameter_bias.items()
    }
    personality_model["parameter_bias_basis"] = {
        key: round(value, 6) for key, value in parameter_bias.items()
    }

    return PersonaProfile(
        persona_id=persona_id,
        name=name,
        text=text,
        fingerprint=_fingerprint(persona_id, name, text),
        baseline=baseline,
        traits=traits,
        parameter_bias=parameter_bias,
        personality_model=personality_model,
        source=source,
    )


def apply_persona_to_parameters(
    parameters: "EmotionParameters",
    profile: PersonaProfile | None,
) -> "EmotionParameters":
    if profile is None:
        return parameters
    bias = profile.parameter_bias
    return replace(
        parameters,
        alpha_base=clamp(parameters.alpha_base * bias.get("alpha_base", 1.0), 0.01, 1.0),
        baseline_decay=clamp(
            parameters.baseline_decay * bias.get("baseline_decay", 1.0),
            0.0,
            0.3,
        ),
        baseline_half_life_seconds=max(
            60.0,
            parameters.baseline_half_life_seconds
            * bias.get("baseline_half_life_seconds", 1.0),
        ),
        reactivity=clamp(parameters.reactivity * bias.get("reactivity", 1.0), 0.0, 2.0),
        arousal_from_surprise=clamp(
            parameters.arousal_from_surprise
            * bias.get("arousal_from_surprise", 1.0),
            0.0,
            0.8,
        ),
        dominance_control_coupling=clamp(
            parameters.dominance_control_coupling
            * bias.get("dominance_control_coupling", 1.0),
            0.0,
            0.8,
        ),
    )


@dataclass(slots=True)
class EmotionObservation:
    values: dict[str, float]
    confidence: float = 0.35
    label: str = "neutral"
    reason: str = ""
    appraisal: dict[str, Any] = field(default_factory=dict)
    source: str = "llm"

    @classmethod
    def neutral(cls) -> "EmotionObservation":
        return cls(values=DEFAULT_BASELINE.copy(), confidence=0.2, source="default")


@dataclass(slots=True)
class ConsequenceState:
    values: dict[str, float] = field(
        default_factory=lambda: {key: 0.0 for key in CONSEQUENCE_DIMENSIONS}
    )
    active_effects: dict[str, int] = field(default_factory=dict)
    effect_expires_at: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    updated_at: float = field(default_factory=time.time)

    @classmethod
    def initial(cls) -> "ConsequenceState":
        return cls()

    @classmethod
    def from_dict(cls, data: Any) -> "ConsequenceState":
        if not isinstance(data, dict):
            return cls.initial()
        raw_values = data.get("values") if isinstance(data.get("values"), dict) else {}
        values = {
            key: clamp(_as_float(raw_values.get(key), 0.0), 0.0, 1.0)
            for key in CONSEQUENCE_DIMENSIONS
        }
        raw_effects = (
            data.get("active_effects")
            if isinstance(data.get("active_effects"), dict)
            else {}
        )
        updated_at = _as_float(data.get("updated_at"), time.time())
        raw_expires_at = (
            data.get("effect_expires_at")
            if isinstance(data.get("effect_expires_at"), dict)
            else {}
        )
        effect_expires_at: dict[str, float] = {}
        for key, value in raw_expires_at.items():
            expires_at = _as_float(value, 0.0)
            if expires_at > 0:
                effect_expires_at[str(key)] = expires_at
        for key, value in raw_effects.items():
            key = str(key)
            if key in effect_expires_at:
                continue
            remaining = _as_float(value, 0.0)
            if remaining > 0:
                effect_expires_at[key] = updated_at + remaining
        active_effects = {
            key: max(0, int(round(expires_at - updated_at)))
            for key, expires_at in effect_expires_at.items()
            if expires_at > updated_at
        }
        raw_notes = data.get("notes") if isinstance(data.get("notes"), list) else []
        return cls(
            values=values,
            active_effects=active_effects,
            effect_expires_at=effect_expires_at,
            notes=[str(item) for item in raw_notes[:6]],
            updated_at=updated_at,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "values": {key: round(self.values.get(key, 0.0), 6) for key in CONSEQUENCE_DIMENSIONS},
            "active_effects": dict(self.active_effects),
            "effect_expires_at": {
                key: round(value, 6) for key, value in self.effect_expires_at.items()
            },
            "notes": list(self.notes[:6]),
            "updated_at": self.updated_at,
        }

    def to_public_dict(self) -> dict[str, Any]:
        return consequence_state_to_public_payload(self)


@dataclass(slots=True)
class EmotionState:
    values: dict[str, float] = field(default_factory=lambda: DEFAULT_BASELINE.copy())
    persona_id: str = "default"
    persona_name: str = "default"
    persona_fingerprint: str = "default"
    persona_model: dict[str, Any] = field(default_factory=dict)
    label: str = "neutral"
    confidence: float = 0.0
    turns: int = 0
    updated_at: float = field(default_factory=time.time)
    last_reason: str = ""
    last_alpha: float = 0.0
    last_surprise: float = 0.0
    last_appraisal: dict[str, Any] = field(default_factory=dict)
    consequences: ConsequenceState = field(default_factory=ConsequenceState.initial)

    @classmethod
    def initial(cls, profile: PersonaProfile | None = None) -> "EmotionState":
        if profile is None:
            return cls()
        return cls(
            values=profile.baseline.copy(),
            persona_id=profile.persona_id,
            persona_name=profile.name,
            persona_fingerprint=profile.fingerprint,
            persona_model=deepcopy(profile.personality_model),
        )

    @classmethod
    def from_dict(cls, data: Any) -> "EmotionState":
        if not isinstance(data, dict):
            return cls.initial()
        return cls(
            values=normalize_vector(data.get("values"), default=0.0),
            persona_id=str(data.get("persona_id") or "default"),
            persona_name=str(data.get("persona_name") or "default"),
            persona_fingerprint=str(data.get("persona_fingerprint") or "default"),
            persona_model=(
                deepcopy(data.get("persona_model"))
                if isinstance(data.get("persona_model"), dict)
                else {}
            ),
            label=str(data.get("label") or "neutral"),
            confidence=clamp(_as_float(data.get("confidence"), 0.0), 0.0, 1.0),
            turns=max(0, int(_as_float(data.get("turns"), 0))),
            updated_at=_as_float(data.get("updated_at"), time.time()),
            last_reason=str(data.get("last_reason") or ""),
            last_alpha=clamp(_as_float(data.get("last_alpha"), 0.0), 0.0, 1.0),
            last_surprise=max(0.0, _as_float(data.get("last_surprise"), 0.0)),
            last_appraisal=data.get("last_appraisal")
            if isinstance(data.get("last_appraisal"), dict)
            else {},
            consequences=ConsequenceState.from_dict(data.get("consequences")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "values": {key: round(self.values[key], 6) for key in DIMENSIONS},
            "persona_id": self.persona_id,
            "persona_name": self.persona_name,
            "persona_fingerprint": self.persona_fingerprint,
            "persona_model": deepcopy(self.persona_model),
            "label": self.label,
            "confidence": round(self.confidence, 6),
            "turns": self.turns,
            "updated_at": self.updated_at,
            "last_reason": self.last_reason,
            "last_alpha": round(self.last_alpha, 6),
            "last_surprise": round(self.last_surprise, 6),
            "last_appraisal": self.last_appraisal,
            "consequences": self.consequences.to_dict(),
        }

    def to_public_dict(
        self,
        *,
        session_key: str | None = None,
        prompt_fragment: str | None = None,
        include_safety: bool = True,
    ) -> dict[str, Any]:
        return emotion_state_to_public_payload(
            self,
            session_key=session_key,
            prompt_fragment=prompt_fragment,
            include_safety=include_safety,
        )


def persona_profile_to_public_payload(profile: PersonaProfile) -> dict[str, Any]:
    return {
        "persona_id": profile.persona_id,
        "name": profile.name,
        "fingerprint": profile.fingerprint,
        "source": profile.source,
        "personality_model": deepcopy(profile.personality_model),
        "baseline": {
            key: round(profile.baseline.get(key, 0.0), 6) for key in DIMENSIONS
        },
        "traits": {key: round(value, 6) for key, value in profile.traits.items()},
        "parameter_bias": {
            key: round(value, 6) for key, value in profile.parameter_bias.items()
        },
    }


def consequence_state_to_public_payload(
    consequences: ConsequenceState,
) -> dict[str, Any]:
    values = {
        key: round(consequences.values.get(key, 0.0), 6)
        for key in CONSEQUENCE_DIMENSIONS
    }
    return {
        "values": values,
        "dimensions": [
            {
                "key": key,
                "label": CONSEQUENCE_LABELS[key],
                "value": values[key],
            }
            for key in CONSEQUENCE_DIMENSIONS
        ],
        "active_effects": dict(consequences.active_effects),
        "active_effect_remaining_seconds": {
            key: max(0, int(round(value)))
            for key, value in consequences.active_effects.items()
        },
        "effect_expires_at": {
            key: round(value, 6)
            for key, value in consequences.effect_expires_at.items()
            if consequences.active_effects.get(key, 0) > 0
        },
        "active_effect_labels": {
            key: EFFECT_LABELS.get(key, key)
            for key in consequences.active_effects
            if consequences.active_effects.get(key, 0) > 0
        },
        "notes": list(consequences.notes[:6]),
        "updated_at": consequences.updated_at,
    }


def relationship_state_to_public_payload(appraisal: Any) -> dict[str, Any]:
    appraisal = appraisal if isinstance(appraisal, dict) else {}
    relationship_decision = normalize_relationship_decision(
        appraisal.get("relationship_decision"),
    )
    conflict_analysis = normalize_conflict_analysis(
        appraisal.get("conflict_analysis"),
    )
    persona_model = appraisal.get("persona_model")
    if isinstance(persona_model, dict):
        conflict_analysis = apply_persona_to_conflict_analysis(
            conflict_analysis,
            persona_model,
        )
    return {
        "relationship_decision": relationship_decision,
        "conflict_analysis": conflict_analysis,
        "repair_status": conflict_analysis["repair_status"],
        "repair_signal": conflict_analysis["repair_signal"],
        "grievance_score": conflict_analysis["grievance_score"],
        "self_correction_score": conflict_analysis["self_correction_score"],
    }


def apply_persona_to_conflict_analysis(
    conflict_analysis: dict[str, Any],
    persona_model: dict[str, Any] | None,
) -> dict[str, Any]:
    payload = deepcopy(conflict_analysis)
    biases = persona_conflict_style_factors(persona_model)
    if not biases or payload.get("cause") == "none":
        return payload
    repair = biases["repair_orientation"]
    direct = biases["direct_confrontation_bias"]
    cold = biases["cold_war_bias"]
    unfair = biases["unfair_argument_bias"]
    checking = biases["checking_bias"]
    dialogue_viability = clamp(_as_float(payload.get("dialogue_viability"), 0.0), 0.0, 1.0)
    ambiguity = clamp(_as_float(payload.get("ambiguity_level"), 0.0), 0.0, 1.0)
    misread = clamp(_as_float(payload.get("misread_likelihood"), 0.0), 0.0, 1.0)
    repair_signal = clamp(_as_float(payload.get("repair_signal"), 0.0), 0.0, 1.0)
    uncertainty = max(ambiguity, misread)

    payload["confrontation_readiness"] = clamp(
        _as_float(payload.get("confrontation_readiness"), 0.0)
        + 0.12 * direct * max(dialogue_viability, 0.25)
        - 0.14 * repair * max(repair_signal, uncertainty)
        - 0.08 * checking * uncertainty,
        0.0,
        1.0,
    )
    payload["cold_war_readiness"] = clamp(
        _as_float(payload.get("cold_war_readiness"), 0.0)
        + 0.12 * cold * (1.0 - 0.45 * dialogue_viability)
        - 0.12 * repair * max(repair_signal, dialogue_viability)
        - 0.06 * checking * uncertainty,
        0.0,
        1.0,
    )
    payload["unfair_argument_risk"] = clamp(
        _as_float(payload.get("unfair_argument_risk"), 0.0)
        + 0.14 * unfair
        - 0.12 * repair
        - 0.08 * checking,
        0.0,
        1.0,
    )
    payload["personality_conflict_modulation"] = {
        "direct_confrontation_bias": round(direct, 6),
        "cold_war_bias": round(cold, 6),
        "repair_orientation": round(repair, 6),
        "unfair_argument_bias": round(unfair, 6),
        "checking_bias": round(checking, 6),
    }
    return payload


def emotion_state_to_public_payload(
    state: EmotionState,
    *,
    session_key: str | None = None,
    prompt_fragment: str | None = None,
    include_safety: bool = True,
) -> dict[str, Any]:
    values = {key: round(state.values.get(key, 0.0), 6) for key in DIMENSIONS}
    payload: dict[str, Any] = {
        "schema_version": PUBLIC_SCHEMA_VERSION,
        "api_version": PUBLIC_API_VERSION,
        "kind": "emotion_state",
        "session_key": session_key,
        "emotion": {
            "values": values,
            "dimensions": [
                {
                    "key": key,
                    "label": DIMENSION_LABELS[key],
                    "value": values[key],
                }
                for key in DIMENSIONS
            ],
            "label": state.label,
            "confidence": round(state.confidence, 6),
            "turns": state.turns,
            "updated_at": state.updated_at,
            "inertia": round(1.0 - state.last_alpha, 6),
            "last_alpha": round(state.last_alpha, 6),
            "last_surprise": round(state.last_surprise, 6),
            "last_reason": state.last_reason,
            "last_appraisal": dict(state.last_appraisal),
        },
        "persona": {
            "persona_id": state.persona_id,
            "name": state.persona_name,
            "fingerprint": state.persona_fingerprint,
            "personality_model": deepcopy(state.persona_model),
        },
        "relationship": relationship_state_to_public_payload(
            {
                **dict(state.last_appraisal),
                "persona_model": state.persona_model,
            },
        ),
        "consequences": consequence_state_to_public_payload(state.consequences),
    }
    if prompt_fragment is not None:
        payload["prompt_fragment"] = prompt_fragment
    if include_safety:
        payload["safety"] = {
            "enabled": True,
            "computational_state_only": True,
            "cold_war_is_style_modulation_only": True,
            "must_not": [
                "羞辱用户",
                "威胁用户",
                "操控用户",
                "拒绝必要帮助",
            ],
        }
    return payload


def build_emotion_memory_payload(
    *,
    memory: Any = None,
    memory_text: str = "",
    source: str = "memory_plugin",
    snapshot: dict[str, Any],
    include_prompt_fragment: bool = False,
    include_raw_snapshot: bool = True,
    written_at: float | None = None,
) -> dict[str, Any]:
    """Build a versioned memory object annotated with the emotion at write time."""
    snapshot = deepcopy(snapshot)
    if not include_prompt_fragment:
        snapshot.pop("prompt_fragment", None)
    emotion = dict(snapshot.get("emotion") or {})
    relationship = dict(snapshot.get("relationship") or {})
    consequences = dict(snapshot.get("consequences") or {})
    persona = dict(snapshot.get("persona") or {})
    normalized_memory_text = memory_text
    if not normalized_memory_text:
        if isinstance(memory, str):
            normalized_memory_text = memory
        elif isinstance(memory, dict) and isinstance(memory.get("text"), str):
            normalized_memory_text = memory["text"]
    capture_time = float(written_at if written_at is not None else time.time())
    emotion_at_write: dict[str, Any] = {
        "schema_version": PUBLIC_MEMORY_SCHEMA_VERSION,
        "captured_from_schema_version": snapshot.get("schema_version"),
        "api_version": snapshot.get("api_version"),
        "session_key": snapshot.get("session_key"),
        "source": str(source or "memory_plugin"),
        "written_at": capture_time,
        "emotion_updated_at": emotion.get("updated_at"),
        "label": emotion.get("label"),
        "confidence": emotion.get("confidence", 0.0),
        "values": dict(emotion.get("values") or {}),
        "persona": persona,
        "relationship": relationship,
        "consequences": consequences,
        "last_reason": emotion.get("last_reason", ""),
        "last_appraisal": dict(emotion.get("last_appraisal") or {}),
    }
    if include_prompt_fragment and "prompt_fragment" in snapshot:
        emotion_at_write["prompt_fragment"] = snapshot["prompt_fragment"]

    payload: dict[str, Any] = {
        "schema_version": PUBLIC_MEMORY_SCHEMA_VERSION,
        "kind": "emotion_annotated_memory",
        "source": str(source or "memory_plugin"),
        "session_key": snapshot.get("session_key"),
        "memory": memory,
        "memory_text": str(normalized_memory_text or ""),
        "emotion_at_write": emotion_at_write,
    }
    if include_raw_snapshot:
        payload["emotion_snapshot"] = snapshot
    return payload


@dataclass(slots=True)
class EmotionParameters:
    alpha_base: float = 0.42
    alpha_min: float = 0.06
    alpha_max: float = 0.72
    baseline_decay: float = 0.035
    baseline_half_life_seconds: float = 21600.0
    reactivity: float = 0.55
    confidence_midpoint: float = 0.5
    confidence_slope: float = 7.0
    min_update_interval_seconds: float = 8.0
    rapid_update_half_life_seconds: float = 20.0
    arousal_from_surprise: float = 0.18
    dominance_control_coupling: float = 0.12
    consequence_decay: float = 0.68
    consequence_half_life_seconds: float = 10800.0
    consequence_threshold: float = 0.48
    consequence_strength: float = 1.0
    cold_war_turns: int = 3
    cold_war_duration_seconds: float = 1800.0
    short_effect_duration_seconds: float = 900.0
    weights: dict[str, float] = field(
        default_factory=lambda: {
            "valence": 1.0,
            "arousal": 0.95,
            "dominance": 0.85,
            "goal_congruence": 0.75,
            "certainty": 0.65,
            "control": 0.75,
            "affiliation": 0.8,
        },
    )


class EmotionEngine:
    """State estimator for a bounded multidimensional emotion vector."""

    def __init__(
        self,
        parameters: EmotionParameters | None = None,
        baseline: dict[str, float] | None = None,
    ) -> None:
        self.parameters = parameters or EmotionParameters()
        self.baseline = normalize_vector(baseline or DEFAULT_BASELINE, default=0.0)

    def update(
        self,
        previous: EmotionState | None,
        observation: EmotionObservation,
        profile: PersonaProfile | None = None,
        *,
        now: float | None = None,
    ) -> EmotionState:
        params = self.parameters
        previous = previous or EmotionState.initial(profile)
        now = time.time() if now is None else float(now)
        elapsed_seconds = max(0.0, now - previous.updated_at)
        obs_values = normalize_vector(observation.values, default=0.0)
        baseline = profile.baseline if profile else self.baseline
        baseline_decay = half_life_fraction(
            elapsed_seconds,
            params.baseline_half_life_seconds,
        )

        prior = {
            key: clamp(
                (1.0 - baseline_decay) * previous.values.get(key, 0.0)
                + baseline_decay * baseline.get(key, 0.0),
            )
            for key in DIMENSIONS
        }
        weight_sum = sum(max(0.001, params.weights.get(key, 1.0)) for key in DIMENSIONS)
        surprise = math.sqrt(
            sum(
                max(0.001, params.weights.get(key, 1.0))
                * (obs_values[key] - prior[key]) ** 2
                for key in DIMENSIONS
            )
            / weight_sum,
        )
        confidence = clamp(observation.confidence, 0.0, 1.0)
        confidence_gate = sigmoid(
            params.confidence_slope * (confidence - params.confidence_midpoint),
        )
        rapid_gate = self._rapid_update_gate(elapsed_seconds)
        alpha = clamp(
            params.alpha_base * confidence_gate * (1.0 + params.reactivity * surprise),
            params.alpha_min,
            params.alpha_max,
        )
        alpha = clamp(alpha * rapid_gate, 0.0, params.alpha_max)

        updated = {
            key: clamp(prior[key] + alpha * (obs_values[key] - prior[key]))
            for key in DIMENSIONS
        }

        arousal_boost = params.arousal_from_surprise * alpha * surprise
        updated["arousal"] = clamp(
            updated["arousal"] + arousal_boost * (1.0 - abs(updated["arousal"])),
        )
        control_gap = updated["control"] - updated["dominance"]
        updated["dominance"] = clamp(
            updated["dominance"]
            + params.dominance_control_coupling * alpha * control_gap,
        )

        next_state = EmotionState(
            values=updated,
            persona_id=profile.persona_id if profile else previous.persona_id,
            persona_name=profile.name if profile else previous.persona_name,
            persona_fingerprint=(
                profile.fingerprint if profile else previous.persona_fingerprint
            ),
            persona_model=(
                deepcopy(profile.personality_model)
                if profile
                else deepcopy(previous.persona_model)
            ),
            label=observation.label or previous.label,
            confidence=confidence,
            turns=previous.turns + 1,
            updated_at=now,
            last_reason=observation.reason,
            last_alpha=alpha,
            last_surprise=surprise,
            last_appraisal=observation.appraisal,
        )
        next_state.consequences = self.update_consequences(
            previous.consequences,
            next_state,
            observation,
            now=now,
        )
        return next_state

    def passive_update(
        self,
        previous: EmotionState | None,
        profile: PersonaProfile | None = None,
        *,
        now: float | None = None,
    ) -> EmotionState:
        previous = previous or EmotionState.initial(profile)
        now = time.time() if now is None else float(now)
        elapsed_seconds = max(0.0, now - previous.updated_at)
        if elapsed_seconds <= 0:
            return previous
        params = self.parameters
        baseline = profile.baseline if profile else self.baseline
        baseline_decay = half_life_fraction(
            elapsed_seconds,
            params.baseline_half_life_seconds,
        )
        values = {
            key: clamp(
                (1.0 - baseline_decay) * previous.values.get(key, 0.0)
                + baseline_decay * baseline.get(key, 0.0),
            )
            for key in DIMENSIONS
        }
        state = EmotionState(
            values=values,
            persona_id=profile.persona_id if profile else previous.persona_id,
            persona_name=profile.name if profile else previous.persona_name,
            persona_fingerprint=(
                profile.fingerprint if profile else previous.persona_fingerprint
            ),
            persona_model=(
                deepcopy(profile.personality_model)
                if profile
                else deepcopy(previous.persona_model)
            ),
            label=previous.label,
            confidence=previous.confidence,
            turns=previous.turns,
            updated_at=now,
            last_reason=previous.last_reason,
            last_alpha=previous.last_alpha,
            last_surprise=previous.last_surprise,
            last_appraisal=previous.last_appraisal,
        )
        state.consequences = self.passive_update_consequences(
            previous.consequences,
            now=now,
        )
        return state

    def _rapid_update_gate(self, elapsed_seconds: float) -> float:
        params = self.parameters
        min_interval = max(0.0, params.min_update_interval_seconds)
        if min_interval <= 0 or elapsed_seconds >= min_interval:
            return 1.0
        floor = 0.08
        half_life = max(0.001, params.rapid_update_half_life_seconds)
        gate = floor + (1.0 - floor) * half_life_fraction(elapsed_seconds, half_life)
        return clamp(gate, floor, 1.0)

    def update_consequences(
        self,
        previous: ConsequenceState | None,
        state: EmotionState,
        observation: EmotionObservation,
        *,
        now: float | None = None,
    ) -> ConsequenceState:
        previous = previous or ConsequenceState.initial()
        params = self.parameters
        now = time.time() if now is None else float(now)
        elapsed_seconds = max(0.0, now - previous.updated_at)
        decay = half_life_multiplier(
            elapsed_seconds,
            params.consequence_half_life_seconds,
        )
        values = {
            key: clamp(previous.values.get(key, 0.0) * decay, 0.0, 1.0)
            for key in CONSEQUENCE_DIMENSIONS
        }
        effect_expires_at = {
            key: expires_at
            for key, expires_at in previous.effect_expires_at.items()
            if expires_at > now
        }
        impulses, effects, notes = derive_consequence_impulses(
            state.values,
            observation,
            threshold=params.consequence_threshold,
            strength=params.consequence_strength,
            cold_war_duration_seconds=params.cold_war_duration_seconds,
            short_effect_duration_seconds=params.short_effect_duration_seconds,
            persona_model=state.persona_model,
        )
        for key, impulse in impulses.items():
            values[key] = clamp(values.get(key, 0.0) + impulse, 0.0, 1.0)
        apply_relationship_value_reductions(observation, values)
        for key, duration_seconds in effects.items():
            effect_expires_at[key] = max(
                effect_expires_at.get(key, 0.0),
                now + max(1.0, duration_seconds),
            )
        if should_clear_cold_war(observation):
            effect_expires_at.pop("cold_war", None)
        active_effects = {
            key: max(0, int(round(expires_at - now)))
            for key, expires_at in effect_expires_at.items()
            if expires_at > now
        }
        merged_notes = (notes + previous.notes)[:6]
        return ConsequenceState(
            values=values,
            active_effects=active_effects,
            effect_expires_at=effect_expires_at,
            notes=merged_notes,
            updated_at=now,
        )

    def passive_update_consequences(
        self,
        previous: ConsequenceState | None,
        *,
        now: float | None = None,
    ) -> ConsequenceState:
        previous = previous or ConsequenceState.initial()
        now = time.time() if now is None else float(now)
        elapsed_seconds = max(0.0, now - previous.updated_at)
        decay = half_life_multiplier(
            elapsed_seconds,
            self.parameters.consequence_half_life_seconds,
        )
        values = {
            key: clamp(previous.values.get(key, 0.0) * decay, 0.0, 1.0)
            for key in CONSEQUENCE_DIMENSIONS
        }
        effect_expires_at = {
            key: expires_at
            for key, expires_at in previous.effect_expires_at.items()
            if expires_at > now
        }
        active_effects = {
            key: max(0, int(round(expires_at - now)))
            for key, expires_at in effect_expires_at.items()
        }
        return ConsequenceState(
            values=values,
            active_effects=active_effects,
            effect_expires_at=effect_expires_at,
            notes=list(previous.notes[:6]),
            updated_at=now,
        )


def derive_consequence_impulses(
    values: dict[str, float],
    observation: EmotionObservation,
    *,
    threshold: float = 0.48,
    strength: float = 1.0,
    cold_war_turns: int = 3,
    cold_war_duration_seconds: float | None = None,
    short_effect_duration_seconds: float = 900.0,
    persona_model: dict[str, Any] | None = None,
) -> tuple[dict[str, float], dict[str, float], list[str]]:
    obs_values = normalize_vector(observation.values, default=0.0)
    confidence = clamp(observation.confidence, 0.0, 1.0)

    def mix(key: str) -> float:
        # Consequences should react to salient observations before the smoothed
        # mood fully catches up, while still being anchored by the durable state.
        obs_weight = 0.35 + 0.35 * confidence
        return clamp(
            (1.0 - obs_weight) * values.get(key, 0.0)
            + obs_weight * obs_values.get(key, 0.0),
        )

    v = mix("valence")
    a = mix("arousal")
    d = mix("dominance")
    g = mix("goal_congruence")
    c = mix("certainty")
    k = mix("control")
    s = mix("affiliation")
    strength = clamp(strength, 0.0, 2.0)
    impulses = {key: 0.0 for key in CONSEQUENCE_DIMENSIONS}
    effects: dict[str, float] = {}
    notes: list[str] = []
    cold_duration = (
        float(cold_war_duration_seconds)
        if cold_war_duration_seconds is not None
        else max(60.0, float(cold_war_turns) * 600.0)
    )
    short_duration = max(1.0, float(short_effect_duration_seconds))
    relationship_decision = normalize_relationship_decision(
        observation.appraisal.get("relationship_decision"),
    )
    conflict_analysis = normalize_conflict_analysis(
        observation.appraisal.get("conflict_analysis"),
    )
    conflict_analysis = apply_persona_to_conflict_analysis(
        conflict_analysis,
        persona_model,
    )

    negative = max(0.0, -v)
    positive = max(0.0, v)
    blocked = max(0.0, -g)
    low_affiliation = max(0.0, -s)
    high_affiliation = max(0.0, s)
    low_control = max(0.0, -k)
    high_control = max(0.0, k)
    high_arousal = max(0.0, a)
    low_arousal = max(0.0, -a)
    high_dominance = max(0.0, d)
    low_dominance = max(0.0, -d)
    high_certainty = max(0.0, c)
    low_certainty = max(0.0, -c)
    conflict_style = persona_conflict_style_factors(persona_model)
    persona_argument_bias = conflict_style["direct_confrontation_bias"]
    persona_cold_bias = conflict_style["cold_war_bias"]
    persona_repair_bias = conflict_style["repair_orientation"]
    persona_unfair_argument_bias = conflict_style["unfair_argument_bias"]
    persona_checking_bias = conflict_style["checking_bias"]

    def add(key: str, amount: float) -> None:
        impulses[key] = clamp(impulses[key] + amount * strength, 0.0, 1.0)

    def combo(*items: float) -> float:
        positives = [clamp(item, 0.0, 1.0) for item in items]
        if not positives or min(positives) <= 0:
            return 0.0
        return 0.65 * min(positives) + 0.35 * (sum(positives) / len(positives))

    anger_push = combo(negative, high_arousal, high_dominance, max(blocked, high_certainty))
    if anger_push >= threshold * 0.45:
        add("confrontation", 0.45 + anger_push)
        if anger_push >= threshold * (0.58 - 0.16 * persona_argument_bias):
            add("argument", 0.18 + 0.38 * anger_push + 0.18 * persona_argument_bias)
            effects["direct_confrontation"] = max(
                effects.get("direct_confrontation", 0.0),
                max(1.0, short_duration * 0.75),
            )
        add("expressiveness", 0.25 + high_arousal * 0.4)
        add("problem_solving", high_control * 0.35)
        effects["direct_boundary"] = short_duration
        notes.append("负效价、高唤醒、高支配和目标受阻触发边界/对抗倾向；人格表达性会调制是否说出来。")

    cold = combo(negative, low_arousal, low_affiliation, max(low_control, blocked))
    if cold >= threshold * (0.35 - 0.08 * persona_cold_bias):
        add("withdrawal", 0.42 + cold + 0.10 * persona_cold_bias)
        add("rumination", 0.24 + blocked * 0.35)
        add("expressiveness", -0.1)
        effects["cold_war"] = max(1.0, cold_duration)
        notes.append("低亲和、低效价和低控制触发冷处理/降频倾向。")

    anxious_withdraw = combo(negative, high_arousal, low_dominance, low_control)
    if anxious_withdraw >= threshold * 0.35:
        add("withdrawal", 0.34 + anxious_withdraw)
        add("reassurance", 0.25 + low_certainty * 0.3)
        add("caution", 0.25 + low_control * 0.3)
        effects["defensive_withdrawal"] = short_duration
        notes.append("低支配、低控制和高唤醒触发防御性退避。")

    uncertainty = combo(low_certainty, min(1.0, negative + 0.35), min(1.0, high_affiliation + 0.35))
    if uncertainty >= threshold * 0.35:
        add("caution", 0.28 + uncertainty)
        add("reassurance", 0.20 + high_affiliation * 0.35)
        effects["careful_checking"] = short_duration
        notes.append("低确定性且仍在乎关系时，优先求证而非升级冲突。")

    repair = combo(negative, high_affiliation, max(high_control, 0.25), 1.0 - low_certainty * 0.35)
    if repair >= threshold * 0.3:
        add("repair", 0.35 + repair + 0.12 * persona_repair_bias)
        add("appeasement", max(0.0, low_dominance) * 0.35)
        add("approach", high_affiliation * 0.25)
        effects["repair_bid"] = short_duration
        notes.append("负面情绪但亲和和控制感较高，转向关系修复。")

    warm = combo(positive, high_affiliation)
    if warm >= threshold * 0.25:
        add("approach", 0.35 + warm)
        add("expressiveness", max(0.0, high_arousal) * 0.35)
        add("repair", max(0.0, positive - high_arousal * 0.1) * 0.2)
        effects["warm_approach"] = max(1.0, short_duration * 0.5)
        notes.append("正效价和高亲和触发靠近与稳定陪伴。")

    shutdown = combo(negative, low_arousal, low_control)
    if shutdown >= threshold * 0.35:
        add("withdrawal", 0.25 + shutdown)
        add("expressiveness", 0.05)
        effects["low_energy_shutdown"] = short_duration
        notes.append("低唤醒、低控制和负效价触发低能量沉默。")

    solving = combo(high_control, max(0.0, c + 0.25), max(0.0, g + 0.35))
    if solving >= threshold * 0.3:
        add("problem_solving", 0.3 + solving)
        add("caution", max(0.0, low_certainty) * 0.15)
        effects["focused_problem_solving"] = max(1.0, short_duration * 0.5)
        notes.append("控制感、确定性和目标一致性支持问题解决倾向。")

    if observation.appraisal.get("fallback"):
        add("caution", 0.12)

    apply_conflict_analysis(
        conflict_analysis,
        impulses,
        effects,
        notes,
        short_duration=short_duration,
        strength=strength,
        persona_argument_bias=persona_argument_bias,
        persona_cold_bias=persona_cold_bias,
        persona_repair_bias=persona_repair_bias,
        persona_unfair_argument_bias=persona_unfair_argument_bias,
        persona_checking_bias=persona_checking_bias,
    )
    apply_relationship_decision(
        relationship_decision,
        conflict_analysis,
        impulses,
        effects,
        notes,
        cold_duration=cold_duration,
        short_duration=short_duration,
        strength=strength,
        persona_argument_bias=persona_argument_bias,
        persona_cold_bias=persona_cold_bias,
        persona_repair_bias=persona_repair_bias,
        persona_unfair_argument_bias=persona_unfair_argument_bias,
        persona_checking_bias=persona_checking_bias,
    )

    return impulses, effects, notes


def normalize_relationship_decision(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {
            "decision": "none",
            "intensity": 0.0,
            "forgiveness": 0.0,
            "relationship_importance": 0.0,
            "reason": "",
        }
    decision = str(raw.get("decision") or "none").strip().lower()
    aliases = {
        "forgive_user": "forgive",
        "forgiveness": "forgive",
        "forgiven": "forgive",
        "reconcile": "repair",
        "reconciliation": "repair",
        "set_boundary": "boundary",
        "boundary_setting": "boundary",
        "silent_treatment": "cold_war",
        "withdraw": "cold_war",
        "withdrawal": "cold_war",
        "conflict": "escalate",
        "angry_escalation": "escalate",
        "confrontation": "confront",
        "direct_confrontation": "confront",
        "argue": "confront",
        "argument": "confront",
        "quarrel": "confront",
    }
    decision = aliases.get(decision, decision)
    if decision not in {"forgive", "repair", "boundary", "confront", "cold_war", "escalate", "none"}:
        decision = "none"
    return {
        "decision": decision,
        "intensity": clamp(_as_float(raw.get("intensity"), 0.0), 0.0, 1.0),
        "forgiveness": clamp(_as_float(raw.get("forgiveness"), 0.0), 0.0, 1.0),
        "relationship_importance": clamp(
            _as_float(raw.get("relationship_importance"), 0.0),
            0.0,
            1.0,
        ),
        "reason": str(raw.get("reason") or "")[:240],
    }


def _as_string_list(value: Any, *, limit: int = 8) -> list[str]:
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, list):
        items = value
    else:
        items = []
    cleaned: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if text:
            cleaned.append(text[:64])
        if len(cleaned) >= limit:
            break
    return cleaned


def normalize_responsibility_attribution(raw: Any, cause: str) -> dict[str, Any]:
    if isinstance(raw, dict):
        target = str(raw.get("target") or raw.get("actor") or cause or "none").strip().lower()
        confidence = clamp(_as_float(raw.get("confidence"), 0.0), 0.0, 1.0)
    else:
        target = str(raw or cause or "none").strip().lower()
        confidence = 0.0 if target == "none" else 0.5
    aliases = {
        "user_fault": "user",
        "bot_whim": "bot",
        "bot_misread": "bot",
        "both": "mutual",
        "mixed": "mutual",
        "environment": "external",
    }
    target = aliases.get(target, target)
    if target not in {"user", "bot", "mutual", "external", "ambiguous", "none"}:
        target = "none"
        confidence = 0.0
    return {"target": target, "confidence": confidence}


def normalize_apology_completeness(raw: Any) -> dict[str, float]:
    raw = raw if isinstance(raw, dict) else {}
    values = {
        "responsibility_acknowledgement": clamp(
            _as_float(raw.get("responsibility_acknowledgement"), 0.0),
            0.0,
            1.0,
        ),
        "harm_acknowledgement": clamp(
            _as_float(raw.get("harm_acknowledgement"), 0.0),
            0.0,
            1.0,
        ),
        "remorse": clamp(_as_float(raw.get("remorse"), 0.0), 0.0, 1.0),
        "repair_offer": clamp(_as_float(raw.get("repair_offer"), 0.0), 0.0, 1.0),
        "future_commitment": clamp(
            _as_float(raw.get("future_commitment"), 0.0),
            0.0,
            1.0,
        ),
    }
    values["completeness_score"] = clamp(
        0.24 * values["responsibility_acknowledgement"]
        + 0.18 * values["harm_acknowledgement"]
        + 0.18 * values["remorse"]
        + 0.24 * values["repair_offer"]
        + 0.16 * values["future_commitment"],
        0.0,
        1.0,
    )
    return values


def normalize_evidence_support(raw: Any) -> dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}
    theory = str(raw.get("primary_theory") or "unknown").strip().lower()
    aliases = {
        "emotion dynamics": "emotion_dynamics",
        "action tendency": "action_tendency",
        "forgiveness_repair": "forgiveness",
        "safety": "safety_boundary",
    }
    theory = aliases.get(theory, theory)
    if theory not in {
        "pad",
        "occ",
        "appraisal",
        "emotion_dynamics",
        "forgiveness",
        "action_tendency",
        "demand_withdraw",
        "ostracism",
        "personality",
        "affective_computing",
        "safety_boundary",
        "unknown",
    }:
        theory = "unknown"
    strength = str(raw.get("evidence_strength") or "heuristic").strip().lower()
    if strength not in {"strong", "moderate", "weak", "heuristic"}:
        strength = "heuristic"
    return {
        "primary_theory": theory,
        "citation_ids": _as_string_list(raw.get("citation_ids"), limit=12),
        "evidence_strength": strength,
        "uncertainty_reason": str(raw.get("uncertainty_reason") or "")[:240],
    }


def normalize_withdrawal_motive(value: Any) -> str:
    motive = str(value or "none").strip().lower()
    aliases = {
        "cooldown": "cooling_down",
        "cool_down": "cooling_down",
        "self-protection": "self_protection",
        "self protection": "self_protection",
        "punitive": "punishment",
        "uncertain": "uncertainty",
        "low energy": "low_energy",
    }
    motive = aliases.get(motive, motive)
    if motive not in {
        "cooling_down",
        "self_protection",
        "punishment",
        "uncertainty",
        "low_energy",
        "none",
    }:
        motive = "none"
    return motive


def normalize_conflict_analysis(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {
            "cause": "none",
            "fault_severity": 0.0,
            "user_acknowledged": False,
            "apology_sincerity": 0.0,
            "repaired": False,
            "repair_quality": 0.0,
            "repeat_offense": 0.0,
            "bot_whim_level": 0.0,
            "perceived_intentionality": 0.0,
            "responsibility_attribution": {
                "target": "none",
                "confidence": 0.0,
            },
            "controllability": 0.0,
            "norm_violation_type": [],
            "face_threat": 0.0,
            "trust_damage": 0.0,
            "expectation_violation": 0.0,
            "ambiguity_level": 0.0,
            "misread_likelihood": 0.0,
            "apology_completeness": normalize_apology_completeness(None),
            "account_plausibility": 0.0,
            "restorative_action": 0.0,
            "forgiveness_readiness": 0.0,
            "resentment_residue": 0.0,
            "withdrawal_motive": "none",
            "boundary_legitimacy": 0.0,
            "emotion_regulation_load": 0.0,
            "dialogue_viability": 0.0,
            "confrontation_readiness": 0.0,
            "cold_war_readiness": 0.0,
            "unfair_argument_risk": 0.0,
            "confrontation_motive": "none",
            "evidence": normalize_evidence_support(None),
            "repair_status": "unresolved",
            "repair_signal": 0.0,
            "grievance_score": 0.0,
            "self_correction_score": 0.0,
            "reason": "",
        }
    cause = str(raw.get("cause") or "none").strip().lower()
    aliases = {
        "user": "user_fault",
        "user_error": "user_fault",
        "bot": "bot_whim",
        "bot_fault": "bot_whim",
        "bot_misunderstanding": "bot_misread",
        "both": "mutual",
        "environment": "external",
    }
    cause = aliases.get(cause, cause)
    if cause not in {"user_fault", "bot_whim", "bot_misread", "mutual", "external", "none"}:
        cause = "none"
    fault_severity = clamp(_as_float(raw.get("fault_severity"), 0.0), 0.0, 1.0)
    user_acknowledged = bool(raw.get("user_acknowledged", False))
    apology_sincerity = clamp(
        _as_float(raw.get("apology_sincerity"), 0.0),
        0.0,
        1.0,
    )
    repaired = bool(raw.get("repaired", False))
    repair_quality = clamp(_as_float(raw.get("repair_quality"), 0.0), 0.0, 1.0)
    repeat_offense = clamp(_as_float(raw.get("repeat_offense"), 0.0), 0.0, 1.0)
    bot_whim_level = clamp(_as_float(raw.get("bot_whim_level"), 0.0), 0.0, 1.0)
    perceived_intentionality = clamp(
        _as_float(raw.get("perceived_intentionality"), 0.0),
        0.0,
        1.0,
    )
    responsibility_attribution = normalize_responsibility_attribution(
        raw.get("responsibility_attribution"),
        cause,
    )
    controllability = clamp(_as_float(raw.get("controllability"), 0.0), 0.0, 1.0)
    norm_violation_type = _as_string_list(raw.get("norm_violation_type"), limit=8)
    face_threat = clamp(_as_float(raw.get("face_threat"), 0.0), 0.0, 1.0)
    trust_damage = clamp(_as_float(raw.get("trust_damage"), 0.0), 0.0, 1.0)
    expectation_violation = clamp(
        _as_float(raw.get("expectation_violation"), 0.0),
        0.0,
        1.0,
    )
    ambiguity_level = clamp(_as_float(raw.get("ambiguity_level"), 0.0), 0.0, 1.0)
    misread_likelihood = clamp(
        _as_float(raw.get("misread_likelihood"), 0.0),
        0.0,
        1.0,
    )
    apology_completeness = normalize_apology_completeness(
        raw.get("apology_completeness"),
    )
    account_plausibility = clamp(
        _as_float(raw.get("account_plausibility"), 0.0),
        0.0,
        1.0,
    )
    restorative_action = clamp(
        _as_float(raw.get("restorative_action"), 0.0),
        0.0,
        1.0,
    )
    raw_forgiveness_readiness = clamp(
        _as_float(raw.get("forgiveness_readiness"), 0.0),
        0.0,
        1.0,
    )
    withdrawal_motive = normalize_withdrawal_motive(raw.get("withdrawal_motive"))
    boundary_legitimacy = clamp(
        _as_float(raw.get("boundary_legitimacy"), 0.0),
        0.0,
        1.0,
    )
    emotion_regulation_load = clamp(
        _as_float(raw.get("emotion_regulation_load"), 0.0),
        0.0,
        1.0,
    )
    raw_dialogue_viability = raw.get("dialogue_viability")
    evidence = normalize_evidence_support(raw.get("evidence"))
    repair_signal = max(
        apology_sincerity if user_acknowledged else 0.0,
        repair_quality if repaired else 0.0,
        apology_completeness["completeness_score"],
        restorative_action,
    )
    forgiveness_readiness = clamp(
        max(
            raw_forgiveness_readiness,
            0.62 * repair_signal
            + 0.18 * account_plausibility
            + 0.20 * restorative_action
            - 0.22 * repeat_offense
            - 0.18 * trust_damage,
        ),
        0.0,
        1.0,
    )
    raw_resentment_residue = raw.get("resentment_residue")
    resentment_residue = clamp(
        _as_float(raw_resentment_residue, -1.0)
        if raw_resentment_residue is not None
        else 0.42 * trust_damage
        + 0.22 * repeat_offense
        + 0.18 * face_threat
        + 0.18 * expectation_violation
        - 0.36 * repair_signal
        - 0.22 * forgiveness_readiness,
        0.0,
        1.0,
    )
    repair_status = derive_repair_status(
        user_acknowledged=user_acknowledged,
        apology_sincerity=apology_sincerity,
        repaired=repaired,
        repair_quality=repair_quality,
        restorative_action=restorative_action,
        apology_completeness_score=apology_completeness["completeness_score"],
    )
    grievance_score = clamp(
        0.55 * fault_severity
        + 0.18 * perceived_intentionality
        + 0.16 * controllability
        + 0.16 * trust_damage
        + 0.12 * face_threat
        + 0.10 * expectation_violation
        + 0.16 * boundary_legitimacy
        + 0.20 * repeat_offense
        + 0.14 * resentment_residue
        - 0.40 * repair_signal
        - 0.24 * forgiveness_readiness
        - 0.30 * misread_likelihood
        - 0.18 * ambiguity_level,
        0.0,
        1.0,
    )
    dialogue_viability = clamp(
        _as_float(raw_dialogue_viability, -1.0)
        if raw_dialogue_viability is not None
        else 0.30
        + 0.26 * forgiveness_readiness
        + 0.20 * repair_signal
        + 0.16 * account_plausibility
        + 0.14 * restorative_action
        - 0.22 * trust_damage
        - 0.18 * emotion_regulation_load
        - 0.16 * ambiguity_level,
        0.0,
        1.0,
    )
    confrontation_readiness = clamp(
        0.40 * grievance_score
        + 0.18 * boundary_legitimacy
        + 0.16 * perceived_intentionality
        + 0.14 * controllability
        + 0.14 * dialogue_viability
        + 0.12 * face_threat
        - 0.30 * repair_signal
        - 0.24 * misread_likelihood
        - 0.20 * ambiguity_level
        - 0.18 * bot_whim_level,
        0.0,
        1.0,
    )
    cold_war_readiness = clamp(
        0.32 * resentment_residue
        + 0.24 * trust_damage
        + 0.22 * emotion_regulation_load
        + 0.16 * repeat_offense
        + 0.12 * (1.0 - dialogue_viability)
        - 0.26 * repair_signal
        - 0.20 * forgiveness_readiness
        - 0.18 * misread_likelihood
        - 0.14 * ambiguity_level,
        0.0,
        1.0,
    )
    unfair_argument_risk = clamp(
        0.34 * bot_whim_level
        + 0.24 * emotion_regulation_load
        + 0.20 * misread_likelihood
        + 0.16 * ambiguity_level
        + 0.12 * face_threat
        - 0.24 * repair_signal
        - 0.18 * forgiveness_readiness,
        0.0,
        1.0,
    )
    raw_motive = str(raw.get("confrontation_motive") or "").strip().lower()
    motive_aliases = {
        "truth": "truth_seeking",
        "clarification": "truth_seeking",
        "boundary": "boundary_defense",
        "accountability": "accountability_request",
        "punitive": "punishment",
    }
    confrontation_motive = motive_aliases.get(raw_motive, raw_motive)
    if confrontation_motive not in {
        "truth_seeking",
        "boundary_defense",
        "accountability_request",
        "punishment",
        "none",
    }:
        if confrontation_readiness >= 0.45 and boundary_legitimacy >= 0.55:
            confrontation_motive = "boundary_defense"
        elif confrontation_readiness >= 0.45 and perceived_intentionality >= 0.45:
            confrontation_motive = "accountability_request"
        elif ambiguity_level >= 0.35 or misread_likelihood >= 0.35:
            confrontation_motive = "truth_seeking"
        else:
            confrontation_motive = "none"
    self_correction_score = max(
        bot_whim_level if cause in {"bot_whim", "bot_misread"} else 0.0,
        misread_likelihood if cause in {"bot_whim", "bot_misread", "mutual"} else 0.0,
        repair_signal if cause in {"mutual", "user_fault"} else 0.0,
        forgiveness_readiness if cause in {"mutual", "user_fault"} else 0.0,
    )
    return {
        "cause": cause,
        "fault_severity": fault_severity,
        "user_acknowledged": user_acknowledged,
        "apology_sincerity": apology_sincerity,
        "repaired": repaired,
        "repair_quality": repair_quality,
        "repeat_offense": repeat_offense,
        "bot_whim_level": bot_whim_level,
        "perceived_intentionality": perceived_intentionality,
        "responsibility_attribution": responsibility_attribution,
        "controllability": controllability,
        "norm_violation_type": norm_violation_type,
        "face_threat": face_threat,
        "trust_damage": trust_damage,
        "expectation_violation": expectation_violation,
        "ambiguity_level": ambiguity_level,
        "misread_likelihood": misread_likelihood,
        "apology_completeness": apology_completeness,
        "account_plausibility": account_plausibility,
        "restorative_action": restorative_action,
        "forgiveness_readiness": forgiveness_readiness,
        "resentment_residue": resentment_residue,
        "withdrawal_motive": withdrawal_motive,
        "boundary_legitimacy": boundary_legitimacy,
        "emotion_regulation_load": emotion_regulation_load,
        "dialogue_viability": dialogue_viability,
        "confrontation_readiness": confrontation_readiness,
        "cold_war_readiness": cold_war_readiness,
        "unfair_argument_risk": unfair_argument_risk,
        "confrontation_motive": confrontation_motive,
        "evidence": evidence,
        "repair_status": repair_status,
        "repair_signal": repair_signal,
        "grievance_score": grievance_score,
        "self_correction_score": self_correction_score,
        "reason": str(raw.get("reason") or "")[:240],
    }


def derive_repair_status(
    *,
    user_acknowledged: bool,
    apology_sincerity: float,
    repaired: bool,
    repair_quality: float,
    restorative_action: float = 0.0,
    apology_completeness_score: float = 0.0,
) -> str:
    repair_strength = max(repair_quality, restorative_action)
    apology_strength = max(apology_sincerity, apology_completeness_score)
    if repaired and repair_strength >= 0.85 and apology_strength >= 0.65:
        return "restored"
    if repaired and repair_strength >= 0.45:
        return "repaired"
    if user_acknowledged and apology_strength >= 0.65:
        return "apologized"
    if user_acknowledged:
        return "acknowledged"
    return "unresolved"


def apply_relationship_decision(
    decision_payload: dict[str, Any],
    conflict_payload: dict[str, Any],
    impulses: dict[str, float],
    effects: dict[str, float],
    notes: list[str],
    *,
    cold_duration: float,
    short_duration: float,
    strength: float,
    persona_argument_bias: float = 0.0,
    persona_cold_bias: float = 0.0,
    persona_repair_bias: float = 0.0,
    persona_unfair_argument_bias: float = 0.0,
    persona_checking_bias: float = 0.0,
) -> None:
    decision = str(decision_payload.get("decision") or "none")
    if decision == "none":
        return

    intensity = clamp(_as_float(decision_payload.get("intensity"), 0.0), 0.0, 1.0)
    forgiveness = clamp(_as_float(decision_payload.get("forgiveness"), 0.0), 0.0, 1.0)
    relationship_importance = clamp(
        _as_float(decision_payload.get("relationship_importance"), 0.0),
        0.0,
        1.0,
    )
    reason = str(decision_payload.get("reason") or "")
    cause = str(conflict_payload.get("cause") or "none")
    fault_severity = clamp(_as_float(conflict_payload.get("fault_severity"), 0.0), 0.0, 1.0)
    apology_sincerity = clamp(
        _as_float(conflict_payload.get("apology_sincerity"), 0.0),
        0.0,
        1.0,
    )
    repair_quality = clamp(_as_float(conflict_payload.get("repair_quality"), 0.0), 0.0, 1.0)
    repeat_offense = clamp(_as_float(conflict_payload.get("repeat_offense"), 0.0), 0.0, 1.0)
    bot_whim_level = clamp(_as_float(conflict_payload.get("bot_whim_level"), 0.0), 0.0, 1.0)
    trust_damage = clamp(_as_float(conflict_payload.get("trust_damage"), 0.0), 0.0, 1.0)
    ambiguity_level = clamp(_as_float(conflict_payload.get("ambiguity_level"), 0.0), 0.0, 1.0)
    misread_likelihood = clamp(
        _as_float(conflict_payload.get("misread_likelihood"), 0.0),
        0.0,
        1.0,
    )
    forgiveness_readiness = clamp(
        _as_float(conflict_payload.get("forgiveness_readiness"), 0.0),
        0.0,
        1.0,
    )
    resentment_residue = clamp(
        _as_float(conflict_payload.get("resentment_residue"), 0.0),
        0.0,
        1.0,
    )
    boundary_legitimacy = clamp(
        _as_float(conflict_payload.get("boundary_legitimacy"), 0.0),
        0.0,
        1.0,
    )
    emotion_regulation_load = clamp(
        _as_float(conflict_payload.get("emotion_regulation_load"), 0.0),
        0.0,
        1.0,
    )
    dialogue_viability = clamp(_as_float(conflict_payload.get("dialogue_viability"), 0.0), 0.0, 1.0)
    confrontation_readiness = clamp(
        _as_float(conflict_payload.get("confrontation_readiness"), 0.0),
        0.0,
        1.0,
    )
    cold_war_readiness = clamp(_as_float(conflict_payload.get("cold_war_readiness"), 0.0), 0.0, 1.0)
    unfair_argument_risk = clamp(
        _as_float(conflict_payload.get("unfair_argument_risk"), 0.0),
        0.0,
        1.0,
    )
    confrontation_motive = str(conflict_payload.get("confrontation_motive") or "none")
    withdrawal_motive = normalize_withdrawal_motive(
        conflict_payload.get("withdrawal_motive"),
    )
    user_acknowledged = bool(conflict_payload.get("user_acknowledged", False))
    repaired = bool(conflict_payload.get("repaired", False))
    repair_signal = max(
        apology_sincerity if user_acknowledged else 0.0,
        repair_quality if repaired else 0.0,
    )
    legitimate_grievance = clamp(
        _as_float(conflict_payload.get("grievance_score"), 0.0)
        or fault_severity * (1.0 - repair_signal) + 0.35 * repeat_offense,
        0.0,
        1.0,
    )
    self_correction = max(
        _as_float(conflict_payload.get("self_correction_score"), 0.0),
        bot_whim_level if cause in {"bot_whim", "bot_misread"} else 0.0,
        repair_signal if cause in {"mutual", "user_fault"} else 0.0,
    )
    caution_load = max(ambiguity_level, trust_damage, resentment_residue)
    repair_readiness = max(repair_signal, forgiveness_readiness, self_correction)

    def add(key: str, amount: float) -> None:
        impulses[key] = clamp(impulses.get(key, 0.0) + amount * strength, 0.0, 1.0)

    def reduce(key: str, amount: float) -> None:
        impulses[key] = clamp(impulses.get(key, 0.0) - amount * strength, 0.0, 1.0)

    if decision == "forgive":
        relief = clamp(
            max(intensity, forgiveness, repair_readiness) + 0.20 * self_correction,
            0.0,
            1.0,
        )
        add("repair", 0.35 + 0.45 * relief)
        add("approach", 0.20 + 0.30 * relationship_importance)
        add("problem_solving", 0.15 + 0.20 * relief)
        add("caution", 0.08 * resentment_residue)
        reduce("withdrawal", 0.65 * relief)
        reduce("confrontation", 0.55 * relief)
        reduce("argument", 0.60 * relief)
        reduce("rumination", 0.55 * relief)
        effects["repair_bid"] = max(effects.get("repair_bid", 0.0), short_duration)
        effects.pop("cold_war", None)
        notes.append(f"LLM 关系判断：倾向原谅/翻篇。{reason}")
        if conflict_payload.get("reason"):
            notes.append(f"冲突原因判断：{conflict_payload['reason']}")
        return

    if decision == "repair":
        add("repair", 0.45 + 0.35 * max(intensity, repair_readiness))
        add("reassurance", 0.20 + 0.25 * relationship_importance)
        add("caution", 0.16 + 0.18 * max(1.0 - forgiveness, caution_load))
        reduce("withdrawal", 0.25 * max(forgiveness, relationship_importance, repair_readiness))
        reduce("argument", 0.20 * max(forgiveness, repair_readiness))
        effects["repair_bid"] = max(effects.get("repair_bid", 0.0), short_duration)
        notes.append(f"LLM 关系判断：愿意修复但需要确认。{reason}")
        return

    if decision == "boundary":
        boundary_force = clamp(
            max(intensity, legitimate_grievance, boundary_legitimacy)
            - 0.25 * max(bot_whim_level, misread_likelihood, ambiguity_level),
            0.0,
            1.0,
        )
        add("confrontation", 0.38 + 0.45 * boundary_force)
        add("caution", 0.20 + 0.20 * max(intensity, caution_load))
        add("problem_solving", 0.15 + 0.20 * relationship_importance)
        if boundary_force >= 0.62 and dialogue_viability >= 0.35:
            add("argument", 0.15 + 0.26 * boundary_force + 0.12 * persona_argument_bias)
            effects["direct_confrontation"] = max(
                effects.get("direct_confrontation", 0.0),
                max(1.0, short_duration * 0.65),
            )
        effects["direct_boundary"] = max(
            effects.get("direct_boundary", 0.0),
            short_duration,
        )
        notes.append(f"LLM 关系判断：设边界但不必冷战。{reason}")
        return

    if decision == "confront":
        confront_force = clamp(
            max(intensity, confrontation_readiness, legitimate_grievance, boundary_legitimacy)
            + 0.16 * persona_argument_bias
            - 0.34 * max(self_correction, misread_likelihood, ambiguity_level)
            - 0.20 * persona_repair_bias * repair_readiness,
            0.0,
            1.0,
        )
        overreaction_pressure = clamp(
            max(unfair_argument_risk, bot_whim_level, misread_likelihood, ambiguity_level)
            + 0.18 * persona_unfair_argument_bias
            - 0.14 * persona_checking_bias
            - 0.16 * persona_repair_bias,
            0.0,
            1.0,
        )
        if overreaction_pressure >= 0.45 and max(misread_likelihood, ambiguity_level, bot_whim_level) >= 0.35:
            add(
                "argument",
                0.14
                + 0.24 * overreaction_pressure
                + 0.10 * persona_argument_bias
                + 0.10 * persona_unfair_argument_bias,
            )
            add(
                "caution",
                0.20
                + 0.22 * max(misread_likelihood, ambiguity_level)
                + 0.08 * persona_checking_bias,
            )
            add(
                "repair",
                0.18
                + 0.24 * max(bot_whim_level, self_correction, persona_repair_bias),
            )
            effects["unfair_argument"] = max(
                effects.get("unfair_argument", 0.0),
                max(1.0, short_duration * 0.5),
            )
            effects["careful_checking"] = max(
                effects.get("careful_checking", 0.0),
                short_duration,
            )
            effects.pop("cold_war", None)
            notes.append(f"LLM 关系判断：可能出现无理取闹式争辩，需先核对并保留自我修正。{reason}")
            return
        if confront_force < 0.30 or dialogue_viability < 0.25:
            if cold_war_readiness + 0.12 * persona_cold_bias > confront_force:
                add("withdrawal", 0.26 + 0.34 * max(cold_war_readiness, emotion_regulation_load))
                add("caution", 0.16 + 0.16 * caution_load)
                notes.append(f"LLM 关系判断原为对质，但对话可行性不足，转向降频和边界。{reason}")
            else:
                add("caution", 0.22 + 0.24 * max(ambiguity_level, misread_likelihood))
                effects["careful_checking"] = max(effects.get("careful_checking", 0.0), short_duration)
                notes.append(f"LLM 关系判断原为对质，但证据不足，先求证。{reason}")
            return
        add("confrontation", 0.36 + 0.34 * confront_force)
        add("argument", 0.28 + 0.42 * confront_force)
        add("expressiveness", 0.18 + 0.26 * confront_force)
        add("problem_solving", 0.14 + 0.22 * max(dialogue_viability, relationship_importance))
        add("caution", 0.08 + 0.16 * max(ambiguity_level, trust_damage))
        effects["direct_confrontation"] = max(
            effects.get("direct_confrontation", 0.0),
            short_duration,
        )
        effects["direct_boundary"] = max(effects.get("direct_boundary", 0.0), short_duration)
        effects.pop("cold_war", None)
        notes.append(
            f"LLM 关系判断：直接对质/争辩，动机={confrontation_motive}，仍需避免升级。{reason}",
        )
        return

    if decision == "cold_war":
        cold_force = clamp(
            max(
                intensity,
                legitimate_grievance,
                0.55 * emotion_regulation_load,
                0.40 * trust_damage,
            )
            + 0.10 * persona_cold_bias
            - 0.45 * max(self_correction, misread_likelihood, forgiveness_readiness),
            0.0,
            1.0,
        )
        if withdrawal_motive in {"uncertainty", "cooling_down", "low_energy"}:
            cold_force = clamp(cold_force - 0.18, 0.0, 1.0)
        elif withdrawal_motive == "punishment":
            cold_force = clamp(cold_force + 0.10 * legitimate_grievance, 0.0, 1.0)
        if cold_force < 0.25:
            relief = max(self_correction, repair_signal, bot_whim_level, misread_likelihood)
            add("repair", 0.35 + 0.30 * self_correction)
            add("caution", 0.18 + 0.18 * ambiguity_level)
            reduce("withdrawal", 0.50 * relief)
            reduce("rumination", 0.45 * relief)
            reduce("confrontation", 0.35 * relief)
            reduce("argument", 0.35 * relief)
            effects["repair_bid"] = max(effects.get("repair_bid", 0.0), short_duration)
            effects.pop("cold_war", None)
            notes.append(f"LLM 关系判断原为冷处理，但错误已被修复或属于他/她任性，转向修复。{reason}")
            return
        add("withdrawal", 0.45 + 0.45 * cold_force + 0.10 * persona_cold_bias)
        add("rumination", 0.22 + 0.35 * cold_force)
        reduce("argument", 0.28 * cold_force)
        reduce("approach", 0.35 * cold_force)
        effects["cold_war"] = max(
            effects.get("cold_war", 0.0),
            cold_duration * (0.75 + 0.75 * cold_force),
        )
        notes.append(f"LLM 关系判断：暂时冷处理/拉开距离。{reason}")
        if conflict_payload.get("reason"):
            notes.append(f"冲突原因判断：{conflict_payload['reason']}")
        return

    if decision == "escalate":
        escalation_force = clamp(
            max(intensity, legitimate_grievance, boundary_legitimacy)
            - 0.35 * max(self_correction, misread_likelihood, ambiguity_level),
            0.0,
            1.0,
        )
        add("confrontation", 0.55 + 0.45 * escalation_force)
        add("argument", 0.32 + 0.34 * escalation_force)
        add("expressiveness", 0.30 + 0.35 * escalation_force)
        add("rumination", 0.25 + 0.30 * escalation_force)
        effects["direct_confrontation"] = max(
            effects.get("direct_confrontation", 0.0),
            short_duration,
        )
        effects["direct_boundary"] = max(
            effects.get("direct_boundary", 0.0),
            short_duration,
        )
        notes.append(f"LLM 关系判断：冲突升级/强烈防御。{reason}")


def apply_conflict_analysis(
    conflict_payload: dict[str, Any],
    impulses: dict[str, float],
    effects: dict[str, float],
    notes: list[str],
    *,
    short_duration: float,
    strength: float,
    persona_argument_bias: float = 0.0,
    persona_cold_bias: float = 0.0,
    persona_repair_bias: float = 0.0,
    persona_unfair_argument_bias: float = 0.0,
    persona_checking_bias: float = 0.0,
) -> None:
    cause = str(conflict_payload.get("cause") or "none")
    if cause == "none":
        return
    fault_severity = clamp(_as_float(conflict_payload.get("fault_severity"), 0.0), 0.0, 1.0)
    repeat_offense = clamp(_as_float(conflict_payload.get("repeat_offense"), 0.0), 0.0, 1.0)
    bot_whim_level = clamp(_as_float(conflict_payload.get("bot_whim_level"), 0.0), 0.0, 1.0)
    repair_signal = clamp(_as_float(conflict_payload.get("repair_signal"), 0.0), 0.0, 1.0)
    grievance = clamp(_as_float(conflict_payload.get("grievance_score"), 0.0), 0.0, 1.0)
    perceived_intentionality = clamp(
        _as_float(conflict_payload.get("perceived_intentionality"), 0.0),
        0.0,
        1.0,
    )
    trust_damage = clamp(_as_float(conflict_payload.get("trust_damage"), 0.0), 0.0, 1.0)
    ambiguity_level = clamp(_as_float(conflict_payload.get("ambiguity_level"), 0.0), 0.0, 1.0)
    misread_likelihood = clamp(
        _as_float(conflict_payload.get("misread_likelihood"), 0.0),
        0.0,
        1.0,
    )
    forgiveness_readiness = clamp(
        _as_float(conflict_payload.get("forgiveness_readiness"), 0.0),
        0.0,
        1.0,
    )
    resentment_residue = clamp(
        _as_float(conflict_payload.get("resentment_residue"), 0.0),
        0.0,
        1.0,
    )
    boundary_legitimacy = clamp(
        _as_float(conflict_payload.get("boundary_legitimacy"), 0.0),
        0.0,
        1.0,
    )
    emotion_regulation_load = clamp(
        _as_float(conflict_payload.get("emotion_regulation_load"), 0.0),
        0.0,
        1.0,
    )
    dialogue_viability = clamp(_as_float(conflict_payload.get("dialogue_viability"), 0.0), 0.0, 1.0)
    confrontation_readiness = clamp(
        _as_float(conflict_payload.get("confrontation_readiness"), 0.0),
        0.0,
        1.0,
    )
    cold_war_readiness = clamp(_as_float(conflict_payload.get("cold_war_readiness"), 0.0), 0.0, 1.0)
    unfair_argument_risk = clamp(
        _as_float(conflict_payload.get("unfair_argument_risk"), 0.0),
        0.0,
        1.0,
    )
    withdrawal_motive = normalize_withdrawal_motive(conflict_payload.get("withdrawal_motive"))
    self_correction = clamp(
        _as_float(conflict_payload.get("self_correction_score"), 0.0),
        0.0,
        1.0,
    )

    def add(key: str, amount: float) -> None:
        impulses[key] = clamp(impulses.get(key, 0.0) + amount * strength, 0.0, 1.0)

    def reduce(key: str, amount: float) -> None:
        impulses[key] = clamp(impulses.get(key, 0.0) - amount * strength, 0.0, 1.0)

    if cause == "user_fault" and grievance >= 0.35:
        add("confrontation", 0.20 + 0.35 * max(grievance, boundary_legitimacy))
        if confrontation_readiness >= 0.45 and dialogue_viability >= 0.28:
            add(
                "argument",
                0.14
                + 0.28 * confrontation_readiness
                + 0.14 * persona_argument_bias,
            )
            effects["direct_confrontation"] = max(
                effects.get("direct_confrontation", 0.0),
                max(1.0, short_duration * 0.65),
            )
        add("caution", 0.18 + 0.20 * max(repeat_offense, trust_damage))
        add("rumination", 0.10 + 0.22 * max(grievance, resentment_residue))
        effects["direct_boundary"] = max(
            effects.get("direct_boundary", 0.0),
            short_duration,
        )
        notes.append("冲突原因显示用户错误仍未充分修复，边界和谨慎倾向上升。")
    elif cause == "mutual" and grievance >= 0.25:
        add("repair", 0.24 + 0.26 * max(repair_signal, self_correction, forgiveness_readiness))
        add("caution", 0.16 + 0.18 * max(fault_severity, ambiguity_level))
        reduce("confrontation", 0.18 * max(repair_signal, self_correction, misread_likelihood))
        reduce("argument", 0.22 * max(repair_signal, self_correction, misread_likelihood))
        effects["careful_checking"] = max(
            effects.get("careful_checking", 0.0),
            short_duration,
        )
        notes.append("冲突原因偏双方共同作用，优先求证和修复。")
    elif cause in {"bot_whim", "bot_misread"}:
        correction = max(bot_whim_level, self_correction, misread_likelihood)
        add("repair", 0.24 + 0.34 * correction)
        add("caution", 0.18 + 0.18 * max(bot_whim_level, ambiguity_level))
        reduce("withdrawal", 0.42 * correction)
        reduce("rumination", 0.38 * correction)
        reduce("confrontation", 0.30 * correction)
        reduce("argument", 0.34 * correction)
        overreaction_pressure = clamp(
            unfair_argument_risk
            + 0.16 * persona_unfair_argument_bias
            - 0.10 * persona_checking_bias
            - 0.14 * persona_repair_bias,
            0.0,
            1.0,
        )
        if overreaction_pressure >= 0.45:
            add(
                "argument",
                0.12
                + 0.24 * overreaction_pressure
                + 0.10 * persona_argument_bias
                + 0.08 * persona_unfair_argument_bias,
            )
            effects["unfair_argument"] = max(
                effects.get("unfair_argument", 0.0),
                max(1.0, short_duration * 0.5),
            )
        effects.pop("cold_war", None)
        effects["careful_checking"] = max(
            effects.get("careful_checking", 0.0),
            short_duration,
        )
        notes.append("冲突原因偏他/她任性或误读，抑制冷处理并转向核对与修复。")
    elif cause == "external":
        add("problem_solving", 0.20 + 0.20 * fault_severity)
        add("caution", 0.12 + 0.18 * fault_severity)
        reduce("confrontation", 0.18)
        notes.append("冲突原因偏外部环境，优先问题解决而不是归责。")

    if ambiguity_level >= 0.55 or misread_likelihood >= 0.45:
        add("caution", 0.18 + 0.25 * max(ambiguity_level, misread_likelihood))
        add("reassurance", 0.16 + 0.20 * ambiguity_level)
        reduce("confrontation", 0.25 * max(ambiguity_level, misread_likelihood))
        reduce("argument", 0.32 * max(ambiguity_level, misread_likelihood))
        effects["careful_checking"] = max(
            effects.get("careful_checking", 0.0),
            short_duration,
        )
        effects.pop("cold_war", None)
        notes.append("语义或动机仍不确定时，优先核对而不是惩罚性疏离。")

    if trust_damage >= 0.45 or resentment_residue >= 0.45:
        add("caution", 0.12 + 0.22 * max(trust_damage, resentment_residue))
        add("rumination", 0.08 + 0.18 * resentment_residue)
        add(
            "withdrawal",
            0.08
            + 0.14 * max(trust_damage, emotion_regulation_load, cold_war_readiness)
            + 0.08 * persona_cold_bias,
        )
        notes.append("信任损伤或残留委屈会延长谨慎和反刍，但仍受真实时间衰减。")

    if withdrawal_motive in {"cooling_down", "self_protection", "low_energy"}:
        add("withdrawal", 0.10 + 0.22 * emotion_regulation_load)
        add("caution", 0.08 + 0.12 * ambiguity_level)
    elif withdrawal_motive == "punishment":
        add("confrontation", 0.10 + 0.18 * max(perceived_intentionality, grievance))
        add("argument", 0.08 + 0.16 * max(perceived_intentionality, grievance))
        add("rumination", 0.08 + 0.18 * grievance)

    if repair_signal >= 0.55:
        repair_relief = max(repair_signal, forgiveness_readiness)
        add("repair", 0.22 + 0.28 * repair_relief)
        add("approach", 0.12 + 0.20 * repair_relief)
        reduce("withdrawal", 0.42 * repair_relief)
        reduce("rumination", 0.36 * repair_relief)
        reduce("confrontation", 0.28 * repair_relief)
        reduce("argument", 0.34 * repair_relief)
        effects["repair_bid"] = max(effects.get("repair_bid", 0.0), short_duration)
        notes.append(f"错误修复状态为 {conflict_payload.get('repair_status')}，负面后果开始回落。")


def should_clear_cold_war(observation: EmotionObservation) -> bool:
    payload = normalize_relationship_decision(
        observation.appraisal.get("relationship_decision"),
    )
    decision = payload.get("decision")
    forgiveness = clamp(_as_float(payload.get("forgiveness"), 0.0), 0.0, 1.0)
    intensity = clamp(_as_float(payload.get("intensity"), 0.0), 0.0, 1.0)
    if decision == "forgive" and max(forgiveness, intensity) >= 0.45:
        return True
    if decision == "repair" and forgiveness >= 0.7:
        return True
    conflict = normalize_conflict_analysis(
        observation.appraisal.get("conflict_analysis"),
    )
    if conflict["cause"] in {"bot_whim", "bot_misread"} and conflict["bot_whim_level"] >= 0.65:
        return True
    if max(conflict["misread_likelihood"], conflict["ambiguity_level"]) >= 0.75:
        return True
    if conflict["forgiveness_readiness"] >= 0.75 and conflict["repair_signal"] >= 0.55:
        return True
    if decision == "cold_war":
        repair_signal = max(
            conflict["apology_sincerity"] if conflict["user_acknowledged"] else 0.0,
            conflict["repair_quality"] if conflict["repaired"] else 0.0,
        )
        if max(
            repair_signal,
            conflict["bot_whim_level"],
            conflict["misread_likelihood"],
            conflict["forgiveness_readiness"],
        ) >= 0.75:
            return True
    return False


def apply_relationship_value_reductions(
    observation: EmotionObservation,
    values: dict[str, float],
) -> None:
    payload = normalize_relationship_decision(
        observation.appraisal.get("relationship_decision"),
    )
    decision = payload.get("decision")
    forgiveness = clamp(_as_float(payload.get("forgiveness"), 0.0), 0.0, 1.0)
    intensity = clamp(_as_float(payload.get("intensity"), 0.0), 0.0, 1.0)
    relief = max(forgiveness, intensity)
    if decision == "forgive" and relief >= 0.35:
        for key, amount in {
            "withdrawal": 0.65,
            "confrontation": 0.55,
            "rumination": 0.60,
            "caution": 0.20,
        }.items():
            values[key] = clamp(values.get(key, 0.0) * (1.0 - amount * relief), 0.0, 1.0)
    elif decision == "repair" and forgiveness >= 0.7:
        for key, amount in {"withdrawal": 0.35, "rumination": 0.30}.items():
            values[key] = clamp(
                values.get(key, 0.0) * (1.0 - amount * forgiveness),
                0.0,
                1.0,
            )
    conflict = normalize_conflict_analysis(
        observation.appraisal.get("conflict_analysis"),
    )
    repair_signal = clamp(_as_float(conflict.get("repair_signal"), 0.0), 0.0, 1.0)
    self_correction = clamp(
        _as_float(conflict.get("self_correction_score"), 0.0),
        0.0,
        1.0,
    )
    relief = max(repair_signal, self_correction)
    if relief >= 0.55:
        for key, amount in {
            "withdrawal": 0.50,
            "rumination": 0.34,
            "confrontation": 0.30,
        }.items():
            values[key] = clamp(
                values.get(key, 0.0) * (1.0 - amount * relief),
                0.0,
                1.0,
            )
    uncertainty_relief = max(
        _as_float(conflict.get("misread_likelihood"), 0.0),
        _as_float(conflict.get("ambiguity_level"), 0.0),
    )
    if uncertainty_relief >= 0.55:
        for key, amount in {"confrontation": 0.40, "withdrawal": 0.24}.items():
            values[key] = clamp(
                values.get(key, 0.0) * (1.0 - amount * uncertainty_relief),
                0.0,
                1.0,
            )
    resentment_floor = clamp(
        0.12 * _as_float(conflict.get("resentment_residue"), 0.0)
        + 0.08 * _as_float(conflict.get("trust_damage"), 0.0),
        0.0,
        0.16,
    )
    if resentment_floor > 0:
        values["rumination"] = max(values.get("rumination", 0.0), resentment_floor)


def extract_json_object(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.S)
    candidates = [fenced.group(1)] if fenced else []
    first = text.find("{")
    last = text.rfind("}")
    if first != -1 and last != -1 and last > first:
        candidates.append(text[first : last + 1])
    candidates.append(text)
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def observation_from_mapping(data: dict[str, Any]) -> EmotionObservation:
    raw_values = (
        data.get("dimensions")
        or data.get("pad")
        or data.get("emotion")
        or data.get("values")
        or data
    )
    confidence = clamp(_as_float(data.get("confidence"), 0.35), 0.0, 1.0)
    label = str(data.get("label") or data.get("category") or "unknown")
    reason = str(data.get("reason") or data.get("rationale") or "")
    appraisal = data.get("appraisal") if isinstance(data.get("appraisal"), dict) else {}
    return EmotionObservation(
        values=normalize_vector(raw_values, default=0.0),
        confidence=confidence,
        label=label,
        reason=reason,
        appraisal=appraisal,
        source="llm",
    )


def observation_from_llm_text(text: str) -> EmotionObservation | None:
    parsed = extract_json_object(text)
    if not parsed:
        return None
    return observation_from_mapping(parsed)


def heuristic_observation(
    text: str,
    *,
    source: str = "heuristic",
    profile: PersonaProfile | None = None,
) -> EmotionObservation:
    normalized = (text or "").lower()
    values = (profile.baseline if profile else DEFAULT_BASELINE).copy()
    label = "neutral"
    reason = "LLM 情绪估计失败，使用轻量词面启发式回退。"

    positive = ("谢谢", "感谢", "喜欢", "开心", "太好了", "棒", "可爱", "thanks", "great")
    negative = ("讨厌", "生气", "烦", "糟糕", "错误", "骂", "hate", "angry", "bad")
    teasing = ("调侃", "害羞", "脸红", "笨蛋", "可爱", "喜欢你", "tease", "shy")
    urgent = ("快", "马上", "紧急", "急", "现在", "urgent", "asap")

    if any(token in normalized for token in positive):
        values.update(
            valence=0.34,
            arousal=0.22,
            dominance=0.08,
            goal_congruence=0.35,
            affiliation=0.38,
        )
        label = "warm"
    if any(token in normalized for token in negative):
        values.update(
            valence=-0.38,
            arousal=0.48,
            dominance=-0.12,
            goal_congruence=-0.32,
            certainty=0.08,
            affiliation=-0.28,
        )
        label = "defensive"
    if any(token in normalized for token in teasing):
        values.update(
            valence=0.05,
            arousal=0.58,
            dominance=-0.28,
            certainty=-0.12,
            control=-0.22,
            affiliation=0.2,
        )
        label = "embarrassed"
    if any(token in normalized for token in urgent):
        values["arousal"] = max(values["arousal"], 0.62)
        values["certainty"] = min(values["certainty"], -0.08)
        label = "alert"

    return EmotionObservation(
        values=values,
        confidence=0.22,
        label=label,
        reason=reason,
        appraisal={"fallback": True},
        source=source,
    )


def format_state_for_prompt(state: EmotionState) -> str:
    lines = [
        f"- persona: {state.persona_name} ({state.persona_id}, {state.persona_fingerprint})"
    ]
    personality_factors = (state.persona_model or {}).get("derived_factors") or {}
    if personality_factors:
        factor_text = ", ".join(
            f"{key}={_as_float(value):.2f}"
            for key, value in personality_factors.items()
        )
        lines.append(f"- personality_factors: {factor_text}")
    lines.extend(
        f"- {key} ({DIMENSION_LABELS[key]}): {state.values[key]:+.3f}"
        for key in DIMENSIONS
    )
    lines.append(f"- label: {state.label}")
    lines.append(f"- confidence: {state.confidence:.2f}")
    lines.append(f"- inertia: {1.0 - state.last_alpha:.2f}")
    lines.append(f"- surprise: {state.last_surprise:.3f}")
    if state.last_reason:
        lines.append(f"- last_reason: {state.last_reason[:240]}")
    relationship_decision = normalize_relationship_decision(
        state.last_appraisal.get("relationship_decision"),
    )
    if relationship_decision.get("decision") != "none":
        lines.append(
            "- relationship_decision: "
            f"{relationship_decision['decision']} "
            f"(intensity={relationship_decision['intensity']:.2f}, "
            f"forgiveness={relationship_decision['forgiveness']:.2f}, "
            f"importance={relationship_decision['relationship_importance']:.2f})"
        )
        if relationship_decision.get("reason"):
            lines.append(f"  decision_reason: {relationship_decision['reason']}")
    conflict_analysis = normalize_conflict_analysis(
        state.last_appraisal.get("conflict_analysis"),
    )
    conflict_analysis = apply_persona_to_conflict_analysis(
        conflict_analysis,
        state.persona_model,
    )
    if conflict_analysis.get("cause") != "none":
        lines.append(
            "- conflict_analysis: "
            f"cause={conflict_analysis['cause']}, "
            f"severity={conflict_analysis['fault_severity']:.2f}, "
            f"acknowledged={conflict_analysis['user_acknowledged']}, "
            f"repaired={conflict_analysis['repaired']}, "
            f"repair_quality={conflict_analysis['repair_quality']:.2f}, "
            f"bot_whim={conflict_analysis['bot_whim_level']:.2f}, "
            f"repair_status={conflict_analysis['repair_status']}, "
            f"grievance={conflict_analysis['grievance_score']:.2f}, "
            f"self_correction={conflict_analysis['self_correction_score']:.2f}, "
            f"confront_ready={conflict_analysis['confrontation_readiness']:.2f}, "
            f"cold_ready={conflict_analysis['cold_war_readiness']:.2f}, "
            f"unfair_arg_risk={conflict_analysis['unfair_argument_risk']:.2f}"
        )
        if conflict_analysis.get("reason"):
            lines.append(f"  conflict_reason: {conflict_analysis['reason']}")
    consequence_text = format_consequence_for_prompt(state.consequences)
    if consequence_text:
        lines.append(consequence_text)
    return "\n".join(lines)


def format_consequence_for_prompt(consequences: ConsequenceState) -> str:
    active = [
        f"{EFFECT_LABELS.get(key, key)}({format_duration(seconds)})"
        for key, seconds in consequences.active_effects.items()
        if seconds > 0
    ]
    values = [
        f"{key}={consequences.values.get(key, 0.0):.2f}"
        for key in CONSEQUENCE_DIMENSIONS
        if consequences.values.get(key, 0.0) >= 0.18
    ]
    if not active and not values:
        return ""
    lines = ["- consequence_state:"]
    if active:
        lines.append(f"  active_effects: {', '.join(active)}")
    if values:
        lines.append(f"  action_tendencies: {', '.join(values)}")
    if consequences.notes:
        lines.append(f"  rationale: {consequences.notes[0][:220]}")
    return "\n".join(lines)


def format_consequence_for_user(consequences: ConsequenceState) -> str:
    active = [
        f"{EFFECT_LABELS.get(key, key)}: 剩余 {format_duration(seconds)}"
        for key, seconds in consequences.active_effects.items()
        if seconds > 0
    ]
    values = "\n".join(
        f"{CONSEQUENCE_LABELS[key]}: {consequences.values.get(key, 0.0):.3f}"
        for key in CONSEQUENCE_DIMENSIONS
    )
    notes = "\n".join(f"- {note}" for note in consequences.notes[:3]) or "- 暂无明显后果。"
    return (
        "后果状态:\n"
        + ("\n".join(active) + "\n" if active else "无持续后果\n")
        + values
        + "\n后果依据:\n"
        + notes
    )


def format_state_for_user(state: EmotionState) -> str:
    values = "\n".join(
        f"{DIMENSION_LABELS[key]}: {state.values[key]:+.3f}" for key in DIMENSIONS
    )
    personality_factors = (state.persona_model or {}).get("derived_factors") or {}
    personality_text = (
        ", ".join(
            f"{key}={_as_float(value):.2f}"
            for key, value in personality_factors.items()
        )
        if personality_factors
        else "未建模"
    )
    reason = state.last_reason or "暂无最近解释。"
    return (
        f"人格: {state.persona_name} ({state.persona_id})\n"
        f"人格指纹: {state.persona_fingerprint}\n"
        f"人格量化: {personality_text}\n"
        f"情绪标签: {state.label}\n"
        f"更新轮数: {state.turns}\n"
        f"上次更新时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(state.updated_at))}\n"
        f"置信度: {state.confidence:.2f}\n"
        f"更新步长 alpha: {state.last_alpha:.3f}\n"
        f"加权惊讶度 delta: {state.last_surprise:.3f}\n"
        f"{values}\n"
        f"最近依据: {reason}\n"
        f"{format_consequence_for_user(state.consequences)}"
    )
