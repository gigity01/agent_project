# AJ3Q Knowledge Admin API

## 项目定位

本项目是知识库文档入库、向量索引和 Conversation Agent 任务编排服务。当前提供：

- 文档上传、格式转换、清洗、父子切块、Embedding 和 Qdrant 入库。
- Planner 历史 Context Selection、Turn Attribution 完成回写及 Redis 热资源队列。
- 基于可验证事实、显式 Gap 前置判断的 Planner、Plan/Task DAG 持久化和澄清流程。
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
  ├─ Context Agent：为当前 Turn 选择 Planner 历史 Read Set
  ├─ Planner Evidence：最多三路并行收集只读事实
  ├─ GapHandler：按需补查、重试、澄清或判定必要事实不可获得
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
├── agents/                       # Planner、Collector、Gap、Clarification 与 Executor Agents
├── agent_runtime/                # Agent Tool 公共上下文、业务文档查询、Registry 与审计
├── bootstrap/                    # 应用工厂、容器和 lifespan 装配
├── config/                       # 环境变量与应用配置
├── infrastructure/              # 数据库、DeepSeek Provider、Redis 客户端
├── shared/observability/         # 文档、Context 与 Agent Tool JSONL 日志
└── modules/
    ├── context/                  # Context Selection、Attribution、Chain 与资源队列
    ├── conversation/             # 面向用户的消息编排与状态查询
    ├── document/                 # 文档入库、处理、切块和索引
    ├── planning/                 # Plan/Task/DAG 与 Planner Tools
    ├── task_runtime/             # Task 领取、执行、完成、失败和 Executor
    ├── messaging/                # Outbox/Inbox、Redis Streams 与事件分派
    ├── clarification/            # 澄清请求及回答关联
    ├── aggregation/              # Plan 结果聚合与 Turn 完成
    └── operations/               # 运行日志查询与 Agent Tools

business_docs/                    # GapHandler 按需查询的业务规则与 Service Map
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
| POST | `/api/conversations/{conversation_id}/messages` | Context Selection 并运行 Planner |
| GET | `/api/conversations/{conversation_id}/turns/{turn_id}` | 查询 Turn、最新 Plan 和任务状态 |
| POST | `/api/context/route` | 兼容 Context Selection 接口，已标记 deprecated |
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
Conversation Message 响应通过 `context_selection` 返回 `selection_mode`、
`relevant_chain_ids` 和 `reason_summary`；Selection 阶段不会返回或预分配新 Chain。
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

### 1. Context Selection

一次完整输入只创建一个 `ConversationTurn`。Context Agent 选择的是 Planner 为正确
理解当前请求所需的历史 Context Read Set，而不是当前 Turn 的最终 Chain 归属。它可
返回 0、1 或多条已有 Chain，不创建 Chain、不拆分任务、不选择 Executor，也不生成
业务回答；系统按数量派生 `no_context`、`single_context` 或 `multi_context`。没有历史
Chain 时直接持久化空集合，不调用 Context LLM，也不存在强制选择最新链的 fallback。

Selection 输入把 `current_user_input` 与当前 Conversation 的全部未归档历史 Chain
分开。每条 Chain 忠实保留 Turn 的 `user_input`、`assistant_content`、
`assistant_compact`、`task_result_summary`、Node relations 和 ResourceQueue；刚创建的
当前 Turn 没有 Node，因此不会混入 historical context。经确定性校验后，Read Set 写入
`context_selection_records`，Turn 从 `routing` 进入 `context_ready`。该事务不创建
Chain 或 Node。

Planner 仅凭 `turn_id` 重新加载持久化 Selection，并接收
`PlannerContextInput(current_user_input, context_chains)`。其 Context Tools 把 Read Set
作为硬权限边界：只能读取当前 Turn，以及 Read Set 中 Chain 引用的历史 Turn、Node 和
资源；宽泛 list 查询会被改写到允许范围，越权 ID 会被拒绝，不能重新枚举整个
Conversation。

Context Agent 的常驻 Prompt 包含短 Service Map，用于理解 Document Processing、Context
Management 和 Operations 三类业务语境。Service Map 不改变 Selection Schema，也不
授予 Tool 权限或扩大历史 Read Set。

同一 Conversation 的 Selection 和完成写回都使用 Redis 短锁串行化；MySQL 保存完整
事实，Redis 保存有版本的热资源队列。

### 2. Planner 与澄清

Planner 主链使用物理隔离的 Evidence、GapHandler 和 Commit Agent。Evidence Agent
只能看到 Document、Context、Operations 三个独立的只读 Collector Agent-as-Tool，开启
`parallel_tool_calls` 且 `max_function_tool_concurrency=3`，因此最多三路并行取证；
每个 Collector 内部保持串行。Evidence Prompt 要求已充分验证的事实不得重复调查，当前
规划所需但仍未知的事实必须明确成为 gap；gap 只陈述未知，不决定后续动作。

