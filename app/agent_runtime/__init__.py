"""Agent Tool 运行时包。

本包提供 Agent Tool 体系的公共运行时支撑，包括：
- 窄依赖上下文传递与作用域隔离 (`context.py`)。
- 工具调用拦截、耗时统计与非阻塞 JSONL 审计 (`audit.py`)。
- 权限校验策略与最小权限原则执行 (`policies.py`)。
- 业务拒绝与系统故障的确定性错误分类 (`errors.py`)。
- 不依赖源码的稳定工具元数据描述模型 (`descriptors.py`)。
- Collector 只读工具目录与动态查询视图 (`tool_registry.py`)。
- 业务规则与系统事实 Markdown 文档按需检索 (`business_docs.py`)。
"""
