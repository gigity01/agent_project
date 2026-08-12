"""Document 高级查询 Repository 的内存数据库测试。"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from sqlalchemy import Text, create_engine
from sqlalchemy.dialects import mysql
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from app.infrastructure.database.base import Base
from app.modules.document.application.dto import (
    ChildChunkSearchQuery,
    DocumentArtifactSearchQuery,
    DocumentSearchQuery,
    ParentBlockSearchQuery,
)
from app.modules.document.infrastructure.persistence.child_chunk_repository import (
    ChildChunkRepository,
)
from app.modules.document.infrastructure.persistence.document_artifact_repository import (
    DocumentArtifactRepository,
)
from app.modules.document.infrastructure.persistence.document_repository import (
    DocumentRepository,
)
from app.modules.document.infrastructure.persistence.knowledge_base_repository import (
    KnowledgeBaseRepository,
)
from app.modules.document.infrastructure.persistence.models.child_chunk import (
    ChildChunk,
)
from app.modules.document.infrastructure.persistence.models.document import Document
from app.modules.document.infrastructure.persistence.models.document_artifact import (
    DocumentArtifact,
)
from app.modules.document.infrastructure.persistence.models.knowledge_base import (
    KnowledgeBase,
)
from app.modules.document.infrastructure.persistence.models.parent_block import (
    ParentBlock,
)
from app.modules.document.infrastructure.persistence.parent_block_repository import (
    ParentBlockRepository,
)


@compiles(MEDIUMTEXT, "sqlite")
def _compile_mediumtext_for_sqlite(_type, compiler, **kwargs):
    """测试替身：生产仍由 MySQL 方言渲染 MEDIUMTEXT。"""
    return compiler.process(Text(), **kwargs)


NOW = datetime(2026, 8, 2, 12, 0, 0)


class DocumentQueryRepositoriesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(
            self.engine,
            tables=[
                KnowledgeBase.__table__,
                Document.__table__,
                DocumentArtifact.__table__,
                ParentBlock.__table__,
                ChildChunk.__table__,
            ],
        )
        self.session = Session(self.engine)
        self._seed()

    def tearDown(self) -> None:
        self.session.close()
        self.engine.dispose()

    def _seed(self) -> None:
        self.session.add(
            KnowledgeBase(
                id=3,
                kb_code="KB_3",
                name="政策知识库",
                domain_code="policy",
                status="active",
                visibility="external",
                embedding_model="text-embedding-v4",
                vector_collection="knowledge_chunks",
            )
        )
        documents = [
            Document(
                id=7,
                doc_code="DOC_POLICY_7",
                kb_id=3,
                domain_code="policy",
                business_scene="compliance",
                title="风险管理办法",
                original_filename="risk-policy.md",
                source_type="md",
                source_uri="storage/raw/local/7.md",
                cleaned_uri="storage/cleaned/7.md",
                content_hash="a" * 64,
                active_content_hash="a" * 64,
                lifecycle_status="active",
                storage_status="active",
                status="indexed",
                risk_level="high",
                created_by_actor_code="actor-a",
                created_at=NOW,
                updated_at=NOW,
                indexed_at=NOW,
            ),
            Document(
                id=8,
                doc_code="DOC_OTHER_8",
                kb_id=3,
                domain_code="policy",
                title="普通说明",
                original_filename="notes.txt",
                source_type="txt",
                source_uri="storage/raw/local/8.txt",
                cleaned_uri=None,
                content_hash="b" * 64,
                active_content_hash=None,
                lifecycle_status="replaced",
                storage_status="archiving",
                status="failed",
                risk_level="low",
                replaced_by=7,
                created_at=NOW - timedelta(days=1),
                updated_at=NOW - timedelta(hours=1),
            ),
        ]
        self.session.add_all(documents)
        self.session.add_all(
            [
                DocumentArtifact(
                    id=11,
                    document_id=7,
                    artifact_code="ART_11",
                    artifact_type="cleaned_text",
                    artifact_role="process_output",
                    artifact_format="md",
                    artifact_uri="storage/cleaned/7.md",
                    provider="local",
                    processor="MarkdownProcessor",
                    status="active",
                    metadata_json={},
                    created_at=NOW,
                ),
                DocumentArtifact(
                    id=12,
                    document_id=7,
                    artifact_code="ART_12",
                    artifact_type="secondary_text",
                    artifact_role="process_input",
                    artifact_format="md",
                    artifact_uri="storage/secondary_text/7.md",
                    provider="docling",
                    processor="DoclingClient",
                    status="superseded",
                    metadata_json={},
                    created_at=NOW - timedelta(hours=1),
                ),
            ]
        )
        self.session.add(
            ParentBlock(
                id=21,
                parent_code="PB_21",
                kb_id=3,
                doc_id=7,
                domain_code="policy",
                block_type="section",
                title="风险章节",
                section_path=["general", "risk-section"],
                content="风险控制正文",
                block_index=0,
                semantic_group_index=0,
                segment_index=0,
                status="active",
                created_at=NOW,
            )
        )
        self.session.add_all(
            [
                ChildChunk(
                    id=31,
                    chunk_code="CC_31",
                    parent_id=21,
                    doc_id=7,
                    kb_id=3,
                    domain_code="policy",
                    chunk_index=0,
                    chunk_type="csv_row",
                    section_path=["general", "risk-section"],
                    source_row_index=10,
                    content="风险记录 A",
                    embedding_text="风险章节 风险记录 A",
                    vector_status="indexed",
                    qdrant_point_id="31",
                    status="active",
                    created_at=NOW,
                    indexed_at=NOW,
                ),
                ChildChunk(
                    id=32,
                    chunk_code="CC_32",
                    parent_id=21,
                    doc_id=7,
                    kb_id=3,
                    domain_code="policy",
                    chunk_index=1,
                    chunk_type="csv_row",
                    section_path=["general", "risk-section"],
                    source_row_index=11,
                    content="普通记录 B",
                    embedding_text="风险章节 普通记录 B",
                    vector_status="failed",
                    qdrant_point_id=None,
                    status="active",
                    created_at=NOW,
                ),
            ]
        )
        self.session.commit()

    def test_document_search_applies_whitelisted_filters_and_sort(self) -> None:
        repository = DocumentRepository(self.session)
        query = DocumentSearchQuery(
            kb_ids=[3],
            statuses=["indexed"],
            keyword="risk-policy",
            has_cleaned_output=True,
            has_active_content_hash=True,
            created_from=NOW - timedelta(minutes=1),
            sort_by="updated_at",
            sort_order="asc",
        )

        items = repository.search(query)

        self.assertEqual([item.id for item in items], [7])
        self.assertEqual(repository.count_search(query), 1)

    def test_artifact_search_can_select_inactive_versions(self) -> None:
        repository = DocumentArtifactRepository(self.session)
        query = DocumentArtifactSearchQuery(
            document_ids=[7],
            providers=["docling"],
            active_only=False,
        )

        items = repository.search(query)

        self.assertEqual([item.id for item in items], [12])
        self.assertEqual(repository.count_search(query), 1)

    def test_parent_block_search_matches_section_path_and_content(self) -> None:
        repository = ParentBlockRepository(self.session)
        query = ParentBlockSearchQuery(
            document_ids=[7],
            section_path_contains="risk-section",
            keyword="控制",
        )

        self.assertEqual([item.id for item in repository.search(query)], [21])
        self.assertEqual(repository.count_by_status_for_document(7), {"active": 1})

    def test_child_chunk_search_combines_row_vector_and_keyword_filters(self) -> None:
        repository = ChildChunkRepository(self.session)
        query = ChildChunkSearchQuery(
            document_id=7,
            vector_statuses=["failed"],
            section_path_contains="risk-section",
            source_row_from=11,
            source_row_to=11,
            has_vector_id=False,
            keyword="普通记录",
        )

        self.assertEqual([item.id for item in repository.search(query)], [32])
        self.assertEqual(repository.count_search(query), 1)
        self.assertEqual(
            repository.count_by_vector_status_for_kb(3),
            {"failed": 1, "indexed": 1},
        )

    def test_section_path_filters_compile_for_production_mysql(self) -> None:
        parent_statement = ParentBlockRepository(self.session)._search_query(
            ParentBlockSearchQuery(section_path_contains="风险章节")
        ).statement
        child_statement = ChildChunkRepository(self.session)._search_query(
            ChildChunkSearchQuery(section_path_contains="风险章节")
        ).statement

        for statement in (parent_statement, child_statement):
            sql = str(statement.compile(dialect=mysql.dialect()))
            self.assertIn("section_path", sql)
            self.assertIn("LIKE", sql)

    def test_knowledge_base_repository_reads_registered_business_model(self) -> None:
        item = KnowledgeBaseRepository(self.session).get_by_id(3)

        self.assertIsNotNone(item)
        self.assertEqual(item.name, "政策知识库")


if __name__ == "__main__":
    unittest.main()
