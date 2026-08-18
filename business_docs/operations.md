# Operations

Operations 只提供运行与审计事实查询，不执行恢复、补偿或业务写入。

## 查询路径

- `query_document_log_events`：按关联字段查询文档业务事件。
- `get_document_operation_timeline`：查询单次文档 Operation 时间线。
- `get_document_workflow_timeline`：查询完整文档 Workflow 时间线。
- `query_document_business_logs`：查询文档业务日志。
- `get_document_execution_timeline` / `get_document_failure_timeline`：查询执行或失败时间线。
- `query_agent_tool_audits`：查询 Agent Tool 审计。
- `get_task_tool_timeline` / `get_agent_run_tool_timeline`：查询 Task 或 Agent Run 的 Tool
  调用时间线。

Operations Evidence 可以解释已经发生的执行与失败，但不能替代 Document 当前状态查询，
也不能授权 Planner 直接执行 Recovery 或 Compensation。
