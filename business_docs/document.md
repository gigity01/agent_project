# Document Processing

## 支持的动作

- `process_document`：处理本地文本，或把受支持的办公格式转换并清洗为标准文本。
- `build_document_chunks`：基于 cleaned 产物构建 ParentBlock 和 ChildChunk。
- `index_document_vectors`：为尚未索引的 ChildChunk 生成向量并写入 Qdrant。
- 查询 Document、Artifact、ParentBlock、ChildChunk、知识库统计和完整流水线状态。

## 关键状态与前置事实

- Process Document 需要确认 Document 存在，以及当前状态允许进入处理阶段。
- Build Chunks 需要确认 Document 已有可用 cleaned 产物且当前状态允许切块。
- Index Vectors 需要确认 Document 已完成切块，并存在可索引的 ChildChunk。
- `DocumentStatus` 与业务生命周期状态是两条独立状态轴；不能只凭资源引用推断状态。
- 查询成功但对象不存在仍是一项有效 Evidence；它证明查询结果为空，而不是证明查询漏做。

## 查询路径

- `get_document`：确认一份 Document 的完整元数据和当前状态。
- `search_documents`：按受限业务条件定位 Document。
- `get_document_pipeline_state`：确认处理、切块和索引阶段状态。
- `get_document_chunk_statistics`：确认 ParentBlock、ChildChunk 及向量状态统计。
- `list_document_artifacts` / `search_document_artifacts`：确认 cleaned 等派生产物。
- `list_parent_blocks` / `list_child_chunks`：读取具体切块明细。
- `get_knowledge_base_statistics`：读取知识库级文档与切块统计。

业务文档描述预期查询路径；当前 Tool 是否真实可用仍以 Tool Registry 为准。
