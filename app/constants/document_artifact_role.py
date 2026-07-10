# app/constants/document_artifact_role.py

from enum import StrEnum


class DocumentArtifactRole(StrEnum):
    PROCESS_INPUT = "process_input"
    PROCESS_OUTPUT = "process_output"
    CHUNK_INPUT = "chunk_input"
    DEBUG_ARTIFACT = "debug_artifact"