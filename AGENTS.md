# AGENTS.md — agent-knowledge

## 项目定位

本项目是知识库文档入库与向量索引服务，当前主线负责：

1. 接收并校验原始文档。
2. 保存文档元数据和原始文件。
3. 将复杂格式转换为 Markdown，并清洗为标准文本。
4. 构建父级语义块（parent block）和可向量化子块（child chunk）。
5. 调用 DashScope / Qwen Embedding 生成向量。
6. 将向量写入 Qdrant。
7. 使用 Context Agent 将完整用户输入路由到一条或多条历史上下文链。

当前尚未提供检索、召回、重排或问答 API。Context Agent 只负责上下文关联，
不提供业务规划或问答能力，因此本项目仍不是完整 RAG 问答系统。

## 当前入口与命令

- FastAPI 入口：`app/main.py`
- 应用对象：`app.main:app`
- 依赖声明：`pyproject.toml`
- 锁文件：`uv.lock`
- 本地运行：`uv run --frozen uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`
- 数据库迁移：`uv run --frozen alembic upgrade head`
- 自动化测试：`uv run --frozen python -m unittest discover -s tests -v`
- 语法检查：`uv run --frozen python -m compileall -q app core main_config main_utils alembic`
- 差异检查：`git diff --check`

仓库使用 `pyproject.toml` 和 `uv.lock` 管理依赖，自动化测试基于标准库
`unittest`。当前没有独立的 lint、typecheck 或 CI 配置；不要声称未实际执行的
检查已经运行。首次同步依赖或修改锁文件前仍需说明影响并取得确认。

## HTTP API

`app/main.py` 和 `app/api/context.py` 当前暴露六个接口：

| 方法 | 路径 | 作用 |
|---|---|---|
| POST | `/api/admin/documents/upload` | 上传原件并创建文档记录 |
| POST | `/api/admin/documents/{document_id}/process` | 转换或清洗文档 |
| POST | `/api/admin/documents/{document_id}/build-chunks` | 重建父块和子块 |
| POST | `/api/admin/documents/{document_id}/index-vectors` | 生成向量并写入 Qdrant |
| POST | `/api/context/route` | 创建唯一 Turn 并执行上下文链路由 |
| POST | `/api/context/turns/{turn_id}/complete` | 补全 Turn 并关联已路由的目标链 |

四个文档步骤彼此独立，必须按顺序调用。上传成功不会自动触发处理、切块或索引。
两个 Context 接口组成独立流程：先路由，待下游处理完成后再回写 Turn。

## 目录与分层

