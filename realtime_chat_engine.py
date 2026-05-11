from __future__ import annotations

import math
import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any


PUBLIC_REALTIME_CHAT_SCHEMA_VERSION = "astrbot.realtime_chat_plan.v1"
PUBLIC_STICKER_MEMORY_SCHEMA_VERSION = "astrbot.sticker_memory.v1"

_SENTENCE_BREAK_RE = re.compile(r"([。！？!?；;]+|\.{3,}|…{1,2})")
_SOFT_BREAK_RE = re.compile(r"([，,、：:]+)")
_MARKDOWN_REPLACEMENTS = (
    (re.compile(r"```.*?```", re.S), ""),
    (re.compile(r"`([^`]+)`"), r"\1"),
    (re.compile(r"^\s*[-*+]\s+", re.M), ""),
    (re.compile(r"^\s*\d+[.)]\s+", re.M), ""),
    (re.compile(r"\*\*([^*]+)\*\*"), r"\1"),
    (re.compile(r"\*([^*]+)\*"), r"\1"),
    (re.compile(r"__([^_]+)__"), r"\1"),
    (re.compile(r"_([^_]+)_"), r"\1"),
)


@dataclass(frozen=True)
class RealtimeChatSettings:
    enabled: bool = True
    max_parts: int = 5
    min_part_chars: int = 3
    max_part_chars: int = 72
    chars_per_second: float = 7.0
    min_delay_seconds: float = 0.35
    max_delay_seconds: float = 4.0
    jitter_ratio: float = 0.22
    strip_markdown: bool = True


@dataclass(frozen=True)
class StickerSettings:
    enabled: bool = True
    local_root: str = ""
    default_repo_url: str = "https://github.com/zhaoolee/ChineseBQB.git"
    allowed_extensions: str = ".jpg,.jpeg,.png,.gif,.webp"
    selected_packs: str = ""
    index_limit: int = 1000
    max_file_bytes: int = 5 * 1024 * 1024
    send_probability: float = 0.18
    learned_enabled: bool = True


def build_realtime_chat_plan(
    text: str,
    *,
    settings: RealtimeChatSettings | None = None,
    session_key: str = "",
    now: float = 0.0,
    emotion_values: dict[str, float] | None = None,
    atmosphere_values: dict[str, float] | None = None,
    sticker_candidates: list[dict[str, Any]] | None = None,
    sticker_settings: StickerSettings | None = None,
) -> dict[str, Any]:
    settings = settings or RealtimeChatSettings()
    sticker_settings = sticker_settings or StickerSettings(enabled=False)
    cleaned = normalize_realtime_text(text, strip_markdown=settings.strip_markdown)
    parts = split_realtime_text(cleaned, settings=settings)
    message_parts = [
        {
            "index": index,
            "text": part,
            "delay_before_seconds": estimate_delay(
                part,
                index=index,
                total=len(parts),
                settings=settings,
                seed=f"{session_key}:{now}:{index}:{part}",
            ),
        }
        for index, part in enumerate(parts)
    ]
    sticker_decision = select_sticker_reaction(
        text=cleaned,
        emotion_values=emotion_values or {},
        atmosphere_values=atmosphere_values or {},
        sticker_candidates=sticker_candidates or [],
        settings=sticker_settings,
        seed=f"{session_key}:{now}:{cleaned[:80]}",
    )
    total_delay = round(
        sum(float(part["delay_before_seconds"]) for part in message_parts),
        3,
    )
    return {
        "schema_version": PUBLIC_REALTIME_CHAT_SCHEMA_VERSION,
        "kind": "realtime_chat_plan",
        "enabled": settings.enabled,
        "session_key": session_key,
        "message_count": len(message_parts),
        "message_parts": message_parts,
        "sticker": sticker_decision,
        "typing": {
            "chars_per_second": settings.chars_per_second,
            "min_delay_seconds": settings.min_delay_seconds,
            "max_delay_seconds": settings.max_delay_seconds,
            "jitter_ratio": settings.jitter_ratio,
            "estimated_total_delay_seconds": total_delay,
        },
        "source_text_chars": len(str(text or "")),
        "normalized_text_chars": len(cleaned),
    }


