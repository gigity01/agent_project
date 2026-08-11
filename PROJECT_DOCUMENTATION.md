# AJ3Q Knowledge Admin API

## 项目定位

本项目是知识库文档入库、向量索引和 Conversation Agent 任务编排服务。当前提供：

- 文档上传、格式转换、清洗、父子切块、Embedding 和 Qdrant 入库。
- Context Chain 路由、Turn 完成回写及 Redis 热资源队列。
- 基于可验证事实的 Planner、Plan/Task DAG 持久化和澄清流程。
- 独立 Task Runtime Worker、可靠事件投递、失败重试和 Replan。
- Task 全部成功后的确定性结果聚合及 Context Turn 回写。

当前 Planner 只支持已有文档的 `process_document`、
`build_document_chunks` 和 `index_document_vectors` 三种能力。项目仍不提供检索、
召回、重排或通用问答 API；任务聚合结果是执行事实摘要，不是 RAG 问答结果。

## 运行架构

服务由两个进程共同完成异步任务闭环：

```text
Client
  │ POST /api/conversations/{conversation_id}/messages
  ▼
FastAPI
  ├─ Context Agent：路由完整用户输入并创建唯一 Turn
  ├─ Planner Evidence：最多三路并行收集只读事实
  ├─ Planner Commit：串行创建 Task、发布 Plan 或澄清
  ├─ MySQL：原子发布 Plan、Task DAG 和 Outbox Event
  └─ 返回 processing / needs_clarification / unsupported / ...
                         │
                         ▼
Runtime Worker
  ├─ Outbox Publisher → Redis Stream
  ├─ Event Consumer → Task Runtime / Replan / Aggregation
  ├─ Capability-scoped Document Executor Agent → 唯一 Command Tool → Use Case
  └─ 聚合结果并完成 Context Turn
                         │
                         ▼
Client 轮询 GET /api/conversations/{conversation_id}/turns/{turn_id}
```

FastAPI lifespan 和独立 Worker 分别创建自己的应用容器与外部客户端。FastAPI 不在
Web 进程内启动后台消费循环；只启动 API 而不启动 Worker 时，已发布的异步 Plan 会
停留在待执行状态。

## 模块化单体结构

```text
app/
├── main.py
├── api/router.py
├── workers/runtime_main.py       # 独立 Runtime Worker 入口
├── agents/                       # Planner、Collector、Clarification 与 Executor Agents
├── agent_runtime/                # Agent Tool 公共上下文、策略与审计
├── bootstrap/                    # 应用工厂、容器和 lifespan 装配
├── config/                       # 环境变量与应用配置
├── infrastructure/              # 数据库、DeepSeek Provider、Redis 客户端
├── shared/observability/         # 文档生命周期与 Agent Tool JSONL 日志
└── modules/
    ├── context/                  # Context 路由、Chain、Turn 与资源队列
    ├── conversation/             # 面向用户的消息编排与状态查询
    ├── document/                 # 文档入库、处理、切块和索引
    ├── planning/                 # Plan/Task/DAG 与 Planner Tools
    ├── task_runtime/             # Task 领取、执行、完成、失败和 Executor
    ├── messaging/                # Outbox/Inbox、Redis Streams 与事件分派
    ├── clarification/            # 澄清请求及回答关联
    ├── aggregation/              # Plan 结果聚合与 Turn 完成
    └── operations/               # 运行日志查询与 Agent Tools
```

固定依赖方向：

```text
Presentation → Application → Domain
Infrastructure → Application Port / Domain
Bootstrap → 具体对象装配
```

`tests/architecture/test_import_boundaries.py` 使用 Python AST 检查 Domain、
Application、Presentation 和跨模块 Infrastructure 的导入边界。

## HTTP API

### 核心写入与状态接口

| 方法 | 路径 | 作用 |
|---|---|---|
| POST | `/api/admin/documents/upload` | 上传原件并创建文档 |
| POST | `/api/admin/documents/{document_id}/process` | 转换或清洗文档 |
| POST | `/api/admin/documents/{document_id}/build-chunks` | 构建父块和子块 |
| POST | `/api/admin/documents/{document_id}/index-vectors` | 生成并写入向量 |
| POST | `/api/conversations/{conversation_id}/messages` | Context 路由并运行 Planner |
| GET | `/api/conversations/{conversation_id}/turns/{turn_id}` | 查询 Turn、最新 Plan 和任务状态 |
| POST | `/api/context/route` | 兼容 Context 路由接口，已标记 deprecated |
| POST | `/api/context/turns/{turn_id}/complete` | 兼容下游手工完成 Turn 接口 |

