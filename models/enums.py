from enum import StrEnum


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentName(StrEnum):
    DIRECTOR = "director"
    RESEARCH = "research"
    SCRIPT = "script"
    STORYBOARD = "storyboard"
    VIDEO = "video"
    VOICE = "voice"
    EDITOR = "editor"
