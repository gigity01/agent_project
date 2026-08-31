"""独立后台 Runtime Worker 进程模块包。

负责从数据库 Outbox 发布可靠事件至 Redis Streams，并由 Consumer Group 消费事件驱动异步 Task 执行、失败重试与 Plan 结果聚合。
"""