Document 模块还提供文档、产物、父块、子块、流水线状态与知识库统计等只读接口。
OpenAPI 文档由运行中的 FastAPI 提供。

### Conversation Message

请求只包含完整用户输入：

```json
{
  "message": "处理文档 42，然后切块并建立向量索引"
}
```

`ContextAgentInput`、Chain、Plan、Task 和资源队列均为后端内部契约，不由前端构造。
响应中的主要状态如下：

| 状态 | HTTP | 含义 |
|---|---:|---|
| `processing` | 202 | Plan 已发布，等待 Worker 执行 |
| `retry_pending` | 202 | Planner 或澄清后的 Replan 等待异步重试 |
| `needs_clarification` | 200 | 需要用户补充信息，问题位于 `assistant_message` |
| `unsupported` | 200 | 当前 Capability 无法支持请求 |
| `failed` | 200 | 本轮规划失败，未形成可执行 Plan |

异步执行完成后，通过 Turn 状态接口读取 `turn_status`、最新 `plan_status`、
`revision`、`task_ids` 和最终 `assistant_message`。

## Conversation 任务闭环

### 1. Context 路由

一次完整输入只创建一个 `ConversationTurn`。Context Agent 只判断输入与哪些历史
Context Chain 相关，不拆分任务、不选择 Executor，也不生成业务回答。同一
Conversation 的路由使用 Redis 短锁串行化；MySQL 保存完整事实，Redis 保存有版本的
热资源队列。

### 2. Planner 与澄清

Planner 是一个逻辑 Agent，但使用两个物理隔离的执行阶段。Evidence Agent 只能看到
Document、Context、Operations 三个独立的只读 Collector Agent-as-Tool，开启
`parallel_tool_calls` 且 `max_function_tool_concurrency=3`，因此最多三路并行取证；
每个 Collector 内部保持串行，并通过统一 extractor 返回由 `collector_code`、
`summary`、`facts`、`resource_refs` 和 `gaps` 组成的稳定 JSON
`CollectorResult`。Evidence Run 的完整 Tool Call/Output 历史通过
`RunResult.to_input_list()` 交给 Commit Agent。

Commit Agent 物理上只看到 Planning Tools 和 Clarification Handoff，关闭
`parallel_tool_calls` 且 `max_function_tool_concurrency=1`，只能串行创建 Task、
发布 Plan、标记不支持或生成澄清问题。Collector 与 Planning Tool 不会出现在同一个
Run 中，因此两类操作的隔离由代码保证，而不是仅依赖 Prompt。

- 每个 Plan 必须包含 1～10 个 Task。
- `sequence` 必须从 1 开始连续且唯一。
- 依赖通过 `task_ref` 表达，发布时校验 DAG；最大深度为 3。
- 当前 Capability 只有文档处理、文档切块和向量索引。
- Plan、Task、依赖边、Turn 状态和首个 Outbox Event 在同一数据库事务中发布。

若存在未回答的澄清请求，下一条用户消息会被关联为回答，并通过 Outbox 请求新的
Plan revision。澄清请求在新 Plan 成功聚合后变为 `resolved`。

### 3. 可靠消息与 Task Runtime

独立 Worker 同时运行 Outbox 发布循环和 Redis Stream 消费循环：

- Outbox Event 最多发布 10 次，耗尽后标记为 `dead_letter`。
- Redis Consumer Group 使用唯一 consumer name，并接管超时未 ACK 的消息。
- Inbox 记录抑制已完成事件的重复消费；处理失败的 Stream 消息不 ACK。
- 同一 Plan 同时只执行一个 Task；只有依赖均成功的 Task 才能领取。
- Claim、事务外 Executor 调用、Completion/Failure 使用三个独立阶段。
- 每次执行保存稳定的 `execution_id`、`operation_id`、`agent_run_id`、attempt 和
  输入快照；这些字段贯穿 Agent Tool 审计与文档阶段日志。
- `operation_id` 同时是 Document 执行 ownership token：处理、切块和索引 claim 会
  写入 `documents.active_operation_id`，finalize 和补偿只有在 token 相同时才能推进或
  释放状态。

