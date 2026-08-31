"""Document 模块基础设施层（Infrastructure）。

包含以下技术实现子模块：
1. chunking: 文本、Markdown 与 CSV 格式的父子块分词与切块器（TextChunker, MarkdownChunker, CsvChunker）。
2. parsing: 文本清洗与格式转换器（TextProcessor, MarkdownProcessor, CsvProcessor, DoclingClient 等）。
3. embedding: DashScope Qwen 向量生成客户端。
4. vector_store: Qdrant 向量数据库读写客户端（以 child_chunks.id 作为 Point ID 幂等操作）。
5. persistence: 基于 SQLAlchemy 的 MySQL 仓储层实现与 ORM 模型。
6. storage: 本地文件存储管理（原始文件、staging 产物与正式产物）。
"""
