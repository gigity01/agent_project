"""Plan 与 Task 的事务型核心 Use Cases。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
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
    MarkPlanNeedsClarificationInput,
    MarkPlanUnsupportedInput,
    PlanResult,
    TaskResult,
    SetClarificationQuestionInput,
)
from app.modules.planning.application.errors import PlanningApplicationError
from app.modules.planning.application.ports import PlanningApplicationPorts
from app.modules.planning.domain.enums import (
    PlanningCapabilityCode,
    PlanStatus,
    TaskStatus,
)
from app.modules.context.domain.enums import ContextTurnStatus
from app.modules.messaging.domain.enums import (
    OutboxEventStatus,
    RuntimeEventType,
)
from app.modules.clarification.domain.enums import ClarificationStatus


MAX_TASKS_PER_PLAN = 10
MAX_PLAN_DAG_DEPTH = 3


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _new_outbox_event(
    ports: PlanningApplicationPorts,
    *,
    event_type: RuntimeEventType,
    aggregate_id: str,
    payload: dict,
):
    return ports.outbox_event_factory(
        event_id=_new_id("event"),
        event_type=event_type.value,
        aggregate_type="plan",
        aggregate_id=aggregate_id,
        payload_json=payload,
        status=OutboxEventStatus.PENDING.value,
        attempts=0,
        available_at=datetime.now(),
        published_at=None,
    )


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
            existing = (
                uow.plans.get_by_workflow_and_revision(
                    command.workflow_id,
                    command.revision,
                )
                if command.workflow_id is not None
                else uow.plans.get_by_turn_and_revision(
                    command.turn_id,
                    command.revision,
                )
            )
            if existing is not None:
                raise PlanningApplicationError(
                    409,
                    "该 Turn 的 Plan revision 已存在",
                    result_code="plan_revision_conflict",
                )
            plan = uow.plans.create(
                self._ports.plan_factory(
                    plan_id=_new_id("plan"),
                    workflow_id=(command.workflow_id or _new_id("workflow")),
                    turn_id=command.turn_id,
                    parent_plan_id=command.parent_plan_id,
                    current_task_id=None,
                    status=PlanStatus.PLANNING.value,
                    revision=command.revision,
                    failure_code=None,
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
            draft_tasks = (
                uow.tasks.list_by_plan_id_and_status_for_update(
                    plan.plan_id,
                    TaskStatus.DRAFT.value,
                )
            )
            if len(draft_tasks) >= MAX_TASKS_PER_PLAN:
                raise PlanningApplicationError(
                    409,
                    f"Plan 的 draft Task 数量不能超过 {MAX_TASKS_PER_PLAN}",
                    result_code="plan_task_limit_exceeded",
                )
            if any(
                task.sequence == command.sequence
                for task in draft_tasks
            ):
                raise PlanningApplicationError(
                    409,
                    "同一 Plan 的 Task sequence 不得重复",
                    result_code="plan_task_sequence_conflict",
                )
            if any(task.task_ref == command.task_ref for task in draft_tasks):
                raise PlanningApplicationError(
                    409,
                    "同一 Plan 的 task_ref 不得重复",
                    result_code="plan_task_ref_conflict",
                )
            dependency_refs = list(dict.fromkeys(command.depends_on_task_refs))
            if command.task_ref in dependency_refs:
                raise PlanningApplicationError(
                    409,
                    "Task 不能依赖自身 task_ref",
                    result_code="plan_task_dependency_invalid",
                )
            try:
                task = uow.tasks.create(
                    self._ports.task_factory(
                        task_id=_new_id("task"),
                        plan_id=plan.plan_id,
                        turn_id=plan.turn_id,
                        task_ref=command.task_ref,
                        capability_code=self._capability_code.value,
                        input_json={
                            "document_id": command.document_id,
                            "_depends_on_task_refs": dependency_refs,
                        },
                        sequence=command.sequence,
                        status=TaskStatus.DRAFT.value,
                        attempt_count=0,
                        max_attempts=3,
                    )
                )
            except Exception as exc:
                if self._ports.is_integrity_error(exc):
                    raise PlanningApplicationError(
                        409,
                        "同一 Plan 的 Task sequence 不得重复",
                        result_code="plan_task_sequence_conflict",
                    ) from exc
                raise
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
            if not tasks:
                raise PlanningApplicationError(
                    409,
                    "Plan 至少需要一个 draft Task 才能发布",
                    result_code="plan_task_count_invalid",
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

            dependency_pairs = self._validate_dag(tasks)

            turn = uow.conversation_turns.get_by_id_for_update(plan.turn_id)
            if turn is None:
                raise _turn_not_found()
            if turn.status not in {
                ContextTurnStatus.CONTEXT_READY.value,
                ContextTurnStatus.PROCESSING.value,
            }:
                raise PlanningApplicationError(
                    409,
                    "Conversation Turn 当前状态不允许发布 Plan",
                    result_code="turn_state_conflict",
                )
            task_ids = [task.task_id for task in tasks]
            uow.task_dependencies.add_all(
                self._ports.task_dependency_factory(
                    dependency_id=_new_id("dependency"),
                    plan_id=plan.plan_id,
                    task_id=task_id,
                    depends_on_task_id=depends_on_task_id,
                )
                for task_id, depends_on_task_id in dependency_pairs
            )
            for task in tasks:
                task.input_json = {
                    key: value
                    for key, value in task.input_json.items()
                    if key != "_depends_on_task_refs"
                }
            uow.tasks.set_status(tasks, TaskStatus.PENDING.value)
            uow.plans.set_status(
                plan,
                status=PlanStatus.READY.value,
                failure_reason=None,
            )
            uow.conversation_turns.set_task_ids(turn, task_ids)
            uow.conversation_turns.set_status(
                turn,
                ContextTurnStatus.PROCESSING.value,
            )
            uow.outbox.add(
                _new_outbox_event(
                    self._ports,
                    event_type=RuntimeEventType.PLAN_WAKEUP,
                    aggregate_id=plan.plan_id,
                    payload={
                        "workflow_id": plan.workflow_id,
                        "plan_id": plan.plan_id,
                    },
                )
            )
            uow.commit()
            return FinalizePlanResult(
                plan_id=plan.plan_id,
                turn_id=plan.turn_id,
                plan_status=plan.status,
                task_ids=task_ids,
            )

    @staticmethod
    def _validate_dag(tasks: list[Any]) -> list[tuple[str, str]]:
        by_ref = {task.task_ref: task for task in tasks}
        if len(by_ref) != len(tasks):
            raise PlanningApplicationError(
                409,
                "Task task_ref 必须唯一",
                result_code="plan_task_ref_conflict",
            )
        graph: dict[str, list[str]] = {}
        for task in tasks:
            refs = list(task.input_json.get("_depends_on_task_refs", []))
            if len(refs) != len(set(refs)):
                raise PlanningApplicationError(
                    409,
                    "Task 依赖引用不得重复",
                    result_code="plan_task_dependency_invalid",
                )
            unknown = set(refs) - set(by_ref)
            if unknown:
                raise PlanningApplicationError(
                    409,
                    "Task 依赖引用不存在: " + ", ".join(sorted(unknown)),
                    result_code="plan_task_dependency_missing",
                )
            if task.task_ref in refs:
                raise PlanningApplicationError(
                    409,
                    "Task 不能依赖自身",
                    result_code="plan_task_dependency_invalid",
                )
            graph[task.task_ref] = refs

        depths: dict[str, int] = {}
        visiting: set[str] = set()

        def depth(task_ref: str) -> int:
            if task_ref in depths:
                return depths[task_ref]
            if task_ref in visiting:
                raise PlanningApplicationError(
                    409,
                    "Task DAG 不能包含循环依赖",
                    result_code="plan_task_dependency_cycle",
                )
            visiting.add(task_ref)
            predecessors = graph[task_ref]
            result = 1 + max((depth(ref) for ref in predecessors), default=0)
            visiting.remove(task_ref)
            depths[task_ref] = result
            return result

        if max((depth(task_ref) for task_ref in graph), default=0) > MAX_PLAN_DAG_DEPTH:
            raise PlanningApplicationError(
                409,
                f"Plan DAG 深度不能超过 {MAX_PLAN_DAG_DEPTH}",
                result_code="plan_task_dependency_depth_exceeded",
            )
        return [
            (by_ref[task_ref].task_id, by_ref[dependency_ref].task_id)
            for task_ref, dependency_refs in graph.items()
            for dependency_ref in dependency_refs
        ]


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
            if not (
                self._target_status == PlanStatus.RETRY_PENDING
                and plan.status == PlanStatus.NEEDS_CLARIFICATION.value
            ):
                _require_planning(plan)
            uow.plans.set_status(
                plan,
                status=self._target_status.value,
                failure_code=(
                    "planner_system_failure"
                    if self._target_status == PlanStatus.RETRY_PENDING
                    else "unsupported"
                ),
                failure_reason=normalized_reason,
            )
            if self._target_status == PlanStatus.RETRY_PENDING:
                clarification = uow.clarifications.get_by_plan_id_for_update(
                    plan.plan_id
                )
                if clarification is not None:
                    clarification.status = ClarificationStatus.EXPIRED.value
                    clarification.resolved_at = datetime.now()
                turn = uow.conversation_turns.get_by_id_for_update(
                    plan.turn_id
                )
                if turn is None:
                    raise _turn_not_found()
                uow.conversation_turns.set_status(
                    turn,
                    ContextTurnStatus.PROCESSING.value,
                )
                uow.outbox.add(
                    _new_outbox_event(
                        self._ports,
                        event_type=RuntimeEventType.REPLAN_REQUESTED,
                        aggregate_id=plan.plan_id,
                        payload={
                            "workflow_id": plan.workflow_id,
                            "conversation_id": turn.conversation_id,
                            "root_turn_id": plan.turn_id,
                            "previous_plan_id": plan.plan_id,
                            "next_revision": plan.revision + 1,
                            "trigger_type": "planner_system_failure",
                            "source_task_id": None,
                            "error_code": "planner_system_failure",
                            "error_message": normalized_reason,
                        },
                    )
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


class MarkPlanNeedsClarificationUseCase:
    def __init__(self, *, ports: PlanningApplicationPorts) -> None:
        self._ports = ports

    def execute(self, command: MarkPlanNeedsClarificationInput) -> PlanResult:
        with self._ports.uow_factory() as uow:
            plan = uow.plans.get_by_id_for_update(command.plan_id)
            if plan is None:
                raise _plan_not_found()
            _require_planning(plan)
            turn = uow.conversation_turns.get_by_id_for_update(plan.turn_id)
            if turn is None:
                raise _turn_not_found()
            if turn.conversation_id != command.conversation_id:
                raise PlanningApplicationError(
                    409,
                    "Clarification 会话归属不一致",
                    result_code="clarification_conversation_conflict",
                )
            if turn.status not in {
                ContextTurnStatus.CONTEXT_READY.value,
                ContextTurnStatus.PROCESSING.value,
            }:
                raise PlanningApplicationError(
                    409,
                    "Conversation Turn 当前状态不允许标记需要澄清",
                    result_code="turn_state_conflict",
                )
            if (
                uow.clarifications.get_by_source_turn_id_for_update(
                    plan.turn_id
                )
                is not None
            ):
                raise PlanningApplicationError(
                    409,
                    "Conversation Turn 已存在 ClarificationRequest",
                    result_code="clarification_conflict",
                )
            uow.plans.set_status(
                plan,
                status=PlanStatus.NEEDS_CLARIFICATION.value,
                failure_code="clarification_required",
                failure_reason=command.reason,
            )
            uow.conversation_turns.set_status(
                turn,
                ContextTurnStatus.NEEDS_CLARIFICATION.value,
            )
            uow.clarifications.add(
                self._ports.clarification_request_factory(
                    clarification_id=_new_id("clarification"),
                    conversation_id=command.conversation_id,
                    source_turn_id=plan.turn_id,
                    source_plan_id=plan.plan_id,
                    kind=command.kind,
                    reason=command.reason,
                    question=None,
                    required_information_json=list(
                        command.required_information
                    ),
                    known_resource_refs_json=list(
                        command.known_resource_refs
                    ),
                    status=ClarificationStatus.OPEN.value,
                    answer_turn_id=None,
                    resolved_at=None,
                )
            )
            uow.commit()
            return PlanResult.model_validate(plan)


class SetClarificationQuestionUseCase:
    def __init__(self, *, ports: PlanningApplicationPorts) -> None:
        self._ports = ports

    def execute(self, command: SetClarificationQuestionInput) -> str:
        with self._ports.uow_factory() as uow:
            plan = uow.plans.get_by_id_for_update(command.plan_id)
            request = uow.clarifications.get_by_plan_id_for_update(
                command.plan_id
            )
            if plan is None or request is None:
                raise PlanningApplicationError(
                    404,
                    "ClarificationRequest 不存在",
                    result_code="clarification_not_found",
                )
            turn = uow.conversation_turns.get_by_id_for_update(plan.turn_id)
            if turn is None:
                raise _turn_not_found()
            if plan.status != PlanStatus.NEEDS_CLARIFICATION.value:
                raise PlanningApplicationError(
                    409,
                    "Plan 当前不等待澄清",
                    result_code="plan_state_conflict",
                )
            if turn.status != ContextTurnStatus.NEEDS_CLARIFICATION.value:
                raise PlanningApplicationError(
                    409,
                    "Conversation Turn 当前不等待澄清",
                    result_code="turn_state_conflict",
                )
            request.question = command.question
            turn.assistant_content = command.question
            turn.assistant_compact = command.question
            turn.task_result_summary = "等待用户补充信息"
            uow.commit()
            return request.question


@dataclass(frozen=True)
class PlanningUseCases:
    create_plan: CreatePlanUseCase
    create_process_document_task: CreateProcessDocumentTaskUseCase
    create_build_chunks_task: CreateBuildChunksTaskUseCase
    create_index_vectors_task: CreateIndexVectorsTaskUseCase
    finalize_plan: FinalizePlanUseCase
    mark_plan_unsupported: MarkPlanUnsupportedUseCase
    mark_plan_retry_pending: MarkPlanRetryPendingUseCase
    mark_plan_needs_clarification: MarkPlanNeedsClarificationUseCase
    set_clarification_question: SetClarificationQuestionUseCase


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
        mark_plan_needs_clarification=MarkPlanNeedsClarificationUseCase(
            ports=ports
        ),
        set_clarification_question=SetClarificationQuestionUseCase(
            ports=ports
        ),
    )
