"""Docling HTTP 服务的文件转 Markdown 客户端。"""

from pathlib import Path
from typing import Any

import requests

from app.app_config.settings import (
    DOCLING_CONVERT_ENDPOINT,
    DOCLING_OUTPUT_TYPE,
    DOCLING_TIMEOUT_SECONDS,
)
from app.schemas.markdownconvert import MarkdownConvertResult


class DoclingClient:
    """封装 Docling 转换请求、响应校验和异常转换。"""
    provider = "docling"

    def __init__(
        self,
        convert_endpoint: str = DOCLING_CONVERT_ENDPOINT,
        timeout_seconds: int = DOCLING_TIMEOUT_SECONDS,
    ) -> None:
        """配置转换服务地址与请求超时时间。"""
        self.convert_endpoint = convert_endpoint.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def convert_to_markdown(
        self,
        source_path: Path,
        source_type: str,
        *,
        do_ocr: bool = False,
        table_mode: str = "fast",
    ) -> MarkdownConvertResult:
        """上传文件至 Docling，并返回非空的 Markdown 转换结果。"""
        self._validate_source_path(source_path)

        normalized_source_type = self._normalize_format(source_type)

        payload = self._request_convert(
            source_path=source_path,
            source_format=normalized_source_type,
            do_ocr=do_ocr,
            table_mode=table_mode,
        )

        status = payload.get("status")

        if status not in {"success", "partial_success"}:
            errors = payload.get("errors") or payload.get("warnings")
            raise RuntimeError(
                f"Docling convert failed. status={status}, errors={errors}"
            )

        markdown = payload.get("document", {}).get("md_content")

        if not markdown or not markdown.strip():
            warnings = payload.get("warnings")
            raise RuntimeError(
                f"Docling markdown empty. status={status}, warnings={warnings}"
            )

        return MarkdownConvertResult(
            source_path=source_path,
            source_format=normalized_source_type,
            markdown=markdown.strip() + "\n",
            provider=self.provider,
            status=status,
            metadata={
                "warnings": payload.get("warnings"),
                "errors": payload.get("errors"),
                "output_type": DOCLING_OUTPUT_TYPE,
                "do_ocr": do_ocr,
                "table_mode": table_mode,
            },
        )

    def _request_convert(
            self,
            *,
            source_path: Path,
            source_format: str,
            do_ocr: bool = False,
            table_mode: str = "fast",
    ) -> dict[str, Any]:
        """发送 multipart 转换请求，并将网络或响应错误包装为运行时异常。"""
        url = self.convert_endpoint

        try:
            with source_path.open("rb") as file:
                response = requests.post(
                    url=url,
                    files={
                        "files": (
                            source_path.name,
                            file,
                            "application/octet-stream",
                        )
                    },
                    data={
                        "from_formats": source_format,
                        "to_formats": DOCLING_OUTPUT_TYPE,
                        "do_ocr": str(do_ocr).lower(),
                        "image_export_mode": "placeholder",
                        "table_mode": table_mode,
                    },
                    timeout=self.timeout_seconds,
                )

            response.raise_for_status()
            return response.json()

        except requests.Timeout as exc:
            raise RuntimeError(
                f"Docling request timeout. url={url}, source_format={source_format}"
            ) from exc

        except requests.RequestException as exc:
            raise RuntimeError(
                f"Docling request failed. url={url}, source_format={source_format}"
            ) from exc

        except ValueError as exc:
            raise RuntimeError(
                f"Docling response is not valid JSON. url={url}, source_format={source_format}"
            ) from exc




    def _validate_source_path(self, source_path: Path) -> None:
        """确认待上传给转换服务的路径是存在的普通文件。"""
        if not source_path.exists():
            raise FileNotFoundError(f"源文件不存在: {source_path}")

        if not source_path.is_file():
            raise ValueError(f"源路径不是有效文件: {source_path}")

    def _normalize_format(self, source_type: str) -> str:
        """去除扩展名前导点并归一化大小写。"""
        return source_type.lower().lstrip(".")
