from enum import Enum


class EventSource(Enum):
    USER_UTTERANCE = "user_utterance"
    ASSISTANT_DELIVERED_SPEECH = "assistant_delivered_speech"
    ASSISTANT_UNDELIVERED_DRAFT = "assistant_undelivered_draft"
    WORLD_SYSTEM_SIGNAL = "world_system_signal"
    INTERNAL_BODY_SURFACE = "internal_body_surface"
    TOOL_RESULT = "tool_result"
    USER_COMMAND = "user_command"
    BACKGROUND_WAKE = "background_wake"
    ARCHIVE_RECALL = "archive_recall"
