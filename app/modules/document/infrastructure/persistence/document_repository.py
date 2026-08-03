"""文档模块 ORM 模型的数据库访问封装。"""

from collections.abc import Iterable

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.modules.document.application.dto import DocumentSearchQuery
from app.modules.document.domain.enums import (
    DocumentLifecycleStatus,
    DocumentStorageStatus,
)
from app.modules.document.infrastructure.persistence.models.document import Document


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

    def list_filtered(
        self,
        *,
        kb_id: int,
        status: str | None = None,
        source_type: str | None = None,
        lifecycle_status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Document]:
        """按 Agent 查询所需条件稳定分页返回文档。"""
        query = self._filtered_query(
            kb_id=kb_id,
            status=status,
            source_type=source_type,
            lifecycle_status=lifecycle_status,
        )
        return (
            query.order_by(Document.id.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    def count_filtered(
        self,
        *,
        kb_id: int,
        status: str | None = None,
        source_type: str | None = None,
        lifecycle_status: str | None = None,
    ) -> int:
        """统计与列表查询相同过滤条件下的文档总数。"""
        return self._filtered_query(
            kb_id=kb_id,
            status=status,
            source_type=source_type,
            lifecycle_status=lifecycle_status,
        ).count()

    def search(self, query: DocumentSearchQuery) -> list[Document]:
        """按白名单字段筛选并以显式排序稳定分页。"""
        filtered = self._search_query(query)
        sort_column = {
            "id": Document.id,
            "created_at": Document.created_at,
            "updated_at": Document.updated_at,
            "indexed_at": Document.indexed_at,
            "title": Document.title,
        }[query.sort_by]
        order = sort_column.asc if query.sort_order == "asc" else sort_column.desc
        id_order = Document.id.asc if query.sort_order == "asc" else Document.id.desc
        order_by = [order()]
        if query.sort_by != "id":
            order_by.append(id_order())
        return (
            filtered.order_by(*order_by)
            .offset(query.offset)
            .limit(query.limit)
            .all()
        )

    def count_search(self, query: DocumentSearchQuery) -> int:
        """统计与高级查询同一过滤条件下的文档数量。"""
        return self._search_query(query).count()

    def count_for_kb(
        self,
        kb_id: int,
        *,
        status: str | None = None,
        lifecycle_status: str | None = None,
    ) -> int:
        """按知识库和可选状态轴统计文档。"""
        query = self.db.query(Document.id).filter(Document.kb_id == kb_id)
        if status is not None:
            query = query.filter(Document.status == status)
        if lifecycle_status is not None:
            query = query.filter(
                Document.lifecycle_status == lifecycle_status
            )
        return query.count()

    def _search_query(self, filters: DocumentSearchQuery):
        query = self.db.query(Document)
        list_filters = (
            (Document.kb_id, filters.kb_ids),
            (Document.id, filters.document_ids),
            (Document.doc_code, filters.doc_codes),
            (Document.domain_code, filters.domain_codes),
            (Document.business_scene, filters.business_scenes),
            (Document.status, filters.statuses),
            (Document.lifecycle_status, filters.lifecycle_statuses),
            (Document.storage_status, filters.storage_statuses),
            (Document.source_type, filters.source_types),
            (Document.risk_level, filters.risk_levels),
        )
        for column, values in list_filters:
            if values:
                query = query.filter(column.in_(values))

        keyword = filters.keyword.strip() if filters.keyword else None
        if keyword:
            query = query.filter(
                or_(
                    Document.title.contains(keyword, autoescape=True),
                    Document.doc_code.contains(keyword, autoescape=True),
                    Document.original_filename.contains(
                        keyword,
                        autoescape=True,
                    ),
                )
            )
        original_filename = (
            filters.original_filename.strip()
            if filters.original_filename
            else None
        )
        if original_filename:
            query = query.filter(
                Document.original_filename.contains(
                    original_filename,
                    autoescape=True,
                )
            )
        if filters.created_by_actor_code is not None:
            query = query.filter(
                Document.created_by_actor_code
                == filters.created_by_actor_code
            )

        range_filters = (
            (Document.created_at, filters.created_from, filters.created_to),
            (Document.updated_at, filters.updated_from, filters.updated_to),
            (Document.indexed_at, filters.indexed_from, filters.indexed_to),
        )
        for column, start, end in range_filters:
            if start is not None:
                query = query.filter(column >= start)
            if end is not None:
                query = query.filter(column <= end)
        if filters.effective_at_before is not None:
            query = query.filter(
                Document.effective_at <= filters.effective_at_before
            )
        if filters.expired_at_before is not None:
            query = query.filter(
                Document.expired_at <= filters.expired_at_before
            )

        nullable_filters = (
            (Document.cleaned_uri, filters.has_cleaned_output),
            (Document.active_content_hash, filters.has_active_content_hash),
        )
        for column, expected in nullable_filters:
            if expected is True:
                query = query.filter(column.is_not(None))
            elif expected is False:
                query = query.filter(column.is_(None))
        if filters.replaced_by is not None:
            query = query.filter(Document.replaced_by == filters.replaced_by)
        return query

    def _filtered_query(
        self,
        *,
        kb_id: int,
        status: str | None,
        source_type: str | None,
        lifecycle_status: str | None,
    ):
        query = self.db.query(Document).filter(Document.kb_id == kb_id)
        if status is not None:
            query = query.filter(Document.status == status)
        if source_type is not None:
            query = query.filter(Document.source_type == source_type)
        if lifecycle_status is not None:
            query = query.filter(
                Document.lifecycle_status == lifecycle_status
            )
        return query

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

    def get_by_ids_for_update(
        self,
        document_ids: Iterable[int],
    ) -> list[Document]:
        """按主键升序锁定多份文档，避免替代操作形成循环等待。"""
        ordered_ids = sorted(set(document_ids))
        if not ordered_ids:
            return []

        return (
            self.db.query(Document)
            .filter(Document.id.in_(ordered_ids))
            .order_by(Document.id)
            .with_for_update()
            .all()
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