```text
app/main.py
  -> app/api/                      # Context 等拆分路由与请求依赖
  -> app/agents/                   # Context Agent 与 DeepSeek Provider
  -> app/services/                 # 业务编排和事务边界
    -> app/repositories/           # SQLAlchemy 查询与持久化，不应自行 commit
      -> app/models/               # ORM 表模型
    -> app/processors/             # 本地文本清洗
    -> app/chunkers/               # 父子切块策略
    -> app/integrations/           # Docling、Redis 客户端、路由锁和热资源队列
    -> app/vectorstores/           # Qdrant 封装
  -> app/schemas/                  # Pydantic 请求/响应模型
  -> app/db/                       # engine、session、Unit of Work
  -> app/app_config/settings.py    # 应用配置

core/observability/                # JSONL 生命周期事件日志
main_config/                       # 环境变量与日志目录配置
main_utils/                        # 跨模块的小型辅助函数
alembic/                           # 数据库迁移
tests/                             # unittest 自动化测试
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

- 领取事务只查询 `status=active` 且 `vector_status=pending/failed` 的子块，已索引子块不会重复生成向量。
- 领取时以行锁把 Document 和本次子块推进到 `indexing` 并提交，外部 Embedding/Qdrant 调用不占用数据库事务。
- 使用 DashScope OpenAI-compatible Embedding API。
- Service 按 `EMBEDDING_BATCH_SIZE` 分批执行，并校验每批向量数量和 `EMBEDDING_VECTOR_SIZE`。
- Qdrant point id 与 `child_chunks.id` 一一对应，重试时可幂等 upsert。
- 最终短事务会重新检查 Document 三状态轴并锁定本次子块，成功后同时把 ChildChunk 和 Document 标记为 `indexed`。
- 失败时以独立短事务把本次 `indexing` 状态补偿为 `failed`；已经尝试写入的 Point 会尽力按稳定 ID 删除。

数据库、Embedding 服务和 Qdrant 无法组成单一事务。必须考虑“Qdrant 已写入但数据库状态更新失败”等跨存储不一致场景。

## Context Agent 子系统

入口：

- API：`app/api/context.py`
- Agent：`app/agents/context_agent.py`
- Service：`app/services/context_service.py`
- 资源 Service：`app/services/context_resource_service.py`
- 确定性校验：`app/services/context_route_validation.py`
- Redis 锁客户端：`app/integrations/conversation_route_lock.py`
- Redis 资源队列：`app/integrations/context_resource_queue.py`

Context Agent 是上下文路由器，只判断当前完整用户输入关联哪些已有链，以及是否
包含与所有已有链无关的新内容。它不拆分或改写输入，也不负责业务计划、Task
拆解、Service 选择、权限判断、操作执行或最终回答。

固定路由模式包括：

- `single_match`：关联一条已有链。
- `multi_match`：关联多条已有链。
- `new_chain`：与全部已有链无关，创建新链。
- `existing_and_new`：同时关联已有链并创建新链。
- `fallback_latest`：存在上下文关联但无法判断具体归属时，选择
  `last_active_at` 最新的未归档链，不向用户追问。

Context 数据约束：

- 一次完整用户输入只创建一个 `ConversationTurn`。
- `ContextChainNode` 只引用 Turn；同一个 Turn 可以关联多条链。
- Agent 输入包含当前完整用户输入、当前 Conversation 的全部未归档完整链，以及每条
  链按最久未使用到最近使用排列的热资源队列。
- Agent 只读链资源，不得修改资源、归档状态或时间戳。
- 普通代码必须校验链存在性、Conversation 归属、重复、归档状态以及
  `route_mode` 与字段组合。
- 路由阶段只保存决定并预分配新链 ID；下游完成后才补全 Turn、建立链节点并更新
  资源和 `last_active_at`。
- 旧助手回答可以使用 `assistant_compact`，但链节点和用户原始输入不得丢失。

资源管理以 MySQL 为完整事实层：

- `context_chain_nodes.related_resource_refs` 保存某个 Turn 在某条链中涉及的资源 Key。
- `context_chain_resource_events` 追加保存 `seen`、`refreshed`、`removed` 和
  `invalidated` 事件，Redis 淘汰不得删除这些历史。
- `context_chain_resources` 以 `UNIQUE(chain_id, resource_key)` 保存资源当前状态、
  首次/最近使用 Turn、时间、使用次数和有效性。
- `context_chains.resource_version` 在资源状态变化时递增；旧 `resources` JSON 列仅
  作为兼容字段保留，不再由完成流程整包替换，也不是正式事实来源。

下游完成 Turn 时只提交本轮 `related_resources` 和 `removed_resource_keys`，不提交
完整资源快照。数据库事务内必须创建 Node、追加事件、upsert 或停用资源、递增版本并
更新 `last_active_at`；数据库提交后才能刷新 Redis。Redis 失败不能回滚已提交的
MySQL 事务，应删除该链的热队列 Key，使下一次读取从数据库预热。

Redis 为每条 Chain 使用 List、Hash 和 Version 三个 Key，维护默认容量 16 的刷新式
FIFO：新资源或再次使用的资源先从旧位置移除，再进入队尾；超过容量时从队头推出最久
未再次使用的资源；明确失效资源从 List 和 Hash 删除。List、Hash、版本更新必须通过
Lua 原子完成，增量刷新必须校验 Redis 当前版本等于数据库新版本的前一版本。版本
缺失、不一致、出现跳号或缓存结构不完整时，从
`context_chain_resources` 查询最近 N 个 active 资源，反转为最旧到最新后整体预热。

同一 Conversation 的路由通过 Redis 短锁串行化。FastAPI lifespan 根据 `REDIS_URL`
创建一个应用级 `redis.asyncio.Redis` 客户端，路由锁和资源队列共享其连接池，并在
启动时执行 `PING` 验证连接，在应用关闭时统一 `aclose()`。Redis 不可用时应用启动
必须失败，不能带着不可用的 Context 并发锁进入服务状态；离线测试必须使用替身，
除非用户明确提供安全的测试实例。

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
`failed`；切块和向量索引服务已经分别接入 `chunking/chunked` 与 `indexing/indexed`
中间状态，并在外部耗时工作前后使用独立短事务。

修改状态逻辑时必须使用 `DocumentStatus`，并同步检查各服务的准入条件和响应模型，
不要把“枚举中已定义”误认为“业务流程已接入”。

子块向量状态目前使用字符串：`pending`、`indexing`、`indexed`、`failed`。

## 数据库与事务边界

- SQLAlchemy engine/session/Base：`app/db/session.py`
- ORM 模型：`app/models/`
- Repository：`app/repositories/`
- Unit of Work：`app/db/uow/`
- Alembic 当前迁移头：`d4f8a1c7e2b9`

Repository 原则：

- 可以 `add()`、`flush()`、查询和修改实体。
- 不应自行 `commit()` 或 `rollback()`。
- 业务事务由 Service 或 Unit of Work 管理。

当前主要文档 Service 和 Context Service 已通过 `SQLAlchemyUnitOfWork` 管理事务。
Service 可以调用 `uow.commit()` / `uow.rollback()`，但不应绕过 UoW 直接提交其
内部 Session。修改 UoW 或 Repository 契约时必须同步检查所有调用方。

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

Context Agent 启用时还需要：

- `DEEPSEEK_API_KEY`

可覆盖配置包括 Qdrant、DashScope endpoint/model、Embedding 维度与批量大小、
Docling 地址/超时/输出格式、DeepSeek endpoint/model/超时/重试次数、Redis URL、
Redis socket 超时、Context 路由锁超时、热资源队列容量和日志目录。Redis URL 可能
包含凭据，不得输出或写入日志。

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
- OpenAI Agents SDK 与 OpenAI 异步客户端（用于 DeepSeek Context Agent）
- qdrant-client
- redis-py 异步客户端（Conversation 路由锁与 Context 热资源队列共享）

运行时还需要可访问的 MySQL、Qdrant、DashScope 和 Docling 服务；启用 Context
路由时还需要 DeepSeek 和 Redis。安装依赖、修改依赖清单或访问外部服务前，先说明
影响并取得确认。

## 观测日志

`core/observability/` 将上传、处理、切块和索引事件按日期追加为 JSONL。日志用于
诊断和审计，但不得记录密钥、数据库连接串、完整认证头或其他敏感值。

当前已实现上传、处理、切块和索引日志组件；尚未提供 retrieval 流程，不要因为
日志目录配置存在就声称检索事件已经实现。

## 容易遗漏的约束

- `app/main.py` 导入 `app.models` 是为了确保 ORM 表注册完整。
- `QdrantVectorStore.ensure_collection()` 只创建不存在的 collection，不迁移已有 collection schema；补偿删除按稳定 Point ID 执行。
- 修改 Embedding 模型或维度前，必须评估 Qdrant collection 重建/迁移。
- Markdown 标题本身没有正文时不会生成可检索父块。
- `embedding_text` 会加入章节路径，但父块正文仍保留清洗后的原始内容。
- 文档查重范围是单个知识库，不是全局。
- Content hash 基于完整落盘后的文件字节计算。
- `created_by_actor_code` 当前在 API 层使用固定默认值，尚未接入真实认证主体。
- 当前没有检索 API，也没有 Qdrant search 封装。
- Context Agent 的 `reason_summary` 只能说明路由依据，不能包含业务计划或执行建议。
- Context 完成回写不得扩张已保存路由决定的目标链范围。
- 读取、压缩或缓存刷新不得更新 Context Chain 的 `last_active_at`。
- Redis 热队列只保存资源引用和简短描述，不能写入完整文档、完整结果或完整 Task。
- 资源再次使用必须刷新到队尾；从 Redis 推出不等于从 MySQL 删除。

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
- 修改 Context 路由规则时同步检查 Prompt、Schema、确定性校验、完成回写和离线测试。
- 修改 Context 资源逻辑时同步检查事件历史、当前状态、`resource_version`、Lua 队列、
  数据库提交后刷新、版本预热和缓存失败补偿。
- 修改 Context 并发逻辑时保留 Conversation 级串行语义；Redis 客户端只能由 FastAPI
  lifespan 创建和关闭，Repository 与 Service 不得自行创建连接。
- 安装依赖、修改配置/锁文件、删除或移动文件、联网、部署、提交或推送前，说明影响并取得确认。
- Code review 先按严重程度报告具体问题和文件行号；除非明确要求，否则不修改代码。

## 交付验证

至少执行：

```powershell
uv run --frozen python -m compileall -q app core main_config main_utils alembic
git diff --check
```

在项目依赖环境可用时，按改动范围运行针对性 `unittest`；涉及多个子系统或交付前
再运行：

```powershell
uv run --frozen python -m unittest discover -s tests -v
```

`tests/test_document_lifecycle_migration_mysql.py` 只有在显式提供
`TEST_MYSQL_DATABASE_URL` 时才运行，并要求指向名称以 `_test` 结尾的空测试库。
不要为了验证连接真实生产数据库、Qdrant、DashScope、Docling、DeepSeek 或 Redis。
