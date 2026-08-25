"""Document 模块 MySQL 数据库访问与仓储实现层（Persistence）。

包含各业务实体的 Repository：
- KnowledgeBaseRepository: 知识库只读查询。
- DocumentRepository: 文档 CRUD、状态推进与生命周期停用。
- DocumentArtifactRepository: 派生产物创建、查询与 superseded 标记。
- ParentBlockRepository: 父级语义块批量创建、查询与删除。
- ChildChunkRepository: 可向量化子块批量创建、查询、删除、行锁与向量状态更新（indexing/indexed/failed）。
"""
