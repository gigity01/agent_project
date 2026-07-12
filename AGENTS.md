# AGENTS.md — agent-knowledge

## 项目简介

RAG 知识库管理系统。处理流程：读取文件 → 标准化 → 结构检测 → 父子分块 → Chroma 向量库 + BM25 混合检索。

## 入口

- `main.py` — FastAPI 服务：`POST /api/agent` 调用 `kb_agent.run()`
- `facade/file_process_facade.py` — 主 API：`process_file()`、`process_and_split()`、`process_and_store()`、`query()`
- `KBagent/kb_agent.py` — Agent 编排器：意图解析 → 校验 → 工具调度

## 架构（分层，依赖方向）

```
main.py → KBagent/ → facade/ → processors/（工厂 + 策略） → utils/（标准化/检测/分块） → core/（单例、日志、配置、向量库）
api/（空 — 未来占位）
```

## 依赖（无清单文件）

手动安装。所需包：
- chromadb、langchain-chroma、langchain-community、langchain-text-splitters
- dashscope（通义千问 embedding API）
- sentence-transformers、rank-bm25
- pandas、pypdf、unstructured

不存在 `requirements.txt`、`pyproject.toml` 或 `setup.py`。

## 命令

| 操作 | 命令 |
|---|---|
| 运行 | `python main.py` |
| 测试 / lint / typecheck | 均不存在 |

## Agent 容易遗漏的结构性坑点

- **所有处理器输出的都是 `.txt` 文件**，无论输入格式是什么。详见各 processor 中的 `save_cleaned_file(content, ".txt")`。
- **输入文件必须在 `uploads/` 目录下** — `is_safe_file_path()` 通过 `os.path.abspath` 前缀检查 `UPLOADS_DIR`。目录外的文件会被拒绝。
- **向量库存储在 `./chroma_db`**（见 `config/settings.py` 的 `VECTOR_DB_PATH` 和 `core/vector_store.py:38`）。
- **`config/settings.py` 使用 `Path(__file__).parent.parent.absolute()`** 获取 `BASE_DIR`，基准目录固定为项目根。
- **`core/logger.py` 使用 `os.getcwd()`** 获取 `LOG_DIR`，与 `settings.py` 的 `__file__` 方式不一致。运行位置影响日志路径。
- **存在三种不同的单例实现**：
  - `core/singleton.py` — `@singleton` 装饰器（用于 `MdProcessor`、`HierarchicalChunker`、`TextNormalizer`、`StructureDetector`）
  - `facade/file_process_facade.py` 使用 `__new__` 模式
  - `core/vector_store.py` 使用 `__new__` 模式
  - `core/metadata_manager.py` 使用 `__new__` 模式
- **PDF 处理器的文档注释说明它是占位符**："这里只是简单处理，本项目中不会如此处理pdf文件"。真实流程计划先用 `marker` 工具将 PDF 转成 MD 再处理。
- **`api/` 目录存在但没有任何文件** — 未来占位，尚未接入。
- **所有注释和设计文档都是中文**（`ZDoucument/V1/` 中有架构文档）。
- **`KBagent/validator.py` 使用内存状态机**（`self.user_state`、`self.pending_task`），重启丢失。生产环境需替换为 Redis。
- **`ingest` intent 在 validator 中跳过元数据检查** — 查重逻辑在 `WriteTools.ingest_file()` 工具层处理。
- **`restore` intent 在 validator 中匹配非 active 状态文件**（包括 deleted/replaced）。
- **`WriteTools.soft_delete_file()` 和 `restore_file()` 先通过 `metadata_manager.fuzzy_match()` 解析 `file_path`，再传给 `vector_store`。**

## 处理流水线（按顺序）

1. `ProcessorFactory.get_processor()` — 根据扩展名映射到单例处理器实例
2. Processor: `read()` → `is_safe_file_path()` 安全检查
3. 清洗链：`normalizer.clean()` → `clean_text()` → `deduplicate_lines()`
4. `save_cleaned_file()` → 写入 `cleaned_files/`，保存为 `.txt`
5. （可选完整流水线）`StructureDetector.extract_markdown_structure()` → `HierarchicalChunker.build_chunks()` → `VectorStore.add_hierarchical_chunks()`
6. 搜索：`VectorStore.hybrid_search()` — 当前为纯向量检索（BM25 尚未实现）

## 无测试、CI 或 lint

- 仓库中没有任何测试
- 没有 CI 工作流
- 没有配置格式化工具、linter 或 typechecker
- 项目根目录没有 `.gitignore`（只有 `.idea/.gitignore`）
