"""文档 ORM 模型的数据库访问封装。"""

from sqlalchemy.orm import Session

from app.models.document import Document


class DocumentRepository:
    """集中处理文档记录的创建、查询和状态更新。"""
    def __init__(self, db: Session):
        """绑定当前请求或任务使用的数据库会话。"""
        self.db = db

    def create(self, document: Document) -> Document:
        """持久化文档并刷新以取得数据库生成字段。"""
        self.db.add(document)
        self.db.commit()
        self.db.refresh(document)
        return document

    def get_by_id(self, document_id: int) :
        """按主键查询单个文档。"""
        return (
            self.db.query(Document)
            .filter(Document.id == document_id)
            .first()
        )

    def get_by_hash_in_kb(
            self,
            kb_id: int,
            content_hash: str,
    ) :
        """在知识库内查询未删除、未归档、未替换的同内容文档。"""
        return (
            self.db.query(Document)
            .filter(
                Document.kb_id == kb_id,
                Document.content_hash == content_hash,
                Document.status.notin_(["deleted", "archived", "replaced"]),
            )
            .first()
        )

    def update_status(
            self,
            document: Document,
            status: str,
    ) -> Document:
        """更新文档状态并立即提交。"""
        document.status = status
        self.db.commit()
        self.db.refresh(document)
        return document

    def update_cleaned_uri(
            self,
            document: Document,
            cleaned_uri: str,
            status: str = "active",
    ) -> Document:
        """写入清洗文件路径并更新文档状态。"""
        document.cleaned_uri = cleaned_uri
        document.status = status
        self.db.commit()
        self.db.refresh(document)
        return document
