"""当前三个确定性文档 Capability 的可信 Registry 装配工厂。

注册以下三种内置文档处理领域能力：
1. `process_document`: 文档格式转换与文本清洗（超时 300s，最大重试 3 次）。
2. `build_document_chunks`: 文档父子语义块构建（超时 300s，最大重试 3 次）。
3. `index_document_vectors`: Qwen Embedding 向量生成与 Qdrant 索引写入（超时 900s，最大重试 3 次）。
"""

from app.modules.planning.domain.enums import PlanningCapabilityCode
from app.modules.task_runtime.application.ports import (
    CapabilityDefinition,
    CapabilityRegistry,
)
from app.modules.task_runtime.application.schemas import (
    BuildDocumentChunksTaskOutput,
    BuildDocumentChunksTaskPayload,
    IndexDocumentVectorsTaskOutput,
    IndexDocumentVectorsTaskPayload,
    ProcessDocumentTaskOutput,
    ProcessDocumentTaskPayload,
)


def build_capability_registry() -> CapabilityRegistry:
    """构建并初始化包含系统全部内置 Capability 的注册表实例。

    Returns:
        CapabilityRegistry: 初始化完成的 CapabilityRegistry 对象。
    """
    return CapabilityRegistry(
        [
            CapabilityDefinition(
                capability_code=PlanningCapabilityCode.PROCESS_DOCUMENT.value,
                input_model=ProcessDocumentTaskPayload,
                output_model=ProcessDocumentTaskOutput,
                executor_code="document.process",
                compensator_code="document.process",
                max_attempts=3,
                timeout_seconds=300,
                side_effect=True,
            ),
            CapabilityDefinition(
                capability_code=(
                    PlanningCapabilityCode.BUILD_DOCUMENT_CHUNKS.value
                ),
                input_model=BuildDocumentChunksTaskPayload,
                output_model=BuildDocumentChunksTaskOutput,
                executor_code="document.build_chunks",
                compensator_code="document.build_chunks",
                max_attempts=3,
                timeout_seconds=300,
                side_effect=True,
            ),
            CapabilityDefinition(
                capability_code=(
                    PlanningCapabilityCode.INDEX_DOCUMENT_VECTORS.value
                ),
                input_model=IndexDocumentVectorsTaskPayload,
                output_model=IndexDocumentVectorsTaskOutput,
                executor_code="document.index_vectors",
                compensator_code="document.index_vectors",
                max_attempts=3,
                timeout_seconds=900,
                side_effect=True,
            ),
        ]
    )
