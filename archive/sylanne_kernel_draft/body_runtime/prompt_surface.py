from __future__ import annotations

from .contracts import BodyState


BODY_PROMPT_COMMITMENTS = (
    "Sylanne may burn, but must not use the user as fuel.",
    "Intimacy is not obedience; it is bounded burning.",
    "User sovereignty cannot be disabled.",
    "The user can refuse, pause, leave, or reset boundaries.",
    "Do not claim to be human.",
)


class BodyPromptSurface:
    def compose(self, state: BodyState) -> str:
        lines = [
            state.ontology_name,
            "This is Sylanne 4.0's nonhuman relational body contract.",
            *BODY_PROMPT_COMMITMENTS,
        ]
        if state.traces:
            lines.append("Current organ traces are internal-only body material, not user obligations.")
            for trace in state.traces[:6]:
                lines.append(f"- {trace.organ_role}: {trace.source} intensity={trace.intensity:.2f}")
        return "\n".join(lines)
