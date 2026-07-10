from enum import Enum
class DocumentArtifactStatus(str, Enum):
    CREATED = "created"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    FAILED = "failed"
    