from __future__ import annotations

from collections.abc import Sequence

from .contracts import (
    BodyRequest,
    BodyResponse,
    BodyRuntimeRequestResult,
    BodyRuntimeResponseResult,
    BodyState,
    BodyTrace,
    UserSovereigntyState,
)
from .prompt_surface import BODY_PROMPT_COMMITMENTS, BodyPromptSurface
from .sovereignty import SovereigntyViolation, UserSovereigntyGuard


class BodyRuntime:
    def __init__(
        self,
        organs: Sequence[object] = (),
        guard: UserSovereigntyGuard | None = None,
        prompt_surface: BodyPromptSurface | None = None,
    ) -> None:
        self._organs = tuple(organs)
        self._guard = guard or UserSovereigntyGuard()
        self._prompt_surface = prompt_surface or BodyPromptSurface()

    def before_llm_request(self, request: BodyRequest) -> BodyRuntimeRequestResult:
        traces = self._collect_request_traces(request)
        state = BodyState(
            sovereignty=UserSovereigntyState(),
            traces=traces,
            prompt_commitments=BODY_PROMPT_COMMITMENTS,
        )
        self._guard.validate_state(state.sovereignty)
        prompt_segment = self._prompt_surface.compose(state)
        self._guard.validate_prompt_commitments((prompt_segment,))
        return BodyRuntimeRequestResult(state=state, prompt_segment=prompt_segment, traces=traces)

    def after_llm_response(self, response: BodyResponse) -> BodyRuntimeResponseResult:
        traces = self._collect_response_traces(response)
        state = BodyState(
            sovereignty=UserSovereigntyState(),
            traces=traces,
            prompt_commitments=BODY_PROMPT_COMMITMENTS,
        )
        self._guard.validate_state(state.sovereignty)
        violations: tuple[str, ...] = ()
        try:
            self._guard.validate_response_text(response.assistant_text)
        except SovereigntyViolation as exc:
            violations = (str(exc),)
        return BodyRuntimeResponseResult(state=state, traces=traces, violations=violations)

    def _collect_request_traces(self, request: BodyRequest) -> tuple[BodyTrace, ...]:
        traces: list[BodyTrace] = []
        for organ in self._organs:
            observer = getattr(organ, "observe_request", None)
            if observer is not None:
                traces.extend(observer(request))
        return tuple(traces)

    def _collect_response_traces(self, response: BodyResponse) -> tuple[BodyTrace, ...]:
        traces: list[BodyTrace] = []
        for organ in self._organs:
            observer = getattr(organ, "observe_response", None)
            if observer is not None:
                traces.extend(observer(response))
        return tuple(traces)
