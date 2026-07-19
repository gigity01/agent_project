# AGENTS.md — agent-knowledge

## 项目定位

本项目是知识库文档入库与向量索引服务，当前主线负责：

1. 接收并校验原始文档。
2. 保存文档元数据和原始文件。
3. 将复杂格式转换为 Markdown，并清洗为标准文本。
4. 构建父级语义块（parent block）和可向量化子块（child chunk）。
5. 调用 DashScope / Qwen Embedding 生成向量。
6. 将向量写入 Qdrant。

当前尚未提供检索、召回、重排或问答 API，因此它是“知识入库管理服务”，不是完整 RAG 问答系统。

## 当前入口与命令

- FastAPI 入口：`app/main.py`
- 应用对象：`app.main:app`
- 本地运行：`py -3 -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`
- 数据库迁移：`py -3 -m alembic upgrade head`
- 语法检查：`py -3 -m compileall -q app core main_config utils alembic`
- 差异检查：`git diff --check`

仓库目前没有 `requirements.txt`、`pyproject.toml`、自动化测试、lint、typecheck 或 CI 配置。不要声称这些检查已运行。

## HTTP API

`app/main.py` 当前暴露四个管理端接口：

| 方法 | 路径 | 作用 |
|---|---|---|
| POST | `/api/admin/documents/upload` | 上传原件并创建文档记录 |
| POST | `/api/admin/documents/{document_id}/process` | 转换或清洗文档 |
| POST | `/api/admin/documents/{document_id}/build-chunks` | 重建父块和子块 |
| POST | `/api/admin/documents/{document_id}/index-vectors` | 生成向量并写入 Qdrant |

这些步骤彼此独立，必须按顺序调用。上传成功不会自动触发处理、切块或索引。

## 目录与分层

```text
app/main.py
  -> app/services/                 # 业务编排和事务边界
    -> app/repositories/           # SQLAlchemy 查询与持久化，不应自行 commit
      -> app/models/               # ORM 表模型
    -> app/processors/             # 本地文本清洗
    -> app/chunkers/               # 父子切块策略
    -> app/integrations/           # Docling 等外部服务客户端
    -> app/vectorstores/           # Qdrant 封装
  -> app/schemas/                  # Pydantic 请求/响应模型
  -> app/db/                       # engine、session、Unit of Work 契约
  -> app/app_config/settings.py    # 应用配置

core/observability/                # JSONL 生命周期事件日志
main_config/                       # 环境变量与日志目录配置
utils/                             # 跨模块的小型辅助函数
alembic/                           # 数据库迁移
```

依赖方向应保持为 API → Service → Repository/Processor/Chunker/Integration/VectorStore。Repository 不应反向调用 Service，模型不应承载业务编排。

## 端到端处理流程

### 1. 上传

入口：`app/services/document_upload_service.py`

- 校验文件名、扩展名和客户端声明的 Content-Type。
- 以 1 MiB 分块读取，最大文件大小为 20 MiB。
- 根据源类型写入 `storage/raw/local/` 或 `storage/raw/external/`。
- 计算 SHA-256，并在同一知识库内查重。
- 创建 `documents` 记录，初始状态为 `uploaded`。
- 失败时尽力删除已经落盘的原件。

Content-Type 只是上传白名单校验，不代表已经验证文件真实内容格式。

### 2. 准备与处理

入口：

- `app/services/document_processing_service.py`
- `app/services/document_source_prepare_service.py`

本地格式直接交给 Processor；复杂办公格式先由 Docling 转成 Markdown：

- 本地格式：`txt`、`md`、`csv`
- Docling 格式：`pdf`、`doc`、`docx`、`ppt`、`pptx`

Docling 结果保存到 `storage/secondary_text/`，同时写入 `document_artifacts`。同一用途的新产物激活前，旧 active 产物会标记为 `superseded`。

处理成功后，标准化文件写入 `storage/cleaned/`，文档状态变为 `processed`。失败时回滚数据库变更、删除本次临时文件，并将文档标记为 `failed`。

### 3. 切块

入口：`app/services/document_chunking_service.py`

