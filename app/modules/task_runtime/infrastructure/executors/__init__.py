"""Task Executor 适配器导出。

导出 AgentTaskExecutor、确定性后备 Executor 以及输出适配函数。
"""

from app.modules.task_runtime.infrastructure.executors.agent import (
    AgentTaskExecutor,
    adapt_build_document_chunks_output,
    adapt_index_document_vectors_output,
    adapt_process_document_output,
)
from app.modules.task_runtime.infrastructure.executors.document import (
    DeterministicBuildDocumentChunksExecutor,
    DeterministicIndexDocumentVectorsExecutor,
    DeterministicProcessDocumentExecutor,
)

__all__ = [
    "AgentTaskExecutor",
    "DeterministicBuildDocumentChunksExecutor",
    "DeterministicIndexDocumentVectorsExecutor",
    "DeterministicProcessDocumentExecutor",
    "adapt_build_document_chunks_output",
    "adapt_index_document_vectors_output",
    "adapt_process_document_output",
]
