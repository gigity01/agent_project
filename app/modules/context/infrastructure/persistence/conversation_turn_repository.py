"""ConversationTurn 的窄仓储，供跨模块事务协作。"""

from sqlalchemy.orm import Session

from app.modules.context.infrastructure.persistence.models.conversation_turn import (
    ConversationTurn,
)


class ConversationTurnRepository:
    """提供 Planning 所需的 Turn 查询、锁定与 task_ids 更新。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, turn_id: str) -> ConversationTurn | None:
        return (
            self.db.query(ConversationTurn)
            .filter(ConversationTurn.turn_id == turn_id)
            .first()
        )

    def get_by_id_for_update(
        self,
        turn_id: str,
    ) -> ConversationTurn | None:
        return (
            self.db.query(ConversationTurn)
            .filter(ConversationTurn.turn_id == turn_id)
            .with_for_update()
            .first()
        )

    def set_task_ids(
        self,
        turn: ConversationTurn,
        task_ids: list[str],
    ) -> ConversationTurn:
        turn.task_ids = list(task_ids)
        self.db.flush()
        return turn

    def set_status(self, turn: ConversationTurn, status: str) -> ConversationTurn:
        turn.status = status
        self.db.flush()
        return turn
