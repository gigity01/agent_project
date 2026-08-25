"""读取已完成 Plan 的事实，生成确定性回答并完成 Context Turn。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from app.modules.context.application.attribution_policy import (
    build_read_set_fallback_attribution,
)
from app.modules.context.application.dto import (
    ChainTurnUpdate,
    CompleteTurnCommand,
    ContextResourceInput,
)
from app.modules.planning.domain.enums import PlanStatus, TaskStatus
from app.modules.task_runtime.domain.enums import TaskExecutionStatus


@dataclass(frozen=True)
class _AggregationSnapshot:
    turn_id: str
    task_ids: list[str]
    relevant_chain_ids: list[str]
    summaries: list[str]
    resource_refs: list[str]


class AggregatePlanUseCase:
    """聚合已完成 Plan 执行结果的用例。

    主流程：
    1. 从数据库读取所有成功 Task 的产出摘要与涉及的资源引用（稳定去重）。
    2. 生成确定性执行事实摘要字符串（非 RAG 问答）。
    3. 若该 Turn 存在已回答的 ClarificationRequest，原子标记为 RESOLVED。
    4. 调用 ContextService.complete_turn 完成 Turn，在关联的上下文链上创建节点并刷新热资源队列。
    """

    def __init__(self, *, uow_factory, context_service) -> None:
        self._uow_factory = uow_factory
        self._context_service = context_service

    async def execute(self, plan_id: str):
        """执行 Plan 结果聚合并完成 Context 回写。"""
        snapshot = await asyncio.to_thread(self._load_snapshot, plan_id)
        summary = "；".join(snapshot.summaries)
        assistant_content = f"已完成 {len(snapshot.task_ids)} 项任务。{summary}"
        resources = [
            self._resource(resource_ref)
            for resource_ref in snapshot.resource_refs
        ]
        new_chain_id = (
            None
            if snapshot.relevant_chain_ids
            else f"chain_{uuid4().hex}"
        )
        attribution = build_read_set_fallback_attribution(
            snapshot.relevant_chain_ids,
            new_chain_id=new_chain_id,
        )
        target_chain_ids = list(attribution.existing_chain_ids)
        if attribution.create_new_chain:
            assert attribution.new_chain_id is not None
            target_chain_ids.append(attribution.new_chain_id)
        result = await self._context_service.complete_turn(
            snapshot.turn_id,
            CompleteTurnCommand(
                assistant_content=assistant_content,
                assistant_compact=assistant_content,
                task_ids=snapshot.task_ids,
                task_result_summary=summary,
                attribution=attribution,
                chain_updates=[
                    ChainTurnUpdate(
                        chain_id=chain_id,
                        related_task_ids=snapshot.task_ids,
                        related_resources=resources,
                    )
                    for chain_id in target_chain_ids
                ],
            ),
        )
        await asyncio.to_thread(self._resolve_clarification, plan_id)
        return result

    def _load_snapshot(self, plan_id: str) -> _AggregationSnapshot:
        with self._uow_factory() as uow:
            plan = uow.plans.get_by_id(plan_id)
            if plan is None or plan.status != PlanStatus.COMPLETED.value:
                raise ValueError("Plan 尚未完成，不能聚合")
            tasks = uow.tasks.list_by_plan_id(plan_id)
            if not tasks or any(
                task.status != TaskStatus.SUCCEEDED.value for task in tasks
            ):
                raise ValueError("Plan Task 尚未全部成功")
            executions = [
                execution
                for execution in uow.task_executions.list_by_plan_id(plan_id)
                if execution.status == TaskExecutionStatus.SUCCEEDED.value
            ]
            latest_by_task = {}
            for execution in executions:
                latest_by_task[execution.task_id] = execution
            if set(latest_by_task) != {task.task_id for task in tasks}:
                raise ValueError("Task 成功执行记录不完整")
            selection = uow.context.get_selection_record_for_update(
                plan.turn_id
            )
            if selection is None:
                raise ValueError("Turn 缺少 Context Selection 记录")
            resource_refs = list(
                dict.fromkeys(
                    resource_ref
                    for execution in latest_by_task.values()
                    for resource_ref in (execution.resource_refs_json or [])
                )
            )
            summaries = [
                f"{task.capability_code}: {task.output_json}"
                for task in tasks
            ]
            return _AggregationSnapshot(
                turn_id=plan.turn_id,
                task_ids=[task.task_id for task in tasks],
                relevant_chain_ids=list(
                    selection.relevant_chain_ids or []
                ),
                summaries=summaries,
                resource_refs=resource_refs,
            )

    @staticmethod
    def _resource(resource_ref: str) -> ContextResourceInput:
        resource_type, separator, resource_id = resource_ref.partition(":")
        if not separator or not resource_type or not resource_id:
            raise ValueError(f"非法资源引用: {resource_ref}")
        return ContextResourceInput(
            resource_type=resource_type,
            resource_id=resource_id,
            relation="task_output",
            summary="Task Runtime 产生的资源",
        )

    def _resolve_clarification(self, plan_id: str) -> None:
        with self._uow_factory() as uow:
            plan = uow.plans.get_by_id(plan_id)
            if plan is None or plan.parent_plan_id is None:
                return
            request = uow.clarifications.get_by_plan_id_for_update(
                plan.parent_plan_id
            )
            if request is None or request.status != "answered":
                return
            request.status = "resolved"
            request.resolved_at = datetime.now()
            uow.commit()
