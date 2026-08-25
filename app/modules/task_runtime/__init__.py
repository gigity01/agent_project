"""Task Runtime 业务模块。

负责 Plan 任务的 Claim 领取、事务外 Executor 驱动执行、Completion/Failure 终态更新
以及确定性 Compensator 补偿与状态机流转。
"""
