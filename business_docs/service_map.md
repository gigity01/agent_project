# Service Map

本系统主要承接三类业务：

- Document Processing：文档处理、切块、向量索引和流水线状态查询。
- Context Management：Conversation、Turn、ContextChain、ResourceQueue 和 Context
  Selection。
- Operations：Workflow、Operation、Task Execution、Compensation、Recovery 和 Agent Tool
  审计查询。

Service Map 只帮助 Agent 理解用户请求所属的业务语境。它不授予 Tool 权限，也不扩大
Context Selection 已经确定的历史 Read Set。
