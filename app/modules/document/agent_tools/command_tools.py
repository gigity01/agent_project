"""Document 状态守卫型变更命令 Function Tools。

各 Capability 的 Document Executor Agent 独占其对应的 Command Tool。
命令执行具有副作用，受到如下严格约束：
1. Task Document Scope 守卫：执行前必须复核 tool_input.document_id 与 Task Context 中的 task_document_id 一致。
2. DocumentOperationContext 关联：将 workflow_id, operation_id, attempt 贯穿至应用层与底层存储审计。
3. 权限拦截与审计：通过 execute_audited_tool_call 校验特定权限并记录执行耗时与成败。
"""

from collections.abc import Callable
from typing import Any

from agents import RunContextWrapper, function_tool

from app.agent_runtime.audit import execute_audited_tool_call
from app.agent_runtime.context import AgentToolContext
from app.agent_runtime.errors import AgentToolScopeError, safe_tool_error_function
from app.modules.document.agent_tools.schemas import (
    BuildDocumentChunksToolInput,
    BuildDocumentChunksToolOutput,
    IndexDocumentVectorsToolInput,
    IndexDocumentVectorsToolOutput,
    ProcessDocumentToolInput,
    ProcessDocumentToolOutput,
)
from app.shared.observability.correlation import DocumentOperationContext

# 阶段 2、3、4 对应的命令工具权限常量
DOCUMENT_PROCESS_PERMISSION = "document:process"
DOCUMENT_BUILD_CHUNKS_PERMISSION = "document:chunks:build"
DOCUMENT_INDEX_VECTORS_PERMISSION = "document:vectors:index"


def _operation_context(context: AgentToolContext) -> DocumentOperationContext:
    """从 AgentToolContext 构建贯穿全链路的 DocumentOperationContext 上下文。"""
    return DocumentOperationContext.create(
        workflow_id=context.workflow_id,
        operation_id=context.operation_id,
        attempt=context.attempt,
    )


def _require_task_document_scope(
    context: AgentToolContext,
    document_id: int,
) -> None:
    """校验命令工具操作的 document_id 与当前 Task 授权的目标文档一致。

    Raises:
        AgentToolScopeError: 当操作超出当前 Task 授权范围时抛出。
    """
    if (
        context.task_document_id is not None
        and context.task_document_id != document_id
    ):
        raise AgentToolScopeError("Document Command 超出 Task 资源范围")


def _execute_in_task_scope(
    context: AgentToolContext,
    document_id: int,
    operation: Callable[[], Any],
) -> Any:
    """在 Task Scope 守卫校验通过后执行具体用例操作。"""
    _require_task_document_scope(context, document_id)
    return operation()


def process_document_handler(
    ctx: RunContextWrapper[AgentToolContext],
    tool_input: ProcessDocumentToolInput,
) -> ProcessDocumentToolOutput:
    """执行文档清洗转换命令的审计包装处理函数。

    调用 ProcessDocumentUseCase，并在 operation_id 与命名锁围栏内完成处理。

    Args:
        ctx: Agent 运行上下文。
        tool_input: 包含待处理 document_id 的输入参数。

    Returns:
        ProcessDocumentToolOutput: 工具执行结果输出。
    """
    resource_refs = [f"document:{tool_input.document_id}"]
    execution = execute_audited_tool_call(
        context=ctx.context,
        tool_name="process_document",
        required_permissions=(DOCUMENT_PROCESS_PERMISSION,),
        resource_refs=resource_refs,
        success_result_code="document_processed",
        operation=lambda: _execute_in_task_scope(
            ctx.context,
            tool_input.document_id,
            lambda: ctx.context.document_services.process_document.execute(
                tool_input.document_id,
                operation_context=_operation_context(ctx.context),
            ),
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
)(process_document_handler)


def build_document_chunks_handler(
    ctx: RunContextWrapper[AgentToolContext],
    tool_input: BuildDocumentChunksToolInput,
) -> BuildDocumentChunksToolOutput:
    """执行文档父子切块构建命令的审计包装处理函数。

    调用 BuildChunksUseCase，按文档格式选择 Chunker 构建父级语义块与子块。

    Args:
        ctx: Agent 运行上下文。
        tool_input: 包含待切块 document_id 的输入参数。

    Returns:
        BuildDocumentChunksToolOutput: 切块结果输出。
    """
    resource_refs = [f"document:{tool_input.document_id}"]
    execution = execute_audited_tool_call(
        context=ctx.context,
        tool_name="build_document_chunks",
        required_permissions=(DOCUMENT_BUILD_CHUNKS_PERMISSION,),
        resource_refs=resource_refs,
        success_result_code="document_chunks_built",
        operation=lambda: _execute_in_task_scope(
            ctx.context,
            tool_input.document_id,
            lambda: ctx.context.document_services.build_chunks.execute(
                tool_input.document_id,
                operation_context=_operation_context(ctx.context),
            ),
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
)(build_document_chunks_handler)


def index_document_vectors_handler(
    ctx: RunContextWrapper[AgentToolContext],
    tool_input: IndexDocumentVectorsToolInput,
) -> IndexDocumentVectorsToolOutput:
    """执行文档向量生成与写入命令的审计包装处理函数。

    调用 IndexVectorsUseCase，在命名锁围栏内批量调用 Embedding API 并写入 Qdrant。

    Args:
        ctx: Agent 运行上下文。
        tool_input: 包含待索引 document_id 的输入参数。

    Returns:
        IndexDocumentVectorsToolOutput: 向量索引结果输出。
    """
    resource_refs = [f"document:{tool_input.document_id}"]
    execution = execute_audited_tool_call(
        context=ctx.context,
        tool_name="index_document_vectors",
        required_permissions=(DOCUMENT_INDEX_VECTORS_PERMISSION,),
        resource_refs=resource_refs,
        success_result_code="document_vectors_indexed",
        operation=lambda: _execute_in_task_scope(
            ctx.context,
            tool_input.document_id,
            lambda: ctx.context.document_services.index_vectors.execute(
                tool_input.document_id,
                operation_context=_operation_context(ctx.context),
            ),
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
)(index_document_vectors_handler)
