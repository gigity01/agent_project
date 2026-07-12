"""父块 ORM 模型的创建和按文档删除操作。"""

from sqlalchemy.orm import Session

from app.models.parent_block import ParentBlock


class ParentBlockRepository:
    """封装父块的最小数据库访问操作。"""
    def __init__(self, db: Session):
        self.db = db

    def create(self, parent_block: ParentBlock) -> ParentBlock:
        """加入会话并 flush，以便后续子块取得父块主键。"""
        self.db.add(parent_block)
        self.db.flush()
        return parent_block

    def delete_by_doc_id(self, doc_id: int) -> None:
        """删除指定文档的全部父块，不在此处提交事务。"""
        (
            self.db.query(ParentBlock)
            .filter(ParentBlock.doc_id == doc_id)
            .delete(synchronize_session=False)
        )
