# app/constants/document_artifact_type.py

from enum import StrEnum


class DocumentArtifactType(StrEnum):
    SECONDARY_TEXT = "secondary_text"
    CLEANED_TEXT = "cleaned_text"
    LAYOUT_JSON = "layout_json"
    EXTRACTED_TABLE = "extracted_table"
    EXTRACTED_IMAGE = "extracted_image"