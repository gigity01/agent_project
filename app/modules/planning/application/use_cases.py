"""Plan 与 Task 的事务型核心 Use Cases。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from app.modules.planning.application.dto import (
    CreateBuildChunksTaskInput,
    CreateIndexVectorsTaskInput,
    CreatePlanInput,
    CreateProcessDocumentTaskInput,
    FinalizePlanInput,
    FinalizePlanResult,
    MarkPlanRetryPendingInput,
    MarkPlanUnsupportedInput,
    PlanResult,
    TaskResult,
)
from app.modules.planning.application.errors import PlanningApplicationError
from app.modules.planning.application.ports import PlanningApplicationPorts
from app.modules.planning.domain.enums import (
    PlanningCapabilityCode,
    PlanStatus,
    TaskStatus,
)


MAX_TASKS_PER_PLAN = 10


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _plan_not_found() -> PlanningApplicationError:
    return PlanningApplicationError(
        404,
        "Plan 不存在",
        result_code="plan_not_found",
    )


def _turn_not_found() -> PlanningApplicationError:
    return PlanningApplicationError(
        404,
        "Conversation Turn 不存在",
        result_code="turn_not_found",
    )


def _require_planning(plan: Any) -> None:
    if plan.status != PlanStatus.PLANNING.value:
        raise PlanningApplicationError(
            409,
            f"Plan 当前状态不允许继续规划: {plan.status}",
            result_code="plan_state_conflict",
        )


def _require_turn_ownership(plan: Any, turn_id: str) -> None:
    if plan.turn_id != turn_id:
        raise PlanningApplicationError(
            409,
            "Plan 与 Conversation Turn 归属不一致",
            result_code="plan_turn_conflict",
        )


class CreatePlanUseCase:
    """为已持久化 Turn 创建 planning 状态的 revision。"""

    def __init__(self, *, ports: PlanningApplicationPorts) -> None:
        self._ports = ports

    def execute(self, command: CreatePlanInput) -> PlanResult:
        with self._ports.uow_factory() as uow:
            turn = uow.conversation_turns.get_by_id(command.turn_id)
            if turn is None:
                raise _turn_not_found()
            if uow.plans.get_by_turn_and_revision(
                command.turn_id,
                command.revision,
            ) is not None:
                raise PlanningApplicationError(
                    409,
                    "该 Turn 的 Plan revision 已存在",
                    result_code="plan_revision_conflict",
                )
            plan = uow.plans.create(
                self._ports.plan_factory(
                    plan_id=_new_id("plan"),
                    turn_id=command.turn_id,
                    status=PlanStatus.PLANNING.value,
                    revision=command.revision,
                    failure_reason=None,
                )
            )
            uow.commit()
            return PlanResult.model_validate(plan)


class _CreateDocumentTaskUseCase:
    def __init__(
        self,
        *,
        ports: PlanningApplicationPorts,
        capability_code: PlanningCapabilityCode,
    ) -> None:
        self._ports = ports
        self._capability_code = capability_code

    def _execute(self, command: Any) -> TaskResult:
        with self._ports.uow_factory() as uow:
            plan = uow.plans.get_by_id_for_update(command.plan_id)
            if plan is None:
                raise _plan_not_found()
            _require_planning(plan)
            _require_turn_ownership(plan, command.turn_id)
            task = uow.tasks.create(
                self._ports.task_factory(
                    task_id=_new_id("task"),
                    plan_id=plan.plan_id,
                    turn_id=plan.turn_id,
                    capability_code=self._capability_code.value,
                    input_json={"document_id": command.document_id},
                    sequence=command.sequence,
                    status=TaskStatus.DRAFT.value,
                )
            )
            uow.commit()
            return TaskResult.model_validate(task)


class CreateProcessDocumentTaskUseCase(_CreateDocumentTaskUseCase):
    def __init__(self, *, ports: PlanningApplicationPorts) -> None:
        super().__init__(
            ports=ports,
            capability_code=PlanningCapabilityCode.PROCESS_DOCUMENT,
        )

    def execute(self, command: CreateProcessDocumentTaskInput) -> TaskResult:
        return self._execute(command)


class CreateBuildChunksTaskUseCase(_CreateDocumentTaskUseCase):
    def __init__(self, *, ports: PlanningApplicationPorts) -> None:
        super().__init__(
            ports=ports,
            capability_code=PlanningCapabilityCode.BUILD_DOCUMENT_CHUNKS,
        )

    def execute(self, command: CreateBuildChunksTaskInput) -> TaskResult:
        return self._execute(command)


class CreateIndexVectorsTaskUseCase(_CreateDocumentTaskUseCase):
    def __init__(self, *, ports: PlanningApplicationPorts) -> None:
        super().__init__(
            ports=ports,
            capability_code=PlanningCapabilityCode.INDEX_DOCUMENT_VECTORS,
        )

    def execute(self, command: CreateIndexVectorsTaskInput) -> TaskResult:
        return self._execute(command)


class FinalizePlanUseCase:
    """原子发布 draft Tasks，并把真实 task_id 写回 Turn。"""

    def __init__(self, *, ports: PlanningApplicationPorts) -> None:
        self._ports = ports

    def execute(self, command: FinalizePlanInput) -> FinalizePlanResult:
        with self._ports.uow_factory() as uow:
            plan = uow.plans.get_by_id_for_update(command.plan_id)
            if plan is None:
                raise _plan_not_found()
            _require_planning(plan)
            _require_turn_ownership(plan, command.turn_id)

            tasks = uow.tasks.list_by_plan_id_and_status_for_update(
                plan.plan_id,
                TaskStatus.DRAFT.value,
            )
            if len(tasks) > MAX_TASKS_PER_PLAN:
                raise PlanningApplicationError(
                    409,
                    f"Plan 的 Task 数量不能超过 {MAX_TASKS_PER_PLAN}",
                    result_code="plan_task_limit_exceeded",
                )
            sequences = [task.sequence for task in tasks]
            expected_sequences = list(range(1, len(tasks) + 1))
            if sequences != expected_sequences:
                raise PlanningApplicationError(
                    409,
                    "Task sequence 必须唯一且从 1 开始连续",
                    result_code="plan_task_sequence_invalid",
                )

            turn = uow.conversation_turns.get_by_id_for_update(plan.turn_id)
            if turn is None:
                raise _turn_not_found()
            task_ids = [task.task_id for task in tasks]
            uow.tasks.set_status(tasks, TaskStatus.PENDING.value)
            uow.plans.set_status(
                plan,
                status=PlanStatus.READY.value,
                failure_reason=None,
            )
            uow.conversation_turns.set_task_ids(turn, task_ids)
            uow.commit()
            return FinalizePlanResult(
                plan_id=plan.plan_id,
                turn_id=plan.turn_id,
                plan_status=plan.status,
                task_ids=task_ids,
            )


class _MarkPlanUseCase:
    def __init__(
        self,
        *,
        ports: PlanningApplicationPorts,
        target_status: PlanStatus,
    ) -> None:
        self._ports = ports
        self._target_status = target_status

    def _execute(self, plan_id: str, reason: str) -> PlanResult:
        normalized_reason = reason.strip()
        if not normalized_reason:
            raise PlanningApplicationError(
                400,
                "失败原因不能为空",
                result_code="invalid_plan_failure_reason",
            )
        with self._ports.uow_factory() as uow:
            plan = uow.plans.get_by_id_for_update(plan_id)
            if plan is None:
                raise _plan_not_found()
            _require_planning(plan)
            uow.plans.set_status(
                plan,
                status=self._target_status.value,
                failure_reason=normalized_reason,
            )
            uow.commit()
            return PlanResult.model_validate(plan)


class MarkPlanUnsupportedUseCase(_MarkPlanUseCase):
    def __init__(self, *, ports: PlanningApplicationPorts) -> None:
        super().__init__(ports=ports, target_status=PlanStatus.UNSUPPORTED)

    def execute(self, command: MarkPlanUnsupportedInput) -> PlanResult:
        return self._execute(command.plan_id, command.reason)


class MarkPlanRetryPendingUseCase(_MarkPlanUseCase):
    def __init__(self, *, ports: PlanningApplicationPorts) -> None:
        super().__init__(ports=ports, target_status=PlanStatus.RETRY_PENDING)

    def execute(self, command: MarkPlanRetryPendingInput) -> PlanResult:
        return self._execute(command.plan_id, command.reason)


@dataclass(frozen=True)
class PlanningUseCases:
    create_plan: CreatePlanUseCase
    create_process_document_task: CreateProcessDocumentTaskUseCase
    create_build_chunks_task: CreateBuildChunksTaskUseCase
    create_index_vectors_task: CreateIndexVectorsTaskUseCase
    finalize_plan: FinalizePlanUseCase
    mark_plan_unsupported: MarkPlanUnsupportedUseCase
    mark_plan_retry_pending: MarkPlanRetryPendingUseCase


def build_planning_use_cases(
    ports: PlanningApplicationPorts,
) -> PlanningUseCases:
    """以同一组显式 Ports 装配全部 Planning Use Cases。"""
    return PlanningUseCases(
        create_plan=CreatePlanUseCase(ports=ports),
        create_process_document_task=CreateProcessDocumentTaskUseCase(
            ports=ports
        ),
        create_build_chunks_task=CreateBuildChunksTaskUseCase(ports=ports),
        create_index_vectors_task=CreateIndexVectorsTaskUseCase(ports=ports),
        finalize_plan=FinalizePlanUseCase(ports=ports),
        mark_plan_unsupported=MarkPlanUnsupportedUseCase(ports=ports),
        mark_plan_retry_pending=MarkPlanRetryPendingUseCase(ports=ports),
    )
