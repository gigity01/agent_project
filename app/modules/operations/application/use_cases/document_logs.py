"""文档业务日志的显式只读 Use Case。"""

from app.modules.operations.application.dto import (
    DocumentBusinessLogPage,
    DocumentBusinessLogQuery,
    DocumentOperationTimelineQuery,
    DocumentOperationTimelineResult,
    DocumentWorkflowTimelineQuery,
    DocumentWorkflowTimelineResult,
)
from app.modules.operations.application.query_service import (
    OperationsQueryService,
)


class QueryDocumentLogEventsUseCase:
    """按关联 ID、文档、阶段和时间筛选文档业务事件。"""

    def __init__(self, query_service: OperationsQueryService) -> None:
        self._query_service = query_service

    def execute(
        self,
        query: DocumentBusinessLogQuery,
    ) -> DocumentBusinessLogPage:
        return self._query_service.query_document_business_logs(query)


class GetDocumentOperationTimelineUseCase:
    """读取一个 operation_id 下的完整阶段事件时间线。"""

    def __init__(self, query_service: OperationsQueryService) -> None:
        self._query_service = query_service

    def execute(
        self,
        query: DocumentOperationTimelineQuery,
    ) -> DocumentOperationTimelineResult:
        return self._query_service.get_document_operation_timeline(query)


class GetDocumentWorkflowTimelineUseCase:
    """读取一个 workflow_id 下跨阶段、跨重试的完整事件时间线。"""

    def __init__(self, query_service: OperationsQueryService) -> None:
        self._query_service = query_service

    def execute(
        self,
        query: DocumentWorkflowTimelineQuery,
    ) -> DocumentWorkflowTimelineResult:
        return self._query_service.get_document_workflow_timeline(query)
