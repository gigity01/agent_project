"""可独立进程运行的 Task Runtime Worker 模块。

负责从 Redis Stream 消费 `runtime.plan_wakeup` 事件驱动任务状态机，
并运行 Outbox 轮询发布器向 Redis Stream 分发事件。
"""