Collector LLM 的结构化输出只包含 `summary` 和 `gaps`；Runtime 从 nested Run 的
`new_items` 按 `call_id` 配对实际 Tool Call 与 Tool Output，每次调用生成一个
`EvidenceItem`。其中 `arguments` 保存实际查询条件，`payload` 保存公共执行 envelope
之外的业务结果；Runtime 再确定性组合为 `CollectorResult`。顶层 Evidence Run 还会
按 `call_id` 配对三个 Collector Agent-as-Tool 的结果并核对 `collector_code`。缺少调用
边界、非法 arguments/envelope、重复 `call_id`、来源不一致或非法输出都会 fail closed。

`CollectorResult.resource_refs` 是 EvidenceItem 引用的稳定去重并集，只表示调查涉及相应
资源，不证明资源存在或状态正常。业务结论必须以 `evidence_items` 的 `arguments` 和
`payload` 为主要依据；`summary` 和 `gaps` 只能辅助解释。Tool succeeded 但业务对象
不存在仍是有效 Evidence。空 `evidence_items` 不代表任何状态已验证，当前也不持久化
Evidence Graph。

第一轮至少包含一个 succeeded EvidenceItem，且不存在 rejected/failed EvidenceItem 或
gap 时，才直接进入 Commit。Evidence 为空、只有失败/拒绝结果或存在 gap 时运行
GapHandler；这样纯 Capability 请求仍可由 GapHandler 放行给 Commit 判断 unsupported，
依赖业务状态的请求则不能用空 Evidence 绕过前置判断。GapHandler 只看到
`search_business_docs`、`list_evidence_tools` 和
`find_evidence_tools`：

- `business_docs/*.md` 描述业务规则、前置事实、推荐查询路径和明确能力边界，不是运行时
  业务事实，也不使用向量数据库。常驻短 Service Map 使用代码内稳定文本，避免 Markdown
  缺失阻断模块导入；详细查询按需读取该目录，部署时必须与应用源码一并保留，缺失时本轮
  Planning fail closed。
- Tool Registry 每次动态投影 Document、Context、Operations 现有 Collector Catalog 的
  `ToolDescriptor`，不是第二份注册表；Business Docs 与 Registry 冲突时以后者为准。
- Registry 只证明 Tool 已注册，真正查询仍受 `AgentToolContext` 的权限和 selected
  Context Read Set 限制。

`GapDecision` 只有 `COMMIT`、`COLLECT_MORE`、`RETRY`、`CLARIFICATION` 和
`UNSUPPORTED` 五种动作。`COLLECT_MORE` 必须携带定向 `follow_up`，Runner 把第一轮完整
历史和 follow-up 一并交给第二轮 Evidence；第二轮仍经过 GapHandler，但运行时禁止再次
返回 `COLLECT_MORE`，因此最多补查一次。`RETRY` 必须有 `outcome=failed` 且
`retryable=true` 的 Evidence 支持，并通过明确控制信号交给 Planning Application 复用
`retry_pending` 和 Replan Outbox。非重试失败不能伪装成 RETRY；非法决策按 Planner
系统失败收敛。

GapHandler 的 `CLARIFICATION` 复用现有 `MarkPlanNeedsClarificationInput`、Clarification
Request 和 Clarification Agent；Commit 的 `clarification_handoff` 仍保留，用于创建
Task 时才暴露的用户意图或必要参数歧义。GapHandler 的 `UNSUPPORTED` 表示系统无法取得
当前规划必需事实；Commit 的 `mark_plan_unsupported` 表示系统没有执行用户动作的
Capability，两者语义分离。

Commit Agent 物理上仍只看到 Planning Tools 和 Clarification Handoff，关闭
`parallel_tool_calls` 且 `max_function_tool_concurrency=1`。它以前置 Gap 层已确认
Evidence 足够为默认前提，只负责基于 Evidence 创建 Task、发布 Plan，或处理执行
Capability 本身不支持和 Task 参数歧义。Collector、Gap 查询 Tool 与 Planning Tool
不会暴露在同一个 Run 中。

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

UseCase 负责局部执行正确性，Task Runtime 负责 Operation 失败生命周期，Compensator
负责持久化业务副作用恢复。claim 提交前，UseCase 可以回滚事务并清理不属于 Operation
的局部临时资源；claim 提交后，UseCase 失败只记录诊断并抛出错误，必须保留 Document
状态、`active_operation_id`、operation-scoped 文件、Chunk 状态和 Qdrant Point，由
Runtime 先持久化 `compensation_required`，再驱动幂等且 operation-fenced 的
Compensator 恢复。

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

Document Executor 的 timeout 是“到达截止时间后请求取消，等待副作用执行静默，再进入
补偿”，不是强制终止同步线程。deterministic Executor 会排空其 `to_thread` UseCase，
Agent Executor 会排空内部 Agent/Command Tool Run，然后才把取消传播给 Runtime；因此
不可中断的同步调用会使 `execute_next` 的实际返回时间超过 Capability timeout，但
Compensator 不会与同一进程中仍可写入副作用的旧执行并发。

