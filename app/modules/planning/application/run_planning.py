"""一次 Planner Run 的 Application 闭环入口。"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from uuid import uuid4

from app.agent_runtime.audit import AgentToolAuditLogger
from app.agent_runtime.context import (
    AgentToolContext,
    ContextToolServices,
    DocumentToolServices,
    OperationsToolServices,
    PlanningToolServices,
)
from app.modules.context.domain.enums import ContextTurnStatus
from app.modules.planning.application.dto import (
    CreatePlanInput,
    MarkPlanRetryPendingInput,
    RunPlanningInput,
    RunPlanningResult,
    SetClarificationQuestionInput,
)
from app.modules.planning.application.errors import PlanningApplicationError
from app.modules.planning.application.ports import (
    PlannerRunnerPort,
    PlanningApplicationPorts,
)
from app.modules.planning.application.use_cases import PlanningUseCases
from app.modules.planning.domain.enums import PlanStatus, TaskStatus


PLANNER_PERMISSIONS = frozenset(
    {
        "document:read",
        "context:read",
        "operations:read",
        "planning:write",
    }
)
PLANNER_ACTOR_CODE = "planner_agent"
PLANNER_AGENT_NAME = "planner"


class RunPlanningUseCase:
    """创建新 Plan、运行 Agent，并以数据库状态结束本轮规划。"""

    def __init__(
        self,
        *,
        ports: PlanningApplicationPorts,
        planning_use_cases: PlanningUseCases,
        planner_runner: PlannerRunnerPort,
        document_services: DocumentToolServices,
        context_services: ContextToolServices,
        operations_services: OperationsToolServices,
        audit_logger_factory: Callable[[], AgentToolAuditLogger] = (
            AgentToolAuditLogger
        ),
    ) -> None:
        self._ports = ports
        self._planning_use_cases = planning_use_cases
        self._planner_runner = planner_runner
        self._document_services = document_services
        self._context_services = context_services
        self._operations_services = operations_services
        self._audit_logger_factory = audit_logger_factory

    async def execute(self, command: RunPlanningInput) -> RunPlanningResult:
        user_input = await asyncio.to_thread(
            self._load_plannable_turn_input,
            command,
            {ContextTurnStatus.ROUTED.value},
        )
        plan = await asyncio.to_thread(
            self._planning_use_cases.create_plan.execute,
            CreatePlanInput(
                turn_id=command.turn_id,
                revision=command.revision,
                workflow_id=command.workflow_id,
                parent_plan_id=command.parent_plan_id,
            ),
        )
        return await self._run_existing_plan(
            command,
            plan.plan_id,
            user_input,
        )

    async def execute_existing(
        self,
        command: RunPlanningInput,
        plan_id: str,
    ) -> RunPlanningResult:
        """运行已由外层事务创建的新 revision Plan。"""
        user_input = await asyncio.to_thread(
            self._load_plannable_turn_input,
            command,
            {
                ContextTurnStatus.ROUTED.value,
                ContextTurnStatus.PROCESSING.value,
                ContextTurnStatus.COMPLETED.value,
            },
        )
        await asyncio.to_thread(self._validate_existing_plan, command, plan_id)
        return await self._run_existing_plan(command, plan_id, user_input)

    async def _run_existing_plan(
        self,
        command: RunPlanningInput,
        plan_id: str,
        user_input: str,
    ) -> RunPlanningResult:
        context = self._build_agent_context(command, plan_id)

        try:
            runner_result = await self._planner_runner.run(
                user_input=user_input,
                context=context,
            )
        except Exception:
            return await asyncio.to_thread(
                self._finish_from_database,
                plan_id,
                command.turn_id,
                "Planner Runner 或 Tool 执行发生系统异常",
            )

        question = getattr(
            getattr(runner_result, "final_output", None),
            "question",
            None,
        )
        if isinstance(question, str) and question.strip():
            await asyncio.to_thread(
                self._planning_use_cases.set_clarification_question.execute,
                SetClarificationQuestionInput(
                    plan_id=plan_id,
                    question=question,
                ),
            )

        return await asyncio.to_thread(
            self._finish_from_database,
            plan_id,
            command.turn_id,
            "Planner 未调用 finalize_plan 或 mark_plan_unsupported",
        )

    def _load_plannable_turn_input(
        self,
        command: RunPlanningInput,
        allowed_statuses: set[str],
    ) -> str:
        with self._ports.uow_factory() as uow:
            turn = uow.conversation_turns.get_by_id(command.turn_id)
            if turn is None:
                raise PlanningApplicationError(
                    404,
                    "Conversation Turn 不存在",
                    result_code="turn_not_found",
                )
            if turn.conversation_id != command.conversation_id:
                raise PlanningApplicationError(
                    409,
                    "Conversation Turn 会话归属不一致",
                    result_code="turn_conversation_conflict",
                )
            if turn.status not in allowed_statuses:
                raise PlanningApplicationError(
                    409,
                    "Conversation Turn 尚未完成 Context 路由",
                    result_code="turn_state_conflict",
                )
            return turn.user_input

    def _validate_existing_plan(
        self,
        command: RunPlanningInput,
        plan_id: str,
    ) -> None:
        with self._ports.uow_factory() as uow:
            plan = uow.plans.get_by_id(plan_id)
            if plan is None:
                raise PlanningApplicationError(
                    404, "Plan 不存在", result_code="plan_not_found"
                )
            if (
                plan.turn_id != command.turn_id
                or plan.revision != command.revision
                or plan.status != PlanStatus.PLANNING.value
            ):
                raise PlanningApplicationError(
                    409,
                    "Plan revision 当前不可运行",
                    result_code="plan_state_conflict",
                )

    def _build_agent_context(
        self,
        command: RunPlanningInput,
        plan_id: str,
    ) -> AgentToolContext:
        return AgentToolContext(
            trace_id=f"trace_{uuid4().hex}",
            agent_run_id=f"agent_run_{uuid4().hex}",
            agent_name=PLANNER_AGENT_NAME,
            conversation_id=command.conversation_id,
            turn_id=command.turn_id,
            task_id=None,
            actor_code=PLANNER_ACTOR_CODE,
            permissions=PLANNER_PERMISSIONS,
            document_services=self._document_services,
            context_services=self._context_services,
            operations_services=self._operations_services,
            planning_services=PlanningToolServices(
                create_process_document_task=(
                    self._planning_use_cases.create_process_document_task
                ),
                create_build_chunks_task=(
                    self._planning_use_cases.create_build_chunks_task
                ),
                create_index_vectors_task=(
                    self._planning_use_cases.create_index_vectors_task
                ),
                finalize_plan=self._planning_use_cases.finalize_plan,
                mark_plan_unsupported=(
                    self._planning_use_cases.mark_plan_unsupported
                ),
                mark_plan_needs_clarification=(
                    self._planning_use_cases.mark_plan_needs_clarification
                ),
            ),
            plan_id=plan_id,
            audit_logger=self._audit_logger_factory(),
        )

    def _finish_from_database(
        self,
        plan_id: str,
        turn_id: str,
        retry_reason: str,
    ) -> RunPlanningResult:
        result = self._read_result(plan_id, turn_id)
        needs_retry = result.status == PlanStatus.PLANNING or (
            result.status == PlanStatus.NEEDS_CLARIFICATION
            and result.clarification_question is None
        )
        if not needs_retry:
            return result

        self._planning_use_cases.mark_plan_retry_pending.execute(
            MarkPlanRetryPendingInput(
                plan_id=plan_id,
                reason=retry_reason,
            )
        )
        return self._read_result(plan_id, turn_id)

    def _read_result(
        self,
        plan_id: str,
        turn_id: str,
    ) -> RunPlanningResult:
        with self._ports.uow_factory() as uow:
            plan = uow.plans.get_by_id(plan_id)
            if plan is None:
                raise PlanningApplicationError(
                    404,
                    "Plan 不存在",
                    result_code="plan_not_found",
                )
            if plan.turn_id != turn_id:
                raise PlanningApplicationError(
                    409,
                    "Plan 与 Conversation Turn 归属不一致",
                    result_code="plan_turn_conflict",
                )
            turn = uow.conversation_turns.get_by_id(turn_id)
            if turn is None:
                raise PlanningApplicationError(
                    404,
                    "Conversation Turn 不存在",
                    result_code="turn_not_found",
                )
            tasks = uow.tasks.list_by_plan_id(plan_id)
            clarification = uow.clarifications.get_by_plan_id(plan_id)
            status = PlanStatus(plan.status)
            task_ids: list[str] = []
            if status == PlanStatus.READY:
                pending_task_ids = [
                    task.task_id
                    for task in tasks
                    if task.status == TaskStatus.PENDING.value
                ]
                if list(turn.task_ids or []) != pending_task_ids:
                    raise PlanningApplicationError(
                        500,
                        "Plan、Task 与 Turn 的发布状态不一致",
                        result_code="planning_state_inconsistent",
                    )
                task_ids = pending_task_ids
            return RunPlanningResult(
                plan_id=plan.plan_id,
                turn_id=plan.turn_id,
                status=status,
                task_ids=task_ids,
                failure_reason=plan.failure_reason,
                clarification_question=(
                    clarification.question
                    if clarification is not None
                    else None
                ),
            )