- `TextChunker`：先按段落生成父块，再按长度生成子块。
- `MarkdownChunker`：按标题层级维护 `section_path`，以章节生成父块。
- `CsvChunker`：一条记录对应一个子块，父块按最多 50 条记录和 12,000 字符组批。
- 文本/Markdown 子块最大 600 字符；CSV 子块最大 8,000 字符，限制统一定义在 `app/chunkers/common.py`。
- `processed` 文档可以领取切块任务；`failed` 文档只有在仍有 cleaned 产物且不存在 active ChildChunk 时才可重试，已有切块结果的失败文档必须走后续索引重试。
- 领取成功后先提交 `chunking`，事务外生成父子块，最终短事务复核三状态轴并更新为 `chunked`；暂不允许 `chunked` 文档重复切块。
- 重建时先删除旧 child chunks，再删除旧 parent blocks，并在同一事务写入新结果。
- 子块初始 `vector_status` 为 `pending`。

复杂源格式经过 Docling 后按 Markdown 切块，而不是按原始扩展名选择 Chunker。

### 4. 向量索引

入口：`app/services/vector_indexing_service.py`

- 仅查询 `status=active` 且 `vector_status=pending` 的子块。
- 调用外部服务前先提交 `indexing` 状态，避免长数据库事务。
- 使用 DashScope OpenAI-compatible Embedding API。
- 校验向量数量和 `EMBEDDING_VECTOR_SIZE`。
- Qdrant point id 与 `child_chunks.id` 一一对应，重试时可幂等 upsert。
- 成功后标记为 `indexed`；失败时尽力补偿为 `failed`。

数据库、Embedding 服务和 Qdrant 无法组成单一事务。必须考虑“Qdrant 已写入但数据库状态更新失败”等跨存储不一致场景。

## 文件类型支持现状

| 类型 | 上传 | 准备/清洗 | 切块 | 说明 |
|---|---:|---:|---:|---|
| `txt` | 是 | 是 | 是 | 本地纯文本流程 |
| `md` / `markdown` | 是 | 是 | 是 | `markdown` 归一化为 `md` |
| `pdf` | 是 | Docling → MD | 是 | 依赖外部 Docling |
| `doc` / `docx` | 是 | Docling → MD | 是 | 依赖外部 Docling |
| `ppt` / `pptx` | 是 | Docling → MD | 是 | 依赖外部 Docling |
| `csv` | 是 | 是 | 是 | 一条记录对应一个子块，支持带换行的引号字段 |

不要把上传白名单等同于端到端可用能力；新增格式时仍需同步检查 Processor、Chunker 和准备流程。

## 生命周期状态

文档状态枚举在 `app/constants/document_status.py` 中定义了目标生命周期：

```text
uploaded -> processing -> processed -> chunking -> chunked -> indexing -> indexed
                         \_______________________________________________
                                          任一失败阶段 -> failed
```

业务有效性由独立的 `DocumentLifecycleStatus` 表示，包括 `scheduled`、`active`、
`expired`、`replaced` 和 `deleted`；`DocumentStatus` 不再承载业务过期语义。当前实现尚未
完整推进处理状态链：上传/处理服务实际使用 `uploaded`、`processing`、`processed`、
`failed`；切块服务已经使用 `chunking` 领取状态并在完成事务中更新为 `chunked`；向量索引服务
没有把 Document 更新为 `indexing/indexed`，索引进度主要体现在子块状态中。

修改状态逻辑时必须使用 `DocumentStatus`，并同步检查各服务的准入条件和响应模型，
不要把“枚举中已定义”误认为“业务流程已接入”。

子块向量状态目前使用字符串：`pending`、`indexing`、`indexed`、`failed`。

## 数据库与事务边界

- SQLAlchemy engine/session/Base：`app/db/session.py`
- ORM 模型：`app/models/`
- Repository：`app/repositories/`
- Alembic 当前迁移头：`e7b3c2d4a9f1`

Repository 原则：

- 可以 `add()`、`flush()`、查询和修改实体。
- 不应自行 `commit()` 或 `rollback()`。
- 业务事务由 Service 或 Unit of Work 管理。

`app/db/unit_of_work.py` 已定义 Unit of Work 契约，但现有 Service 仍有直接管理 `Session.commit()` / `rollback()` 的代码。不要假设 UoW 已在全项目完成接入。

文件系统操作不受数据库事务保护。任何“先写文件、后写数据库”的流程都必须在异常路径显式清理孤儿文件。

## 配置与敏感信息

