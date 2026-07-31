"""Context Chain 资源事实与 Redis 热队列的跨存储编排。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any
from uuid import uuid4

from starlette.concurrency import run_in_threadpool

from app.modules.context.application.dto import ChainTurnUpdate
from app.modules.context.application.ports import (
    ContextRecordFactoryPort,
    ResourceQueuePort,
    UnitOfWorkFactory,
)
from app.modules.context.domain.enums import ContextResourceAction
from app.modules.context.domain.models import (
    ContextResourceQueue,
    ContextResourceRef,
)


@dataclass(frozen=True)
class ContextResourceQueueRefresh:
    """数据库提交后需要应用到 Redis 的资源增量。"""

    conversation_id: str
    chain_id: str
    resources: list[ContextResourceRef]
    removed_resource_keys: list[str]
    expected_previous_version: int
    database_version: int


def split_resource_key(resource_key: str) -> tuple[str, str]:
    """将规范资源 Key 拆为类型和 ID。"""
    resource_type, separator, resource_id = resource_key.partition(":")
    if (
        not separator
        or not resource_type
        or not resource_id
        or re.fullmatch(r"[a-z][a-z0-9_]*", resource_type) is None
        or len(resource_type) > 100
        or len(resource_id) > 400
    ):
        raise ValueError(f"Invalid Context resource key: {resource_key}")
    return resource_type, resource_id


class ContextResourceService:
    """以 MySQL 为事实来源，维护可丢弃并可重建的 Redis 热队列。"""

    def __init__(
        self,
        *,
        queue_repository: ResourceQueuePort,
        uow_factory: UnitOfWorkFactory,
        record_factory: ContextRecordFactoryPort,
    ) -> None:
        self._queue_repository = queue_repository
        self._uow_factory = uow_factory
        self._record_factory = record_factory

    @property
    def queue_capacity(self) -> int:
        return self._queue_repository.capacity

    def empty_queue(self) -> ContextResourceQueue:
        return ContextResourceQueue(capacity=self.queue_capacity)

    def apply_in_transaction(
        self,
        *,
        repository: Any,
        chain: Any,
        update: ChainTurnUpdate | None,
        turn_id: str,
        now: datetime,
    ) -> ContextResourceQueueRefresh | None:
        """在调用方数据库事务中追加事件并更新资源当前状态。"""
        if update is None:
            return None

        refreshed_resources: list[ContextResourceRef] = []
        for resource_input in update.related_resources:
            resource, created = repository.upsert_chain_resource(
                chain_id=chain.chain_id,
                resource_key=resource_input.resource_key,
                resource_type=resource_input.resource_type,
                resource_id=resource_input.resource_id,
                relation=resource_input.relation,
                summary=resource_input.summary,
                turn_id=turn_id,
                seen_at=now,
            )
            repository.create_resource_event(
                self._record_factory.context_resource_event(
                    event_id=f"resource_event_{uuid4().hex}",
                    chain_id=chain.chain_id,
                    turn_id=turn_id,
                    resource_key=resource.resource_key,
                    resource_type=resource.resource_type,
                    resource_id=resource.resource_id,
                    action=(
                        ContextResourceAction.SEEN.value
                        if created
                        else ContextResourceAction.REFRESHED.value
                    ),
                    relation=resource.relation,
                    summary=resource.summary,
                    created_at=now,
                )
            )
            refreshed_resources.append(
                ContextResourceRef(
                    resource_key=resource.resource_key,
                    resource_type=resource.resource_type,
                    resource_id=resource.resource_id,
                    relation=resource.relation,
                    summary=resource.summary,
                    source_turn_id=turn_id,
                    last_seen_at=now,
                )
            )

        for resource_key in update.removed_resource_keys:
            resource_type, resource_id = split_resource_key(resource_key)
            existing = repository.deactivate_chain_resource(
                chain_id=chain.chain_id,
                resource_key=resource_key,
                removed_at=now,
            )
            repository.create_resource_event(
                self._record_factory.context_resource_event(
                    event_id=f"resource_event_{uuid4().hex}",
                    chain_id=chain.chain_id,
                    turn_id=turn_id,
                    resource_key=resource_key,
                    resource_type=(
                        existing.resource_type
                        if existing is not None
                        else resource_type
                    ),
                    resource_id=(
                        existing.resource_id
                        if existing is not None
                        else resource_id
                    ),
                    action=ContextResourceAction.REMOVED.value,
                    relation=(
                        existing.relation if existing is not None else None
                    ),
                    summary=(
                        existing.summary if existing is not None else None
                    ),
                    created_at=now,
                )
            )

        if not refreshed_resources and not update.removed_resource_keys:
            return None

        previous_version = chain.resource_version
        database_version = repository.increment_resource_version(chain)
        return ContextResourceQueueRefresh(
            conversation_id=chain.conversation_id,
            chain_id=chain.chain_id,
            resources=refreshed_resources,
            removed_resource_keys=list(update.removed_resource_keys),
            expected_previous_version=previous_version,
            database_version=database_version,
        )

    async def get_queue(
        self,
        *,
        conversation_id: str,
        chain_id: str,
        resource_version: int,
    ) -> ContextResourceQueue:
        """优先读取版本一致的热队列，未命中时从 MySQL 预热。"""
        try:
            cached = await self._queue_repository.get(
                conversation_id=conversation_id,
                chain_id=chain_id,
                expected_version=resource_version,
            )
        except Exception:
            cached = None
        if cached is not None:
            return cached

        resources = await run_in_threadpool(
            self._load_resources_for_warmup,
            conversation_id,
            chain_id,
            resource_version,
        )
        try:
            await self._queue_repository.replace(
                conversation_id=conversation_id,
                chain_id=chain_id,
                resources=resources,
                database_version=resource_version,
            )
        except Exception:
            await self._best_effort_invalidate(
                conversation_id=conversation_id,
                chain_id=chain_id,
            )
        return ContextResourceQueue(
            capacity=self.queue_capacity,
            items=resources,
        )

    async def refresh_after_commit(
        self,
        refresh: ContextResourceQueueRefresh,
    ) -> None:
        """数据库成功后刷新 Redis；失败时仅使缓存失效。"""
        try:
            applied = await self._queue_repository.refresh(
                conversation_id=refresh.conversation_id,
                chain_id=refresh.chain_id,
                resources=refresh.resources,
                removed_resource_keys=refresh.removed_resource_keys,
                expected_previous_version=(
                    refresh.expected_previous_version
                ),
                database_version=refresh.database_version,
            )
            if not applied:
                await self._best_effort_invalidate(
                    conversation_id=refresh.conversation_id,
                    chain_id=refresh.chain_id,
                )
        except Exception:
            await self._best_effort_invalidate(
                conversation_id=refresh.conversation_id,
                chain_id=refresh.chain_id,
            )

    async def invalidate_chain(
        self,
        *,
        conversation_id: str,
        chain_id: str,
    ) -> None:
        """供归档流程删除 Redis 热队列，数据库历史保持不变。"""
        await self._queue_repository.invalidate(
            conversation_id=conversation_id,
            chain_id=chain_id,
        )

    def _load_resources_for_warmup(
        self,
        conversation_id: str,
        chain_id: str,
        resource_version: int,
    ) -> list[ContextResourceRef]:
        with self._uow_factory() as uow:
            chain = uow.context.get_chain(chain_id)
            if chain is None:
                raise RuntimeError(f"Context Chain 不存在: {chain_id}")
            if chain.conversation_id != conversation_id:
                raise RuntimeError(
                    f"Context Chain 会话归属不一致: {chain_id}"
                )
            if chain.resource_version != resource_version:
                raise RuntimeError(
                    f"Context Chain 资源版本已变化: {chain_id}"
                )

            newest_first = uow.context.list_resources_for_warmup(
                chain_id,
                limit=self.queue_capacity,
            )
            return [
                ContextResourceRef(
                    resource_key=resource.resource_key,
                    resource_type=resource.resource_type,
                    resource_id=resource.resource_id,
                    relation=resource.relation,
                    summary=resource.summary,
                    source_turn_id=resource.last_seen_turn_id,
                    last_seen_at=resource.last_seen_at,
                )
                for resource in reversed(newest_first)
            ]

    async def _best_effort_invalidate(
        self,
        *,
        conversation_id: str,
        chain_id: str,
    ) -> None:
        try:
            await self._queue_repository.invalidate(
                conversation_id=conversation_id,
                chain_id=chain_id,
            )
        except Exception:
            pass
