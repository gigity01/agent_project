"""同一 Plan 并发度为 1 的三段式 Task Runtime。"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from uuid import uuid4

from app.modules.messaging.domain.enums import (
    OutboxEventStatus,
    RuntimeEventType,
)
from app.modules.planning.domain.enums import PlanStatus, TaskStatus
from app.modules.task_runtime.application.dto import (
    ClaimNextTaskInput,
    ClaimNextTaskResult,
    ExecutePlanResult,
    RecoverySnapshot,
    TaskRuntimeContext,
    TaskSnapshot,
)
from app.modules.task_runtime.application.errors import TaskExecutionError
from app.modules.task_runtime.application.ports import (
    CapabilityRegistry,
    CompensatorRegistry,
    ExecutorRegistry,
    TaskRuntimePorts,
)
from app.modules.task_runtime.domain.enums import TaskExecutionStatus


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class TaskRuntimeService:
    """Claim、事务外执行、Completion 三段式业务 Runtime。"""

    def __init__(
        self,
        *,
        ports: TaskRuntimePorts,
        capabilities: CapabilityRegistry,
        executors: ExecutorRegistry,
        compensators: CompensatorRegistry,
        retry_delay_seconds: int = 30,
    ) -> None:
        self._ports = ports
        self._capabilities = capabilities
        self._executors = executors
        self._compensators = compensators
        self._retry_delay_seconds = retry_delay_seconds

    async def execute_next(
        self,
        plan_id: str,
        *,
        event_id: str | None = None,
    ) -> ExecutePlanResult:
        claimed = await asyncio.to_thread(
            self._claim_next,
            ClaimNextTaskInput(plan_id=plan_id),
            event_id,
        )
        if claimed.recovery is not None:
            recovery = claimed.recovery
            await self._compensate_recovery(recovery)
            return await asyncio.to_thread(
                self._complete_stale_recovery,
                recovery,
                event_id,
            )
        if claimed.task is None:
            return ExecutePlanResult(plan_id=plan_id, outcome=claimed.outcome)

        task = claimed.task
        definition = self._capabilities.require(task.capability_code)
        executor = self._executors.require(definition.executor_code)
        try:
            payload = definition.input_model.model_validate(task.input_json)
            raw_result = await asyncio.wait_for(
                executor.execute(
                    payload,
                    TaskRuntimeContext(
                        workflow_id=task.workflow_id,
                        plan_id=task.plan_id,
                        task_id=task.task_id,
                        conversation_id=task.conversation_id,
                        turn_id=task.turn_id,
                        execution_id=task.execution_id,
                        operation_id=task.operation_id,
                        agent_run_id=task.agent_run_id,
                        attempt=task.attempt,
                    ),
                ),
                timeout=definition.timeout_seconds,
            )
            output = definition.output_model.model_validate(
                raw_result.output_json
            )
        except asyncio.TimeoutError as exc:
            error = TaskExecutionError(
                "executor_timeout",
                "Task Executor 执行超时",
                retryable=True,
            )
            await self._compensate_task(task, definition)
            await asyncio.to_thread(self._fail, task, error)
            return self._failure_result(task, error)
        except TaskExecutionError as error:
            await self._compensate_task(task, definition)
            await asyncio.to_thread(self._fail, task, error)
            return self._failure_result(task, error)
        except Exception as exc:
            error = TaskExecutionError(
                "executor_system_error",
                f"Task Executor 系统异常: {type(exc).__name__}",
                retryable=False,
            )
            await self._compensate_task(task, definition)
            await asyncio.to_thread(self._fail, task, error)
            return self._failure_result(task, error)

        await asyncio.to_thread(
            self._complete,
            task,
            output.model_dump(mode="json"),
            raw_result.resource_refs,
        )
        return ExecutePlanResult(
            plan_id=plan_id,
            outcome="task_succeeded",
            task_id=task.task_id,
            execution_id=task.execution_id,
        )

    def claim_next_task(
        self,
        command: ClaimNextTaskInput,
    ) -> ClaimNextTaskResult:
        return self._claim_next(command)

    def complete_task(
        self,
        snapshot: TaskSnapshot,
        output_json: dict,
        resource_refs: list[str],
    ) -> None:
        self._complete(snapshot, output_json, resource_refs)

    def fail_task(
        self,
        snapshot: TaskSnapshot,
        error: TaskExecutionError,
    ) -> None:
        self._fail(snapshot, error)

    def _claim_next(
        self,
        command: ClaimNextTaskInput,
        event_id: str | None = None,
    ) -> ClaimNextTaskResult:
        with self._ports.uow_factory() as uow:
            if event_id is not None and uow.inbox.exists(
                "task_runtime", event_id
            ):
                return ClaimNextTaskResult(outcome="terminal")
            plan = uow.plans.get_by_id_for_update(command.plan_id)
            if plan is None:
                raise ValueError("Plan 不存在")
            if plan.status in {
                PlanStatus.COMPLETED.value,
                PlanStatus.FAILED.value,
                PlanStatus.CANCELLED.value,
                PlanStatus.SUPERSEDED.value,
                PlanStatus.REPLAN_PENDING.value,
            }:
                self._record_inbox(uow, event_id)
                if event_id is not None:
                    uow.commit()
                return ClaimNextTaskResult(outcome="terminal")
            if plan.current_task_id is not None:
                recovery = self._recover_stale_execution(uow, plan)
                if recovery is not None:
                    uow.commit()
                    return ClaimNextTaskResult(
                        outcome="compensation_required",
                        recovery=recovery,
                    )
                self._record_inbox(uow, event_id)
                if event_id is not None:
                    uow.commit()
                return ClaimNextTaskResult(outcome="already_running")
            if plan.status not in {
                PlanStatus.READY.value,
                PlanStatus.RUNNING.value,
            }:
                self._record_inbox(uow, event_id)
                if event_id is not None:
                    uow.commit()
                return ClaimNextTaskResult(outcome="terminal")

            retrying = uow.tasks.list_by_plan_id_and_status_for_update(
                plan.plan_id,
                TaskStatus.RETRY_WAIT.value,
            )
            if retrying:
                uow.tasks.set_status(retrying, TaskStatus.PENDING.value)
            task = uow.tasks.get_next_runnable_for_update(
                plan.plan_id,
                TaskStatus.PENDING.value,
                TaskStatus.SUCCEEDED.value,
            )
            if task is None:
                if retrying or event_id is not None:
                    self._record_inbox(uow, event_id)
                    uow.commit()
                return ClaimNextTaskResult(outcome="no_task")

            definition = self._capabilities.require(task.capability_code)
            attempt = task.attempt_count + 1
            task.attempt_count = attempt
            task.max_attempts = definition.max_attempts
            task.status = TaskStatus.RUNNING.value
            task.started_at = datetime.now()
            plan.status = PlanStatus.RUNNING.value
            if plan.started_at is None:
                plan.started_at = datetime.now()
            operation_id = _new_id("operation")
            execution_id = _new_id("execution")
            agent_run_id = _new_id("agent_run")
            conversation_id = self._turn_conversation_id(uow, plan.turn_id)
            uow.plans.set_current_task(plan, task.task_id)
            uow.task_executions.add(
                self._ports.task_execution_factory(
                    execution_id=execution_id,
                    task_id=task.task_id,
                    plan_id=plan.plan_id,
                    workflow_id=plan.workflow_id,
                    attempt=attempt,
                    status=TaskExecutionStatus.RUNNING.value,
                    executor_code=definition.executor_code,
                    input_snapshot_json=dict(task.input_json),
                    output_json=None,
                    resource_refs_json=[],
                    error_code=None,
                    error_message=None,
                    retryable=None,
                    agent_run_id=agent_run_id,
                    operation_id=operation_id,
                    started_at=datetime.now(),
                    completed_at=None,
                )
            )
            uow.outbox.add(
                self._event(
                    plan,
                    RuntimeEventType.PLAN_WAKEUP,
                    available_at=(
                        datetime.now()
                        + timedelta(seconds=definition.timeout_seconds)
                    ),
                )
            )
            self._record_inbox(uow, event_id)
            uow.commit()
            return ClaimNextTaskResult(
                outcome="claimed",
                task=TaskSnapshot(
                    task_id=task.task_id,
                    plan_id=plan.plan_id,
                    workflow_id=plan.workflow_id,
                    conversation_id=conversation_id,
                    turn_id=plan.turn_id,
                    capability_code=task.capability_code,
                    input_json=dict(task.input_json),
                    sequence=task.sequence,
                    attempt=attempt,
                    max_attempts=task.max_attempts,
                    execution_id=execution_id,
                    operation_id=operation_id,
                    agent_run_id=agent_run_id,
                    executor_code=definition.executor_code,
                ),
            )

    def _record_inbox(self, uow, event_id: str | None) -> None:
        if event_id is None:
            return
        uow.inbox.add(
            self._ports.inbox_event_factory(
                inbox_id=_new_id("inbox"),
                consumer_name="task_runtime",
                event_id=event_id,
                processed_at=datetime.now(),
            )
        )

    def _recover_stale_execution(
        self,
        uow,
        plan,
    ) -> RecoverySnapshot | None:
        task = uow.tasks.get_by_id_for_update(plan.current_task_id)
        if task is None:
            raise RuntimeError("Plan current_task_id 指向不存在的 Task")
        definition = self._capabilities.require(task.capability_code)
        execution = uow.task_executions.get_latest_by_task_for_update(
            task.task_id
        )
        if execution is None:
            raise RuntimeError("Running Task 缺少 TaskExecution")
        if execution.status == TaskExecutionStatus.COMPENSATION_REQUIRED.value:
            return self._recovery_snapshot(uow, plan, task, execution)
        if execution.status != TaskExecutionStatus.RUNNING.value:
            raise RuntimeError("Running Task 的 TaskExecution 状态不一致")
        started_at = task.started_at
        if (
            started_at is None
            or datetime.now()
            < started_at + timedelta(seconds=definition.timeout_seconds)
        ):
            return None
        execution.status = TaskExecutionStatus.COMPENSATION_REQUIRED.value
        execution.error_code = "execution_lease_expired"
        execution.error_message = "Task Execution 超时未完成"
        execution.retryable = True
        execution.completed_at = None
        return self._recovery_snapshot(uow, plan, task, execution)

    def _recovery_snapshot(self, uow, plan, task, execution) -> RecoverySnapshot:
        if execution.agent_run_id is None:
            raise RuntimeError("TaskExecution 缺少 agent_run_id")
        return RecoverySnapshot(
            task_id=task.task_id,
            plan_id=plan.plan_id,
            workflow_id=plan.workflow_id,
            conversation_id=self._turn_conversation_id(uow, plan.turn_id),
            turn_id=plan.turn_id,
            capability_code=task.capability_code,
            input_json=dict(execution.input_snapshot_json),
            attempt=execution.attempt,
            max_attempts=task.max_attempts,
            execution_id=execution.execution_id,
            operation_id=execution.operation_id,
            agent_run_id=execution.agent_run_id,
        )

    async def _compensate_task(self, task: TaskSnapshot, definition) -> None:
        await self._run_compensator(task, definition)

    async def _compensate_recovery(self, recovery: RecoverySnapshot) -> None:
        definition = self._capabilities.require(recovery.capability_code)
        await self._run_compensator(recovery, definition)

    async def _run_compensator(self, snapshot, definition) -> None:
        if definition.compensator_code is None:
            if definition.side_effect:
                raise RuntimeError("有副作用的 Capability 缺少 Compensator")
            return
        payload = definition.input_model.model_validate(snapshot.input_json)
        compensator = self._compensators.require(
            definition.compensator_code
        )
        await compensator.compensate(
            operation_id=snapshot.operation_id,
            payload=payload,
            context=self._runtime_context(snapshot),
        )

    @staticmethod
    def _runtime_context(snapshot) -> TaskRuntimeContext:
        return TaskRuntimeContext(
            workflow_id=snapshot.workflow_id,
            plan_id=snapshot.plan_id,
            task_id=snapshot.task_id,
            conversation_id=snapshot.conversation_id,
            turn_id=snapshot.turn_id,
            execution_id=snapshot.execution_id,
            operation_id=snapshot.operation_id,
            agent_run_id=snapshot.agent_run_id,
            attempt=snapshot.attempt,
        )

    def _complete_stale_recovery(
        self,
        snapshot: RecoverySnapshot,
        event_id: str | None,
    ) -> ExecutePlanResult:
        with self._ports.uow_factory() as uow:
            plan = uow.plans.get_by_id_for_update(snapshot.plan_id)
            task = uow.tasks.get_by_id_for_update(snapshot.task_id)
            execution = uow.task_executions.get_by_id_for_update(
                snapshot.execution_id
            )
            if plan is None or task is None or execution is None:
                raise RuntimeError("Task Runtime 恢复状态记录不存在")
            if (
                plan.current_task_id != task.task_id
                or task.status != TaskStatus.RUNNING.value
                or execution.status
                != TaskExecutionStatus.COMPENSATION_REQUIRED.value
                or execution.attempt != snapshot.attempt
                or execution.operation_id != snapshot.operation_id
            ):
                raise RuntimeError("Task Execution 补偿 token 已失效")

            now = datetime.now()
            execution.status = TaskExecutionStatus.COMPENSATED.value
            execution.completed_at = now
            task.last_error_code = execution.error_code
            task.last_error_message = execution.error_message
            task.completed_at = now
            uow.plans.set_current_task(plan, None)
            if task.attempt_count < task.max_attempts:
                task.status = TaskStatus.PENDING.value
                uow.outbox.add(
                    self._event(plan, RuntimeEventType.PLAN_WAKEUP)
                )
                outcome = "retry_scheduled"
            else:
                task.status = TaskStatus.FAILED.value
                plan.status = PlanStatus.REPLAN_PENDING.value
                plan.failure_code = execution.error_code
                plan.failure_reason = execution.error_message
                uow.outbox.add(
                    self._event(
                        plan,
                        RuntimeEventType.REPLAN_REQUESTED,
                        payload={
                            "workflow_id": plan.workflow_id,
                            "conversation_id": snapshot.conversation_id,
                            "root_turn_id": plan.turn_id,
                            "previous_plan_id": plan.plan_id,
                            "next_revision": plan.revision + 1,
                            "trigger_type": "task_terminal_failure",
                            "source_task_id": task.task_id,
                            "error_code": execution.error_code,
                            "error_message": execution.error_message,
                        },
                    )
                )
                outcome = "replan_requested"
            self._record_inbox(uow, event_id)
            uow.commit()
            return ExecutePlanResult(
                plan_id=plan.plan_id,
                outcome=outcome,
                task_id=task.task_id,
                execution_id=execution.execution_id,
            )

    def _complete(
        self,
        snapshot: TaskSnapshot,
        output_json: dict,
        resource_refs: list[str],
    ) -> None:
        with self._ports.uow_factory() as uow:
            plan, task, execution = self._lock_execution(uow, snapshot)
            now = datetime.now()
            task.status = TaskStatus.SUCCEEDED.value
            task.output_json = output_json
            task.last_error_code = None
            task.last_error_message = None
            task.completed_at = now
            execution.status = TaskExecutionStatus.SUCCEEDED.value
            execution.output_json = output_json
            execution.resource_refs_json = list(dict.fromkeys(resource_refs))
            execution.completed_at = now
            uow.plans.set_current_task(plan, None)

            pending_count = uow.tasks.count_by_plan_and_status(
                plan.plan_id, TaskStatus.PENDING.value
            )
            retry_count = uow.tasks.count_by_plan_and_status(
                plan.plan_id, TaskStatus.RETRY_WAIT.value
            )
            if pending_count or retry_count:
                uow.outbox.add(self._event(plan, RuntimeEventType.PLAN_WAKEUP))
            else:
                unfinished = [
                    item
                    for item in uow.tasks.list_by_plan_id(plan.plan_id)
                    if item.status != TaskStatus.SUCCEEDED.value
                ]
                if not unfinished:
                    plan.status = PlanStatus.COMPLETED.value
                    plan.completed_at = now
                    uow.outbox.add(
                        self._event(plan, RuntimeEventType.AGGREGATION_REQUESTED)
                    )
            uow.commit()

    def _fail(self, snapshot: TaskSnapshot, error: TaskExecutionError) -> None:
        with self._ports.uow_factory() as uow:
            plan, task, execution = self._lock_execution(uow, snapshot)
            now = datetime.now()
            execution.status = TaskExecutionStatus.FAILED.value
            execution.error_code = error.error_code
            execution.error_message = str(error)
            execution.retryable = error.retryable
            execution.completed_at = now
            task.last_error_code = error.error_code
            task.last_error_message = str(error)
            task.completed_at = now
            uow.plans.set_current_task(plan, None)

            if error.retryable and task.attempt_count < task.max_attempts:
                task.status = TaskStatus.RETRY_WAIT.value
                uow.outbox.add(
                    self._event(
                        plan,
                        RuntimeEventType.PLAN_WAKEUP,
                        available_at=now + timedelta(seconds=self._retry_delay_seconds),
                    )
                )
            else:
                task.status = (
                    TaskStatus.BLOCKED.value if error.blocked else TaskStatus.FAILED.value
                )
                plan.status = PlanStatus.REPLAN_PENDING.value
                plan.failure_code = error.error_code
                plan.failure_reason = str(error)
                uow.outbox.add(
                    self._event(
                        plan,
                        RuntimeEventType.REPLAN_REQUESTED,
                        payload={
                            "workflow_id": plan.workflow_id,
                            "conversation_id": self._turn_conversation_id(uow, plan.turn_id),
                            "root_turn_id": plan.turn_id,
                            "previous_plan_id": plan.plan_id,
                            "next_revision": plan.revision + 1,
                            "trigger_type": (
                                "task_blocked" if error.blocked else "task_terminal_failure"
                            ),
                            "source_task_id": task.task_id,
                            "error_code": error.error_code,
                            "error_message": str(error),
                        },
                    )
                )
            uow.commit()

    def _lock_execution(self, uow, snapshot: TaskSnapshot):
        plan = uow.plans.get_by_id_for_update(snapshot.plan_id)
        task = uow.tasks.get_by_id_for_update(snapshot.task_id)
        execution = uow.task_executions.get_by_id_for_update(snapshot.execution_id)
        if plan is None or task is None or execution is None:
            raise RuntimeError("Task Runtime 状态记录不存在")
        if (
            plan.current_task_id != task.task_id
            or task.status != TaskStatus.RUNNING.value
            or execution.status != TaskExecutionStatus.RUNNING.value
            or execution.attempt != snapshot.attempt
            or execution.operation_id != snapshot.operation_id
            or execution.agent_run_id != snapshot.agent_run_id
        ):
            raise RuntimeError("Task Execution token 已失效")
        return plan, task, execution

    def _event(
        self,
        plan,
        event_type: RuntimeEventType,
        *,
        payload: dict | None = None,
        available_at: datetime | None = None,
    ):
        return self._ports.outbox_event_factory(
            event_id=_new_id("event"),
            event_type=event_type.value,
            aggregate_type="plan",
            aggregate_id=plan.plan_id,
            payload_json=(
                payload
                or {"workflow_id": plan.workflow_id, "plan_id": plan.plan_id}
            ),
            status=OutboxEventStatus.PENDING.value,
            attempts=0,
            available_at=available_at or datetime.now(),
            published_at=None,
        )

    @staticmethod
    def _turn_conversation_id(uow, turn_id: str) -> str:
        turn = uow.conversation_turns.get_by_id(turn_id)
        if turn is None:
            raise RuntimeError("Plan 对应 Turn 不存在")
        return turn.conversation_id

    @staticmethod
    def _failure_result(
        task: TaskSnapshot,
        error: TaskExecutionError,
    ) -> ExecutePlanResult:
        retry = error.retryable and task.attempt < task.max_attempts
        return ExecutePlanResult(
            plan_id=task.plan_id,
            outcome="retry_scheduled" if retry else "replan_requested",
            task_id=task.task_id,
            execution_id=task.execution_id,
        )
