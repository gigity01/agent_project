"""文档模块父块 ORM 模型的创建和按文档删除操作。"""

from sqlalchemy.orm import Session

from app.modules.document.infrastructure.persistence.models.parent_block import (
    ParentBlock,
)


class ParentBlockRepository:
    """封装父块的最小数据库访问操作。"""
    def __init__(self, db: Session):
        self.db = db

    def create(self, parent_block: ParentBlock) -> ParentBlock:
        """加入会话并 flush，以便后续子块取得父块主键。"""
        self.db.add(parent_block)
        self.db.flush()
        return parent_block

    def create_many(
        self,
        parent_blocks: list[ParentBlock],
    ) -> list[ParentBlock]:
        """批量加入父块并统一 flush；事务提交仍由调用方负责。"""
        if not parent_blocks:
            return []

        self.db.add_all(parent_blocks)
        self.db.flush()
        return parent_blocks

    def delete_by_doc_id(self, doc_id: int) -> None:
        """删除指定文档的全部父块，不在此处提交事务。"""
        (
            self.db.query(ParentBlock)
            .filter(ParentBlock.doc_id == doc_id)
            .delete(synchronize_session=False)
        )

    def list_by_semantic_group(
        self,
        *,
        doc_id: int,
        semantic_group_index: int,
    ) -> list[ParentBlock]:
        """按组内顺序返回指定文档中一个完整有效语义单元的父块。"""
        return (
            self.db.query(ParentBlock)
            .filter(
                ParentBlock.doc_id == doc_id,
                ParentBlock.semantic_group_index == semantic_group_index,
                ParentBlock.status == "active",
            )
            .order_by(ParentBlock.segment_index.asc())
            .all()
        )
