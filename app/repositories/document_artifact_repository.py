from sqlalchemy.orm import Session

from app.models.document_artifact import DocumentArtifact
from app.schemas.document_artifact import DocumentArtifactCreate


class DocumentArtifactRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, data: DocumentArtifactCreate) -> DocumentArtifact:
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
        self.db.commit()
        self.db.refresh(artifact)

        return artifact

    def get_by_id(self, artifact_id: int) -> DocumentArtifact | None:
        return (
            self.db.query(DocumentArtifact)
            .filter(DocumentArtifact.id == artifact_id)
            .first()
        )

    def get_by_code(self, artifact_code: str) -> DocumentArtifact | None:
        return (
            self.db.query(DocumentArtifact)
            .filter(DocumentArtifact.artifact_code == artifact_code)
            .first()
        )

    def get_latest_active(
        self,
        *,
        document_id: int,
        artifact_type: str,
        artifact_role: str | None = None,
        artifact_format: str | None = None,
    ) -> DocumentArtifact | None:
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

        self.db.commit()

        return count