# AJ3Q Knowledge Admin API

## 项目定位

本项目是知识库文档入库、向量索引与 Conversation Context 路由服务。当前提供：

- 文档上传、处理、父子切块、Embedding 和 Qdrant 入库。
- Context Chain 路由、Turn 完成回写与 Redis 热资源队列。
- 面向用户的 Conversation Message 接口；用户只提交消息，Chain、Turn 和资源队列由后端加载。

当前不提供检索、召回、重排或最终问答 API。

## 模块化单体结构

```text
app/
├── main.py
├── api/router.py
├── bootstrap/
│   ├── app_factory.py
│   ├── container.py
│   └── lifespan.py
├── config/
│   ├── environment.py
│   └── settings.py
├── shared/
│   ├── time.py
│   └── observability/
├── infrastructure/
│   ├── database/
│   ├── llm/deepseek/
│   └── redis/
└── modules/
    ├── context/
    │   ├── presentation/
    │   ├── application/
    │   ├── domain/
    │   └── infrastructure/
    └── document/
        ├── presentation/
        ├── application/
        ├── domain/
        └── infrastructure/
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

| 方法 | 路径 | 作用 |
|---|---|---|
| POST | `/api/admin/documents/upload` | 上传原件并创建文档 |
| POST | `/api/admin/documents/{document_id}/process` | 转换或清洗文档 |
| POST | `/api/admin/documents/{document_id}/build-chunks` | 构建父块和子块 |
| POST | `/api/admin/documents/{document_id}/index-vectors` | 生成并写入向量 |
| POST | `/api/conversations/{conversation_id}/messages` | 发送用户消息并执行 Context 路由 |
| POST | `/api/context/route` | 兼容路由接口，已标记 deprecated |
| POST | `/api/context/turns/{turn_id}/complete` | 完成 Turn 并关联目标 Chain |

Conversation Message 请求只包含：

```json
{
  "message": "继续完善之前的文档处理日志方案"
}
```

`ContextAgentInput` 是后端内部契约，不能由前端构造。

## 配置与运行

配置入口是 `app/config/settings.py`。真实数据库密码、API Key、Redis 凭据等只应由
进程环境或被 Git 忽略的项目根目录 `.env` 提供。

```bash
uv run --frozen alembic upgrade head
uv run --frozen uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

应用启动时会创建并验证共享 Redis 客户端，装配 Context 与 Document 的具体
Infrastructure，并将统一容器写入 `app.state.container`。关闭时统一释放外部客户端。

## 验证

```bash
uv run --frozen python -m compileall -q app core main_config main_utils alembic
uv run --frozen python -m unittest discover -s tests -v
git diff --check
```

MySQL migration 集成测试只有在显式提供名称以 `_test` 结尾的空测试库
`TEST_MYSQL_DATABASE_URL` 时才运行。
