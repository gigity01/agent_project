"""上传前置校验和存储准备进入日志异常边界的测试。"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT_DIR = Path(__file__).resolve().parents[1]
SERVICE_PATH = (
    ROOT_DIR
    / "app"
    / "modules"
    / "document"
    / "application"
    / "use_cases"
    / "upload_document.py"
)


class _HTTPException(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class _IntegrityError(Exception):
    pass


class _DocumentUploadLogger:
    instances = []

    def __init__(self) -> None:
        self.failed_fields = None
        self.started_fields = None
        self.__class__.instances.append(self)

    def started(self, **fields) -> None:
        self.started_fields = fields

    def raw_file_saved(self, **fields) -> None:
        pass

    def hash_calculated(self, **fields) -> None:
        pass

    def duplicate_detected(self, **fields) -> None:
        pass

    def completed(self, **fields) -> None:
        pass

    def failed_by_http_exception(self, **fields) -> None:
        self.failed_fields = fields

    def failed_by_unexpected_exception(self, **fields) -> None:
        self.failed_fields = fields


def _load_service_module():
    replacements = {
        "app.config.settings": types.ModuleType("app.config.settings"),
        "app.modules.document.application.dto": types.ModuleType(
            "app.modules.document.application.dto"
        ),
        "app.modules.document.application.errors": types.ModuleType(
            "app.modules.document.application.errors"
        ),
        "app.modules.document.application.ports": types.ModuleType(
            "app.modules.document.application.ports"
        ),
        "app.shared.observability.document_upload_logger": types.ModuleType(
            "app.shared.observability.document_upload_logger"
        ),
    }

    settings = replacements["app.config.settings"]
    settings.RAW_LOCAL_STORAGE_DIR = Path("raw/local")
    settings.RAW_EXTERNAL_STORAGE_DIR = Path("raw/external")
    settings.MAX_UPLOAD_FILE_SIZE = 20 * 1024 * 1024
    settings.DEFAULT_DOCUMENT_STATUS = "uploaded"
    settings.DEFAULT_DOCUMENT_VERSION = 1
    settings.DEFAULT_CREATED_BY_ACTOR_CODE = "operator"
    settings.DOCUMENT_CODE_PREFIX = "DOC"
    settings.DOCUMENT_CODE_RANDOM_LENGTH = 8

    replacements["app.modules.document.application.dto"].DocumentResult = object
    replacements[
        "app.modules.document.application.errors"
    ].DocumentApplicationError = _HTTPException
    ports = replacements["app.modules.document.application.ports"]
    ports.UploadFilePort = object
    ports.UploadMetadataPort = object
    ports.calculate_file_hash = lambda path: "hash"
    ports.cleanup_file = lambda path: True
    ports.create_document = object
    ports.create_uow = object
    ports.get_safe_extension = lambda filename: "txt"
    ports.is_integrity_error = lambda exc: isinstance(exc, _IntegrityError)
    ports.validate_content_type = lambda file: None
    replacements[
        "app.shared.observability.document_upload_logger"
    ].DocumentUploadLogger = _DocumentUploadLogger

    originals = {name: sys.modules.get(name) for name in replacements}
    sys.modules.update(replacements)
    try:
        spec = importlib.util.spec_from_file_location(
            "document_upload_service_under_test",
            SERVICE_PATH,
        )
        if spec is None or spec.loader is None:
            raise RuntimeError("无法加载待测试的文档上传 Service")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.modules.pop("document_upload_service_under_test", None)
        for name, original in originals.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


def _meta() -> SimpleNamespace:
    return SimpleNamespace(
        kb_id=1,
        domain_code="domain",
        business_scene="scene",
        title="title",
        effective_at=None,
        expired_at=None,
        risk_level=None,
    )


class _FailingStoragePath:
    def mkdir(self, *, parents: bool, exist_ok: bool) -> None:
        raise OSError("read only")


class DocumentUploadServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.service = _load_service_module()

    def test_empty_filename_is_logged_in_validate_phase(self) -> None:
        file = SimpleNamespace(filename=None)

        with self.assertRaises(self.service.HTTPException) as raised:
            asyncio.run(self.service.save_uploaded_document(file, _meta()))

        upload_logger = self.service.DocumentUploadLogger.instances[-1]
        self.assertEqual(raised.exception.status_code, 400)
        self.assertEqual(upload_logger.failed_fields["phase"], "validate")
        self.assertIsNone(upload_logger.failed_fields["filename"])
        self.assertIsNone(upload_logger.failed_fields["source_type"])
        self.assertIsNone(upload_logger.failed_fields["source_uri"])
        self.assertIsNone(upload_logger.started_fields)

    def test_storage_directory_failure_is_logged_before_upload_started(self) -> None:
        file = SimpleNamespace(filename="document.txt")
        original_external = self.service.RAW_EXTERNAL_STORAGE_DIR
        self.service.RAW_EXTERNAL_STORAGE_DIR = _FailingStoragePath()
        try:
            with self.assertRaises(OSError):
                asyncio.run(self.service.save_uploaded_document(file, _meta()))
        finally:
            self.service.RAW_EXTERNAL_STORAGE_DIR = original_external

        upload_logger = self.service.DocumentUploadLogger.instances[-1]
        self.assertEqual(
            upload_logger.failed_fields["phase"],
            "prepare_storage",
        )
        self.assertEqual(upload_logger.failed_fields["source_type"], "txt")
        self.assertIsNone(upload_logger.failed_fields["source_uri"])
        self.assertIsNone(upload_logger.started_fields)


if __name__ == "__main__":
    unittest.main()
