"""Document 查询 Function Tools。"""

from agents import RunContextWrapper, function_tool

from app.agent_runtime.audit import execute_audited_tool_call
from app.agent_runtime.context import AgentToolContext
from app.agent_runtime.errors import safe_tool_error_function
from app.modules.document.agent_tools.schemas import (
    ChildChunkToolView,
    DocumentArtifactToolView,
    DocumentChunkStatisticsToolView,
    DocumentListToolItem,
    DocumentPipelineToolView,
    DocumentToolView,
    GetDocumentChunkStatisticsToolInput,
    GetDocumentChunkStatisticsToolOutput,
    GetDocumentPipelineStateToolInput,
    GetDocumentPipelineStateToolOutput,
    GetDocumentToolInput,
    GetDocumentToolOutput,
    GetKnowledgeBaseStatisticsToolInput,
    GetKnowledgeBaseStatisticsToolOutput,
    KnowledgeBaseStatisticsToolView,
    ListChildChunksToolInput,
    ListChildChunksToolOutput,
    ListDocumentArtifactsToolInput,
    ListDocumentArtifactsToolOutput,
    ListDocumentsToolInput,
    ListDocumentsToolOutput,
    ListParentBlocksToolInput,
    ListParentBlocksToolOutput,
    ParentBlockToolView,
    SearchDocumentArtifactsToolInput,
    SearchDocumentArtifactsToolOutput,
    SearchDocumentsToolInput,
    SearchDocumentsToolOutput,
)
from app.modules.document.application.dto import (
    ChildChunkSearchQuery,
    DocumentArtifactSearchQuery,
    DocumentListQuery,
    DocumentSearchQuery,
    ParentBlockSearchQuery,
)


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


