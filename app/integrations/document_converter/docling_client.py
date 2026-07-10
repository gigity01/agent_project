from pathlib import Path
from typing import Any

import requests

from app.app_config.settings import DOCLING_OUTPUT_TYPE, DOCLING_SERVER_URL
from app.schemas.markdownconvert import MarkdownConvertResult


class DoclingClient:
    provider = "docling"

    def __init__(
        self,
        base_url: str = DOCLING_SERVER_URL,
        timeout_seconds: int = 100,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def convert_to_markdown(
        self,
        source_path: Path,
        source_type: str,
        *,
        do_ocr: bool = False,
        table_mode: str = "fast",
    ) -> MarkdownConvertResult:
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
        url = f"{self.base_url}/v1/convert/file"

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
        if not source_path.exists():
            raise FileNotFoundError(f"源文件不存在: {source_path}")

        if not source_path.is_file():
            raise ValueError(f"源路径不是有效文件: {source_path}")

    def _normalize_format(self, source_type: str) -> str:
        return source_type.lower().lstrip(".")