"""文档派生产物在处理流程中的角色枚举。"""

from enum import Enum

class DocumentArtifactRole(str, Enum):
    """区分处理输入、输出、切块输入与调试产物。"""
    PROCESS_INPUT = "process_input"
    PROCESS_OUTPUT = "process_output"
    CHUNK_INPUT = "chunk_input"
    DEBUG_ARTIFACT = "debug_artifact"
