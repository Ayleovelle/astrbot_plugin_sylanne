from __future__ import annotations

from typing import Any, Callable


def append_auxiliary_state(
    *,
    request: Any,
    state_name: str,
    full_builder: Callable[[], str],
    source: str,
    injection_decision: Any,
    injection_budget: Any,
    append_text_part: Callable[..., bool],
    build_state_injection: Callable[[str, Callable[[], str], Any], str],
    build_compact_injection: Callable[[str], str],
    fallback_source: str | None = None,
    after_append: Callable[[], None] | None = None,
) -> bool:
    appended = append_text_part(
        request,
        build_state_injection(state_name, full_builder, injection_decision),
        source=source,
        budget=injection_budget,
    )
    if appended:
        if after_append is not None:
            after_append()
    elif injection_decision.auxiliary_detail == "full" and fallback_source is not None:
        append_text_part(
            request,
            build_compact_injection(state_name),
            source=fallback_source,
            budget=injection_budget,
        )
    return appended
