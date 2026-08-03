"""文档模块父块 ORM 模型的创建和按文档删除操作。"""

from sqlalchemy import String, cast, func, or_
from sqlalchemy.orm import Session

from app.modules.document.application.dto import ParentBlockSearchQuery
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

    def count_active_by_doc_id(self, doc_id: int) -> int:
        """统计文档当前 active 父块数量。"""
        return (
            self.db.query(ParentBlock.id)
            .filter(
                ParentBlock.doc_id == doc_id,
                ParentBlock.status == "active",
            )
            .count()
        )

    def search(self, filters: ParentBlockSearchQuery) -> list[ParentBlock]:
        """按文档、知识库和语义字段稳定分页返回父块。"""
        return (
            self._search_query(filters)
            .order_by(
                ParentBlock.doc_id.asc(),
                ParentBlock.block_index.asc(),
                ParentBlock.id.asc(),
            )
            .offset(filters.offset)
            .limit(filters.limit)
            .all()
        )

    def count_search(self, filters: ParentBlockSearchQuery) -> int:
        return self._search_query(filters).count()

    def _search_query(self, filters: ParentBlockSearchQuery):
        query = self.db.query(ParentBlock)
        list_filters = (
            (ParentBlock.doc_id, filters.document_ids),
            (ParentBlock.id, filters.parent_ids),
            (ParentBlock.kb_id, filters.kb_ids),
            (ParentBlock.block_type, filters.block_types),
            (ParentBlock.status, filters.statuses),
        )
        for column, values in list_filters:
            if values:
                query = query.filter(column.in_(values))
        section_path = (
            filters.section_path_contains.strip()
            if filters.section_path_contains
            else None
        )
        if section_path:
            query = query.filter(
                cast(ParentBlock.section_path, String).contains(
                    section_path,
                    autoescape=True,
                )
            )
        keyword = filters.keyword.strip() if filters.keyword else None
        if keyword:
            query = query.filter(
                or_(
                    ParentBlock.title.contains(keyword, autoescape=True),
                    ParentBlock.content.contains(keyword, autoescape=True),
                )
            )
        return query

    def count_by_status_for_document(self, doc_id: int) -> dict[str, int]:
        """按持久化状态汇总文档的全部父块。"""
        rows = (
            self.db.query(ParentBlock.status, func.count(ParentBlock.id))
            .filter(ParentBlock.doc_id == doc_id)
            .group_by(ParentBlock.status)
            .all()
        )
        return {status: count for status, count in rows}

    def count_active_for_kb(self, kb_id: int) -> int:
        """统计知识库当前 active 父块。"""
        return (
            self.db.query(ParentBlock.id)
            .filter(
                ParentBlock.kb_id == kb_id,
                ParentBlock.status == "active",
            )
            .count()
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
