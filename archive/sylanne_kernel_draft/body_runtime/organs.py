from __future__ import annotations

from typing import Any, Protocol

from .contracts import BodyRequest, BodyResponse, BodyTrace

LEGACY_ORGAN_ROLES = {
    "emotion_engine": "heart_temperature_material",
    "memory_engine": "blood_trace_material",
    "conversation_event_ledger": "nerve_material",
    "lifelike_learning_engine": "expression_muscle_action_tendency",
    "fallibility_engine": "boundary_immunity",
    "moral_repair_engine": "relational_wound",
    "personality_drift_engine": "long_term_tissue_reshaping",
    "integrated_self": "body_schema",
    "project_life_engine": "foundation_pass_organ_material",
}


class BodyOrgan(Protocol):
    name: str
    organ_role: str

    def observe_request(self, request: BodyRequest) -> tuple[BodyTrace, ...]:
        ...

    def observe_response(self, response: BodyResponse) -> tuple[BodyTrace, ...]:
        ...


class NoopOrgan:
    def __init__(self, *, name: str, organ_role: str) -> None:
        self.name = name
        self.organ_role = organ_role

    def observe_request(self, request: BodyRequest) -> tuple[BodyTrace, ...]:
        return ()

    def observe_response(self, response: BodyResponse) -> tuple[BodyTrace, ...]:
        return ()


class LegacyOrganAdapter:
    def __init__(self, *, name: str, legacy_module: Any, organ_role: str | None = None) -> None:
        self.name = name
        self.legacy_module = legacy_module
        self.organ_role = organ_role or LEGACY_ORGAN_ROLES[name]

    def observe_request(self, request: BodyRequest) -> tuple[BodyTrace, ...]:
        intensity = 0.5 if str(request.user_text or "").strip() else 0.0
        return (
            BodyTrace(
                source=self.name,
                organ_role=self.organ_role,
                intensity=intensity,
                notes=("request observed as body material",),
            ),
        )

    def observe_response(self, response: BodyResponse) -> tuple[BodyTrace, ...]:
        intensity = 0.5 if str(response.assistant_text or "").strip() else 0.0
        return (
            BodyTrace(
                source=self.name,
                organ_role=self.organ_role,
                intensity=intensity,
                notes=("response observed as body material",),
            ),
        )
