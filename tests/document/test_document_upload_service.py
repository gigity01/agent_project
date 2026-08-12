"""上传前置校验和存储准备进入日志异常边界的测试。"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT_DIR = Path(__file__).resolve().parents[2]
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
        "app.modules.document.application.dto": types.ModuleType(
            "app.modules.document.application.dto"
        ),
        "app.modules.document.application.errors": types.ModuleType(
            "app.modules.document.application.errors"
        ),
        "app.modules.document.application.ports": types.ModuleType(
            "app.modules.document.application.ports"
        ),
        "app.modules.document.application.settings": types.ModuleType(
            "app.modules.document.application.settings"
        ),
        "app.shared.observability.document_upload_logger": types.ModuleType(
            "app.shared.observability.document_upload_logger"
        ),
    }

    replacements["app.modules.document.application.dto"].DocumentResult = object
    replacements[
        "app.modules.document.application.errors"
    ].DocumentApplicationError = _HTTPException
    ports = replacements["app.modules.document.application.ports"]
    ports.DocumentApplicationPorts = object
    ports.UploadFilePort = object
    ports.UploadMetadataPort = object
    replacements[
        "app.modules.document.application.settings"
    ].DocumentUploadSettings = object
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
        module.test_ports = SimpleNamespace(
            validate_content_type=lambda file: None,
            get_safe_extension=lambda filename: "txt",
            calculate_file_hash=lambda path: "hash",
            cleanup_file=lambda path: True,
            uow_factory=object,
            document_factory=object,
            is_integrity_error=lambda exc: isinstance(exc, _IntegrityError),
        )
        module.test_settings = SimpleNamespace(
            raw_local_storage_dir=Path("raw/local"),
            raw_external_storage_dir=Path("raw/external"),
            max_upload_file_size=20 * 1024 * 1024,
            default_document_status="uploaded",
            default_document_version=1,
            default_created_by_actor_code="operator",
            document_code_prefix="DOC",
            document_code_random_length=8,
        )
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
        cls.use_case = cls.service.UploadDocumentUseCase(
            ports=cls.service.test_ports,
            settings=cls.service.test_settings,
        )

    def test_empty_filename_is_logged_in_validate_phase(self) -> None:
        file = SimpleNamespace(filename=None)

        with self.assertRaises(self.service.DocumentApplicationError) as raised:
            asyncio.run(self.use_case.execute(file, _meta()))

        upload_logger = self.service.DocumentUploadLogger.instances[-1]
        self.assertEqual(raised.exception.status_code, 400)
        self.assertEqual(upload_logger.failed_fields["phase"], "validate")
        self.assertIsNone(upload_logger.failed_fields["filename"])
        self.assertIsNone(upload_logger.failed_fields["source_type"])
        self.assertIsNone(upload_logger.failed_fields["source_uri"])
        self.assertIsNone(upload_logger.started_fields)

    def test_storage_directory_failure_is_logged_before_upload_started(self) -> None:
        file = SimpleNamespace(filename="document.txt")
        original_external = self.service.test_settings.raw_external_storage_dir
        self.service.test_settings.raw_external_storage_dir = (
            _FailingStoragePath()
        )
        try:
            with self.assertRaises(OSError):
                asyncio.run(self.use_case.execute(file, _meta()))
        finally:
            self.service.test_settings.raw_external_storage_dir = (
                original_external
            )

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