def search_documents_handler(
    ctx: RunContextWrapper[AgentToolContext],
    tool_input: SearchDocumentsToolInput,
) -> SearchDocumentsToolOutput:
    """按受限高级条件查询文档。"""
    resource_refs = [
        *(f"knowledge_base:{kb_id}" for kb_id in tool_input.kb_ids),
        *(f"document:{doc_id}" for doc_id in tool_input.document_ids),
    ] or ["document:*"]
    query = DocumentSearchQuery.model_validate(tool_input.model_dump())
    execution = execute_audited_tool_call(
        context=ctx.context,
        tool_name="search_documents",
        required_permissions=(DOCUMENT_READ_PERMISSION,),
        resource_refs=resource_refs,
        success_result_code="documents_searched",
        operation=lambda: (
            ctx.context.document_services.search_documents.execute(query)
        ),
    )
    if execution.error is not None:
        return SearchDocumentsToolOutput(
            **execution.error.__dict__,
            limit=tool_input.limit,
            offset=tool_input.offset,
        )
    result = execution.value
    assert result is not None
    return SearchDocumentsToolOutput(
        outcome="succeeded",
        result_code="documents_searched",
        message="文档高级查询成功",
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


search_documents = function_tool(
    name_override="search_documents",
    description_override=(
        "按受限业务字段、状态轴、时间范围和白名单排序查询文档。"
    ),
    failure_error_function=safe_tool_error_function,
)(search_documents_handler)


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


def search_document_artifacts_handler(
    ctx: RunContextWrapper[AgentToolContext],
    tool_input: SearchDocumentArtifactsToolInput,
) -> SearchDocumentArtifactsToolOutput:
    """按受限条件查询派生产物。"""
    resource_refs = [
        f"document:{document_id}"
        for document_id in tool_input.document_ids
    ] or ["document_artifact:*"]
    query = DocumentArtifactSearchQuery.model_validate(
        tool_input.model_dump()
    )
    execution = execute_audited_tool_call(
        context=ctx.context,
        tool_name="search_document_artifacts",
        required_permissions=(DOCUMENT_READ_PERMISSION,),
        resource_refs=resource_refs,
        success_result_code="document_artifacts_searched",
        operation=lambda: (
            ctx.context.document_services.search_document_artifacts.execute(
                query
            )
        ),
    )
    if execution.error is not None:
        return SearchDocumentArtifactsToolOutput(
            **execution.error.__dict__,
            limit=tool_input.limit,
            offset=tool_input.offset,
        )
    result = execution.value
    assert result is not None
    return SearchDocumentArtifactsToolOutput(
        outcome="succeeded",
        result_code="document_artifacts_searched",
        message="文档产物高级查询成功",
        retryable=False,
        resource_refs=resource_refs,
        artifacts=[
            DocumentArtifactToolView.model_validate(item)
            for item in result.items
        ],
        total=result.total,
        limit=result.limit,
        offset=result.offset,
    )


search_document_artifacts = function_tool(
    name_override="search_document_artifacts",
    description_override=(
        "按文档、产物类型、角色、格式、状态、处理器和时间查询派生产物。"
    ),
    failure_error_function=safe_tool_error_function,
)(search_document_artifacts_handler)


def list_parent_blocks_handler(
    ctx: RunContextWrapper[AgentToolContext],
    tool_input: ListParentBlocksToolInput,
) -> ListParentBlocksToolOutput:
    """查询父级语义块明细。"""
    resource_refs = [
        *(f"document:{doc_id}" for doc_id in tool_input.document_ids),
        *(f"knowledge_base:{kb_id}" for kb_id in tool_input.kb_ids),
    ] or ["parent_block:*"]
    query = ParentBlockSearchQuery.model_validate(tool_input.model_dump())
    execution = execute_audited_tool_call(
        context=ctx.context,
        tool_name="list_parent_blocks",
        required_permissions=(DOCUMENT_READ_PERMISSION,),
        resource_refs=resource_refs,
        success_result_code="parent_blocks_listed",
        operation=lambda: (
            ctx.context.document_services.list_parent_blocks.execute(query)
        ),
    )
    if execution.error is not None:
        return ListParentBlocksToolOutput(
            **execution.error.__dict__,
            limit=tool_input.limit,
            offset=tool_input.offset,
        )
    result = execution.value
    assert result is not None
    return ListParentBlocksToolOutput(
        outcome="succeeded",
        result_code="parent_blocks_listed",
        message="父级语义块查询成功",
        retryable=False,
        resource_refs=resource_refs,
        parent_blocks=[
            ParentBlockToolView.model_validate(item)
            for item in result.items
        ],
        total=result.total,
        limit=result.limit,
        offset=result.offset,
    )


list_parent_blocks = function_tool(
    name_override="list_parent_blocks",
    description_override="按文档、知识库、块类型、章节路径和关键词查询父块。",
    failure_error_function=safe_tool_error_function,
)(list_parent_blocks_handler)


def list_child_chunks_handler(
    ctx: RunContextWrapper[AgentToolContext],
    tool_input: ListChildChunksToolInput,
) -> ListChildChunksToolOutput:
    """查询可向量化子块明细。"""
    resource_refs = []
    if tool_input.document_id is not None:
        resource_refs.append(f"document:{tool_input.document_id}")
    if tool_input.parent_id is not None:
        resource_refs.append(f"parent_block:{tool_input.parent_id}")
    if tool_input.kb_id is not None:
        resource_refs.append(f"knowledge_base:{tool_input.kb_id}")
    resource_refs = resource_refs or ["child_chunk:*"]
    query = ChildChunkSearchQuery.model_validate(tool_input.model_dump())
    execution = execute_audited_tool_call(
        context=ctx.context,
        tool_name="list_child_chunks",
        required_permissions=(DOCUMENT_READ_PERMISSION,),
        resource_refs=resource_refs,
        success_result_code="child_chunks_listed",
        operation=lambda: (
            ctx.context.document_services.list_child_chunks.execute(query)
        ),
    )
    if execution.error is not None:
        return ListChildChunksToolOutput(
            **execution.error.__dict__,
            limit=tool_input.limit,
            offset=tool_input.offset,
        )
    result = execution.value
    assert result is not None
    return ListChildChunksToolOutput(
        outcome="succeeded",
        result_code="child_chunks_listed",
        message="子块查询成功",
        retryable=False,
        resource_refs=resource_refs,
        child_chunks=[
            ChildChunkToolView.model_validate(item)
            for item in result.items
        ],
        total=result.total,
        limit=result.limit,
        offset=result.offset,
    )


list_child_chunks = function_tool(
    name_override="list_child_chunks",
    description_override=(
        "按文档、父块、知识库、向量状态、章节、CSV 行范围和关键词查询子块。"
    ),
    failure_error_function=safe_tool_error_function,
)(list_child_chunks_handler)


def get_document_chunk_statistics_handler(
    ctx: RunContextWrapper[AgentToolContext],
    tool_input: GetDocumentChunkStatisticsToolInput,
) -> GetDocumentChunkStatisticsToolOutput:
    """读取文档父子块和向量状态统计。"""
    resource_refs = [f"document:{tool_input.document_id}"]
    execution = execute_audited_tool_call(
        context=ctx.context,
        tool_name="get_document_chunk_statistics",
        required_permissions=(DOCUMENT_READ_PERMISSION,),
        resource_refs=resource_refs,
        success_result_code="document_chunk_statistics_retrieved",
        operation=lambda: (
            ctx.context.document_services.get_document_chunk_statistics.execute(
                tool_input.document_id
            )
        ),
    )
    if execution.error is not None:
        return GetDocumentChunkStatisticsToolOutput(
            **execution.error.__dict__
        )
    return GetDocumentChunkStatisticsToolOutput(
        outcome="succeeded",
        result_code="document_chunk_statistics_retrieved",
        message="文档切块统计读取成功",
        retryable=False,
        resource_refs=resource_refs,
        statistics=DocumentChunkStatisticsToolView.model_validate(
            execution.value
        ),
    )


get_document_chunk_statistics = function_tool(
    name_override="get_document_chunk_statistics",
    description_override=(
        "统计文档父块、子块、块类型、持久化状态和向量写入状态。"
    ),
    failure_error_function=safe_tool_error_function,
)(get_document_chunk_statistics_handler)


def get_knowledge_base_statistics_handler(
    ctx: RunContextWrapper[AgentToolContext],
    tool_input: GetKnowledgeBaseStatisticsToolInput,
) -> GetKnowledgeBaseStatisticsToolOutput:
    """读取知识库整体统计。"""
    resource_refs = [f"knowledge_base:{tool_input.kb_id}"]
    execution = execute_audited_tool_call(
        context=ctx.context,
        tool_name="get_knowledge_base_statistics",
        required_permissions=(DOCUMENT_READ_PERMISSION,),
        resource_refs=resource_refs,
        success_result_code="knowledge_base_statistics_retrieved",
        operation=lambda: (
            ctx.context.document_services.get_knowledge_base_statistics.execute(
                tool_input.kb_id
            )
        ),
    )
    if execution.error is not None:
        return GetKnowledgeBaseStatisticsToolOutput(
            **execution.error.__dict__
        )
    return GetKnowledgeBaseStatisticsToolOutput(
        outcome="succeeded",
        result_code="knowledge_base_statistics_retrieved",
        message="知识库统计读取成功",
        retryable=False,
        resource_refs=resource_refs,
        statistics=KnowledgeBaseStatisticsToolView.model_validate(
            execution.value
        ),
    )


get_knowledge_base_statistics = function_tool(
    name_override="get_knowledge_base_statistics",
    description_override=(
        "获取知识库元数据、文档状态以及父块、子块和向量状态汇总。"
    ),
    failure_error_function=safe_tool_error_function,
)(get_knowledge_base_statistics_handler)
