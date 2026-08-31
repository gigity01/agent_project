"""构建 Task Runtime 异步执行、可靠消息传递（Outbox/Inbox）、澄清请求与 Task DAG 依赖关系基础设施。

业务背景与设计规范：
1. Plan / Task 模型演进：
   - plans 增加 `workflow_id`（同一业务流程的多 revision 标识）、`parent_plan_id`、`current_task_id`、`failure_code` 等。
   - tasks 增加 `task_ref`（如 task_1, task_2）、`attempt_count`、`max_attempts`（默认 3）、`output_json`、`last_error_code` 等。
2. 任务执行跟踪 `task_executions`：
   - 记录每次 Task attempt 的执行快照、状态、执行器（executor_code）、输入/输出快照、资源引用、operation_id 及 agent_run_id。
3. 事务性消息驱动 `outbox_events` & `inbox_events`：
   - Outbox 模式：业务事务与事件在 MySQL 内同事务提交，由 Publisher 轮询并推入 Redis Streams。
   - Inbox 模式：记录各消费组对事件的处理记录，实现幂等去重与防重放。
4. 交互式澄清 `clarification_requests`：
   - 当参数缺失或存在歧义时持久化澄清请求，支持后续用户回复关联并触发 Replan。
5. 任务依赖 DAG `task_dependencies`：
   - 持久化 Task 之间的拓扑依赖关系（task_id 依赖 depends_on_task_id），增加无自环 Check 约束与边唯一约束。

Revision ID: a8d2e4f6b1c3
Revises: f6c1d8a4e2b7
Create Date: 2026-08-05 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a8d2e4f6b1c3"
down_revision: Union[str, Sequence[str], None] = "f6c1d8a4e2b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """扩展 plans/tasks 表字段，并创建 task_executions、outbox_events、inbox_events、clarification_requests 与 task_dependencies 表。"""
    op.add_column("plans", sa.Column("workflow_id", sa.String(100)))
    op.add_column("plans", sa.Column("parent_plan_id", sa.String(100)))
    op.add_column("plans", sa.Column("current_task_id", sa.String(100)))
    op.add_column("plans", sa.Column("failure_code", sa.String(100)))
    op.add_column("plans", sa.Column("started_at", sa.DateTime()))
    op.add_column("plans", sa.Column("completed_at", sa.DateTime()))
    op.execute("UPDATE plans SET workflow_id = plan_id WHERE workflow_id IS NULL")
    op.alter_column(
        "plans",
        "workflow_id",
        existing_type=sa.String(length=100),
        nullable=False,
    )
    op.create_unique_constraint(
        "uq_plans_workflow_revision",
        "plans",
        ["workflow_id", "revision"],
    )
    op.create_foreign_key(
        "fk_plans_parent_plan_id",
        "plans",
        "plans",
        ["parent_plan_id"],
        ["plan_id"],
    )

    op.add_column("tasks", sa.Column("task_ref", sa.String(100)))
    op.add_column(
        "tasks",
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "tasks",
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
    )
    op.add_column("tasks", sa.Column("output_json", sa.JSON()))
    op.add_column("tasks", sa.Column("last_error_code", sa.String(100)))
    op.add_column("tasks", sa.Column("last_error_message", sa.Text()))
    op.add_column("tasks", sa.Column("started_at", sa.DateTime()))
    op.add_column("tasks", sa.Column("completed_at", sa.DateTime()))
    op.execute(
        "UPDATE tasks SET task_ref = CONCAT('task_', sequence) "
        "WHERE task_ref IS NULL"
    )
    op.alter_column(
        "tasks",
        "task_ref",
        existing_type=sa.String(length=100),
        nullable=False,
    )
    op.create_unique_constraint(
        "uq_tasks_plan_task_ref", "tasks", ["plan_id", "task_ref"]
    )
    op.create_foreign_key(
        "fk_plans_current_task_id",
        "plans",
        "tasks",
        ["current_task_id"],
        ["task_id"],
    )
    op.create_index(
        "idx_plans_workflow_revision",
        "plans",
        ["workflow_id", "revision"],
    )

    op.create_table(
        "task_executions",
        sa.Column("execution_id", sa.String(100), primary_key=True),
        sa.Column("task_id", sa.String(100), nullable=False),
        sa.Column("plan_id", sa.String(100), nullable=False),
        sa.Column("workflow_id", sa.String(100), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("executor_code", sa.String(100), nullable=False),
        sa.Column("input_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("output_json", sa.JSON()),
        sa.Column("resource_refs_json", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(100)),
        sa.Column("error_message", sa.Text()),
        sa.Column("retryable", sa.Boolean()),
        sa.Column("agent_run_id", sa.String(100)),
        sa.Column("operation_id", sa.String(100), nullable=False),
        sa.Column(
            "started_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("completed_at", sa.DateTime()),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.task_id"]),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.plan_id"]),
        sa.UniqueConstraint(
            "task_id", "attempt", name="uq_task_executions_task_attempt"
        ),
    )
    op.create_index(
        "idx_task_executions_plan_status",
        "task_executions",
        ["plan_id", "status"],
    )

    op.create_table(
        "outbox_events",
        sa.Column("event_id", sa.String(100), primary_key=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("aggregate_type", sa.String(100), nullable=False),
        sa.Column("aggregate_id", sa.String(100), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("available_at", sa.DateTime(), nullable=False),
        sa.Column("published_at", sa.DateTime()),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "idx_outbox_pending_available",
        "outbox_events",
        ["status", "available_at"],
    )
    op.create_table(
        "inbox_events",
        sa.Column("inbox_id", sa.String(100), primary_key=True),
        sa.Column("consumer_name", sa.String(100), nullable=False),
        sa.Column("event_id", sa.String(100), nullable=False),
        sa.Column("processed_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "consumer_name", "event_id", name="uq_inbox_consumer_event"
        ),
    )
    op.create_table(
        "clarification_requests",
        sa.Column("clarification_id", sa.String(100), primary_key=True),
        sa.Column("conversation_id", sa.String(100), nullable=False),
        sa.Column("source_turn_id", sa.String(100), nullable=False),
        sa.Column("source_plan_id", sa.String(100), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("question", sa.Text()),
        sa.Column("required_information_json", sa.JSON(), nullable=False),
        sa.Column("known_resource_refs_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("answer_turn_id", sa.String(100)),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("resolved_at", sa.DateTime()),
        sa.ForeignKeyConstraint(["source_turn_id"], ["conversation_turns.turn_id"]),
        sa.ForeignKeyConstraint(["source_plan_id"], ["plans.plan_id"]),
        sa.ForeignKeyConstraint(["answer_turn_id"], ["conversation_turns.turn_id"]),
        sa.UniqueConstraint(
            "source_plan_id", name="uq_clarification_requests_source_plan"
        ),
    )
    op.create_index(
        "idx_clarification_conversation_status",
        "clarification_requests",
        ["conversation_id", "status"],
    )
    op.create_table(
        "task_dependencies",
        sa.Column("dependency_id", sa.String(100), primary_key=True),
        sa.Column("plan_id", sa.String(100), nullable=False),
        sa.Column("task_id", sa.String(100), nullable=False),
        sa.Column("depends_on_task_id", sa.String(100), nullable=False),
        sa.CheckConstraint(
            "task_id <> depends_on_task_id",
            name="ck_task_dependencies_no_self",
        ),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.plan_id"]),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.task_id"]),
        sa.ForeignKeyConstraint(["depends_on_task_id"], ["tasks.task_id"]),
        sa.UniqueConstraint(
            "task_id", "depends_on_task_id", name="uq_task_dependencies_edge"
        ),
    )


def downgrade() -> None:
    op.drop_table("task_dependencies")
    op.drop_index(
        "idx_clarification_conversation_status",
        table_name="clarification_requests",
    )
    op.drop_table("clarification_requests")
    op.drop_table("inbox_events")
    op.drop_index("idx_outbox_pending_available", table_name="outbox_events")
    op.drop_table("outbox_events")
    op.drop_index(
        "idx_task_executions_plan_status", table_name="task_executions"
    )
    op.drop_table("task_executions")
    op.drop_index("idx_plans_workflow_revision", table_name="plans")
    op.drop_constraint("fk_plans_current_task_id", "plans", type_="foreignkey")
    op.drop_constraint("uq_tasks_plan_task_ref", "tasks", type_="unique")
    for column in (
        "completed_at",
        "started_at",
        "last_error_message",
        "last_error_code",
        "output_json",
        "max_attempts",
        "attempt_count",
        "task_ref",
    ):
        op.drop_column("tasks", column)
    op.drop_constraint("fk_plans_parent_plan_id", "plans", type_="foreignkey")
    op.drop_constraint("uq_plans_workflow_revision", "plans", type_="unique")
    for column in (
        "completed_at",
        "started_at",
        "failure_code",
        "current_task_id",
        "parent_plan_id",
        "workflow_id",
    ):
        op.drop_column("plans", column)
