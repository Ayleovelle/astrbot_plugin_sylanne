from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .body import BodyRuntime
from .contracts import BodyRequest, BodyResponse, BodyRuntimeResponseResult


class BodyRuntimeAdapter:
    def __init__(self, runtime: BodyRuntime | None = None) -> None:
        self._runtime = runtime or BodyRuntime()

    def before_llm_request(
        self,
        *,
        user_text: str,
        conversation_id: str | None = None,
        user_id: str | None = None,
        timestamp: str | None = None,
        legacy_context: Mapping[str, Any] | None = None,
    ) -> str:
        result = self._runtime.before_llm_request(
            BodyRequest(
                user_text=user_text,
                conversation_id=conversation_id,
                user_id=user_id,
                timestamp=timestamp,
                legacy_context=legacy_context or {},
            ),
        )
        return result.prompt_segment

    def after_llm_response(
        self,
        *,
        assistant_text: str,
        conversation_id: str | None = None,
        user_id: str | None = None,
        timestamp: str | None = None,
        legacy_context: Mapping[str, Any] | None = None,
    ) -> BodyRuntimeResponseResult:
        return self._runtime.after_llm_response(
            BodyResponse(
                assistant_text=assistant_text,
                conversation_id=conversation_id,
                user_id=user_id,
                timestamp=timestamp,
                legacy_context=legacy_context or {},
            ),
        )