每个 Task 仍对应一个固定 Capability。启用 DeepSeek Provider 时，Runtime 通过通用
`AgentTaskExecutor` 调用三个 capability-scoped Document Executor Agent：每个 Agent
只能看到 `get_document`、流水线/切块状态等受限查询 Tool，以及当前 Capability 的
唯一 Command Tool。Executor 内部关闭并行 Tool Call，允许在命令前多次查询；调用
`process_document`、`build_document_chunks` 或 `index_document_vectors` 后由
`StopAtTools` 立即结束 Run。Command Tool 不再二次请求 SDK approval，因为已领取的
固定 Capability Task 就是授权边界；Command 的 `document_id` 还必须等于 Task Payload
中的资源范围。

Task 成败只由 Use Case 返回的结构化 Command Tool Output 和确定性 adapter 决定：
`succeeded` 映射为 Task Output，`rejected` 映射为 blocked，`failed` 保留
`retryable`；LLM 文本不能成为 Task Result。未配置 DeepSeek Provider 时保留明确命名
的 deterministic Executor 作为现有非 Agent 启动路径的后备，Task/Plan 模型、
Capability Registry、claim/complete/fail、重试和 Replan 状态机均不变。

三种内置 Capability 的最大尝试次数均为 3；处理与切块超时为 300 秒，向量索引超时
为 900 秒。可重试错误默认延迟 30 秒后再次唤醒。不可重试、阻塞或尝试耗尽时请求
Replan；同一 workflow 最多保留 3 个 revision，旧 Plan 和未完成 Task 会被标记为
`superseded`。

三个 Document Capability 均在 Capability Registry 中声明对应的 Compensator。普通
Executor 失败和过期执行恢复使用同一套三阶段管线：数据库先把 `TaskExecution` 标记为
`compensation_required` 并持久化 error、`retryable` 与 `blocked` disposition，事务外
执行文件系统或 Qdrant 补偿，最后以新事务标记 `compensated`，清除 Plan 当前 Task，再
安排 retry 或请求 Replan。普通可重试错误继续使用 `retry_wait` 和默认 30 秒延迟；lease
过期恢复直接回到 `pending`。

补偿失败次数是 `TaskExecution.compensation_attempt_count` 的持久化事实；每次失败还会
更新 `compensation_last_error` 与 `compensation_last_attempt_at`。自动补偿默认最多执行
5 次，未达上限时保留原 Task、`compensation_required` 状态和 Document ownership，并在
Outbox 中可靠写入新的 `runtime.plan_wakeup`：从 30 秒开始指数退避，最大延迟 300 秒。
补偿消息的控制字段只携带目标 `execution_id` 与 `operation_id`，Runtime 从数据库读取
尝试次数，因此旧消息不能改写计数或误领后续 Task；原 Stream 消息可在重试事件持久化
后 ACK。

第五次自动补偿仍失败时，同一事务把 Execution 置为 `compensation_locked`，记录
`compensation_locked_at`、最后错误和 `retry_exhausted` 原因，不再发布自动补偿唤醒。
该状态表示补偿生命周期被冻结而非业务终止：Plan 当前 Task、运行中 Task、Operation
和 Document ownership 全部保留；后续 Plan 唤醒只返回锁定结果，不执行补偿、不创建新
Task attempt、不请求 Replan，也不释放 ownership，等待未来系统级运维恢复能力接管。

### 4. 聚合与完成

Plan 的全部 Task 成功后，Runtime 写入聚合事件。Aggregation 从数据库读取成功的
Task 与 TaskExecution，生成确定性执行摘要，收集去重后的资源引用，随后完成原始
Context Turn、建立 Chain Node 并刷新热资源队列。它不会调用检索或生成通用问答。

## 文档处理流水线

文档四个步骤仍可通过管理 API 独立调用，且必须按顺序执行：

```text
uploaded → processing → processed → chunking → chunked → indexing → indexed
                                  任一失败阶段 → failed
```

- `txt`、`md`、`csv` 使用本地 Processor；`pdf`、`doc`、`docx`、`ppt`、`pptx`
  先经 Docling 转为 Markdown。
