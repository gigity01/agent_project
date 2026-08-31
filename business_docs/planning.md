# Planning

## 当前执行能力

Planner 只能创建以下三种 Task：

- `process_document`
- `build_document_chunks`
- `index_document_vectors`

Commit Agent 负责根据已经充分的 Evidence 创建 Task、表达 DAG 并发布 Plan。它不能
补查业务事实，也不能把 Collector 的 `summary` 当作比 `evidence_items` 更高优先级的
事实。

## Gap 处理

- Gap 只陈述调查结束后仍未知的事实。
- 与当前请求无关的 Gap 不阻塞 Commit。
- 已有查询能力但 Evidence 未查或查得不够时，应定向补查。
- 查询路径正确但发生 `retryable=true` 的失败时，由 Planning Application 进入重试语义。
- 查询能力已注册、查询路径正确但发生 `retryable=false` 的系统失败时，应返回
  `SYSTEM_FAILURE`，由 Planning Application 的失败恢复机制处理。
- 只有用户语义无法唯一确定且业务查询不能替用户回答时，才要求用户澄清。
- 当前规划必需事实没有任何可用查询能力时，才是 Gap 层的 unsupported。

Gap 层的 unsupported 表示“系统无法取得必要事实”；Commit 层的 unsupported 表示
“系统没有执行用户要求动作的 Capability”。两者不能混淆。

Business Docs 说明系统应该如何工作，Tool Registry 说明当前代码真实注册了什么。
两者冲突时必须以 Tool Registry 为准，不得根据文档假装存在未注册能力。
