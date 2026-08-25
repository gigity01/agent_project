"""Document Executor Agent 工具范围隔离、StopAtTools 拦截与确定性适配器测试。

核心业务不变量（遵循 AGENTS.md 规范）：
1. Capability 级别工具范围隔离与单写约束：
   - 每个 Executor Agent（process, build_chunks, index_vectors）只能看到查询 Tool 与当前 Capability 的唯一定向写命令 Tool。
   - `parallel_tool_calls=False` 且 `max_function_tool_concurrency=1`。
2. StopAtTools 与确定性判定：
   - 命令 Tool 执行后通过 `StopAtTools` 直接将结构化 Tool Output 交给确定性适配器（Adapter），LLM 的自然语言文本输出不能决定 Task 的成败。
   - 命令 `succeeded` 映射为 Task Output，`rejected` 映射为 blocked 终态，`failed` 保留 retryable 标记。
"""

from __future__ import annotations

import asyncio
import json
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import mock

from agents import ModelSettings, RunContextWrapper

from app.agent_runtime.audit import AgentToolAuditLogger
from app.agent_runtime.context import (
    ContextToolServices,
    DocumentToolServices,
)
from app.agents.document_executors import build_document_executor_agents
from app.modules.document.agent_tools.command_tools import (
    DOCUMENT_PROCESS_PERMISSION,
    process_document_handler,
)
from app.modules.document.agent_tools.query_tools import DOCUMENT_READ_PERMISSION
from app.modules.document.agent_tools.schemas import (
    ProcessDocumentToolInput,
    ProcessDocumentToolOutput,
)
from app.modules.task_runtime.application.dto import TaskRuntimeContext
from app.modules.task_runtime.application.errors import TaskExecutionError
from app.modules.task_runtime.application.schemas import (
    ProcessDocumentTaskPayload,
)
from app.modules.task_runtime.infrastructure.executors import (
    AgentTaskExecutor,
    adapt_process_document_output,
)


class _AuditWriter:
    """测试用审计日志写入器。"""
    def __init__(self) -> None:
        self.events: list[dict] = []

    def write(self, event: dict) -> bool:
        self.events.append(dict(event))
        return True


def _services(process_result=None) -> DocumentToolServices:
    process = mock.Mock()
    process.execute.return_value = process_result
    return DocumentToolServices(
        get_document=mock.Mock(),
        list_documents=mock.Mock(),
        search_documents=mock.Mock(),
        get_document_pipeline_state=mock.Mock(),
        list_document_artifacts=mock.Mock(),
        search_document_artifacts=mock.Mock(),
        list_parent_blocks=mock.Mock(),
        list_child_chunks=mock.Mock(),
        get_document_chunk_statistics=mock.Mock(),
        get_knowledge_base_statistics=mock.Mock(),
        process_document=process,
        build_chunks=mock.Mock(),
        index_vectors=mock.Mock(),
    )


def _runtime_context() -> TaskRuntimeContext:
    return TaskRuntimeContext(
        workflow_id="workflow-1",
        plan_id="plan-1",
        task_id="task-1",
        conversation_id="conversation-1",
        turn_id="turn-1",
        execution_id="execution-1",
        operation_id="operation-1",
        agent_run_id="agent_run-1",
        attempt=2,
    )


class _CommandRunner:
    def __init__(self, document_id: int = 7) -> None:
        self.document_id = document_id
        self.calls: list[tuple] = []

    async def __call__(self, agent, agent_input, **kwargs):
        self.calls.append((agent, json.loads(agent_input), kwargs))
        output = process_document_handler(
            RunContextWrapper(kwargs["context"]),
            ProcessDocumentToolInput(document_id=self.document_id),
        )
        return SimpleNamespace(final_output=output)


class _StaticRunner:
    def __init__(self, final_output) -> None:
        self.final_output = final_output

    async def __call__(self, *_args, **_kwargs):
        return SimpleNamespace(final_output=self.final_output)