def normalize_realtime_text(text: str, *, strip_markdown: bool) -> str:
    value = str(text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    value = re.sub(r"\n{3,}", "\n\n", value)
    if strip_markdown:
        for pattern, replacement in _MARKDOWN_REPLACEMENTS:
            value = pattern.sub(replacement, value)
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n[ \t]+", "\n", value)
    return value.strip()


def split_realtime_text(
    text: str,
    *,
    settings: RealtimeChatSettings | None = None,
) -> list[str]:
    settings = settings or RealtimeChatSettings()
    text = normalize_realtime_text(text, strip_markdown=False)
    if not text:
        return []
    explicit_line_break_mode = "\n" in text
    hard_chunks: list[str] = []
    for block in re.split(r"\n{2,}", text):
        block = block.strip()
        if not block:
            continue
        if explicit_line_break_mode and "\n" in block:
            hard_chunks.extend(_split_by_explicit_lines(block, settings.max_part_chars))
        else:
            hard_chunks.extend(_split_by_delimiters(block, _SENTENCE_BREAK_RE))
    chunks: list[str] = []
    for chunk in hard_chunks:
        if len(chunk) <= settings.max_part_chars:
            chunks.append(chunk)
            continue
        chunks.extend(_split_long_chunk(chunk, settings.max_part_chars))
    if explicit_line_break_mode:
        bounded = _limit_parts(chunks, settings.max_parts, settings.max_part_chars)
        return [part for part in bounded if part.strip()]
    merged = _merge_short_chunks(chunks, settings.min_part_chars, settings.max_part_chars)
    bounded = _limit_parts(merged, settings.max_parts, settings.max_part_chars)
    return [part for part in bounded if part.strip()]


def estimate_delay(
    text: str,
    *,
    index: int,
    total: int,
    settings: RealtimeChatSettings | None = None,
    seed: str = "",
) -> float:
    settings = settings or RealtimeChatSettings()
    if total <= 0:
        return 0.0
    if index == 0:
        base = min(settings.min_delay_seconds, 0.35)
    else:
        cps = max(1.0, float(settings.chars_per_second))
        base = len(str(text or "")) / cps
        base = max(settings.min_delay_seconds, base)
    jitter = _stable_unit(seed) * 2.0 - 1.0
    delay = base * (1.0 + jitter * max(0.0, settings.jitter_ratio))
    return round(max(0.0, min(settings.max_delay_seconds, delay)), 3)


def index_local_stickers(settings: StickerSettings | None = None) -> list[dict[str, Any]]:
    settings = settings or StickerSettings()
    root_text = str(settings.local_root or "").strip()
    if not root_text:
        return []
    root = Path(root_text).expanduser()
    if not root.exists() or not root.is_dir():
        return []
    allowed = _allowed_extensions(settings.allowed_extensions)
    selected = _selected_pack_tokens(settings.selected_packs)
    limit = max(0, int(settings.index_limit))
    max_file_bytes = max(1, int(settings.max_file_bytes))
    indexed: list[dict[str, Any]] = []
    for path in root.rglob("*"):
        if limit and len(indexed) >= limit:
            break
        if not path.is_file() or path.suffix.lower() not in allowed:
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        if stat.st_size > max_file_bytes:
            continue
        rel = path.relative_to(root).as_posix()
        if selected and not any(token in rel.lower() for token in selected):
            continue
        indexed.append(
            {
                "id": sha256(rel.encode("utf-8", errors="ignore")).hexdigest()[:16],
                "origin": "local_sticker_pack",
                "path": str(path),
                "relative_path": rel,
                "name": path.stem,
                "extension": path.suffix.lower(),
                "size_bytes": stat.st_size,
                "tags": _tokens_from_name(path.stem + " " + rel),
            },
        )
    return indexed


def select_sticker_reaction(
    *,
    text: str,
    emotion_values: dict[str, float],
    atmosphere_values: dict[str, float],
    sticker_candidates: list[dict[str, Any]],
    settings: StickerSettings | None = None,
    seed: str = "",
) -> dict[str, Any]:
    settings = settings or StickerSettings()
    if not settings.enabled:
        return {"enabled": False, "should_send": False, "reason": "disabled"}
    candidates = [item for item in sticker_candidates if isinstance(item, dict)]
    if not candidates:
        return {
            "enabled": True,
            "should_send": False,
            "reason": "no_sticker_candidates",
            "default_repo_url": settings.default_repo_url,
        }
    intent, intent_score = infer_sticker_intent(
        text=text,
        emotion_values=emotion_values,
        atmosphere_values=atmosphere_values,
    )
    probability = max(0.0, min(1.0, float(settings.send_probability)))
    if intent_score * probability < _stable_unit(seed + ":gate"):
        return {
            "enabled": True,
            "should_send": False,
            "reason": "probability_gate",
            "intent": intent,
            "intent_score": round(intent_score, 3),
        }
    scored = [
        (_sticker_score(candidate, intent, text, seed), candidate)
        for candidate in candidates
    ]
    scored.sort(key=lambda item: item[0], reverse=True)
    score, chosen = scored[0]
    return {
        "enabled": True,
        "should_send": True,
        "intent": intent,
        "intent_score": round(intent_score, 3),
        "score": round(score, 3),
        "candidate": _public_sticker_candidate(chosen),
        "reason": "intent_and_context_match",
    }


def infer_sticker_intent(
    *,
    text: str,
    emotion_values: dict[str, float],
    atmosphere_values: dict[str, float],
) -> tuple[str, float]:
    lowered = str(text or "").lower()
    valence = _float_value(emotion_values.get("valence"), 0.0)
    arousal = _float_value(emotion_values.get("arousal"), 0.0)
    affiliation = _float_value(emotion_values.get("affiliation"), 0.0)
    tension = _float_value(atmosphere_values.get("tension"), 0.0)
    playfulness = 0.0
    if any(marker in lowered for marker in ("哈哈", "笑死", "草", "hhh", "233", "乐")):
        playfulness += 0.45
    if any(marker in lowered for marker in ("抱抱", "难过", "委屈", "累", "呜", "哭")):
        return "comfort", max(0.35, min(1.0, 0.55 - valence * 0.3 + affiliation * 0.2))
    if any(marker in lowered for marker in ("对不起", "抱歉", "错了", "补偿")):
        return "apology", max(0.35, min(1.0, 0.45 + tension * 0.3))
    if any(marker in lowered for marker in ("好耶", "赢", "成功", "通过", "太好了")):
        return "celebrate", max(0.35, min(1.0, 0.5 + valence * 0.4))
    if playfulness or valence > 0.25:
        return "tease", max(0.25, min(1.0, 0.35 + playfulness + valence * 0.25 + arousal * 0.15))
    if tension > 0.35 or valence < -0.25:
        return "awkward", max(0.25, min(1.0, 0.35 + tension * 0.35 - valence * 0.2))
    return "idle", max(0.15, min(0.45, 0.25 + affiliation * 0.15))


def build_sticker_memory_item(
    raw: dict[str, Any],
    *,
    session_key: str,
    now: float,
    source: str = "user_message",
) -> dict[str, Any]:
    payload = {
        "schema_version": PUBLIC_STICKER_MEMORY_SCHEMA_VERSION,
        "kind": "sticker_memory_item",
        "id": "",
        "session_key": str(session_key or ""),
        "source": str(source or "user_message"),
        "origin": str(raw.get("origin") or raw.get("type") or "observed_user_sticker"),
        "url": _short_text(raw.get("url"), 500),
        "path": _short_text(raw.get("path") or raw.get("file") or raw.get("file_path"), 500),
        "file_id": _short_text(raw.get("file_id") or raw.get("id"), 240),
        "name": _short_text(raw.get("name") or raw.get("filename"), 120),
        "mime": _short_text(raw.get("mime") or raw.get("mime_type"), 80),
        "tags": list(raw.get("tags") or [])[:12] if isinstance(raw.get("tags"), list) else [],
        "interest_score": max(0.0, min(1.0, _float_value(raw.get("interest_score"), 0.5))),
        "first_seen_at": float(now),
        "last_seen_at": float(now),
        "use_count": 0,
    }
    basis = "|".join(
        str(payload.get(key) or "")
        for key in ("session_key", "url", "path", "file_id", "name", "mime")
    )
    payload["id"] = sha256(basis.encode("utf-8", errors="ignore")).hexdigest()[:16]
    if not payload["tags"]:
        payload["tags"] = _tokens_from_name(" ".join([payload["name"], payload["url"], payload["path"]]))
    return payload


def merge_sticker_memory(
    current: list[dict[str, Any]],
    item: dict[str, Any],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    limit = max(1, int(limit))
    merged: list[dict[str, Any]] = []
    seen = False
    for old in current:
        if not isinstance(old, dict):
            continue
        if old.get("id") == item.get("id"):
            updated = dict(old)
            updated["last_seen_at"] = item.get("last_seen_at")
            updated["interest_score"] = max(
                _float_value(old.get("interest_score"), 0.0),
                _float_value(item.get("interest_score"), 0.0),
            )
            updated["use_count"] = int(_float_value(old.get("use_count"), 0)) + 1
            merged.append(updated)
            seen = True
        else:
            merged.append(dict(old))
    if not seen:
        merged.append(dict(item))
    merged.sort(
        key=lambda value: (
            _float_value(value.get("last_seen_at"), 0.0),
            _float_value(value.get("interest_score"), 0.0),
        ),
    )
    return merged[-limit:]


def realtime_style_prompt_fragment() -> str:
    return (
        "[realtime_chat_style]\n"
        "请把回复写得像即时聊天：优先自然短句，可以有轻微停顿、追问和口语连接；"
        "不要为了显得正式而写长篇 Markdown、编号清单或总结报告。"
        "如果问题需要严谨回答，仍保持准确，但把解释拆成更像聊天的几小段。"
    )


def _split_by_delimiters(text: str, pattern: re.Pattern[str]) -> list[str]:
    pieces = pattern.split(text)
    chunks: list[str] = []
    current = ""
    for piece in pieces:
        if not piece:
            continue
        current += piece
        if pattern.fullmatch(piece):
            chunks.append(current.strip())
            current = ""
    if current.strip():
        chunks.append(current.strip())
    return chunks or [text.strip()]


def _split_by_explicit_lines(text: str, max_chars: int) -> list[str]:
    chunks: list[str] = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        if len(line) <= max_chars:
            chunks.append(line)
            continue
        chunks.extend(_split_long_chunk(line, max_chars))
    return chunks


def _split_long_chunk(text: str, max_chars: int) -> list[str]:
    max_chars = max(12, int(max_chars))
    soft = _split_by_delimiters(text, _SOFT_BREAK_RE)
    chunks: list[str] = []
    for piece in soft:
        if len(piece) <= max_chars:
            chunks.append(piece)
            continue
        start = 0
        while start < len(piece):
            chunks.append(piece[start : start + max_chars].strip())
            start += max_chars
    return chunks


def _merge_short_chunks(chunks: list[str], min_chars: int, max_chars: int) -> list[str]:
    min_chars = max(1, int(min_chars))
    max_chars = max(min_chars, int(max_chars))
    merged: list[str] = []
    pending = ""
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        if not pending:
            pending = chunk
            continue
        if (len(pending) < min_chars or len(chunk) < min_chars) and (
            len(pending) + len(chunk) <= max_chars
        ):
            pending = (pending + " " + chunk).strip()
        else:
            merged.append(pending)
            pending = chunk
    if pending:
        merged.append(pending)
    return merged


def _limit_parts(chunks: list[str], max_parts: int, max_chars: int) -> list[str]:
    max_parts = max(1, int(max_parts))
    max_chars = max(12, int(max_chars))
    bounded = [
        piece
        for chunk in chunks
        for piece in _split_long_chunk(str(chunk or ""), max_chars)
        if piece.strip()
    ]
    if len(bounded) <= max_parts:
        return bounded
    head = bounded[: max_parts - 1]
    tail = _pack_bounded_chunks(bounded[max_parts - 1 :], max_chars)
    return head + tail


def _pack_bounded_chunks(chunks: list[str], max_chars: int) -> list[str]:
    max_chars = max(12, int(max_chars))
    packed: list[str] = []
    pending = ""
    for chunk in chunks:
        chunk = str(chunk or "").strip()
        if not chunk:
            continue
        if not pending:
            pending = chunk
            continue
        candidate = (pending + " " + chunk).strip()
        if len(candidate) <= max_chars:
            pending = candidate
        else:
            packed.append(pending)
            pending = chunk
    if pending:
        packed.append(pending)
    return packed


def _stable_unit(seed: str) -> float:
    digest = sha256(str(seed or "").encode("utf-8", errors="ignore")).hexdigest()
    return int(digest[:12], 16) / float(0xFFFFFFFFFFFF)


def _allowed_extensions(value: str) -> set[str]:
    result = set()
    for part in str(value or "").split(","):
        ext = part.strip().lower()
        if not ext:
            continue
        if not ext.startswith("."):
            ext = "." + ext
        result.add(ext)
    return result or {".jpg", ".jpeg", ".png", ".gif", ".webp"}


def _selected_pack_tokens(value: str) -> list[str]:
    return [
        token.strip().lower()
        for token in str(value or "").replace(";", ",").split(",")
        if token.strip()
    ]


def _tokens_from_name(value: str) -> list[str]:
    lowered = str(value or "").lower()
    parts = re.split(r"[\s_\-/\\.,，。!！?？()[\]【】]+", lowered)
    return [part[:32] for part in parts if 1 < len(part) <= 32][:12]


def _sticker_score(candidate: dict[str, Any], intent: str, text: str, seed: str) -> float:
    tags = " ".join(str(tag).lower() for tag in candidate.get("tags") or [])
    name = str(candidate.get("name") or candidate.get("relative_path") or "").lower()
    haystack = tags + " " + name
    intent_keywords = {
        "comfort": ("抱", "摸", "哭", "安慰", "可怜", "hug", "cry"),
        "apology": ("跪", "错", "对不起", "抱歉", "哭", "sorry"),
        "celebrate": ("好耶", "赢", "赞", "鼓掌", "开心", "ok", "yes"),
        "tease": ("笑", "坏", "偷", "调皮", "哈哈", "doge", "滑稽"),
        "awkward": ("尴尬", "汗", "怕", "呆", "疑惑", "awkward"),
        "idle": ("看", "等", "猫", "摸鱼", "吃瓜"),
    }
    score = 0.35 + _stable_unit(seed + ":" + str(candidate.get("id"))) * 0.2
    for keyword in intent_keywords.get(intent, ()):
        if keyword in haystack:
            score += 0.18
    for token in _tokens_from_name(text):
        if token in haystack:
            score += 0.08
    if candidate.get("origin") == "observed_user_sticker":
        score += 0.08
    return min(1.0, score)


def _public_sticker_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    public = {
        "id": candidate.get("id"),
        "origin": candidate.get("origin"),
        "name": candidate.get("name"),
        "path": candidate.get("path"),
        "url": candidate.get("url"),
        "file_id": candidate.get("file_id"),
        "relative_path": candidate.get("relative_path"),
        "extension": candidate.get("extension"),
        "mime": candidate.get("mime"),
    }
    return {key: value for key, value in public.items() if value not in (None, "")}


def _float_value(value: Any, default: float) -> float:
    try:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _short_text(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip()
