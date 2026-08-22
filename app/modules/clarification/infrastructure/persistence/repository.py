"""ClarificationRequest 仓储。"""

from sqlalchemy.orm import Session

from app.modules.clarification.infrastructure.persistence.models import (
    ClarificationRequest,
)


class ClarificationRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def add(self, request: ClarificationRequest) -> ClarificationRequest:
        self.db.add(request)
        self.db.flush()
        return request

    def get_open_for_conversation_for_update(
        self, conversation_id: str
    ) -> ClarificationRequest | None:
        return (
            self.db.query(ClarificationRequest)
            .filter(
                ClarificationRequest.conversation_id == conversation_id,
                ClarificationRequest.status == "open",
            )
            .order_by(ClarificationRequest.created_at.desc())
            .with_for_update()
            .first()
        )

    def get_by_source_turn_id_for_update(
        self,
        source_turn_id: str,
    ) -> ClarificationRequest | None:
        return (
            self.db.query(ClarificationRequest)
            .filter(ClarificationRequest.source_turn_id == source_turn_id)
            .with_for_update()
            .first()
        )

    def get_by_plan_id(self, plan_id: str) -> ClarificationRequest | None:
        return (
            self.db.query(ClarificationRequest)
            .filter(ClarificationRequest.source_plan_id == plan_id)
            .first()
        )

    def get_by_plan_id_for_update(
        self, plan_id: str
    ) -> ClarificationRequest | None:
        return (
            self.db.query(ClarificationRequest)
            .filter(ClarificationRequest.source_plan_id == plan_id)
            .with_for_update()
            .first()
        )
