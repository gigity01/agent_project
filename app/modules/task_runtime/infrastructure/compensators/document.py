"""把 Document capability 补偿用例适配为 Task Runtime Port。"""

from __future__ import annotations

import asyncio

from pydantic import BaseModel

from app.modules.document.application.use_cases.build_chunks import (
    BuildChunksCompensator,
)
from app.modules.document.application.use_cases.index_vectors import (
    IndexVectorsCompensator,
)
from app.modules.document.application.use_cases.process_document import (
    ProcessDocumentCompensator,
)
from app.modules.task_runtime.application.dto import TaskRuntimeContext
from app.modules.task_runtime.application.schemas import (
    BuildDocumentChunksTaskPayload,
    IndexDocumentVectorsTaskPayload,
    ProcessDocumentTaskPayload,
)


class ProcessDocumentOperationCompensator:
    def __init__(self, compensator: ProcessDocumentCompensator) -> None:
        self._compensator = compensator

    async def compensate(
        self,
        *,
        operation_id: str,
        payload: BaseModel,
        context: TaskRuntimeContext,
    ) -> None:
        del context
        validated = ProcessDocumentTaskPayload.model_validate(payload)
        await asyncio.to_thread(
            self._compensator.compensate,
            document_id=validated.document_id,
            operation_id=operation_id,
        )


class BuildDocumentChunksOperationCompensator:
    def __init__(self, compensator: BuildChunksCompensator) -> None:
        self._compensator = compensator

    async def compensate(
        self,
        *,
        operation_id: str,
        payload: BaseModel,
        context: TaskRuntimeContext,
    ) -> None:
        del context
        validated = BuildDocumentChunksTaskPayload.model_validate(payload)
        await asyncio.to_thread(
            self._compensator.compensate,
            document_id=validated.document_id,
            operation_id=operation_id,
        )


class IndexDocumentVectorsOperationCompensator:
    def __init__(self, compensator: IndexVectorsCompensator) -> None:
        self._compensator = compensator

    async def compensate(
        self,
        *,
        operation_id: str,
        payload: BaseModel,
        context: TaskRuntimeContext,
    ) -> None:
        del context
        validated = IndexDocumentVectorsTaskPayload.model_validate(payload)
        await asyncio.to_thread(
            self._compensator.compensate,
            document_id=validated.document_id,
            operation_id=operation_id,
        )
