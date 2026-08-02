"""Document 查询 Function Tools。"""

from agents import RunContextWrapper, function_tool

from app.agent_runtime.audit import execute_audited_tool_call
from app.agent_runtime.context import AgentToolContext
from app.agent_runtime.errors import safe_tool_error_function
from app.modules.document.agent_tools.schemas import (
    DocumentArtifactToolView,
    DocumentListToolItem,
    DocumentPipelineToolView,
    DocumentToolView,
    GetDocumentPipelineStateToolInput,
    GetDocumentPipelineStateToolOutput,
    GetDocumentToolInput,
    GetDocumentToolOutput,
    ListDocumentArtifactsToolInput,
    ListDocumentArtifactsToolOutput,
    ListDocumentsToolInput,
    ListDocumentsToolOutput,
)
from app.modules.document.application.dto import DocumentListQuery


DOCUMENT_READ_PERMISSION = "document:read"


def get_document_handler(
    ctx: RunContextWrapper[AgentToolContext],
    tool_input: GetDocumentToolInput,
) -> GetDocumentToolOutput:
    """获取指定文档。"""
    resource_refs = [f"document:{tool_input.document_id}"]
    execution = execute_audited_tool_call(
        context=ctx.context,
        tool_name="get_document",
        required_permissions=(DOCUMENT_READ_PERMISSION,),
        resource_refs=resource_refs,
        success_result_code="document_retrieved",
        operation=lambda: ctx.context.document_services.get_document.execute(
            tool_input.document_id
        ),
    )
    if execution.error is not None:
        return GetDocumentToolOutput(**execution.error.__dict__)
    return GetDocumentToolOutput(
        outcome="succeeded",
        result_code="document_retrieved",
        message="文档状态读取成功",
        retryable=False,
        resource_refs=resource_refs,
        document=DocumentToolView.model_validate(execution.value),
    )


get_document = function_tool(
    name_override="get_document",
    description_override="获取一份文档的完整元数据和当前状态。",
    failure_error_function=safe_tool_error_function,
)(get_document_handler)


def list_documents_handler(
    ctx: RunContextWrapper[AgentToolContext],
    tool_input: ListDocumentsToolInput,
) -> ListDocumentsToolOutput:
    """筛选并分页列出文档。"""
    resource_refs = [f"knowledge_base:{tool_input.kb_id}"]
    query = DocumentListQuery.model_validate(tool_input.model_dump())
    execution = execute_audited_tool_call(
        context=ctx.context,
        tool_name="list_documents",
        required_permissions=(DOCUMENT_READ_PERMISSION,),
        resource_refs=resource_refs,
        success_result_code="documents_listed",
        operation=lambda: ctx.context.document_services.list_documents.execute(
            query
        ),
    )
    if execution.error is not None:
        return ListDocumentsToolOutput(
            **execution.error.__dict__,
            limit=tool_input.limit,
            offset=tool_input.offset,
        )
    result = execution.value
    assert result is not None
    return ListDocumentsToolOutput(
        outcome="succeeded",
        result_code="documents_listed",
        message="文档列表读取成功",
        retryable=False,
        resource_refs=resource_refs,
        documents=[
            DocumentListToolItem.model_validate(item)
            for item in result.items
        ],
        total=result.total,
        limit=result.limit,
        offset=result.offset,
    )


list_documents = function_tool(
    name_override="list_documents",
    description_override="按知识库、流程状态、来源类型和生命周期筛选文档。",
    failure_error_function=safe_tool_error_function,
)(list_documents_handler)


def get_document_pipeline_state_handler(
    ctx: RunContextWrapper[AgentToolContext],
    tool_input: GetDocumentPipelineStateToolInput,
) -> GetDocumentPipelineStateToolOutput:
    """获取文档流水线状态。"""
    resource_refs = [f"document:{tool_input.document_id}"]
    execution = execute_audited_tool_call(
        context=ctx.context,
        tool_name="get_document_pipeline_state",
        required_permissions=(DOCUMENT_READ_PERMISSION,),
        resource_refs=resource_refs,
        success_result_code="document_pipeline_state_retrieved",
        operation=lambda: (
            ctx.context.document_services.get_document_pipeline_state.execute(
                tool_input.document_id
            )
        ),
    )
    if execution.error is not None:
        return GetDocumentPipelineStateToolOutput(
            **execution.error.__dict__
        )
    return GetDocumentPipelineStateToolOutput(
        outcome="succeeded",
        result_code="document_pipeline_state_retrieved",
        message="文档流水线状态读取成功",
        retryable=False,
        resource_refs=resource_refs,
        pipeline_state=DocumentPipelineToolView.model_validate(
            execution.value
        ),
    )


get_document_pipeline_state = function_tool(
    name_override="get_document_pipeline_state",
    description_override="获取文档处理、切块和向量索引的聚合状态。",
    failure_error_function=safe_tool_error_function,
)(get_document_pipeline_state_handler)


def list_document_artifacts_handler(
    ctx: RunContextWrapper[AgentToolContext],
    tool_input: ListDocumentArtifactsToolInput,
) -> ListDocumentArtifactsToolOutput:
    """列出文档产物。"""
    resource_refs = [f"document:{tool_input.document_id}"]
    execution = execute_audited_tool_call(
        context=ctx.context,
        tool_name="list_document_artifacts",
        required_permissions=(DOCUMENT_READ_PERMISSION,),
        resource_refs=resource_refs,
        success_result_code="document_artifacts_listed",
        operation=lambda: (
            ctx.context.document_services.list_document_artifacts.execute(
                tool_input.document_id
            )
        ),
    )
    if execution.error is not None:
        return ListDocumentArtifactsToolOutput(
            **execution.error.__dict__,
            document_id=tool_input.document_id,
        )
    result = execution.value
    assert result is not None
    return ListDocumentArtifactsToolOutput(
        outcome="succeeded",
        result_code="document_artifacts_listed",
        message="文档产物读取成功",
        retryable=False,
        resource_refs=resource_refs,
        document_id=result.document_id,
        source_uri=result.source_uri,
        source_type=result.source_type,
        original_filename=result.original_filename,
        artifacts=[
            DocumentArtifactToolView.model_validate(item)
            for item in result.items
        ],
    )


list_document_artifacts = function_tool(
    name_override="list_document_artifacts",
    description_override="列出文档原件转换和清洗流程生成的派生产物。",
    failure_error_function=safe_tool_error_function,
)(list_document_artifacts_handler)
