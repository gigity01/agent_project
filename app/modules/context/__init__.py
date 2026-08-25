"""Context 上下文路由与会话状态管理模块。

本模块负责：
1. 上下文路由模式判断（single_match / multi_match / new_chain / existing_and_new / fallback_latest）。
2. 会话级 Redis 并发短锁串行化。
3. 上下文链（Context Chain）、节点（Node）与热资源队列（FIFO 缓存 + MySQL 事实表）生命周期管理。
4. 提供只读 Collector Agent Tools 与上下文查询能力。
"""
