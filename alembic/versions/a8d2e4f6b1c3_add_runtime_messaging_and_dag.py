"""增加 Task Runtime、可靠消息、澄清与 DAG 持久化基座。

Revision ID: a8d2e4f6b1c3
Revises: f6c1d8a4e2b7
Create Date: 2026-08-05 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a8d2e4f6b1c3"
down_revision: Union[str, Sequence[str], None] = "f6c1d8a4e2b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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
