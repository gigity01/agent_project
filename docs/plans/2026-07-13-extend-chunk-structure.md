# 扩展 Chunk 语义结构实施计划

## 目标与约束

- 稳定 `Document -> Artifact -> ParentBlock -> ChildChunk` 的语义恢复关系。
- 父块受字符上限约束，并通过 `semantic_group_index`、`segment_index` 恢复完整语义单元。
- 子块只保存检索需要的 `section_path`、`source_row_index`，不引入通用 metadata。
- CSV 一条数据记录对应一个 child；相邻记录按行数或字符数上限聚合为 parent。
- 优先使用 active cleaned Artifact，并兼容只有 `Document.cleaned_uri` 的旧记录。
- 不连接真实数据库、Embedding、Qdrant 或其他外部服务。

## 风险与验收标准

- Alembic migration 必须从 `a473f5174f52` 单链向前，upgrade/downgrade 对称。
- Markdown Artifact 的行号元信息必须按 1-based 范围正确提取正文；缺失元信息时保留解析降级路径。
- CSV 批次必须同时遵守最大行数和最大字符数，超大单行给出明确错误。
- 重建块数据仍在单一数据库事务内，成功后文档为 `chunked`，异常时回滚。
- `compileall`、定向纯函数运行检查和 `git diff --check` 通过。

## 实施任务

1. 数据模型与迁移
   - 修改 `app/models/parent_block.py`、`app/models/child_chunk.py`，增加字段和复合索引。
   - 新增 `alembic/versions/<revision>_extend_chunk_structure.py`，增加字段/索引并提供逆向 downgrade。
   - 验证：编译模型和迁移，静态检查 revision/down_revision 与 DDL 对称性。

2. Chunker 契约与共享切分
   - 修改 `app/chunkers/base.py`，引入基于路径和处理元信息的 `ChunkBuildInput`。
   - 修改 `app/chunkers/common.py`，定义 TXT/MD/CSV 上限并增加父块限长切分。
   - 验证：针对空文本、长段落和多段落运行定向断言。

3. TXT、Markdown、CSV 策略
   - 修改 `text_chunker.py`、`markdown_chunker.py`，生成语义组与父块分段字段。
   - 新增 `csv_chunker.py`，实现一行一 child、受双上限控制的 parent 批次。
   - 修改 `factory.py` 接入 CSV。
   - 验证：使用临时 TXT/MD/CSV 文件构造结果，断言父子数量、索引、路径、行号和长度上限。

4. 服务、仓储与向量 payload
   - 修改 `document_chunking_service.py`，优先读取 active cleaned Artifact，持久化新字段并推进 `DocumentStatus.CHUNKED`。
   - 修改 `parent_block_repository.py`，增加按语义组有序查询。
   - 修改 `vector_indexing_service.py`，向 Qdrant payload 加入 `section_path`、`source_row_index`。
   - 验证：编译、审查事务边界与状态准入，确保 Repository 仍不 commit。

5. 全量交付检查
   - 运行 `py -3 -m compileall -q app core main_config utils alembic`。
   - 运行定向 Chunker 运行检查（仅本地临时文件，不访问外部服务）。
   - 运行 `git diff --check` 并复核 `git status --short`，保留既有 `app/db/uow/` 不变。
