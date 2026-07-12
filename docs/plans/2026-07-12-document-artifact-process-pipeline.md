# Document Artifact 与复杂文件处理链路实施计划

## 目标

将 PDF、DOC、DOCX、PPT、PPTX 等复杂文件的处理流程统一为：原始文件 → Docling → `secondary_text` Markdown → `document_artifacts` → `MdProcessor` → cleaned Markdown。

## 已证实的问题

- `DocumentArtifactRepository` 在 `create()` 和 `mark_active_as_superseded()` 内部提交事务，不能原子处理产物替换和后续清洗。
- `ArtifactResult` 的统计字段类型错误，且创建人和时间字段不能映射 ORM 属性。
- Artifact ORM 与迁移对 `artifact_code` 长度和 `status` 默认值不一致。
- Factory 将外部类型直接交给未完成的 `ExternalMarkdownProcessor`；这绕过了 Artifact 生命周期。
- Process Service 依据原始扩展名生成 cleaned 文件，并直接返回内部异常文本。

## 实施顺序

1. 对齐 Artifact 契约：修改 `app/models/document_artifact.py`、`app/schemas/document_artifact.py` 和迁移定义，统一为长度 100、默认 `active`，并修正 Schema 属性名与统计字段类型。
   - 验证：模块编译；Schema 可以从 ORM 属性构造。
2. 将 `app/repositories/document_artifact_repository.py` 的提交改为 `flush()`，让服务层负责 `commit()` / `rollback()`。
   - 验证：仓储方法不出现 `commit()`；新实体在 flush 后具备主键。
3. 在 `app/services/document_source_prepare_service.py` 实现外部源文件准备：调用 Docling、写入 `SECONDARY_TEXT_STORAGE_DIR`、计算产物哈希、替换同类有效 Artifact、创建新 Artifact，并返回包含 Markdown 路径和 `source_type="md"` 的结果。
   - 验证：静态模拟可确认服务只在成功后由调用方提交；失败可回滚数据库变更并清理本次输出文件。
4. 收窄 `app/processors/factory.py` 为本地类型映射；Process Service 根据准备结果调用 `MdProcessor`，复杂文件的 cleaned 输出统一为 `.cleaned.md`。
   - 验证：PDF 等外部类型不再直接实例化 `ExternalMarkdownProcessor`；md 处理器接收到二级 Markdown 路径。
5. 统一外部处理类型、上传白名单和派生产物目录；为 Process Service 加入安全的服务端错误日志和泛化客户端错误。
   - 验证：PPT/PPTX 的策略与上传校验一致，`secondary_text` 与 `raw` 同级，异常响应不包含原始异常字符串。
6. 仅在明确确认后删除 `PdfProcessor` 与 `ExternalMarkdownProcessor`；执行数据库迁移和实际 Docling/MySQL 联调同样需单独确认。

## 验收

- Artifact 数据模型、Schema、迁移和 Repository 的事务语义一致。
- 复杂文件产生并登记二级 Markdown，再由 `MdProcessor` 处理。
- 不删除旧文件、不执行迁移、不调用外部服务。
- `py -m compileall app core main_config utils` 与 `git diff --check` 通过。
