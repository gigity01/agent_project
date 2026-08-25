"""Document 业务模块。

本项目核心领域模块之一，负责文档全生命周期管理与多阶段流水线处理，包括：
1. 文档上传、格式校验与原始文件持久化（Upload）
2. 文本清洗与复杂办公格式 Markdown 转换（Process / Prepare）
3. 层次化语义切块：父级语义块与可向量化子块构建（Build Chunks）
4. DashScope / Qwen Embedding 向量计算与 Qdrant 向量存储写入（Index Vectors）
5. 知识库统计、流水线状态观测与 Agent 运行时查询/命令工具集成
"""
