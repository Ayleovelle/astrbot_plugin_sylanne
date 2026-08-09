"""Sealed, request-local transient ``TextPart`` overlay aggregation.

Dynamic runtime guidance is represented as one framework ``TextPart`` marked
temporary.  It is never written into ``system_prompt``, ``prompt``, or
persisted conversation contexts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


_TRANSIENT_CONTEXT_SINK_ISSUER = object()
_OVERLAY_HEADER = "[sylanne_runtime_overlay]"
_MAX_FRAGMENTS = 32
_MAX_FRAGMENT_CHARS = 12_000
_MAX_OVERLAY_CHARS = 12_000
# A sink starts closed.  Some producers (notably realtime recovery) can run
# before the request pipeline knows this turn's gap-aware budget.  Letting
# them succeed against an arbitrary default and later shrinking the budget
# would either lose a consumed fragment or exceed the final cap.  The pipeline
# must therefore establish the budget before any producer gets an admission.
_DEFAULT_TURN_BUDGET = 0
_CHANNEL_ORDER = {
    "state": 10,
    "amnesia": 11,
    "outreach": 12,
    "memory": 13,
    "unfinished": 14,
    "time": 20,
    "inner_context": 20,
    "memory_api": 25,
    "v2_mind": 30,
    "emotion_spirit": 35,
    "realtime_assistant_history": 40,
    "realtime_interrupted_reply": 41,
    "realtime_active_dispatch": 42,
    "realtime_continuity": 43,
    "realtime_backfill": 44,
    "semantic": 90,
    "deliverable": 10_000,
}
_DEFAULT_CHANNEL_ORDER = 500


def _make_text_part(text: str) -> Any:
    """Construct the pinned AstrBot part lazily, only at commit time."""

    from astrbot.core.agent.message import TextPart

    return TextPart(text=text)


@dataclass(frozen=True, slots=True)
class _Fragment:
    channel: str
    text: str
    source: str
    priority: int
    lifecycle: str
    ordinal: int


class TransientContextSink:
    """Registry-issued collector that commits one no-save framework part."""

    __slots__ = (
        "_registry",
        "_view",
        "_fragments",
        "_committed",
        "_released",
        "_max_chars",
        "_budget_set",
    )

    def __init__(
        self,
        _issuer: object | None = None,
        *,
        registry: object = None,
        view: object = None,
    ) -> None:
        if _issuer is not _TRANSIENT_CONTEXT_SINK_ISSUER:
            raise TypeError("TransientContextSink is issued only by ScopeRuntimeRegistry")
        self._registry = registry
        self._view = view
        self._fragments: list[_Fragment] = []
        self._committed = False
        self._released = False
        self._max_chars = min(_DEFAULT_TURN_BUDGET, _MAX_OVERLAY_CHARS)
        self._budget_set = False

    @classmethod
    def _issue(cls, registry: object, view: object) -> "TransientContextSink":
        return cls(_TRANSIENT_CONTEXT_SINK_ISSUER, registry=registry, view=view)

    def _is_active_for(self, request: Any) -> bool:
        registry = self._registry
        checker = getattr(registry, "_is_active_transient_context_binding", None)
        return bool(
            not self._released
            and not self._committed
            and callable(checker)
            and checker(self._view, request, self)
        )

    @staticmethod
    def _valid_metadata(
        channel: Any, source: Any, priority: Any, lifecycle: Any
    ) -> bool:
        return (
            isinstance(channel, str)
            and bool(channel.strip())
            and isinstance(source, str)
            and bool(source.strip())
            and type(priority) is int
            and lifecycle == "turn"
        )

    @staticmethod
    def _channel_order(fragment: _Fragment) -> int:
        return _CHANNEL_ORDER.get(fragment.channel, _DEFAULT_CHANNEL_ORDER)

    @classmethod
    def _render_sort_key(cls, fragment: _Fragment) -> tuple[int, str, int, str, int]:
        return (
            cls._channel_order(fragment),
            fragment.channel,
            fragment.priority,
            fragment.source,
            fragment.ordinal,
        )

    def _render(self, fragments: list[_Fragment] | None = None) -> str:
        ordered = sorted(
            self._fragments if fragments is None else fragments,
            key=self._render_sort_key,
        )
        lines = [_OVERLAY_HEADER]
        for fragment in ordered:
            lines.extend(
                (
                    f"[{fragment.channel} source={fragment.source} "
                    f"lifecycle={fragment.lifecycle}]",
                    fragment.text,
                )
            )
        return "\n".join(lines)

    def set_budget(self, request: Any, max_chars: int) -> bool:
        """Set the hard rendered-overlay budget before producer admission.

        A later lower cap is rejected rather than evicting an already accepted
        fragment.  Callers therefore either get an unchanged sink and ``False``
        or a sink whose final render is provably within this exact cap.
        """

        if not self._is_active_for(request) or type(max_chars) is not int:
            return False
        bounded = max(0, min(max_chars, _MAX_OVERLAY_CHARS))
        existing_chars = len(self._render()) if self._fragments else 0
        # An accepted fragment is a delivery contract: producers such as
        # realtime consume their source only after ``add`` succeeds.  Never
        # reduce the cap by silently evicting one; reject the attempted change.
        if existing_chars > bounded:
            return False
        self._max_chars = bounded
        self._budget_set = True
        return True

    def add(
        self,
        request: Any,
        channel: str,
        text: str,
        source: str,
        priority: int,
        lifecycle: str = "turn",
    ) -> bool:
        """Collect one dynamic fragment without touching the request object.

        Smaller priorities are more important, matching the request pipeline's
        slot budget convention.  An accepted fragment is never displaced later.
        """

        if (
            not self._is_active_for(request)
            or not self._budget_set
            or not isinstance(text, str)
            or not text
            or len(text) > _MAX_FRAGMENT_CHARS
            or not self._valid_metadata(channel, source, priority, lifecycle)
            or len(self._fragments) >= _MAX_FRAGMENTS
        ):
            return False
        if any(
            fragment.channel == channel
            and fragment.source == source
            and fragment.text == text
            for fragment in self._fragments
        ):
            return True
        candidate = [
            *self._fragments,
            _Fragment(
                channel,
                text,
                source,
                priority,
                lifecycle,
                len(self._fragments),
            ),
        ]
        if len(self._render(candidate)) > self._max_chars:
            return False
        self._fragments = candidate
        return True

    def commit(self, request: Any) -> bool:
        """Append exactly one temporary ``TextPart`` after all producers finish."""

        if not self._is_active_for(request) or not self._fragments:
            return False
        text = self._render()
        try:
            part = _make_text_part(text)
            mark_as_temp = getattr(part, "mark_as_temp", None)
            if not callable(mark_as_temp) or mark_as_temp() is not part:
                return False
            if getattr(part, "_no_save", None) is not True:
                return False
            parts = getattr(request, "extra_user_content_parts", None)
            if not isinstance(parts, list):
                return False
            parts.append(part)
            return True
        except Exception:
            return False
        finally:
            self._fragments.clear()
            self._committed = True

    def release(self) -> None:
        """Invalidate the sink and drop every in-memory fragment."""

        self._fragments.clear()
        self._released = True


__all__ = ["TransientContextSink"]
