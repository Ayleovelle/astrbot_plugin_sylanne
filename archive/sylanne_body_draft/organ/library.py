from dataclasses import dataclass

from sylanne_body.event.normalize import NormalizedEvent

LEGACY_BODY_ORGAN_ROLES = {
    "conversation_event_ledger": "nerve_material",
    "memory_engine": "blood_trace_material",
    "emotion_engine": "heart_temperature_material",
    "fallibility_engine": "boundary_immunity_material",
    "moral_repair_engine": "relational_wound_material",
    "lifelike_learning_engine": "expression_muscle_material",
    "personality_drift_engine": "long_term_tissue_material",
    "integrated_self": "body_schema_material",
    "project_life_engine": "foundation_organ_material",
}


@dataclass(frozen=True)
class LegacyOrganTrace:
    source: str
    organ_role: str
    event_id: str
    relation_epoch: int
    internal_only: bool = True
    public_api_eligible: bool = False
    can_disable_user_sovereignty: bool = False

    def to_dict(self) -> dict[str, str | int | bool]:
        return {
            "source": self.source,
            "organ_role": self.organ_role,
            "event_id": self.event_id,
            "relation_epoch": self.relation_epoch,
            "internal_only": self.internal_only,
            "public_api_eligible": self.public_api_eligible,
            "can_disable_user_sovereignty": self.can_disable_user_sovereignty,
        }


class LegacyBodyOrgan:
    def __init__(self, *, module_name: str) -> None:
        if module_name not in LEGACY_BODY_ORGAN_ROLES:
            raise ValueError(f"unknown legacy body organ: {module_name}")
        self.module_name = module_name
        self.organ_role = LEGACY_BODY_ORGAN_ROLES[module_name]

    def observe_event(self, event: NormalizedEvent, *, relation_epoch: int) -> LegacyOrganTrace:
        return LegacyOrganTrace(
            source=self.module_name,
            organ_role=self.organ_role,
            event_id=event.event_id,
            relation_epoch=relation_epoch,
        )

    def describe(self) -> str:
        return f"{self.module_name} supplies {self.organ_role} for Sylanne body material."
