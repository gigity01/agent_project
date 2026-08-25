"""Context 模块只读 Agent Tool 的权限控制、范围围栏、审计与 Tool Catalog 测试。

核心业务不变量：
1. 只读 Tool Catalog 隔离：
   - Context Collector 仅包含 7 个受控只读查询 Tool，严禁暴露任何可变写操作或跨模块底层持久化模型。
2. 权限与范围围栏（Task Scope Fencing）：
   - `context:read` 权限检查：无权限时直接返回 permission_denied，不触达底层数据库。
   - 链与轮次白名单约束：仅允许查询当前 Run 上下文授权的 `allowed_context_chain_ids` 和 `allowed_context_turn_ids`，
     越界查询直接判定为 `task_scope_violation` 并拒绝，宽泛查询自动收敛为授权子集。
3. 结构化审计日志成对性：
   - 每次 Tool 调用必须成对记录 tool_call_started 与 tool_call_completed 审计事件。
"""

from __future__ import annotations

import unittest
from datetime import datetime
from unittest import mock

from agents import RunContextWrapper

from app.agent_runtime.audit import AgentToolAuditLogger
from app.agent_runtime.context import AgentToolContext, ContextToolServices
from app.modules.context.agent_tools.catalog import CONTEXT_COLLECTOR_TOOLS
from app.modules.context.agent_tools.query_tools import (
    get_conversation_turn_handler,
    get_context_chain_handler,
    list_context_chains_handler,
    list_conversation_turns_handler,
)
from app.modules.context.agent_tools.schemas import (
    GetConversationTurnToolInput,
    GetContextChainToolInput,
    ListContextChainsToolInput,
    ListConversationTurnsToolInput,
)
from app.modules.context.application.query_dto import (
    ContextChainListResult,
    ContextChainQueryResult,
    ConversationTurnQueryResult,
    ConversationTurnListResult,
)


NOW = datetime(2026, 8, 3, 12, 0, 0)


class _Writer:
    """测试用审计日志事件收集器。"""
    def __init__(self) -> None:
        self.events: list[dict] = []

    def write(self, event: dict) -> bool:
        self.events.append(dict(event))
        return True


def _context(*, permissions: frozenset[str]):
    """构造具备指定权限与模拟查询服务的 AgentToolContext 上下文对象。"""
    writer = _Writer()
    query_service = mock.Mock()
    query_service.get_conversation_turn.return_value = (
        ConversationTurnQueryResult(
            turn_id="turn-1",
            conversation_id="conversation-1",
            user_input="输入",
            assistant_content="输出",
            assistant_compact=None,
            task_ids=[],
            task_result_summary=None,
            status="completed",
            created_at=NOW,
            completed_at=NOW,
        )
    )
    query_service.list_context_chains.return_value = ContextChainListResult(
        items=[
            ContextChainQueryResult(
                chain_id="chain-1",
                conversation_id="conversation-1",
                resource_version=1,
                last_active_at=NOW,
                archived=False,
                created_at=NOW,
            )
        ],
        total=1,
        limit=20,
        offset=0,
    )
    query_service.list_conversation_turns.return_value = (
        ConversationTurnListResult(
            items=[query_service.get_conversation_turn.return_value],
            total=1,
            limit=20,
            offset=0,
        )
    )
    context = AgentToolContext(
        trace_id="trace-1",
        agent_run_id="run-1",
        agent_name="context-collector",
        conversation_id="conversation-1",
        turn_id="turn-current",
        task_id="task-1",
        actor_code="actor-1",
        permissions=permissions,
        document_services=mock.Mock(),
        context_services=ContextToolServices(query_service=query_service),
        allowed_context_chain_ids=frozenset({"chain-1"}),
        allowed_context_turn_ids=frozenset({"turn-current", "turn-1"}),
        audit_logger=AgentToolAuditLogger(writer),
    )
    return context, query_service, writer


