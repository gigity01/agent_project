"""一次 Planner Run 的 Application 闭环入口。"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
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
from app.modules.context.application.ports import ContextChainMapperPort
from app.modules.context.application.resource_service import (
    ContextResourceService,
)
from app.modules.context.domain.models import ContextChain
from app.modules.planning.application.dto import (
    CreatePlanInput,
    MarkPlanRetryPendingInput,
    PlannerContextInput,
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


@dataclass(frozen=True)
class _PlanningChainSnapshot:
    chain: ContextChain
    resource_version: int


@dataclass(frozen=True)
class _PlannableSnapshot:
    current_user_input: str
    chains: list[_PlanningChainSnapshot]


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
        context_resource_service: ContextResourceService,
        context_chain_mapper: ContextChainMapperPort,
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
        self._context_resource_service = context_resource_service
        self._context_chain_mapper = context_chain_mapper
        self._operations_services = operations_services
        self._audit_logger_factory = audit_logger_factory

    async def execute(self, command: RunPlanningInput) -> RunPlanningResult:
        planner_input = await self._load_plannable_input(
            command,
            {ContextTurnStatus.CONTEXT_READY.value},
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
            planner_input,
        )

    async def execute_existing(
        self,
        command: RunPlanningInput,
        plan_id: str,
    ) -> RunPlanningResult:
        """运行已由外层事务创建的新 revision Plan。"""
        planner_input = await self._load_plannable_input(
            command,
            {
                ContextTurnStatus.CONTEXT_READY.value,
                ContextTurnStatus.PROCESSING.value,
                ContextTurnStatus.COMPLETED.value,
            },
        )
        await asyncio.to_thread(self._validate_existing_plan, command, plan_id)
        return await self._run_existing_plan(command, plan_id, planner_input)

    async def _run_existing_plan(
        self,
        command: RunPlanningInput,
        plan_id: str,
        planner_input: PlannerContextInput,
    ) -> RunPlanningResult:
        context = self._build_agent_context(
            command,
            plan_id,
            planner_input,
        )

        try:
            runner_result = await self._planner_runner.run(
                planner_input=planner_input,
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

    async def _load_plannable_input(
        self,
        command: RunPlanningInput,
        allowed_statuses: set[str],
    ) -> PlannerContextInput:
        snapshot = await asyncio.to_thread(
            self._load_plannable_snapshot,
            command,
            allowed_statuses,
        )
        context_chains: list[ContextChain] = []
        for loaded in snapshot.chains:
            queue = await self._context_resource_service.get_queue(
                conversation_id=command.conversation_id,
                chain_id=loaded.chain.chain_id,
                resource_version=loaded.resource_version,
            )
            context_chains.append(
                loaded.chain.model_copy(update={"resource_queue": queue})
            )
        return PlannerContextInput(
            current_user_input=snapshot.current_user_input,
            context_chains=context_chains,
        )

    def _load_plannable_snapshot(
        self,
        command: RunPlanningInput,
        allowed_statuses: set[str],
    ) -> _PlannableSnapshot:
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
                    "Conversation Turn 尚未完成 Context Selection",
                    result_code="turn_state_conflict",
                )
            selection = uow.context.get_route_record(command.turn_id)
            if selection is None:
                raise PlanningApplicationError(
                    409,
                    "Conversation Turn 缺少 Context Selection",
                    result_code="context_selection_missing",
                )
            if selection.conversation_id != command.conversation_id:
                raise PlanningApplicationError(
                    409,
                    "Context Selection 会话归属不一致",
                    result_code="context_selection_conflict",
                )

            chain_ids = list(selection.selected_chain_ids or [])
            chain_models = uow.context.get_chains_by_ids(chain_ids)
            chain_map = {chain.chain_id: chain for chain in chain_models}
            chains: list[_PlanningChainSnapshot] = []
            for chain_id in chain_ids:
                chain = chain_map.get(chain_id)
                if chain is None:
                    raise PlanningApplicationError(
                        409,
                        f"Context Selection Chain 不存在: {chain_id}",
                        result_code="context_selection_chain_missing",
                    )
                if chain.conversation_id != command.conversation_id:
                    raise PlanningApplicationError(
                        409,
                        f"Context Selection Chain 会话归属不一致: {chain_id}",
                        result_code="context_selection_conflict",
                    )
                chains.append(
                    _PlanningChainSnapshot(
                        chain=self._context_chain_mapper(
                            chain,
                            resource_queue=(
                                self._context_resource_service.empty_queue()
                            ),
                        ),
                        resource_version=chain.resource_version,
                    )
                )
            return _PlannableSnapshot(
                current_user_input=turn.user_input,
                chains=chains,
            )

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
        planner_input: PlannerContextInput,
    ) -> AgentToolContext:
        allowed_chain_ids = frozenset(
            chain.chain_id for chain in planner_input.context_chains
        )
        allowed_turn_ids = frozenset(
            {
                command.turn_id,
                *(
                    node.turn_id
                    for chain in planner_input.context_chains
                    for node in chain.nodes
                ),
            }
        )
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
            allowed_context_chain_ids=allowed_chain_ids,
            allowed_context_turn_ids=allowed_turn_ids,
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
    PlannerContextInput,
