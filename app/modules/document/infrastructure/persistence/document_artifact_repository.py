"""文档模块派生产物 ORM 模型的查询与状态更新封装。"""

from sqlalchemy.orm import Session

from app.modules.document.infrastructure.persistence.models.document_artifact import (
    DocumentArtifact,
)
from app.modules.document.application.dto import (
    DocumentArtifactCreate,
    DocumentArtifactSearchQuery,
)


class DocumentArtifactRepository:
    """管理文档派生产物记录及其当前有效版本。"""
    def __init__(self, db: Session) -> None:
        """绑定当前数据库会话。"""
        self.db = db

    def create(self, data: DocumentArtifactCreate) -> DocumentArtifact:
        """依据创建请求写入派生产物并 flush，由服务层决定何时提交。"""
        artifact = DocumentArtifact(
            document_id=data.document_id,
            artifact_code=data.artifact_code,
            artifact_type=data.artifact_type,
            artifact_role=data.artifact_role,
            artifact_format=data.artifact_format,
            artifact_uri=data.artifact_uri,
            artifact_hash=data.artifact_hash,
            hash_algorithm=data.hash_algorithm,
            provider=data.provider,
            processor=data.processor,
            file_size=data.file_size,
            char_count=data.char_count,
            line_count=data.line_count,
            status=data.status,
            metadata_json=data.metadata,
            created_by_actor_code=data.created_by_actor_code,
        )

        self.db.add(artifact)
        self.db.flush()

        return artifact

    def get_by_id(self, artifact_id: int) -> DocumentArtifact | None:
        """按主键查询派生产物。"""
        return (
            self.db.query(DocumentArtifact)
            .filter(DocumentArtifact.id == artifact_id)
            .first()
        )

    def get_by_code(self, artifact_code: str) -> DocumentArtifact | None:
        """按业务编号查询派生产物。"""
        return (
            self.db.query(DocumentArtifact)
            .filter(DocumentArtifact.artifact_code == artifact_code)
            .first()
        )

    def list_by_document_id(
        self,
        document_id: int,
    ) -> list[DocumentArtifact]:
        """按创建时间和主键稳定返回文档的全部派生产物。"""
        return (
            self.db.query(DocumentArtifact)
            .filter(DocumentArtifact.document_id == document_id)
            .order_by(
                DocumentArtifact.created_at.asc(),
                DocumentArtifact.id.asc(),
            )
            .all()
        )

    def search(
        self,
        filters: DocumentArtifactSearchQuery,
    ) -> list[DocumentArtifact]:
        """按受限条件筛选并分页返回派生产物。"""
        return (
            self._search_query(filters)
            .order_by(
                DocumentArtifact.created_at.desc(),
                DocumentArtifact.id.desc(),
            )
            .offset(filters.offset)
            .limit(filters.limit)
            .all()
        )

    def count_search(self, filters: DocumentArtifactSearchQuery) -> int:
        """统计与派生产物查询相同条件下的结果数量。"""
        return self._search_query(filters).count()

    def _search_query(self, filters: DocumentArtifactSearchQuery):
        query = self.db.query(DocumentArtifact)
        list_filters = (
            (DocumentArtifact.document_id, filters.document_ids),
            (DocumentArtifact.artifact_type, filters.artifact_types),
            (DocumentArtifact.artifact_role, filters.artifact_roles),
            (DocumentArtifact.artifact_format, filters.artifact_formats),
            (DocumentArtifact.status, filters.statuses),
            (DocumentArtifact.provider, filters.providers),
            (DocumentArtifact.processor, filters.processors),
        )
        for column, values in list_filters:
            if values:
                query = query.filter(column.in_(values))
        if filters.created_from is not None:
            query = query.filter(
                DocumentArtifact.created_at >= filters.created_from
            )
        if filters.created_to is not None:
            query = query.filter(
                DocumentArtifact.created_at <= filters.created_to
            )
        if filters.active_only is True:
            query = query.filter(DocumentArtifact.status == "active")
        elif filters.active_only is False:
            query = query.filter(DocumentArtifact.status != "active")
        return query

    def get_latest_active(
        self,
        *,
        document_id: int,
        artifact_type: str,
        artifact_role: str | None = None,
        artifact_format: str | None = None,
    ) -> DocumentArtifact | None:
        """查询指定条件下最新的有效派生产物。"""
        query = (
            self.db.query(DocumentArtifact)
            .filter(DocumentArtifact.document_id == document_id)
            .filter(DocumentArtifact.artifact_type == artifact_type)
            .filter(DocumentArtifact.status == "active")
        )

        if artifact_role is not None:
            query = query.filter(DocumentArtifact.artifact_role == artifact_role)

        if artifact_format is not None:
            query = query.filter(DocumentArtifact.artifact_format == artifact_format)

        return query.order_by(DocumentArtifact.created_at.desc()).first()

    def mark_active_as_superseded(
        self,
        *,
        document_id: int,
        artifact_type: str,
        artifact_role: str | None = None,
        artifact_format: str | None = None,
    ) -> int:
        """将同类有效派生产物置为 superseded，并返回更新数量。"""
        query = (
            self.db.query(DocumentArtifact)
            .filter(DocumentArtifact.document_id == document_id)
            .filter(DocumentArtifact.artifact_type == artifact_type)
            .filter(DocumentArtifact.status == "active")
        )

        if artifact_role is not None:
            query = query.filter(DocumentArtifact.artifact_role == artifact_role)

        if artifact_format is not None:
            query = query.filter(DocumentArtifact.artifact_format == artifact_format)

        count = query.update(
            {
                "status": "superseded",
            },
            synchronize_session=False,
        )

        self.db.flush()

        return count