class ContextAgentToolsTest(unittest.TestCase):
    """验证 Context Agent Tools 的 Catalog 完整性、权限判定、范围重写与审计记录。"""

    def test_catalog_contains_only_seven_read_tools(self) -> None:
        """验证 Context Collector 工具目录严格仅包含 7 个受控只读查询 Tool。"""
        self.assertEqual(
            {tool.name for tool in CONTEXT_COLLECTOR_TOOLS},
            {
                "get_conversation_turn",
                "list_conversation_turns",
                "get_context_chain",
                "list_context_chains",
                "list_context_chain_nodes",
                "list_context_chain_resources",
                "list_context_selection_records",
            },
        )

    def test_get_turn_delegates_and_writes_paired_audit(self) -> None:
        """验证 get_conversation_turn 正常委托给底层服务并成对输出 started/completed 审计事件。"""
        context, service, writer = _context(
            permissions=frozenset({"context:read"})
        )

        output = get_conversation_turn_handler(
            RunContextWrapper(context),
            GetConversationTurnToolInput(turn_id="turn-1"),
        )

        self.assertEqual(output.outcome, "succeeded")
        self.assertEqual(output.turn.turn_id, "turn-1")
        service.get_conversation_turn.assert_called_once_with("turn-1")
        self.assertEqual(len(writer.events), 2)

    def test_list_chains_passes_bounded_query(self) -> None:
        """验证 list_context_chains 自动注入白名单 chain_ids 范围约束。"""
        context, service, _writer = _context(
            permissions=frozenset({"context:read"})
        )

        output = list_context_chains_handler(
            RunContextWrapper(context),
            ListContextChainsToolInput(
                conversation_id="conversation-1",
                archived=False,
                limit=20,
            ),
        )

        query = service.list_context_chains.call_args.args[0]
        self.assertEqual(output.chains[0].chain_id, "chain-1")
        self.assertEqual(query.conversation_id, "conversation-1")
        self.assertEqual(query.chain_ids, ["chain-1"])
        self.assertFalse(query.archived)

    def test_non_selected_chain_is_rejected_without_query(self) -> None:
        """验证请求未授权 chain_id 时返回 rejected 并在访问底层前阻断。"""
        context, service, _writer = _context(
            permissions=frozenset({"context:read"})
        )

        output = get_context_chain_handler(
            RunContextWrapper(context),
            GetContextChainToolInput(chain_id="chain-other"),
        )

        self.assertEqual(output.outcome, "rejected")
        self.assertEqual(output.result_code, "task_scope_violation")
        service.get_context_chain.assert_not_called()

    def test_broad_turn_list_is_rewritten_to_current_and_read_set(self) -> None:
        """验证全量轮次查询自动被收敛改写为授权的 turn_ids 集合。"""
        context, service, _writer = _context(
            permissions=frozenset({"context:read"})
        )

        output = list_conversation_turns_handler(
            RunContextWrapper(context),
            ListConversationTurnsToolInput(
                conversation_id="conversation-1",
                limit=20,
            ),
        )

        self.assertEqual(output.outcome, "succeeded")
        query = service.list_conversation_turns.call_args.args[0]
        self.assertEqual(
            query.turn_ids,
            ["turn-1", "turn-current"],
        )

    def test_non_read_set_turn_is_rejected_without_query(self) -> None:
        """验证请求白名单之外的 turn_id 被拒绝且不调用底层数据库。"""
        context, service, _writer = _context(
            permissions=frozenset({"context:read"})
        )

        output = list_conversation_turns_handler(
            RunContextWrapper(context),
            ListConversationTurnsToolInput(
                conversation_id="conversation-1",
                turn_ids=["turn-other"],
            ),
        )

        self.assertEqual(output.outcome, "rejected")
        self.assertEqual(output.result_code, "task_scope_violation")
        service.list_conversation_turns.assert_not_called()

    def test_permission_denial_does_not_query_database(self) -> None:
        """验证无 context:read 权限时直接拦截并返回 permission_denied。"""
        context, service, _writer = _context(permissions=frozenset())

        output = get_conversation_turn_handler(
            RunContextWrapper(context),
            GetConversationTurnToolInput(turn_id="turn-1"),
        )

        self.assertEqual(output.result_code, "permission_denied")
        service.get_conversation_turn.assert_not_called()

    def test_tool_prefers_explicit_query_use_case(self) -> None:
        """验证 Tool 上下文中注入 explicit use_case 时优先使用该用例执行。"""
        context, service, _writer = _context(
            permissions=frozenset({"context:read"})
        )
        use_case = mock.Mock()
        use_case.execute.return_value = service.get_conversation_turn.return_value
        object.__setattr__(
            context.context_services,
            "get_conversation_turn",
            use_case,
        )

        output = get_conversation_turn_handler(
            RunContextWrapper(context),
            GetConversationTurnToolInput(turn_id="turn-1"),
        )

        self.assertEqual(output.turn.turn_id, "turn-1")
        use_case.execute.assert_called_once_with("turn-1")
        service.get_conversation_turn.assert_not_called()


if __name__ == "__main__":
    unittest.main()
