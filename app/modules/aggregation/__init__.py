"""Task 结果聚合与 Turn Completion 模块。

本模块负责在异步 Plan 中所有 Task 成功执行后，读取任务产出与资源引用，
生成确定性的事实摘要，调用 ContextService 完成 Turn、回写链节点与热资源队列，
并将已回答的 ClarificationRequest 推进至 resolved 状态。
"""
