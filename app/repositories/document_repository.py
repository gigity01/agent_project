"""文档 ORM 模型的数据库访问封装。"""

from sqlalchemy.orm import Session

from app.constants.document_lifecycle_status import DocumentLifecycleStatus
from app.constants.document_storage_status import DocumentStorageStatus
from app.models.document import Document


class DocumentRepository:
    """集中处理文档记录的创建、查询和状态更新。"""

    def __init__(self, db: Session):
        """绑定当前请求或任务使用的数据库会话。"""
        self.db = db

    def create(self, document: Document) -> Document:
        """持久化文档并刷新以取得数据库生成字段。

        仓储层只 ``flush``，不 ``commit``；上传服务据此把文件落盘、去重和建档
        置于同一个由服务层控制的事务边界内。
        """
        self.db.add(document)
        self.db.flush()
        self.db.refresh(document)
        return document

    def get_by_id(self, document_id: int) -> Document | None:
        """按主键查询单个文档。"""
        return (
            self.db.query(Document)
            .filter(Document.id == document_id)
            .first()
        )

    def get_active_by_hash_in_kb(
        self,
        kb_id: int,
        content_hash: str,
    ) -> Document | None:
        """查询仍占用知识库上传去重槽位的同内容文档。"""
        return (
            self.db.query(Document)
            .filter(
                Document.kb_id == kb_id,
                Document.active_content_hash == content_hash,
            )
            .first()
        )

    def get_by_id_for_update(self, document_id: int) -> Document | None:
        """按主键查询并锁定文档，直至当前事务结束。"""
        return (
            self.db.query(Document)
            .filter(Document.id == document_id)
            .with_for_update()
            .first()
        )

    def update_status(
        self,
        document: Document,
        status: str,
    ) -> Document:
        """在当前事务中更新文档状态；调用方负责决定提交或回滚。"""
        document.status = status
        self.db.flush()
        return document

    def update_cleaned_uri(
        self,
        document: Document,
        cleaned_uri: str,
        status: str,
    ) -> Document:
        """在当前事务中写入清洗路径和状态；调用方负责提交或回滚。"""
        document.cleaned_uri = cleaned_uri
        document.status = status
        self.db.flush()
        return document

    def deactivate(
        self,
        document: Document,
        lifecycle_status: str,
        *,
        replaced_by: int | None = None,
    ) -> Document:
        """标记文档业务失效、释放去重 Hash，并进入待归档状态。"""
        document.lifecycle_status = lifecycle_status
        document.active_content_hash = None
        document.storage_status = DocumentStorageStatus.ARCHIVING.value

        if lifecycle_status == DocumentLifecycleStatus.REPLACED.value:
            document.replaced_by = replaced_by

        self.db.flush()
        return document
