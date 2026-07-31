"""Context 路由与完成回写的业务编排。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import uuid4

from starlette.concurrency import run_in_threadpool

from app.modules.context.application.dto import (
    ChainTurnUpdate,
    CompleteTurnCommand,
    CompleteTurnResult,
    ContextAgentInput,
    RouteContextResult,
    SendMessageCommand,
)
from app.modules.context.application.errors import (
    ContextConflictError,
    ContextRoutingError,
    ContextTurnNotFoundError,
    ContextValidationError,
    ConversationLockUnavailable,
)
from app.modules.context.application.ports import (
    ContextChainMapperPort,
    ContextRecordFactoryPort,
    ContextRouterPort,
    ConversationLockPort,
    UnitOfWorkFactory,
)
from app.modules.context.application.resource_service import (
    ContextResourceQueueRefresh,
    ContextResourceService,
    split_resource_key,
)
from app.modules.context.domain.enums import ContextTurnStatus
from app.modules.context.domain.models import (
    ContextChain,
    ContextRouteDecision,
    ConversationTurn,
)
from app.modules.context.domain.route_policy import (
    validate_route_decision,
)


DEFAULT_FULL_ASSISTANT_TURN_COUNT = 5


@dataclass(frozen=True)
class _LoadedContextChain:
    chain: ContextChain
    resource_version: int


@dataclass(frozen=True)
class _CompleteTurnTransactionResult:
    response: CompleteTurnResult
    resource_refreshes: list[ContextResourceQueueRefresh]


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class ContextService:
    """保持 Conversation 路由串行，并划分短数据库事务。"""

    def __init__(
        self,
        *,
        agent_router: ContextRouterPort | None,
        route_lock_manager: ConversationLockPort,
        resource_service: ContextResourceService,
        uow_factory: UnitOfWorkFactory,
        record_factory: ContextRecordFactoryPort,
        chain_mapper: ContextChainMapperPort,
        full_assistant_turn_count: int = DEFAULT_FULL_ASSISTANT_TURN_COUNT,
    ) -> None:
        if full_assistant_turn_count < 0:
            raise ValueError("full_assistant_turn_count cannot be negative")
        self._agent_router = agent_router
        self._route_lock_manager = route_lock_manager
        self._resource_service = resource_service
        self._uow_factory = uow_factory
        self._record_factory = record_factory
        self._chain_mapper = chain_mapper
        self._full_assistant_turn_count = full_assistant_turn_count

    async def send_message(
        self,
        command: SendMessageCommand,
    ) -> RouteContextResult:
        """创建唯一 Turn，并返回完整用户输入和全部命中链。"""
        if self._agent_router is None:
            raise RuntimeError("Context Agent Router 未配置")

        turn_id = _new_id("turn")
        turn_created = False

        try:
            async with self._route_lock_manager.hold(
                command.conversation_id
            ):
                loaded_chains = await run_in_threadpool(
                    self._create_turn_and_load_chains,
                    turn_id,
                    command,
                )
                turn_created = True
                chains: list[ContextChain] = []
                for loaded in loaded_chains:
                    resource_queue = await self._resource_service.get_queue(
                        conversation_id=command.conversation_id,
                        chain_id=loaded.chain.chain_id,
                        resource_version=loaded.resource_version,
                    )
                    chains.append(
                        loaded.chain.model_copy(
                            update={"resource_queue": resource_queue}
                        )
                    )

                agent_input = ContextAgentInput(
                    conversation_id=command.conversation_id,
                    current_turn_id=turn_id,
                    current_user_input=command.message,
                    chains=chains,
                )
                try:
                    raw_decision = await self._agent_router.route(agent_input)
                except Exception as exc:
                    raise ContextRoutingError(
                        "Context Agent 路由失败"
                    ) from exc

                try:
                    decision = validate_route_decision(
                        raw_decision,
                        chains,
                        conversation_id=command.conversation_id,
                    )
                except ValueError as exc:
                    raise ContextRoutingError(
                        f"Context Agent 返回了非法路由结果: {exc}"
                    ) from exc

                new_chain_id = (
                    _new_id("chain")
                    if decision.create_new_chain
                    else None
                )
                await run_in_threadpool(
                    self._save_route_decision,
                    turn_id,
                    command.conversation_id,
                    decision,
                    new_chain_id,
                )

                chain_map = {chain.chain_id: chain for chain in chains}
                return RouteContextResult(
                    conversation_id=command.conversation_id,
                    turn_id=turn_id,
                    message=command.message,
                    selected_chains=[
                        chain_map[chain_id]
                        for chain_id in decision.selected_chain_ids
                    ],
                    new_chain_id=new_chain_id,
                    decision=decision,
                )
        except ConversationLockUnavailable:
            raise
        except Exception:
            if turn_created:
                try:
                    await run_in_threadpool(self._mark_turn_failed, turn_id)
                except Exception:
                    pass
            raise

    async def route_context(self, request: Any) -> RouteContextResult:
        """兼容旧应用调用，转发到 ``send_message()``。"""
        if isinstance(request, SendMessageCommand):
            command = request
        else:
            command = SendMessageCommand(
                conversation_id=request.conversation_id,
                message=request.user_input,
            )
        return await self.send_message(command)

    async def complete_turn(
        self,
        turn_id: str,
        command: CompleteTurnCommand,
    ) -> CompleteTurnResult:
        """按已保存路由决定关联 Turn，不接受下游扩张链路范围。"""
        conversation_id = await run_in_threadpool(
            self._get_turn_conversation_id,
            turn_id,
        )
        if conversation_id is None:
            raise ContextTurnNotFoundError("Context Turn 不存在")

        try:
            async with self._route_lock_manager.hold(conversation_id):
                result = await run_in_threadpool(
                    self._complete_turn_in_transaction,
                    turn_id,
                    conversation_id,
                    command,
                )
                for refresh in result.resource_refreshes:
                    await self._resource_service.refresh_after_commit(refresh)
                return result.response
        except ConversationLockUnavailable:
            raise

    def _create_turn_and_load_chains(
        self,
        turn_id: str,
        command: SendMessageCommand,
    ) -> list[_LoadedContextChain]:
        with self._uow_factory() as uow:
            uow.context.create_turn(
                self._record_factory.conversation_turn(
                    turn_id=turn_id,
                    conversation_id=command.conversation_id,
                    user_input=command.message,
                    task_ids=[],
                    status=ContextTurnStatus.ROUTING.value,
                )
            )
            chain_models = uow.context.list_active_chains(
                command.conversation_id
            )
            chains = [
                _LoadedContextChain(
                    chain=self._chain_mapper(
                        chain,
                        resource_queue=self._resource_service.empty_queue(),
                        full_assistant_turn_count=(
                            self._full_assistant_turn_count
                        ),
                    ),
                    resource_version=chain.resource_version,
                )
                for chain in chain_models
            ]
            uow.commit()
        return chains

    def _save_route_decision(
        self,
        turn_id: str,
        conversation_id: str,
        decision: ContextRouteDecision,
        new_chain_id: str | None,
    ) -> None:
        with self._uow_factory() as uow:
            turn = uow.context.get_turn_for_update(turn_id)
            if turn is None:
                raise RuntimeError("Context Turn disappeared before routing")
            if turn.conversation_id != conversation_id:
                raise RuntimeError("Context Turn conversation changed")
            if turn.status != ContextTurnStatus.ROUTING.value:
                raise RuntimeError("Context Turn is not awaiting routing")

            selected_chains = uow.context.get_chains_by_ids_for_update(
                decision.selected_chain_ids
            )
            selected_map = {
                chain.chain_id: chain for chain in selected_chains
            }
            for chain_id in decision.selected_chain_ids:
                chain = selected_map.get(chain_id)
                if chain is None:
                    raise RuntimeError(
                        f"Selected Context Chain disappeared: {chain_id}"
                    )
                if chain.conversation_id != conversation_id:
                    raise RuntimeError(
                        f"Selected Context Chain changed conversation: {chain_id}"
                    )
                if chain.archived:
                    raise RuntimeError(
                        f"Selected Context Chain was archived: {chain_id}"
                    )

            uow.context.create_route_record(
                self._record_factory.context_route_record(
                    route_id=_new_id("route"),
                    conversation_id=conversation_id,
                    current_turn_id=turn_id,
                    selected_chain_ids=list(
                        decision.selected_chain_ids
                    ),
                    create_new_chain=decision.create_new_chain,
                    route_mode=decision.route_mode.value,
                    reason_summary=decision.reason_summary,
                    new_chain_id=new_chain_id,
                )
            )
            uow.context.set_turn_status(
                turn,
                ContextTurnStatus.ROUTED.value,
            )
            uow.commit()

    def _mark_turn_failed(self, turn_id: str) -> None:
        with self._uow_factory() as uow:
            turn = uow.context.get_turn_for_update(turn_id)
            if (
                turn is not None
                and turn.status == ContextTurnStatus.ROUTING.value
            ):
                uow.context.set_turn_status(
                    turn,
                    ContextTurnStatus.FAILED.value,
                )
                uow.commit()

    def _get_turn_conversation_id(self, turn_id: str) -> str | None:
        with self._uow_factory() as uow:
            turn = uow.context.get_turn(turn_id)
            return None if turn is None else turn.conversation_id

    def _complete_turn_in_transaction(
        self,
        turn_id: str,
        conversation_id: str,
        command: CompleteTurnCommand,
    ) -> _CompleteTurnTransactionResult:
        with self._uow_factory() as uow:
            turn = uow.context.get_turn_for_update(turn_id)
            if turn is None:
                raise ContextTurnNotFoundError("Context Turn 不存在")
            if turn.conversation_id != conversation_id:
                raise ContextConflictError(
                    "Context Turn 会话归属已变化"
                )
            if turn.status == ContextTurnStatus.COMPLETED.value:
                return _CompleteTurnTransactionResult(
                    response=CompleteTurnResult(
                        turn=ConversationTurn.model_validate(turn),
                        linked_chain_ids=(
                            uow.context.list_linked_chain_ids(turn_id)
                        ),
                    ),
                    resource_refreshes=[],
                )
            if turn.status != ContextTurnStatus.ROUTED.value:
                raise ContextConflictError(
                    "Context Turn 尚未完成路由"
                )

            route_record = uow.context.get_route_record_for_update(turn_id)
            if route_record is None:
                raise ContextConflictError(
                    "Context Turn 缺少已校验路由决定"
                )
            if route_record.conversation_id != conversation_id:
                raise ContextConflictError(
                    "Context 路由决定会话归属不一致"
                )

            target_chain_ids = list(route_record.selected_chain_ids or [])
            if route_record.create_new_chain:
                if not route_record.new_chain_id:
                    raise ContextConflictError(
                        "Context 路由决定缺少新链 ID"
                    )
                target_chain_ids.append(route_record.new_chain_id)

            update_map = self._validate_chain_updates(
                command.chain_updates,
                target_chain_ids=target_chain_ids,
                turn_task_ids=command.task_ids,
            )
            existing_ids = list(route_record.selected_chain_ids or [])
            existing_chains = uow.context.get_chains_by_ids_for_update(
                existing_ids
            )
            chain_map = {
                chain.chain_id: chain for chain in existing_chains
            }
            for chain_id in existing_ids:
                chain = chain_map.get(chain_id)
                if chain is None:
                    raise ContextConflictError(
                        f"Context Chain 不存在: {chain_id}"
                    )
                if chain.conversation_id != conversation_id:
                    raise ContextConflictError(
                        f"Context Chain 会话归属不一致: {chain_id}"
                    )

            now = datetime.now()
            if route_record.create_new_chain:
                new_chain_id = route_record.new_chain_id
                if uow.context.get_chain_for_update(new_chain_id) is not None:
                    raise ContextConflictError(
                        "预分配的 Context Chain ID 已存在"
                    )
                new_chain = uow.context.create_chain(
                    self._record_factory.context_chain(
                        chain_id=new_chain_id,
                        conversation_id=conversation_id,
                        resources={},
                        resource_version=0,
                        last_active_at=now,
                        archived=False,
                    )
                )
                chain_map[new_chain_id] = new_chain

            normalized_task_ids = list(dict.fromkeys(command.task_ids))
            uow.context.complete_turn(
                turn,
                assistant_content=command.assistant_content,
                assistant_compact=command.assistant_compact,
                task_ids=normalized_task_ids,
                task_result_summary=command.task_result_summary,
                completed_at=now,
                status=ContextTurnStatus.COMPLETED.value,
            )

            resource_refreshes: list[ContextResourceQueueRefresh] = []
            for chain_id in target_chain_ids:
                chain = chain_map[chain_id]
                update = update_map.get(chain_id)
                related_resource_refs = (
                    list(
                        dict.fromkeys(
                            [
                                resource.resource_key
                                for resource in update.related_resources
                            ]
                            + list(update.removed_resource_keys)
                        )
                    )
                    if update is not None
                    else []
                )
                uow.context.create_node(
                    self._record_factory.context_chain_node(
                        node_id=_new_id("node"),
                        chain_id=chain_id,
                        turn_id=turn_id,
                        sequence=uow.context.get_next_sequence(chain_id),
                        related_task_ids=(
                            list(dict.fromkeys(update.related_task_ids))
                            if update is not None
                            else []
                        ),
                        related_resource_refs=related_resource_refs,
                    )
                )
                resource_refresh = (
                    self._resource_service.apply_in_transaction(
                        repository=uow.context,
                        chain=chain,
                        update=update,
                        turn_id=turn_id,
                        now=now,
                    )
                )
                if resource_refresh is not None:
                    resource_refreshes.append(resource_refresh)
                uow.context.update_chain_activity(
                    chain,
                    last_active_at=now,
                )

            uow.commit()
            return _CompleteTurnTransactionResult(
                response=CompleteTurnResult(
                    turn=ConversationTurn.model_validate(turn),
                    linked_chain_ids=target_chain_ids,
                ),
                resource_refreshes=resource_refreshes,
            )

    @staticmethod
    def _validate_chain_updates(
        updates: list[ChainTurnUpdate],
        *,
        target_chain_ids: list[str],
        turn_task_ids: list[str],
    ) -> dict[str, ChainTurnUpdate]:
        target_set = set(target_chain_ids)
        turn_task_set = set(turn_task_ids)
        update_map: dict[str, ChainTurnUpdate] = {}

        for update in updates:
            if update.chain_id in update_map:
                raise ContextValidationError(
                    f"重复的 Context Chain 更新: {update.chain_id}"
                )
            if update.chain_id not in target_set:
                raise ContextValidationError(
                    f"Context Chain 不在已路由范围内: {update.chain_id}"
                )
            unknown_task_ids = (
                set(update.related_task_ids) - turn_task_set
            )
            if unknown_task_ids:
                unknown = ", ".join(sorted(unknown_task_ids))
                raise ContextValidationError(
                    f"链关联了 Turn 中不存在的 Task: {unknown}"
                )

            resource_keys = [
                resource.resource_key
                for resource in update.related_resources
            ]
            if len(resource_keys) != len(set(resource_keys)):
                raise ContextValidationError(
                    f"链包含重复资源: {update.chain_id}"
                )

            removed_keys = list(update.removed_resource_keys)
            if len(removed_keys) != len(set(removed_keys)):
                raise ContextValidationError(
                    f"链包含重复移除资源: {update.chain_id}"
                )
            for resource_key in removed_keys:
                try:
                    split_resource_key(resource_key)
                except ValueError as exc:
                    raise ContextValidationError(str(exc)) from exc

            conflicts = set(resource_keys) & set(removed_keys)
            if conflicts:
                conflict = ", ".join(sorted(conflicts))
                raise ContextValidationError(
                    f"资源不能在同一轮同时刷新和移除: {conflict}"
                )
            update_map[update.chain_id] = update

        return update_map
