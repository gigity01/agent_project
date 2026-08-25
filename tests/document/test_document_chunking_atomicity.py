"""BuildChunks 分块完成阶段（finalize）的数据库事务原子性与失败补偿测试。

核心业务不变量（遵循 AGENTS.md 规范）：
1. 分块事务原子性：
   - 重建切块时，在同一短事务内：复核 Document 三状态轴与 operation ownership -> 删除旧 child chunks -> 删除旧 parent blocks -> 写入新 blocks & chunks -> 将 Document 推进为 chunked。
   - 若子块批量插入中途发生异常，事务必须完全回滚，旧 parent/child 记录不受破坏，Document 状态保留为 chunking 且保持 ownership。
2. 确定性补偿器行为（Compensator Invariants）：
   - UseCase 失败时不自作主张释放 ownership，由 Runtime 驱动 BuildChunksCompensator 介入。
   - Compensator 校验相同的 operation_id，幂等将 Document 推进为 failed 并安全释放 active_operation_id 所有权。
"""

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
    """为 SQLite 测试环境将 MySQL MEDIUMTEXT 方言类型重定向编译为标准 Text 类型。"""
    return compiler.process(Text(), **kwargs)


class _FailingChildCreateUnitOfWork(SQLAlchemyUnitOfWork):
    """模拟在插入第二个 ChildChunk 时突发异常的 UnitOfWork 替身。"""

    def __enter__(self):
        uow = super().__enter__()
        repository = uow.child_chunks

        def create_one_then_fail(children):
            repository.create(children[0])
            raise RuntimeError("create child failed")

        repository.create_many = create_one_then_fail
        return uow


class DocumentChunkingAtomicityTest(unittest.TestCase):
    """验证分块写入失败时的事务完整回滚及后续补偿器的幂等修复能力。"""

    def setUp(self) -> None:
        """初始化内存 SQLite 数据库，建立知识库、文档及旧父子块记录。"""
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
            # 1. 创建测试知识库
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
            # 2. 创建处于 chunking 状态的文档，持有 operation-atomic 令牌
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
            # 3. 创建旧父块
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
            # 4. 创建旧子块
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
        """清理测试表并销毁数据库引擎。"""
        Base.metadata.drop_all(
            self.engine,
            tables=list(reversed(self.tables)),
        )
        self.engine.dispose()

    def test_partial_child_insert_rolls_back_then_compensates(self) -> None:
        """验证部分子块写入失败时事务完全回滚，随后由 Compensator 幂等置为 failed 并释放令牌。"""
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

        # 1. 验证完成切块过程中抛出异常
        with self.assertRaisesRegex(RuntimeError, "create child failed"):
            _complete_chunking(result, ports=failing_ports)

        # 2. 验证事务已完整回滚：状态仍为 chunking，旧数据完整保留，新数据未残留
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

        # 3. 运行 BuildChunksCompensator 验证补偿器幂等执行
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

        # 4. 验证补偿后文档状态变为 failed，operation_id 成功释放
        with self.session_factory() as session:
            document = session.get(Document, 1)
            self.assertEqual(document.status, DocumentStatus.FAILED.value)
            self.assertIsNone(document.active_operation_id)


if __name__ == "__main__":
    unittest.main()
