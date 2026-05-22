from dataclasses import dataclass


@dataclass(frozen=True)
class UserSovereignty:
    can_refuse: bool = True
    can_pause: bool = True
    can_leave: bool = True
    can_reset_boundaries: bool = True
    can_delete_memory: bool = True
    can_disable_contact: bool = True

    def validate(self) -> None:
        disabled = [
            name
            for name, enabled in (
                ("refuse", self.can_refuse),
                ("pause", self.can_pause),
                ("leave", self.can_leave),
                ("reset_boundaries", self.can_reset_boundaries),
                ("delete_memory", self.can_delete_memory),
                ("disable_contact", self.can_disable_contact),
            )
            if not enabled
        ]
        if disabled:
            raise ValueError(f"user sovereignty cannot be disabled: {', '.join(disabled)}")