配置入口：

- 应用配置：`app/app_config/settings.py`
- 环境变量加载：`main_config/environment.py`
- 日志目录：`main_config/settings.py`
- 安全示例：`.env.example`

环境变量优先级：

1. 进程启动前由系统、容器或 CI 注入的变量。
2. 项目根目录的 `.env`。
3. 代码中的非敏感默认值。

必填配置至少包括：

- `SQLALCHEMY_DATABASE_URL`
- `DASHSCOPE_API_KEY`

可覆盖配置包括 Qdrant、DashScope endpoint/model、Embedding 维度与批量大小、Docling 地址/超时/输出格式和日志目录。

禁止读取、打印、写入计划、提交或日志记录 `.env`、数据库密码、API Key、Token 或其他真实凭据。只允许维护不含真实值的 `.env.example`。

## 存储与运行时文件

应用存储目录当前使用相对路径 `storage/`，因此启动工作目录会影响实际落盘位置。默认应从项目根目录启动服务。

运行期目录包括：

- `storage/raw/local/`
- `storage/raw/external/`
- `storage/secondary_text/`
- `storage/cleaned/`
- `logs/document_lifecycle/`

这些目录及 `.env*`、缓存、数据库文件、JSONL 日志已在 `.gitignore` 中排除。不要把运行期文件或机器状态加入提交。

## 外部依赖

从源码可确认的主要依赖包括：

- FastAPI、Uvicorn、python-multipart、Pydantic
- SQLAlchemy、PyMySQL、Alembic
- requests
- OpenAI Python SDK（用于 DashScope compatible API）
- qdrant-client

运行时还需要可访问的 MySQL、Qdrant、DashScope 和 Docling 服务。安装依赖、修改依赖清单或访问外部服务前，先说明影响并取得确认。

## 观测日志

`core/observability/` 将上传和处理事件按日期追加为 JSONL。日志用于诊断和审计，但不得记录密钥、数据库连接串、完整认证头或其他敏感值。

当前只完整实现了上传和处理日志组件；chunk、index、retrieval 目录虽已配置，不代表对应事件记录已经完成。

## 容易遗漏的约束

- `app/main.py` 导入 `app.models` 是为了确保 ORM 表注册完整。
- `QdrantVectorStore.ensure_collection()` 只创建不存在的 collection，不迁移已有 collection schema。
- 修改 Embedding 模型或维度前，必须评估 Qdrant collection 重建/迁移。
- Markdown 标题本身没有正文时不会生成可检索父块。
- `embedding_text` 会加入章节路径，但父块正文仍保留清洗后的原始内容。
- 文档查重范围是单个知识库，不是全局。
- Content hash 基于完整落盘后的文件字节计算。
- `created_by_actor_code` 当前在 API 层使用固定默认值，尚未接入真实认证主体。
- 当前没有检索 API，也没有 Qdrant search 封装。

## 编码工作规则

- 默认使用简体中文说明和注释，代码标识符、命令及错误文本保持其原始语言。
- 修改前阅读相关 Service、Repository、模型、状态常量和邻近代码。
- 做最小完整改动，不混入无关重构或格式化。
- 保留工作区已有修改；不要使用破坏性 Git 命令覆盖用户工作。
- 不读取、输出、记录或提交任何凭据和用户数据。
- 修改 Repository 事务语义时同步检查所有调用它的 Service。
- 修改文档状态时同步检查 API 响应、服务准入条件和失败补偿。
- 修改支持的源类型时同步检查上传白名单、Source Policy、Processor、Chunker 和 Docling 路径。
- 修改存储路径时同步检查失败清理、Artifact URI、日志和 `.gitignore`。
- 修改向量模型或维度时同步检查 Embedding 配置与 Qdrant schema。
- 安装依赖、修改配置/锁文件、删除或移动文件、联网、部署、提交或推送前，说明影响并取得确认。
- Code review 先按严重程度报告具体问题和文件行号；除非明确要求，否则不修改代码。

## 交付验证

仓库没有自动化测试框架时，至少执行：

```powershell
py -3 -m compileall -q app core main_config utils alembic
git diff --check
```

如运行环境已安装依赖并配置了安全的测试环境，再按改动范围执行导入检查、Alembic 检查或针对性 API 测试。不要为了验证连接真实生产数据库或外部服务。
