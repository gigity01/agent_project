"""应用全局配置包。

职责说明：
- `environment.py`: 提供从 `.env` 文件读取环境变量、安全校验必填/可选配置与类型转换的基础工具。
- `settings.py`: 定义服务运行所需的完整配置常量集合（文件存储、MySQL/Redis/Qdrant、DashScope Embedding、DeepSeek LLM、Docling 与 JSONL 日志路径）。
"""
