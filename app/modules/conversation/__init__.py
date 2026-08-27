"""完整用户消息链路编排模块。

本模块负责对外提供发送消息（POST /api/conversations/{conversation_id}/messages）
与查询 Turn/Plan 状态（GET /api/conversations/{conversation_id}/turns/{turn_id}）的核心端点，
串联历史 Context Read Set 选择、Clarification 回复处理与 Planner 异步规划执行。
"""
