"""Context 历史读取集合选择与会话状态管理模块。

本模块负责：
1. 为 Planner 选择历史 Context Read Set，并派生 no_context / single_context / multi_context 模式；
   Selection 阶段不创建 Chain 或 Node。
2. 使用会话级 Redis 短锁串行化 Context Selection 与完成写回。
3. 上下文链（Context Chain）、节点（Node）与热资源队列（FIFO 缓存 + MySQL 事实表）生命周期管理。
4. 提供只读 Collector Agent Tools 与上下文查询能力。
"""
