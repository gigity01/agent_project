"""Document 状态守卫型命令 Function Tools。"""

from agents import RunContextWrapper, function_tool

from app.agent_runtime.audit import execute_audited_tool_call
from app.agent_runtime.context import AgentToolContext
from app.agent_runtime.errors import safe_tool_error_function
from app.modules.document.agent_tools.schemas import (
    BuildDocumentChunksToolInput,
    BuildDocumentChunksToolOutput,
    IndexDocumentVectorsToolInput,
    IndexDocumentVectorsToolOutput,
    ProcessDocumentToolInput,
    ProcessDocumentToolOutput,
)


DOCUMENT_PROCESS_PERMISSION = "document:process"
DOCUMENT_BUILD_CHUNKS_PERMISSION = "document:chunks:build"
DOCUMENT_INDEX_VECTORS_PERMISSION = "document:vectors:index"


def process_document_handler(
    ctx: RunContextWrapper[AgentToolContext],
    tool_input: ProcessDocumentToolInput,
) -> ProcessDocumentToolOutput:
    """调用现有 ProcessDocumentUseCase。"""
    resource_refs = [f"document:{tool_input.document_id}"]
    execution = execute_audited_tool_call(
        context=ctx.context,
        tool_name="process_document",
        required_permissions=(DOCUMENT_PROCESS_PERMISSION,),
        resource_refs=resource_refs,
        success_result_code="document_processed",
        operation=lambda: (
            ctx.context.document_services.process_document.execute(
                tool_input.document_id
            )
        ),
    )
    if execution.error is not None:
        return ProcessDocumentToolOutput(
            **execution.error.__dict__,
            document_id=tool_input.document_id,
        )
    result = execution.value
    assert result is not None
    return ProcessDocumentToolOutput(
        outcome="succeeded",
        result_code="document_processed",
        message="文档处理完成",
        retryable=False,
        resource_refs=resource_refs,
        document_id=result.document_id,
        document_status=result.status,
        cleaned_uri=result.cleaned_uri,
    )


process_document = function_tool(
    name_override="process_document",
    description_override="处理或转换一份已上传文档，生成标准化清洗文本。",
    failure_error_function=safe_tool_error_function,
    needs_approval=True,
)(process_document_handler)


def build_document_chunks_handler(
    ctx: RunContextWrapper[AgentToolContext],
    tool_input: BuildDocumentChunksToolInput,
) -> BuildDocumentChunksToolOutput:
    """调用现有 BuildChunksUseCase。"""
    resource_refs = [f"document:{tool_input.document_id}"]
    execution = execute_audited_tool_call(
        context=ctx.context,
        tool_name="build_document_chunks",
        required_permissions=(DOCUMENT_BUILD_CHUNKS_PERMISSION,),
        resource_refs=resource_refs,
        success_result_code="document_chunks_built",
        operation=lambda: ctx.context.document_services.build_chunks.execute(
            tool_input.document_id
        ),
    )
    if execution.error is not None:
        return BuildDocumentChunksToolOutput(
            **execution.error.__dict__,
            document_id=tool_input.document_id,
        )
    result = execution.value
    assert result is not None
    return BuildDocumentChunksToolOutput(
        outcome="succeeded",
        result_code="document_chunks_built",
        message="文档切块完成",
        retryable=False,
        resource_refs=resource_refs,
        document_id=result.document_id,
        document_status=result.status,
        parent_count=result.parent_count,
        child_count=result.child_count,
    )


build_document_chunks = function_tool(
    name_override="build_document_chunks",
    description_override="基于文档清洗产物构建父级语义块和可向量化子块。",
    failure_error_function=safe_tool_error_function,
    needs_approval=True,
)(build_document_chunks_handler)


def index_document_vectors_handler(
    ctx: RunContextWrapper[AgentToolContext],
    tool_input: IndexDocumentVectorsToolInput,
) -> IndexDocumentVectorsToolOutput:
    """调用现有 IndexVectorsUseCase。"""
    resource_refs = [f"document:{tool_input.document_id}"]
    execution = execute_audited_tool_call(
        context=ctx.context,
        tool_name="index_document_vectors",
        required_permissions=(DOCUMENT_INDEX_VECTORS_PERMISSION,),
        resource_refs=resource_refs,
        success_result_code="document_vectors_indexed",
        operation=lambda: ctx.context.document_services.index_vectors.execute(
            tool_input.document_id
        ),
    )
    if execution.error is not None:
        return IndexDocumentVectorsToolOutput(
            **execution.error.__dict__,
            document_id=tool_input.document_id,
        )
    result = execution.value
    assert result is not None
    return IndexDocumentVectorsToolOutput(
        outcome="succeeded",
        result_code="document_vectors_indexed",
        message="文档向量索引完成",
        retryable=False,
        resource_refs=resource_refs,
        document_id=result.document_id,
        document_status=result.status,
        total_chunks=result.total_chunks,
        indexed_chunks=result.indexed_chunks,
        failed_chunks=result.failed_chunks,
    )


index_document_vectors = function_tool(
    name_override="index_document_vectors",
    description_override="为文档中尚未完成索引的子块生成向量并写入 Qdrant。",
    failure_error_function=safe_tool_error_function,
    needs_approval=True,
)(index_document_vectors_handler)
