"""可靠消息 Worker 调度模块。

负责接收来自传输层的事件并分派给对应的业务 Worker（Replan、Runtime 任务执行、Plan 结果聚合等）。
"""
