"""Context Selection 与完成回写的业务编排。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from time import monotonic_ns
from typing import Any
from uuid import uuid4

from starlette.concurrency import run_in_threadpool

from app.modules.context.application.dto import (
    ChainTurnUpdate,
    CompleteTurnCommand,
    CompleteTurnResult,
    ContextAgentInput,
    ContextSelectionResult,
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
    ContextSelectionDecision,
    ConversationTurn,
)
from app.modules.context.domain.selection_policy import (
    derive_context_selection_mode,
    validate_context_selection,
)


@dataclass(frozen=True)
class _LoadedContextChain:
    """内部加载的上下文链及其资源版本快照。

    Attributes:
        chain: 上下文链领域对象。
        resource_version: 数据库当前资源版本号。
    """

    chain: ContextChain
    resource_version: int


@dataclass(frozen=True)
class _CompleteTurnTransactionResult:
    """完成 Turn 数据库事务执行结果内部结构。

    Attributes:
        response: 对外返回的 CompleteTurnResult 对象。
        resource_refreshes: 事务提交成功后待应用到 Redis 的资源增量列表。
    """

    response: CompleteTurnResult
    resource_refreshes: list[ContextResourceQueueRefresh]


def _new_id(prefix: str) -> str:
    """生成带有指定前缀的 UUID 字符串。

    Args:
        prefix: ID 前缀（例如 "turn", "selection", "chain", "node"）。

    Returns:
        str: 格式为 `{prefix}_{hex}` 的唯一标识字符串。
    """
    return f"{prefix}_{uuid4().hex}"


class ContextService:
    """保持 Conversation Context 变更串行，并划分短数据库事务的核心应用服务。

    主要职责：
    1. Context Selection 阶段（send_message）：
       - 获取会话级 Redis 短锁，防止并发交互导致链状态分叉。
       - 短事务创建 Turn（ROUTING 状态）并读取当前会话的所有未归档链。
       - 从 Redis（或 MySQL 预热）注入各链的有界热资源队列（FIFO）。
       - 调用 Context Agent 选择历史 Read Set，并经由 SelectionPolicy 校验与保序去重。
       - 短事务持久化 ContextSelectionRecord，将 Turn 推进至 CONTEXT_READY 状态。
    2. 完成阶段（complete_turn）：
       - 在同一短事务内：更新 Turn（COMPLETED 状态）、为归属链建立 ContextChainNode、追加资源事件并递增 resource_version。
       - 事务提交后：将各链的资源增量刷新至 Redis 热队列，若失败则安全失效缓存。
    """

    def __init__(
        self,
        *,
        agent_router: ContextRouterPort | None,
        route_lock_manager: ConversationLockPort,
        resource_service: ContextResourceService,
        uow_factory: UnitOfWorkFactory,
        record_factory: ContextRecordFactoryPort,
        chain_mapper: ContextChainMapperPort,
        event_logger: Any | None = None,
    ) -> None:
        """初始化 ContextService。

        Args:
            agent_router: ContextRouterPort 实例（如 DeepSeekRouter）。
            route_lock_manager: ConversationLockPort 会话分布式锁管理器。
            resource_service: ContextResourceService 资源管理服务。
            uow_factory: UnitOfWork 工厂。
            record_factory: ContextRecordFactoryPort ORM 工厂。
            chain_mapper: ContextChainMapperPort 链映射器。
            event_logger: 结构化可观测性日志记录器（可选）。
        """
        self._agent_router = agent_router
        self._route_lock_manager = route_lock_manager
        self._resource_service = resource_service
        self._uow_factory = uow_factory
        self._record_factory = record_factory
        self._chain_mapper = chain_mapper
        self._event_logger = event_logger

    async def send_message(
        self,
        command: SendMessageCommand,
    ) -> ContextSelectionResult:
        """创建唯一 Turn，并持久化 Planner 所需的历史读取集合。

        主流程：
        1. 获取当前 Conversation 的 Redis 短分布式锁，串行化并发 Selection。
        2. 短事务内创建 Turn（状态为 ROUTING）并加载该会话全部未归档链。
        3. 从 Redis（或 MySQL 兜底预热）为每条链注入热资源队列。
        4. 调用 Context Agent（DeepSeek 或确定性策略）选择历史 Read Set。
        5. 执行严格的领域规则校验（validate_context_selection）。
        6. 短事务保存 Context Selection 记录，将 Turn 推进至 CONTEXT_READY 状态。

        Args:
            command: SendMessageCommand 命令对象。

        Returns:
            ContextSelectionResult: 历史 Read Set 选择结果。

        Raises:
            RuntimeError: Context Agent Router 未配置。
            ConversationLockUnavailable: 会话锁不可用。
            ContextRoutingError: 路由调用失败或输出非法。
        """
        if self._agent_router is None:
            raise RuntimeError("Context Agent Router 未配置")

        turn_id = _new_id("turn")
        turn_created = False
        started_at = monotonic_ns()
        llm_duration_ms = 0.0
        chain_count = 0
        selected_count = 0
        invalid_output_count = 0

        try:
            # 1. 获取分布式锁，防止同一会话多消息并发破坏上下文链路
            async with self._route_lock_manager.hold(
                command.conversation_id
            ):
                # 2. 短事务创建 Turn 并读取未归档链
                loaded_chains = await run_in_threadpool(
                    self._create_turn_and_load_chains,
                    turn_id,
                    command,
                )
                turn_created = True
                chain_count = len(loaded_chains)
                chains: list[ContextChain] = []

                # 3. 为每条未归档链注入热资源队列（优先从 Redis 读取，缺失则从 MySQL 预热）
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

                # 4. 调用 LLM 选择 Planner 所需的历史 Read Set
                try:
                    llm_started_at = monotonic_ns()
                    raw_decision = await self._agent_router.route(agent_input)
                except Exception as exc:
                    raise ContextRoutingError(
                        "Context Agent Selection 失败"
                    ) from exc
                finally:
                    llm_duration_ms = self._elapsed_ms(llm_started_at)

                # 5. 校验决策结果合法性（存在性、未归档、保序去重）
                try:
                    decision = validate_context_selection(
                        raw_decision,
                        chains,
                        conversation_id=command.conversation_id,
                    )
                except ValueError as exc:
                    invalid_output_count = 1
                    raise ContextRoutingError(
                        f"Context Agent 返回了非法 Selection: {exc}"
                    ) from exc

                # 6. 短事务持久化 Context Selection 并推进 Turn 状态至 CONTEXT_READY
                await run_in_threadpool(
                    self._persist_context_selection,
                    turn_id,
                    command.conversation_id,
                    decision,
                )
                selected_count = len(decision.relevant_chain_ids)

                chain_map = {chain.chain_id: chain for chain in chains}
                self._observe(
                    "context_selection_completed",
                    conversation_id=command.conversation_id,
                    turn_id=turn_id,
                    context_selection_total_duration=self._elapsed_ms(
                        started_at
                    ),
                    context_selection_llm_duration=llm_duration_ms,
                    context_selection_chain_count=chain_count,
                    context_selection_selected_count=selected_count,
                    context_selection_no_context_count=int(
                        selected_count == 0
                    ),
                    context_selection_multi_context_count=int(
                        selected_count > 1
                    ),
                    context_selection_invalid_output_count=0,
                    duration_unit="milliseconds",
                )
                return ContextSelectionResult(
                    conversation_id=command.conversation_id,
                    turn_id=turn_id,
                    message=command.message,
                    context_chains=[
                        chain_map[chain_id]
                        for chain_id in decision.relevant_chain_ids
                    ],
                    decision=decision,
                )
        except ConversationLockUnavailable:
            raise
        except Exception as exc:
            self._observe(
                "context_selection_failed",
                level="error",
                conversation_id=command.conversation_id,
                turn_id=turn_id,
                context_selection_total_duration=self._elapsed_ms(
                    started_at
                ),
                context_selection_llm_duration=llm_duration_ms,
                context_selection_chain_count=chain_count,
                context_selection_selected_count=selected_count,
                context_selection_no_context_count=0,
                context_selection_multi_context_count=0,
                context_selection_invalid_output_count=(
                    invalid_output_count
                ),
                error_type=type(exc).__name__,
                duration_unit="milliseconds",
            )
            # 若 Turn 记录已在短事务中创建，则尽力将其标记为 FAILED 终态
            if turn_created:
                try:
                    await run_in_threadpool(self._mark_turn_failed, turn_id)
                except Exception:
                    pass
            raise

    @staticmethod
    def _elapsed_ms(started_at: int) -> float:
        """计算自 started_at（纳秒）以来的毫秒数。"""
        return round((monotonic_ns() - started_at) / 1_000_000, 3)

    def _observe(self, event: str, **fields: Any) -> None:
        """记录结构化观察事件。"""
        if self._event_logger is None:
            return
        try:
            self._event_logger.write(event, **fields)
        except Exception:
            return

    async def complete_turn(
        self,
        turn_id: str,
        command: CompleteTurnCommand,
    ) -> CompleteTurnResult:
        """按完成方提交的 Attribution 原子关联 Turn 与最终 Chain。

        主流程：
        1. 获取会话 ID 并持有会话级 Redis 短锁。
        2. 短事务内执行 complete_turn：
           - 校验 Turn 状态（处于 CONTEXT_READY 或 PROCESSING）。
           - 根据 Attribution 关联已有链或创建新链。
           - 为各归属链创建 ContextChainNode（仅引用 Turn，不复制文本）。
           - 追加资源事件、更新资源状态并递增 resource_version。
           - 标记 Turn 为 COMPLETED 并记录助手回答与完成时间。
        3. 事务提交后，增量刷新 Redis 热资源队列；若刷新失败仅使缓存失效。

        Args:
            turn_id: 待完成的 Turn ID。
            command: CompleteTurnCommand 完成命令。

        Returns:
            CompleteTurnResult: 包含完成后的 Turn 与关联链 ID 列表。

        Raises:
            ContextTurnNotFoundError: Turn 不存在。
            ConversationLockUnavailable: 会话锁获取失败。
            ContextConflictError: 状态冲突或归属错误。
            ContextValidationError: 输入命令参数非法。
        """
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
                # 数据库事务提交后，刷新 Redis 热资源队列
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
        """在短数据库事务中创建 Turn 记录并读取当前会话的所有未归档上下文链。

        Args:
            turn_id: 新分配的 Turn ID。
            command: SendMessageCommand 命令。

        Returns:
            list[_LoadedContextChain]: 加载的上下文链列表及其资源版本。
        """
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
                    ),
                    resource_version=chain.resource_version,
                )
                for chain in chain_models
            ]
            uow.commit()
        return chains

    def _persist_context_selection(
        self,
        turn_id: str,
        conversation_id: str,
        decision: ContextSelectionDecision,
    ) -> None:
        """在短数据库事务中复核并持久化上下文选择记录，将 Turn 推进为 CONTEXT_READY。

        Args:
            turn_id: Turn ID。
            conversation_id: 会话 ID。
            decision: 校验通过的上下文选择决策。

        Raises:
            RuntimeError: Turn 不存在、会话归属变化、状态非 ROUTING、选中链已归档或消失。
        """
        with self._uow_factory() as uow:
            turn = uow.context.get_turn_for_update(turn_id)
            if turn is None:
                raise RuntimeError("Context Turn disappeared before selection")
            if turn.conversation_id != conversation_id:
                raise RuntimeError("Context Turn conversation changed")
            if turn.status != ContextTurnStatus.ROUTING.value:
                raise RuntimeError("Context Turn is not awaiting selection")

            # 锁定选中的所有已有链并复核有效性
            selected_chains = uow.context.get_chains_by_ids_for_update(
                decision.relevant_chain_ids
            )
            selected_map = {
                chain.chain_id: chain for chain in selected_chains
            }
            for chain_id in decision.relevant_chain_ids:
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

            # 创建并插入 ContextSelectionRecord 事实记录
            uow.context.create_selection_record(
                self._record_factory.context_selection_record(
                    selection_id=_new_id("selection"),
                    conversation_id=conversation_id,
                    current_turn_id=turn_id,
                    relevant_chain_ids=list(decision.relevant_chain_ids),
                    selection_mode=derive_context_selection_mode(
                        decision.relevant_chain_ids
                    ).value,
                    reason_summary=decision.reason_summary,
                )
            )
            # 推进 Turn 状态至 CONTEXT_READY
            uow.context.set_turn_status(
                turn,
                ContextTurnStatus.CONTEXT_READY.value,
            )
            uow.commit()

    def _mark_turn_failed(self, turn_id: str) -> None:
        """若 Turn 仍处于 ROUTING 状态，则将其安全更新为 FAILED 终态。

        Args:
            turn_id: Turn ID。
        """
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
        """只读查询 Turn 所属的 conversation_id。

        Args:
            turn_id: Turn ID。

        Returns:
            str | None: 会话 ID，若 Turn 不存在则返回 None。
        """
        with self._uow_factory() as uow:
            turn = uow.context.get_turn(turn_id)
            return None if turn is None else turn.conversation_id

    def _complete_turn_in_transaction(
        self,
        turn_id: str,
        conversation_id: str,
        command: CompleteTurnCommand,
    ) -> _CompleteTurnTransactionResult:
        """在单一短数据库事务中完成 Turn，创建节点并更新链与资源事实。

        Args:
            turn_id: Turn ID。
            conversation_id: 会话 ID。
            command: CompleteTurnCommand 命令。

        Returns:
            _CompleteTurnTransactionResult: 事务执行结果。

        Raises:
            ContextTurnNotFoundError: Turn 不存在。
            ContextConflictError: 状态冲突或归属错误。
            ContextValidationError: 输入命令参数非法。
        """
        with self._uow_factory() as uow:
            # 1. 锁定 Turn 并复核状态
            turn = uow.context.get_turn_for_update(turn_id)
            if turn is None:
                raise ContextTurnNotFoundError("Context Turn 不存在")
            if turn.conversation_id != conversation_id:
                raise ContextConflictError(
                    "Context Turn 会话归属已变化"
                )
            # 幂等处理：若 Turn 已经处于 COMPLETED 状态，直接返回既有链关联
            if turn.status == ContextTurnStatus.COMPLETED.value:
                linked_chain_ids = uow.context.list_linked_chain_ids(turn_id)
                if not linked_chain_ids:
                    raise ContextConflictError(
                        "已完成的 Context Turn 缺少 Chain Attribution"
                    )
                return _CompleteTurnTransactionResult(
                    response=CompleteTurnResult(
                        turn=ConversationTurn.model_validate(turn),
                        linked_chain_ids=linked_chain_ids,
                    ),
                    resource_refreshes=[],
                )
            if turn.status not in {
                ContextTurnStatus.CONTEXT_READY.value,
                ContextTurnStatus.PROCESSING.value,
            }:
                raise ContextConflictError(
                    "Context Turn 当前状态不允许完成"
                )

            # 2. 锁定 ContextSelectionRecord
            selection = uow.context.get_selection_record_for_update(turn_id)
            if selection is None:
                raise ContextConflictError(
                    "Context Turn 缺少已校验的 Context Selection"
                )
            if selection.conversation_id != conversation_id:
                raise ContextConflictError(
                    "Context Selection 会话归属不一致"
                )

            # 3. 校验并解析目标归属链（已有链 + 可选新链）
            target_chain_ids = list(
                dict.fromkeys(command.attribution.existing_chain_ids)
            )
            create_new_chain = command.attribution.create_new_chain
            new_chain_id = command.attribution.new_chain_id
            if new_chain_id is not None and not create_new_chain:
                raise ContextValidationError(
                    "未请求创建新 Chain 时不能指定 new_chain_id"
                )
            if not target_chain_ids and not create_new_chain:
                create_new_chain = True
            if create_new_chain:
                new_chain_id = new_chain_id or _new_id("chain")
                if new_chain_id in target_chain_ids:
                    raise ContextValidationError(
                        "新 Chain ID 不能同时作为 existing attribution"
                    )
                if uow.context.get_chain_for_update(new_chain_id) is not None:
                    raise ContextConflictError(
                        f"Context Chain 已存在，不能重复创建: {new_chain_id}"
                    )
                target_chain_ids.append(new_chain_id)

            # 4. 校验各链更新载荷（ChainTurnUpdate）
            update_map = self._validate_chain_updates(
                command.chain_updates,
                target_chain_ids=target_chain_ids,
                turn_task_ids=command.task_ids,
            )
            existing_chains = uow.context.get_chains_by_ids_for_update(
                command.attribution.existing_chain_ids
            )
            chain_map = {
                chain.chain_id: chain for chain in existing_chains
            }
            for chain_id in dict.fromkeys(
                command.attribution.existing_chain_ids
            ):
                chain = chain_map.get(chain_id)
                if chain is None:
                    raise ContextConflictError(
                        f"Context Chain 不存在: {chain_id}"
                    )
                if chain.conversation_id != conversation_id:
                    raise ContextConflictError(
                        f"Context Chain 会话归属不一致: {chain_id}"
                    )
                if chain.archived:
                    raise ContextConflictError(
                        f"Context Chain 已归档: {chain_id}"
                    )

            now = datetime.now()
            # 5. 若需创建新链，则持久化 ContextChain 记录
            if create_new_chain:
                assert new_chain_id is not None
                new_chain = self._record_factory.context_chain(
                    chain_id=new_chain_id,
                    conversation_id=conversation_id,
                    resources={},
                    resource_version=0,
                    last_active_at=now,
                    archived=False,
                )
                uow.context.create_chain(new_chain)
                chain_map[new_chain_id] = new_chain

            normalized_task_ids = list(dict.fromkeys(command.task_ids))
            resource_refreshes: list[ContextResourceQueueRefresh] = []

            # 6. 为所有目标归属链创建 ContextChainNode，应用资源事实变更并更新活跃时间
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

            # 7. 推进 Turn 状态为 COMPLETED 并记录助手回答
            uow.context.complete_turn(
                turn,
                assistant_content=command.assistant_content,
                assistant_compact=command.assistant_compact,
                task_ids=normalized_task_ids,
                task_result_summary=command.task_result_summary,
                completed_at=now,
                status=ContextTurnStatus.COMPLETED.value,
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
        """校验各链更新载荷的合法性与一致性。

        校验规则：
        1. 禁止针对同一 chain_id 提交多条更新。
        2. 链更新目标必须在 target_chain_ids 范围内。
        3. 涉及的 Task ID 必须在 Turn 的 task_ids 范围内。
        4. 单链内禁止重复新增资源或重复移除资源。
        5. 同一资源 Key 禁止在同一轮同时被刷新和显式移除。

        Args:
            updates: 下游提交的 ChainTurnUpdate 列表。
            target_chain_ids: 本轮所有目标归属链 ID 集合。
            turn_task_ids: 本轮所有执行成功的 Task ID 列表。

        Returns:
            dict[str, ChainTurnUpdate]: 以 chain_id 为键的更新载荷映射字典。

        Raises:
            ContextValidationError: 违反上述任一校验约束时抛出。
        """
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
                    f"Context Chain 不在本轮 Attribution 范围内: "
                    f"{update.chain_id}"
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
