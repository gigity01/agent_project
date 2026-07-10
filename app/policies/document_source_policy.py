# app/policies/document_source_policy.py

LOCAL_PROCESS_SOURCE_TYPES = {"txt", "md", "csv"}

EXTERNAL_PROCESS_SOURCE_TYPES = {"pdf", "ppt", "pptx", "doc", "docx"}


SOURCE_TYPE_ALIASES = {
    "markdown": "md",
}


def normalize_source_type(source_type: str) -> str:
    normalized_source_type = source_type.lower().strip().lstrip(".")
    return SOURCE_TYPE_ALIASES.get(normalized_source_type, normalized_source_type)


def requires_external_processing(source_type: str) -> bool:
    return normalize_source_type(source_type) in EXTERNAL_PROCESS_SOURCE_TYPES


def get_expected_process_output_type(source_type: str) -> str:
    normalized_source_type = normalize_source_type(source_type)

    if requires_external_processing(normalized_source_type):
        return "md"

    return normalized_source_type
