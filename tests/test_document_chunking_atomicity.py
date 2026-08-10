"""BuildChunks finalize 的真实 SQLAlchemy 事务原子性测试。"""

from __future__ import annotations

import unittest
from pathlib import Path

from sqlalchemy import Text, create_engine
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.infrastructure.database.base import Base
from app.infrastructure.database.uow import SQLAlchemyUnitOfWork
from app.modules.document.application.use_cases.build_chunks import (
    BuildChunksCompensator,
    ChunkingContext,
    ChunkingExecutionResult,
    _complete_chunking,
)
from app.modules.document.domain.enums import DocumentStatus
from app.modules.document.domain.models import (
    ChildChunkData,
    ChunkBuildResult,
    ParentBlockData,
)
from app.modules.document.infrastructure.persistence.models.child_chunk import (
    ChildChunk,
)
from app.modules.document.infrastructure.persistence.models.document import (
    Document,
)
from app.modules.document.infrastructure.persistence.models.knowledge_base import (
    KnowledgeBase,
)
from app.modules.document.infrastructure.persistence.models.parent_block import (
    ParentBlock,
)


@compiles(MEDIUMTEXT, "sqlite")
def _compile_mediumtext_for_sqlite(_type, compiler, **kwargs):
    return compiler.process(Text(), **kwargs)


class _FailingChildCreateUnitOfWork(SQLAlchemyUnitOfWork):
    def __enter__(self):
        uow = super().__enter__()
        repository = uow.child_chunks

        def create_one_then_fail(children):
            repository.create(children[0])
            raise RuntimeError("create child failed")

        repository.create_many = create_one_then_fail
        return uow


class DocumentChunkingAtomicityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.session_factory = sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
        )
        self.tables = [
            KnowledgeBase.__table__,
            Document.__table__,
            ParentBlock.__table__,
            ChildChunk.__table__,
        ]
        Base.metadata.create_all(self.engine, tables=self.tables)
        with self.session_factory() as session:
            session.add(
                KnowledgeBase(
                    id=1,
                    kb_code="KB_ATOMIC",
                    name="Atomic",
                    domain_code="test",
                    embedding_model="test-model",
                    vector_collection="test-vectors",
                )
            )
            session.add(
                Document(
                    id=1,
                    doc_code="DOC_ATOMIC",
                    kb_id=1,
                    domain_code="test",
                    title="Atomic document",
                    source_type="md",
                    source_uri="storage/raw/local/atomic.md",
                    cleaned_uri="storage/cleaned/atomic.md",
                    content_hash="a" * 64,
                    active_content_hash="a" * 64,
                    status=DocumentStatus.CHUNKING.value,
                    active_operation_id="operation-atomic",
                )
            )
            session.add(
                ParentBlock(
                    id=10,
                    parent_code="PB_OLD",
                    kb_id=1,
                    doc_id=1,
                    domain_code="test",
                    block_type="section",
                    content="old parent",
                    block_index=0,
                    semantic_group_index=0,
                    segment_index=0,
                )
            )
            session.add(
                ChildChunk(
                    id=20,
                    chunk_code="CK_OLD",
                    parent_id=10,
                    doc_id=1,
                    kb_id=1,
                    domain_code="test",
                    content="old child",
                    embedding_text="old child",
                )
            )
            session.commit()

    def tearDown(self) -> None:
        Base.metadata.drop_all(
            self.engine,
            tables=list(reversed(self.tables)),
        )
        self.engine.dispose()

    def test_partial_child_insert_rolls_back_then_compensates(self) -> None:
        parent_ids = iter((101,))
        child_ids = iter((201, 202))
        failing_ports = type(
            "Ports",
            (),
            {
                "uow_factory": staticmethod(
                    lambda: _FailingChildCreateUnitOfWork(
                        self.session_factory
                    )
                ),
                "parent_block_factory": staticmethod(
                    lambda **values: ParentBlock(
                        id=next(parent_ids),
                        **values,
                    )
                ),
                "child_chunk_factory": staticmethod(
                    lambda **values: ChildChunk(
                        id=next(child_ids),
                        **values,
                    )
                ),
            },
        )()
        result = ChunkingExecutionResult(
            context=ChunkingContext(
                document_id=1,
                doc_code="DOC_ATOMIC",
                source_type="md",
                cleaned_path=Path("storage/cleaned/atomic.md"),
                chunk_source_type="md",
                document_title="Atomic document",
                kb_id=1,
                domain_code="test",
                business_scene=None,
                version=1,
                process_metadata={},
                status_before=DocumentStatus.PROCESSED.value,
                operation_id="operation-atomic",
            ),
            chunks=ChunkBuildResult(
                parents=[
                    ParentBlockData(
                        block_type="section",
                        title="new",
                        section_path=["new"],
                        content="new parent",
                        block_index=0,
                        semantic_group_index=0,
                        segment_index=0,
                    )
                ],
                children_by_parent_index={
                    0: [
                        ChildChunkData(
                            content="new child 1",
                            embedding_text="new child 1",
                            chunk_index=0,
                        ),
                        ChildChunkData(
                            content="new child 2",
                            embedding_text="new child 2",
                            chunk_index=1,
                        ),
                    ]
                },
            ),
        )

        with self.assertRaisesRegex(RuntimeError, "create child failed"):
            _complete_chunking(result, ports=failing_ports)

        with self.session_factory() as session:
            document = session.get(Document, 1)
            parents = session.query(ParentBlock).all()
            children = session.query(ChildChunk).all()
            self.assertEqual(document.status, DocumentStatus.CHUNKING.value)
            self.assertEqual(document.active_operation_id, "operation-atomic")
            self.assertEqual([parent.id for parent in parents], [10])
            self.assertEqual([parent.content for parent in parents], ["old parent"])
            self.assertEqual([child.id for child in children], [20])
            self.assertEqual([child.content for child in children], ["old child"])

        compensator = BuildChunksCompensator(
            ports=type(
                "CompensatorPorts",
                (),
                {
                    "uow_factory": staticmethod(
                        lambda: SQLAlchemyUnitOfWork(self.session_factory)
                    )
                },
            )()
        )
        for _ in range(3):
            compensator.compensate(
                document_id=1,
                operation_id="operation-atomic",
            )

        with self.session_factory() as session:
            document = session.get(Document, 1)
            self.assertEqual(document.status, DocumentStatus.FAILED.value)
            self.assertIsNone(document.active_operation_id)


if __name__ == "__main__":
    unittest.main()
