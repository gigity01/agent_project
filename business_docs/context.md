# Context Management

## 业务对象

- Conversation：一次连续会话。
- Turn：一次完整用户输入及其后续处理结果。
- ContextChain：一条历史上下文链。
- ContextChainNode：把一个历史 Turn 关联到一条 Chain。
- ContextChainResource：Chain 的持久化资源事实。
- ContextSelectionRecord：当前 Turn 授权 Planner 读取的历史 Chain 集合。

## 查询路径

- `get_conversation_turn` / `list_conversation_turns`
- `get_context_chain` / `list_context_chains`
- `list_context_chain_nodes`
- `list_context_chain_resources`
- `list_context_selection_records`

Tool Registry 只证明查询能力在代码中注册。实际调用仍受 `AgentToolContext` 中的
`allowed_context_chain_ids` 和 `allowed_context_turn_ids` 约束；Business Docs 或
Registry 都不能授权读取未被 Context Selection 选中的 Chain 或 Turn。