三个 Document Capability 均在 Capability Registry 中声明对应的 Compensator。普通
Executor 失败和过期执行恢复使用同一个补偿执行入口：数据库先把 `TaskExecution` 标记为
`compensation_required` 并持久化 error、`retryable` 与 `blocked` disposition；每次真正
准备调用 Compensator 前，Runtime 先递增 `compensation_attempt_count`、更新
`compensation_last_attempt_at` 并提交，再在事务外执行文件系统或 Qdrant 补偿；成功后
以新事务标记 `compensated`，清除 Plan 当前 Task，再安排 retry 或请求 Replan。普通可
重试错误继续使用 `retry_wait` 和默认 30 秒延迟；lease 过期恢复直接回到 `pending`。

`TaskExecution.compensation_attempt_count` 表示 Compensator 调用尝试次数，包括首次成功
调用，而不是补偿失败次数。只有调用失败才更新 `compensation_last_error`；后续补偿成功
保留既往错误，便于识别经历故障后恢复成功的执行。自动补偿默认最多执行 5 次，未达
上限时保留原 Task、`compensation_required` 状态和 Document ownership，并在 Outbox 中
可靠写入新的 `runtime.plan_wakeup`：第 1、2、3 次调用失败后分别从 30、60、120 秒继续
指数退避，最大延迟 300 秒。
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

Context Read Set 与最终 Turn Attribution Write Set 是两个独立事实。完成方通过
`TurnAttribution(existing_chain_ids, create_new_chain, new_chain_id)` 指定最终目标，
Attribution 可与 Selection 不同。Context Service 在一个事务内锁定 Turn 与 Selection、
校验并锁定已有目标 Chain、必要时创建新 Chain、创建带最终 Task/Resource relations 的
Node、更新资源和 `last_active_at`，最后把 Turn 推进到 `completed`。任何一步失败都会
回滚整个完成事务；Selection 阶段不再创建 placeholder Node。每个 `completed` Turn
必须至少关联一条 Chain，空 Attribution 会自动创建新 Chain。

当前成功 Aggregation、unsupported 和 clarification 使用同一确定性后备策略：Read Set
非空时把 Turn 归入其全部 Chain；Read Set 为空时创建新 Chain。Aggregation 会在调用
完成事务前预分配新 Chain ID，以便新 Chain 的 Node 与 Task 资源关系一次提交。更精细
的成功执行 Attribution 生产者尚未拆成额外 LLM Agent。

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
  事实。claim 后失败时 UseCase 保留 staging 与可能只完成部分提升的正式目录；Runtime
  驱动的补偿按当前 owner 清理三类 operation-scoped 目录，全部清理成功后才释放
  ownership。Process 的文件生成/提升与补偿清理还共用
  `document:process:{document_id}` MySQL named-lock 围栏；另一个 Worker 发现 execution
  过期时可以先持久化失败，但必须等旧执行退出文件副作用区后才能清理和释放 ownership。
  如果补偿无法取得围栏，则按补偿失败重试并保留 ownership。
- 文本与 Markdown 按语义父块和长度子块切分；CSV 一条记录对应一个子块。
- Embedding 使用 DashScope OpenAI-compatible API，向量以 ChildChunk ID 幂等
  upsert 到 Qdrant；Point payload 同时保存本次 `operation_id` 作为外部归属事实。
- Chunk finalize 的父子块替换保持单一数据库事务；失败时事务回滚并保留
  `chunking` ownership，Runtime 驱动的补偿只负责将文档标记为 `failed` 并释放 token。
- Index 的每批 Qdrant upsert 都先获取文档级 MySQL named lock，并在锁内复核
  `active_operation_id`；UseCase 失败时保留 `indexing` Chunk 和 token，内存中的
  confirmed/uncertain Point ID 只进入诊断日志。Runtime 驱动的 Compensator 从数据库
  当前 `indexing` Chunk 的稳定 ID 独立推导待删 Point，先把 Document 标记为 `failed`
  但保留 token，再使用同一围栏删除 Point；删除成功后才把 Chunk 标记为 `failed` 并
  释放 ownership。围栏获取最多等待 30 秒，失败时进入上述补偿重试。这样
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

`logs/context/` 按日期保存 Context JSONL 事件，可聚合 Selection LLM/总耗时、候选与
选中 Chain 数、空/多 Chain 选择、非法输出/重试，以及 Conversation 锁等待、持有和
过期字段。观测写入尽力而为，不反向阻断业务，也不记录输入正文、密钥或连接串。

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
`f4a7c9e2b6d8`。该迁移把 `context_route_decisions` 正式改为
`context_selection_records`，迁移 `routed` Turn 状态，并清理未完成 Turn 的旧
placeholder Node 和无正式事实的预建空 Chain。由于新的 Read Set 与 Attribution
Write Set 无法无损还原为旧路由记录，该语义迁移的 downgrade 会 fail closed；回退
旧应用前必须恢复升级前的数据库备份。

## 验证

```bash
uv run --frozen python -m compileall -q app alembic
uv run --frozen python -m unittest discover -s tests -v
git diff --check
```

`tests/` 按应用模块和横切职责组织为可递归发现的 Python package；测试文件仍保持
`test_*.py` 命名，因此上述统一 discovery 命令不变。

`tests/document/test_document_lifecycle_migration_mysql.py` 只有在显式提供名称以 `_test` 结尾的
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
