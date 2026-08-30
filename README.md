# Agent Project

企业知识库与 Agent 任务编排实验项目。当前重点是可靠的文档摄取、上下文选择与受控任务执行，不把尚未完成的检索问答链路包装成已落地功能。

## 当前已实现

- 文档 Upload、Process、BuildChunks、IndexVectors 持久化流水线
- operation ownership、短事务、staging / promote、Artifact 谱系与阶段补偿
- Markdown、CSV 等格式的 Parent-Child 分层切块
- Embedding 生成与 Qdrant 向量写入
- Conversation Context Selection、资源归因与上下文记录
- Evidence、Gap、Commit 分阶段规划
- Task Runtime、Retry / Replan、受限 Executor 与 Compensation

## 尚未完成或仍需验证

- 面向用户查询的完整 Qdrant Dense Retrieval 接口
- Elasticsearch BM25、RRF、Cross-Encoder Rerank
- 完整的 RAG 问答产品链路及离线检索 Benchmark

## 核心流程

```text
Document
  -> Upload
  -> Process
  -> Build Parent / Child Chunks
  -> Embedding
  -> Qdrant Upsert

Conversation
  -> Context Selection
  -> Evidence Collection
  -> Gap Decision
  -> Plan Commit
  -> Task Runtime
  -> Restricted Executor / Compensation
```

## 技术栈

Python 3.10+、FastAPI、SQLAlchemy、Alembic、MySQL、Redis、Qdrant、LangGraph、OpenAI Agents SDK、DashScope Embedding、DeepSeek，以及可选的 Docling 文档转换服务。

## 本地启动

1. 安装 [uv](https://docs.astral.sh/uv/)。
2. 准备 MySQL、Redis 与 Qdrant；如需解析 PDF、DOC/DOCX、PPT/PPTX，再配置 Docling 服务。
3. 复制并填写环境变量：

```powershell
Copy-Item .env.example .env
```

4. 安装依赖并执行数据库迁移：

```powershell
uv sync
uv run alembic upgrade head
```

5. 启动 API：

```powershell
uv run uvicorn app.main:app --reload
```

默认地址为 `http://127.0.0.1:8000`。

## 配置说明

`.env.example` 只包含占位值和本地默认地址。不要提交真实 API Key、数据库密码、业务数据、日志或本地存储目录。

常用配置包括：

- `SQLALCHEMY_DATABASE_URL`
- `DASHSCOPE_API_KEY`
- `DEEPSEEK_API_KEY`
- `QDRANT_URL`
- `REDIS_URL`
- `DOCLING_SERVER_URL`

## 项目边界

这是一个面向工程机制验证的后端项目，不是开箱即用的生产级 RAG 产品。上线前仍需补充完整测试矩阵、安全审计、监控告警、容量评估与检索效果评测。