class _ThreadedCommandRunner:
    async def __call__(self, _agent, _agent_input, **kwargs):
        return await asyncio.to_thread(self._run_command, kwargs["context"])

    @staticmethod
    def _run_command(context):
        output = process_document_handler(
            RunContextWrapper(context),
            ProcessDocumentToolInput(document_id=7),
        )
        return SimpleNamespace(final_output=output)


class DocumentExecutorAgentsTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.agents = build_document_executor_agents(
            model="test-model",
            model_settings=ModelSettings(parallel_tool_calls=True),
        )

    def _executor(
        self,
        *,
        services: DocumentToolServices,
        runner,
        writer: _AuditWriter | None = None,
    ) -> AgentTaskExecutor:
        return AgentTaskExecutor(
            agent=self.agents.process,
            executor_code="document.process",
            primary_tool_name="process_document",
            tool_output_model=ProcessDocumentToolOutput,
            output_adapter=adapt_process_document_output,
            document_services=services,
            permissions=frozenset(
                {DOCUMENT_READ_PERMISSION, DOCUMENT_PROCESS_PERMISSION}
            ),
            run_config=self.agents.run_config,
            runner=runner,
            audit_logger_factory=(
                (lambda: AgentToolAuditLogger(writer))
                if writer is not None
                else AgentToolAuditLogger
            ),
        )

    async def test_agents_expose_one_capability_command_and_serial_execution(self) -> None:
        process_tools = {tool.name for tool in self.agents.process.tools}
        chunks_tools = {tool.name for tool in self.agents.build_chunks.tools}
        vectors_tools = {tool.name for tool in self.agents.index_vectors.tools}

        self.assertEqual(
            process_tools,
            {
                "get_document",
                "get_document_pipeline_state",
                "process_document",
            },
        )
        self.assertNotIn("index_document_vectors", chunks_tools)
        self.assertNotIn("build_document_chunks", vectors_tools)
        self.assertFalse(self.agents.process.model_settings.parallel_tool_calls)
        self.assertEqual(
            self.agents.run_config.tool_execution.max_function_tool_concurrency,
            1,
        )
        self.assertEqual(
            self.agents.process.tool_use_behavior,
            {"stop_at_tool_names": ["process_document"]},
        )

    async def test_command_output_drives_task_result_and_correlation(self) -> None:
        services = _services(
            SimpleNamespace(
                document_id=7,
                status="processed",
                cleaned_uri="cleaned/7.txt",
            )
        )
        writer = _AuditWriter()
        runner = _CommandRunner()
        executor = self._executor(
            services=services,
            runner=runner,
            writer=writer,
        )

        result = await executor.execute(
            ProcessDocumentTaskPayload(document_id=7),
            _runtime_context(),
        )

        self.assertEqual(
            result.output_json,
            {
                "document_id": 7,
                "status": "processed",
                "cleaned_uri": "cleaned/7.txt",
            },
        )
        self.assertEqual(result.resource_refs, ["document:7"])
        call = services.process_document.execute.call_args
        operation_context = call.kwargs["operation_context"]
        self.assertEqual(operation_context.workflow_id, "workflow-1")
        self.assertEqual(operation_context.operation_id, "operation-1")
        self.assertEqual(operation_context.attempt, 2)
        agent_context = runner.calls[0][2]["context"]
        self.assertEqual(agent_context.agent_run_id, "agent_run-1")
        self.assertEqual(agent_context.execution_id, "execution-1")
        self.assertEqual(agent_context.task_document_id, 7)
        self.assertEqual(writer.events[-1]["operation_id"], "operation-1")
        self.assertEqual(writer.events[-1]["execution_id"], "execution-1")

    async def test_rejected_tool_output_blocks_task(self) -> None:
        output = ProcessDocumentToolOutput(
            outcome="rejected",
            result_code="document_state_conflict",
            message="当前状态不允许处理",
            retryable=False,
            resource_refs=["document:7"],
            document_id=7,
        )
        executor = self._executor(
            services=_services(),
            runner=_StaticRunner(output),
        )

        with self.assertRaises(TaskExecutionError) as caught:
            await executor.execute(
                ProcessDocumentTaskPayload(document_id=7),
                _runtime_context(),
            )

        self.assertEqual(caught.exception.error_code, "document_state_conflict")
        self.assertFalse(caught.exception.retryable)
        self.assertTrue(caught.exception.blocked)

    async def test_failed_tool_output_preserves_retryability(self) -> None:
        output = ProcessDocumentToolOutput(
            outcome="failed",
            result_code="tool_execution_failed",
            message="工具执行失败",
            retryable=True,
            resource_refs=["document:7"],
            document_id=7,
        )
        executor = self._executor(
            services=_services(),
            runner=_StaticRunner(output),
        )

        with self.assertRaises(TaskExecutionError) as caught:
            await executor.execute(
                ProcessDocumentTaskPayload(document_id=7),
                _runtime_context(),
            )

        self.assertEqual(caught.exception.error_code, "tool_execution_failed")
        self.assertTrue(caught.exception.retryable)
        self.assertFalse(caught.exception.blocked)

    async def test_llm_text_cannot_become_task_result(self) -> None:
        executor = self._executor(
            services=_services(),
            runner=_StaticRunner("我认为已经成功"),
        )

        with self.assertRaises(TaskExecutionError) as caught:
            await executor.execute(
                ProcessDocumentTaskPayload(document_id=7),
                _runtime_context(),
            )

        self.assertEqual(
            caught.exception.error_code,
            "executor_command_not_completed",
        )

    async def test_command_cannot_change_task_document(self) -> None:
        services = _services()
        runner = _CommandRunner(document_id=8)
        executor = self._executor(services=services, runner=runner)

        with self.assertRaises(TaskExecutionError) as caught:
            await executor.execute(
                ProcessDocumentTaskPayload(document_id=7),
                _runtime_context(),
            )

        self.assertEqual(caught.exception.error_code, "task_scope_violation")
        self.assertTrue(caught.exception.blocked)
        services.process_document.execute.assert_not_called()

    async def test_cancellation_waits_for_sync_command_tool_to_quiesce(
        self,
    ) -> None:
        with TemporaryDirectory() as temp_dir:
            side_effect_path = Path(temp_dir) / "tool-output.txt"
            started = threading.Event()
            allow_side_effect = threading.Event()
            side_effect_completed = threading.Event()

            def execute_use_case(document_id, *, operation_context):
                del operation_context
                started.set()
                if not allow_side_effect.wait(timeout=2):
                    raise TimeoutError("test did not release command tool")
                side_effect_path.write_text(
                    "late tool side effect",
                    encoding="utf-8",
                )
                side_effect_completed.set()
                return SimpleNamespace(
                    document_id=document_id,
                    status="processed",
                    cleaned_uri=str(side_effect_path),
                )

            services = _services()
            services.process_document.execute.side_effect = execute_use_case
            executor = self._executor(
                services=services,
                runner=_ThreadedCommandRunner(),
            )
            execution_task = asyncio.create_task(
                executor.execute(
                    ProcessDocumentTaskPayload(document_id=7),
                    _runtime_context(),
                )
            )
            command_started = await asyncio.to_thread(started.wait, 1)
            self.assertTrue(command_started)

            execution_task.cancel()
            await asyncio.sleep(0.05)
            completed_before_release = execution_task.done()
            allow_side_effect.set()

            with self.assertRaises(asyncio.CancelledError):
                await execution_task
            completed = await asyncio.to_thread(
                side_effect_completed.wait,
                1,
            )
            self.assertFalse(completed_before_release)
            self.assertTrue(completed)
            self.assertTrue(side_effect_path.exists())


if __name__ == "__main__":
    unittest.main()
