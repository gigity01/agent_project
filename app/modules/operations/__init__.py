"""运维日志与审计查询模块。

提供面向 Operations Collector Agent 与内部可观测性的结构化日志检索能力：
1. 扫描受控目录下的日切 JSONL 日志（文档业务流水日志与 Agent Tool 调用审计日志）。
2. 提供多维度过滤、统一关联追踪（workflow_id, operation_id, document_id, trace_id 等）与时间线聚合。
3. 暴露只读 Function Tools 供 Planner / Evidence Agent 调查系统运行历史与失败事实。
"""
