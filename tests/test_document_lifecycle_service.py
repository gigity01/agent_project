"""统一文档失效事务的业务不变量测试。"""

from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from app.modules.document.domain.enums import (
    DocumentLifecycleStatus,
    DocumentStatus,
    DocumentStorageStatus,
)


ROOT_DIR = Path(__file__).resolve().parents[1]
SERVICE_PATH = (
    ROOT_DIR
    / "app"
    / "modules"
    / "document"
    / "application"
    / "use_cases"
    / "change_lifecycle.py"
)


class _HTTPException(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class _DocumentResponse:
    @classmethod
    def model_validate(cls, document):
        return SimpleNamespace(**vars(document))


def _load_service_module():
    """使用轻量替身加载 Service，避免测试依赖未声明的第三方包。"""
    replacements = {
        "app.modules.document.application.dto": types.ModuleType(
            "app.modules.document.application.dto"
        ),
        "app.modules.document.application.errors": types.ModuleType(
            "app.modules.document.application.errors"
        ),
        "app.modules.document.application.ports": types.ModuleType(
            "app.modules.document.application.ports"
        ),
    }
    replacements[
        "app.modules.document.application.dto"
    ].DocumentResult = _DocumentResponse
    replacements[
        "app.modules.document.application.errors"
    ].DocumentApplicationError = _HTTPException
    replacements[
        "app.modules.document.application.ports"
    ].create_uow = object

    originals = {name: sys.modules.get(name) for name in replacements}
    sys.modules.update(replacements)
    try:
        spec = importlib.util.spec_from_file_location(
            "document_lifecycle_service_under_test",
            SERVICE_PATH,
        )
        if spec is None or spec.loader is None:
            raise RuntimeError("无法加载待测试的文档生命周期 Service")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        for name, original in originals.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


class _DocumentRepository:
    def __init__(self, documents: dict[int, SimpleNamespace]) -> None:
        self.documents = documents
        self.locked_ids: list[int] = []
        self.batch_lock_calls: list[tuple[int, ...]] = []
        self.deactivate_calls: list[tuple[int, str, int | None]] = []

    def get_by_id_for_update(self, document_id: int):
        self.locked_ids.append(document_id)
        return self.documents.get(document_id)

    def get_by_ids_for_update(self, document_ids):
        ordered_ids = tuple(sorted(set(document_ids)))
        self.batch_lock_calls.append(ordered_ids)
        self.locked_ids.extend(ordered_ids)
        return [
            self.documents[document_id]
            for document_id in ordered_ids
            if document_id in self.documents
        ]

    def deactivate(
        self,
        document: SimpleNamespace,
        lifecycle_status: str,
        *,
        replaced_by: int | None = None,
    ) -> SimpleNamespace:
        self.deactivate_calls.append(
            (document.id, lifecycle_status, replaced_by)
        )
        document.lifecycle_status = lifecycle_status
        document.active_content_hash = None
        document.storage_status = DocumentStorageStatus.ARCHIVING.value
        if lifecycle_status == DocumentLifecycleStatus.REPLACED.value:
            document.replaced_by = replaced_by
        return document


class _UnitOfWork:
    def __init__(self, documents: dict[int, SimpleNamespace]) -> None:
        self.documents = _DocumentRepository(documents)
        self.commit_count = 0
        self.rollback_count = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        if exc_type is not None or self.commit_count == 0:
            self.rollback_count += 1
        return False

    def commit(self) -> None:
        self.commit_count += 1


def _document(
    document_id: int,
    *,
    kb_id: int = 1,
    status: str = DocumentStatus.INDEXED.value,
    lifecycle_status: str = DocumentLifecycleStatus.ACTIVE.value,
    active_content_hash: str | None = "hash-a",
    storage_status: str = DocumentStorageStatus.ACTIVE.value,
    replaced_by: int | None = None,
    effective_at: datetime | None = None,
    expired_at: datetime | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=document_id,
        kb_id=kb_id,
        status=status,
        lifecycle_status=lifecycle_status,
        active_content_hash=active_content_hash,
        storage_status=storage_status,
        replaced_by=replaced_by,
        effective_at=effective_at,
        expired_at=expired_at,
    )


class DocumentLifecycleServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.service = _load_service_module()

    def setUp(self) -> None:
        self.original_uow = self.service.SQLAlchemyUnitOfWork

    def tearDown(self) -> None:
        self.service.SQLAlchemyUnitOfWork = self.original_uow

    def _use_documents(
        self,
        *documents: SimpleNamespace,
    ) -> _UnitOfWork:
        uow = _UnitOfWork({document.id: document for document in documents})
        self.service.SQLAlchemyUnitOfWork = lambda: uow
        return uow

    def test_expire_and_delete_release_hash_without_changing_processing_status(self) -> None:
        for reason in (
            DocumentLifecycleStatus.EXPIRED,
            DocumentLifecycleStatus.DELETED,
        ):
            with self.subTest(reason=reason.value):
                document = _document(1, status=DocumentStatus.INDEXED.value)
                uow = self._use_documents(document)

                response = self.service.deactivate_document(1, reason)

                self.assertEqual(document.status, DocumentStatus.INDEXED.value)
                self.assertEqual(document.lifecycle_status, reason.value)
                self.assertIsNone(document.active_content_hash)
                self.assertEqual(
                    document.storage_status,
                    DocumentStorageStatus.ARCHIVING.value,
                )
                self.assertEqual(response.lifecycle_status, reason.value)
                self.assertEqual(uow.commit_count, 1)

    def test_replace_locks_and_validates_replacement_in_same_transaction(self) -> None:
        document = _document(2, kb_id=7)
        replacement = _document(1, kb_id=7)
        uow = self._use_documents(document, replacement)

        response = self.service.deactivate_document(
            2,
            DocumentLifecycleStatus.REPLACED,
            replaced_by=1,
        )

        self.assertEqual(uow.documents.locked_ids, [1, 2])
        self.assertEqual(uow.documents.batch_lock_calls, [(1, 2)])
        self.assertEqual(document.lifecycle_status, "replaced")
        self.assertEqual(document.replaced_by, 1)
        self.assertIsNone(document.active_content_hash)
        self.assertEqual(document.storage_status, "archiving")
        self.assertEqual(response.replaced_by, 1)
        self.assertEqual(uow.commit_count, 1)

    def test_same_reason_is_idempotent_without_new_write(self) -> None:
        for reason in (
            DocumentLifecycleStatus.EXPIRED,
            DocumentLifecycleStatus.REPLACED,
            DocumentLifecycleStatus.DELETED,
        ):
            with self.subTest(reason=reason.value):
                document = _document(
                    1,
                    lifecycle_status=reason.value,
                    active_content_hash=None,
                    storage_status=DocumentStorageStatus.ARCHIVING.value,
                    replaced_by=2 if reason == DocumentLifecycleStatus.REPLACED else None,
                )
                uow = self._use_documents(document)

                response = self.service.deactivate_document(
                    1,
                    reason,
                    replaced_by=document.replaced_by,
                )

                self.assertEqual(response.lifecycle_status, reason.value)
                self.assertEqual(uow.documents.deactivate_calls, [])
                self.assertEqual(uow.commit_count, 0)
                self.assertEqual(uow.rollback_count, 1)

    def test_replaced_idempotency_rejects_different_target(self) -> None:
        document = _document(
            1,
            lifecycle_status=DocumentLifecycleStatus.REPLACED.value,
            active_content_hash=None,
            storage_status=DocumentStorageStatus.ARCHIVING.value,
            replaced_by=2,
        )
        uow = self._use_documents(document, _document(3))

        with self.assertRaises(self.service.HTTPException) as raised:
            self.service.deactivate_document(
                1,
                DocumentLifecycleStatus.REPLACED,
                replaced_by=3,
            )

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(raised.exception.detail, "文档已经被其他文档替代")
        self.assertEqual(uow.documents.deactivate_calls, [])
        self.assertEqual(uow.commit_count, 0)

    def test_different_deactivation_reason_returns_conflict(self) -> None:
        document = _document(
            1,
            lifecycle_status=DocumentLifecycleStatus.EXPIRED.value,
            active_content_hash=None,
        )
        uow = self._use_documents(document)

        with self.assertRaises(self.service.HTTPException) as raised:
            self.service.deactivate_document(
                1,
                DocumentLifecycleStatus.DELETED,
            )

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(uow.documents.deactivate_calls, [])
        self.assertEqual(uow.commit_count, 0)

    def test_missing_document_returns_not_found(self) -> None:
        uow = self._use_documents()

        with self.assertRaises(self.service.HTTPException) as raised:
            self.service.deactivate_document(
                404,
                DocumentLifecycleStatus.EXPIRED,
            )

        self.assertEqual(raised.exception.status_code, 404)
        self.assertEqual(uow.commit_count, 0)

    def test_invalid_reason_is_rejected_before_opening_transaction(self) -> None:
        factory_calls = 0

        def uow_factory():
            nonlocal factory_calls
            factory_calls += 1
            return _UnitOfWork({})

        self.service.SQLAlchemyUnitOfWork = uow_factory

        with self.assertRaisesRegex(ValueError, "不支持的失效原因"):
            self.service.deactivate_document(
                1,
                DocumentLifecycleStatus.ACTIVE,
            )

        self.assertEqual(factory_calls, 0)

    def test_replace_rejects_missing_or_invalid_replacement(self) -> None:
        now = datetime.now(timezone.utc)
        scenarios = [
            (None, (), 400),
            (2, (), 404),
            (1, (), 400),
            (2, (_document(2, kb_id=8),), 409),
            (
                2,
                (_document(2, status=DocumentStatus.CHUNKED.value),),
                409,
            ),
            (
                2,
                (
                    _document(
                        2,
                        lifecycle_status=DocumentLifecycleStatus.SCHEDULED.value,
                    ),
                ),
                409,
            ),
            (
                2,
                (
                    _document(
                        2,
                        storage_status=DocumentStorageStatus.ARCHIVED.value,
                    ),
                ),
                409,
            ),
            (
                2,
                (_document(2, effective_at=now + timedelta(minutes=5)),),
                409,
            ),
            (
                2,
                (_document(2, expired_at=now - timedelta(minutes=5)),),
                409,
            ),
        ]
        for replaced_by, replacements, expected_status in scenarios:
            with self.subTest(
                replaced_by=replaced_by,
                expected_status=expected_status,
            ):
                document = _document(1)
                uow = self._use_documents(document, *replacements)

                with self.assertRaises(self.service.HTTPException) as raised:
                    self.service.deactivate_document(
                        1,
                        DocumentLifecycleStatus.REPLACED,
                        replaced_by=replaced_by,
                    )

                self.assertEqual(raised.exception.status_code, expected_status)
                self.assertEqual(uow.documents.deactivate_calls, [])
                self.assertEqual(uow.commit_count, 0)


if __name__ == "__main__":
    unittest.main()
