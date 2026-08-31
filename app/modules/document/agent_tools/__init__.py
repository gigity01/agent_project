"""Document Application 业务能力的 Agent Function Tool 适配与注册层。

包含：
1. schemas.py: Agent Tool 交互专用的显式输入输出 Pydantic Schema。
2. query_tools.py: 只读查询类 Function Tool（get_document, search_documents, list_parent_blocks 等）。
3. command_tools.py: 状态守卫型变更类 Function Tool（process_document, build_document_chunks, index_document_vectors）。
4. catalog.py: 基于 Agent 角色与 Capability 的 Tool 目录隔离与权限描述符注册。
"""