- Process 先在 `storage/staging/{operation_id}/` 生成 secondary/cleaned 文件，再分别
  提升到 `storage/secondary_text/{operation_id}/` 和
  `storage/cleaned/{operation_id}/`；正式 URI 作为 Artifact 和 `cleaned_uri` 的持久化
  事实。失败补偿按当前 owner 同时清理 staging 与可能只完成部分提升的正式目录，全部
  清理成功后才释放 ownership。
- 文本与 Markdown 按语义父块和长度子块切分；CSV 一条记录对应一个子块。
- Embedding 使用 DashScope OpenAI-compatible API，向量以 ChildChunk ID 幂等
  upsert 到 Qdrant；Point payload 同时保存本次 `operation_id` 作为外部归属事实。
- Chunk finalize 的父子块替换保持单一数据库事务，补偿只释放 `chunking` ownership。
- Index 的每批 Qdrant upsert 都先获取文档级 MySQL named lock，并在锁内复核
  `active_operation_id`；补偿先把 Document 标记为 `failed` 但保留 token，再使用同一
  围栏删除当前 `indexing` Chunk 的稳定 Point ID，删除成功后才把 Chunk 标记为
  `failed` 并释放 ownership。围栏获取最多等待 30 秒，失败时进入上述补偿重试。这样
  已超时的旧线程即使稍后恢复，也不能在补偿完成或新 Operation 接管后再次 upsert。
  MySQL、文件系统和 Qdrant 仍不共享事务，因此系统继续采用 fail-closed 补偿，而不是
  假定跨存储已经一致。

## 配置与本地运行

配置入口是 `app/config/settings.py`，安全示例见 `.env.example`。必填配置：

- `SQLALCHEMY_DATABASE_URL`
- `DASHSCOPE_API_KEY`
- `DEEPSEEK_API_KEY`（使用 Context、Planner 或 Executor Agent 时）

运行时还需要可访问的 MySQL、Redis、Qdrant、DashScope；复杂办公格式需要 Docling，
Agent 链路需要 DeepSeek。Redis 在应用和 Worker 启动时都会执行 `PING`，不可用则启动
失败。

先执行数据库迁移：

```bash
uv run --frozen alembic upgrade head
```

分别启动 API 与 Worker：

```bash
# terminal 1
uv run --frozen uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# terminal 2
uv run --frozen python -m app.workers.runtime_main
```

存储路径是相对路径，应从项目根目录启动。当前 Alembic 迁移头为
`d8f2a4c6e9b1`。

## 验证

```bash
uv run --frozen python -m compileall -q app alembic
uv run --frozen python -m unittest discover -s tests -v
git diff --check
```

`tests/test_document_lifecycle_migration_mysql.py` 只有在显式提供名称以 `_test` 结尾的
空测试库 `TEST_MYSQL_DATABASE_URL` 时才运行。离线测试使用替身，不应为了验证连接
真实 MySQL、Redis、Qdrant、DashScope、Docling 或 DeepSeek。

## 文档维护约定

每个完整功能或重要更新都必须在同一交付中同步更新项目文档，无需额外提醒。

“完整功能”指已经形成可使用闭环的新能力或既有能力扩展，至少具备明确入口、主流程、
状态或结果、失败语义以及与风险相称的验证，不以代码量判断。

一次变更满足以下任一项，即为“重要更新”：

- 改变 HTTP API、命令、公开 Tool、事件 Schema 或其他外部契约。
- 改变模块、Agent、Worker、进程、消息流、同步/异步或事务边界。
- 改变状态机、数据库迁移、Redis/Qdrant/文件存储协议或一致性语义。
- 改变配置、依赖、外部服务、启动部署方式、安全或权限边界。
- 改变支持能力、关键限制、超时、重试、容量或文件类型。
- 改变规范开发、迁移、测试、构建、发布或恢复流程。
- 修复影响安全、数据完整性、生产可用性或下游决策的缺陷。

兜底标准是：只要改动会使本文件或 `AGENTS.md` 中的现有事实变得错误、不完整或容易
误解，就必须更新文档；无法确定时按重要更新处理。纯内部等价重构、排版、注释、非
公开命名或不改变已记录契约的局部修复，默认不属于重要更新，但命中上述任一条件时
仍必须更新。

触发后应同时检查本文件与 `AGENTS.md`，更新受影响章节并移除过时内容。文档维护的是
当前真实状态，不要求为每次改动追加流水账式 Changelog，也不能把计划能力写成已实现
能力。
