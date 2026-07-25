"""Context 路由与完成回写的业务编排。"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from uuid import uuid4

from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool

from app.agents.context_agent import ContextAgentRouter
from app.constants.context_turn_status import ContextTurnStatus
from app.db.uow.sqlalchemy import SQLAlchemyUnitOfWork
from app.integrations.conversation_route_lock import (
    ConversationRouteLockManager,
    ConversationRouteLockUnavailable,
)
from app.models.context_chain import ContextChain as ContextChainModel
from app.models.context_chain_node import ContextChainNode as ContextChainNodeModel
from app.models.context_route_record import (
    ContextRouteRecord as ContextRouteRecordModel,
)
from app.models.conversation_turn import ConversationTurn as ConversationTurnModel
from app.schemas.context import (
    CompleteContextTurnRequest,
    CompleteContextTurnResponse,
    ContextAgentInput,
    ContextChain,
    ContextChainTurnUpdate,
    ContextResources,
    ContextRouteDecision,
    ContextRouteRequest,
    ConversationTurn,
    RoutedContextPackage,
)
from app.services.context_projection import build_context_chain
from app.services.context_route_validation import validate_route_decision


UnitOfWorkFactory = Callable[[], SQLAlchemyUnitOfWork]
DEFAULT_FULL_ASSISTANT_TURN_COUNT = 5


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class ContextService:
    """保持 Conversation 路由串行，并划分短数据库事务。"""

    def __init__(
        self,
        *,
        agent_router: ContextAgentRouter | None,
        route_lock_manager: ConversationRouteLockManager,
        uow_factory: UnitOfWorkFactory = SQLAlchemyUnitOfWork,
        full_assistant_turn_count: int = DEFAULT_FULL_ASSISTANT_TURN_COUNT,
    ) -> None:
        if full_assistant_turn_count < 0:
            raise ValueError("full_assistant_turn_count cannot be negative")
        self._agent_router = agent_router
        self._route_lock_manager = route_lock_manager
        self._uow_factory = uow_factory
        self._full_assistant_turn_count = full_assistant_turn_count

    async def route_context(
        self,
        request: ContextRouteRequest,
    ) -> RoutedContextPackage:
        """创建唯一 Turn，并返回完整用户输入和全部命中链。"""
        if self._agent_router is None:
            raise RuntimeError("Context Agent Router 未配置")

        turn_id = _new_id("turn")
        turn_created = False

        try:
            async with self._route_lock_manager.hold(
                request.conversation_id
            ):
                chains = await run_in_threadpool(
                    self._create_turn_and_load_chains,
                    turn_id,
                    request,
                )
                turn_created = True

                agent_input = ContextAgentInput(
                    conversation_id=request.conversation_id,
                    current_turn_id=turn_id,
                    current_user_input=request.user_input,
                    chains=chains,
                )
                try:
                    raw_decision = await self._agent_router.route(agent_input)
                except Exception as exc:
                    raise HTTPException(
                        status_code=502,
                        detail="Context Agent 路由失败",
                    ) from exc

                try:
                    decision = validate_route_decision(
                        raw_decision,
                        chains,
                        conversation_id=request.conversation_id,
                    )
                except ValueError as exc:
                    raise HTTPException(
                        status_code=502,
                        detail=f"Context Agent 返回了非法路由结果: {exc}",
                    ) from exc

                new_chain_id = (
                    _new_id("chain")
                    if decision.create_new_chain
                    else None
                )
                await run_in_threadpool(
                    self._save_route_decision,
                    turn_id,
                    request.conversation_id,
                    decision,
                    new_chain_id,
                )

                chain_map = {chain.chain_id: chain for chain in chains}
                return RoutedContextPackage(
                    current_turn_id=turn_id,
                    current_user_input=request.user_input,
                    selected_chains=[
                        chain_map[chain_id]
                        for chain_id in decision.selected_chain_ids
                    ],
                    new_chain_id=new_chain_id,
                    route_decision=decision,
                )
        except ConversationRouteLockUnavailable as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except Exception:
            if turn_created:
                try:
                    await run_in_threadpool(self._mark_turn_failed, turn_id)
                except Exception:
                    pass
            raise

    async def complete_turn(
        self,
        turn_id: str,
        request: CompleteContextTurnRequest,
    ) -> CompleteContextTurnResponse:
        """按已保存路由决定关联 Turn，不接受下游扩张链路范围。"""
        conversation_id = await run_in_threadpool(
            self._get_turn_conversation_id,
            turn_id,
        )
        if conversation_id is None:
            raise HTTPException(status_code=404, detail="Context Turn 不存在")

        try:
            async with self._route_lock_manager.hold(conversation_id):
                return await run_in_threadpool(
                    self._complete_turn_in_transaction,
                    turn_id,
                    conversation_id,
                    request,
                )
        except ConversationRouteLockUnavailable as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    def _create_turn_and_load_chains(
        self,
        turn_id: str,
        request: ContextRouteRequest,
    ) -> list[ContextChain]:
        with self._uow_factory() as uow:
            uow.context.create_turn(
                ConversationTurnModel(
                    turn_id=turn_id,
                    conversation_id=request.conversation_id,
                    user_input=request.user_input,
                    task_ids=[],
                    status=ContextTurnStatus.ROUTING.value,
                )
            )
            chain_models = uow.context.list_active_chains(
                request.conversation_id
            )
            chains = [
                build_context_chain(
                    chain,
                    full_assistant_turn_count=(
                        self._full_assistant_turn_count
                    ),
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
                ContextRouteRecordModel(
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
        request: CompleteContextTurnRequest,
    ) -> CompleteContextTurnResponse:
        with self._uow_factory() as uow:
            turn = uow.context.get_turn_for_update(turn_id)
            if turn is None:
                raise HTTPException(
                    status_code=404,
                    detail="Context Turn 不存在",
                )
            if turn.conversation_id != conversation_id:
                raise HTTPException(
                    status_code=409,
                    detail="Context Turn 会话归属已变化",
                )
            if turn.status == ContextTurnStatus.COMPLETED.value:
                return CompleteContextTurnResponse(
                    turn=ConversationTurn.model_validate(turn),
                    linked_chain_ids=(
                        uow.context.list_linked_chain_ids(turn_id)
                    ),
                )
            if turn.status != ContextTurnStatus.ROUTED.value:
                raise HTTPException(
                    status_code=409,
                    detail="Context Turn 尚未完成路由",
                )

            route_record = uow.context.get_route_record_for_update(turn_id)
            if route_record is None:
                raise HTTPException(
                    status_code=409,
                    detail="Context Turn 缺少已校验路由决定",
                )
            if route_record.conversation_id != conversation_id:
                raise HTTPException(
                    status_code=409,
                    detail="Context 路由决定会话归属不一致",
                )

            target_chain_ids = list(route_record.selected_chain_ids or [])
            if route_record.create_new_chain:
                if not route_record.new_chain_id:
                    raise HTTPException(
                        status_code=409,
                        detail="Context 路由决定缺少新链 ID",
                    )
                target_chain_ids.append(route_record.new_chain_id)

            update_map = self._validate_chain_updates(
                request.chain_updates,
                target_chain_ids=target_chain_ids,
                turn_task_ids=request.task_ids,
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
                    raise HTTPException(
                        status_code=409,
                        detail=f"Context Chain 不存在: {chain_id}",
                    )
                if chain.conversation_id != conversation_id:
                    raise HTTPException(
                        status_code=409,
                        detail=f"Context Chain 会话归属不一致: {chain_id}",
                    )

            now = datetime.now()
            if route_record.create_new_chain:
                new_chain_id = route_record.new_chain_id
                if uow.context.get_chain_for_update(new_chain_id) is not None:
                    raise HTTPException(
                        status_code=409,
                        detail="预分配的 Context Chain ID 已存在",
                    )
                new_update = update_map.get(new_chain_id)
                new_chain = uow.context.create_chain(
                    ContextChainModel(
                        chain_id=new_chain_id,
                        conversation_id=conversation_id,
                        resources=(
                            new_update.resources.model_dump()
                            if new_update is not None
                            and new_update.resources is not None
                            else ContextResources().model_dump()
                        ),
                        last_active_at=now,
                        archived=False,
                    )
                )
                chain_map[new_chain_id] = new_chain

            normalized_task_ids = list(dict.fromkeys(request.task_ids))
            uow.context.complete_turn(
                turn,
                assistant_content=request.assistant_content,
                assistant_compact=request.assistant_compact,
                task_ids=normalized_task_ids,
                task_result_summary=request.task_result_summary,
                completed_at=now,
                status=ContextTurnStatus.COMPLETED.value,
            )

            for chain_id in target_chain_ids:
                chain = chain_map[chain_id]
                update = update_map.get(chain_id)
                uow.context.create_node(
                    ContextChainNodeModel(
                        node_id=_new_id("node"),
                        chain_id=chain_id,
                        turn_id=turn_id,
                        sequence=uow.context.get_next_sequence(chain_id),
                        related_task_ids=(
                            list(dict.fromkeys(update.related_task_ids))
                            if update is not None
                            else []
                        ),
                        related_resource_refs=(
                            list(
                                dict.fromkeys(
                                    update.related_resource_refs
                                )
                            )
                            if update is not None
                            else []
                        ),
                    )
                )
                resources = (
                    update.resources.model_dump()
                    if update is not None
                    and update.resources is not None
                    else None
                )
                uow.context.update_chain_activity(
                    chain,
                    last_active_at=now,
                    resources=resources,
                )

            uow.commit()
            return CompleteContextTurnResponse(
                turn=ConversationTurn.model_validate(turn),
                linked_chain_ids=target_chain_ids,
            )

    @staticmethod
    def _validate_chain_updates(
        updates: list[ContextChainTurnUpdate],
        *,
        target_chain_ids: list[str],
        turn_task_ids: list[str],
    ) -> dict[str, ContextChainTurnUpdate]:
        target_set = set(target_chain_ids)
        turn_task_set = set(turn_task_ids)
        update_map: dict[str, ContextChainTurnUpdate] = {}

        for update in updates:
            if update.chain_id in update_map:
                raise HTTPException(
                    status_code=400,
                    detail=f"重复的 Context Chain 更新: {update.chain_id}",
                )
            if update.chain_id not in target_set:
                raise HTTPException(
                    status_code=400,
                    detail=f"Context Chain 不在已路由范围内: {update.chain_id}",
                )
            unknown_task_ids = (
                set(update.related_task_ids) - turn_task_set
            )
            if unknown_task_ids:
                unknown = ", ".join(sorted(unknown_task_ids))
                raise HTTPException(
                    status_code=400,
                    detail=f"链关联了 Turn 中不存在的 Task: {unknown}",
                )
            update_map[update.chain_id] = update

        return update_map
