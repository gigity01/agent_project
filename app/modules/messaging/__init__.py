"""可靠消息 Outbox/Inbox 模块。

提供基于事务发件箱（Transactional Outbox）与收件箱（Inbox）模式的可靠事件传输机制：
1. 业务写入时在同一个数据库事务中持久化 Outbox 事件，确保状态变更与事件记录原子一致。
2. 独立 Runtime Worker 进程异步扫描待投递的 Outbox 事件，通过 Redis Streams 进行传输。
3. 消费端通过 Inbox 唯一约束实现幂等抑制，并在事件成功处理后通过 ACK 确认。
"""
