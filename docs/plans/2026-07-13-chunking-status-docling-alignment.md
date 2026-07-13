# 复杂文档切块、状态与 Docling 配置对齐

## 目标

使外部转换后的复杂文档按 Markdown 切块，统一新建文档状态为 `uploaded`，并让 Docling 客户端采用配置的转换端点和超时时间。

## 范围

- 修改切块服务、状态常量、文档默认值、处理服务、Docling 配置与客户端。
- 不修改数据库内现有 `draft` 记录，不执行数据库迁移，也不调整 Artifact 复用策略。

## 验证

1. `get_expected_process_output_type()` 将 `pdf`、`docx`、`pptx` 映射为 `md`，本地 `txt` 保持不变。
2. 源代码不再写入或接受 `draft` 状态；新增文档默认状态为 `uploaded`。
3. `DoclingClient()` 的默认超时和转换地址与应用配置一致。
4. 执行模块编译、定向断言和 `git diff --check`。
