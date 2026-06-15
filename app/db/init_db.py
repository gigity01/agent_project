from app.db.session import Base, engine

from app.models.knowledge_base import KnowledgeBase
from app.models.document import Document


def init_db() -> None:
    Base.metadata.create_all(bind=engine)