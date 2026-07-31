"""文档模块 Markdown 文本规范化与标题提取处理器。"""

import re
from pathlib import Path
from typing import Any

from app.modules.document.infrastructure.parsing.base import (
    BaseProcessor,
    ProcessResult,
)


class MdProcessor(BaseProcessor):
    """低风险清理 Markdown，并提取 ATX 标题层级元信息。"""

    source_type = "md"

    HEADING_PATTERN = re.compile(
        r"^[ \t]{0,3}(#{1,6})[ \t]+(.+?)\s*$"
    )

    def process(
        self,
        source_path: Path,
        cleaned_path: Path,
    ) -> ProcessResult:
        """严格读取 UTF-8 Markdown，规范文本并记录标题区段。"""
        source_path = self.validate_source_path(source_path)
        cleaned_path = self.prepare_cleaned_path(cleaned_path)

        text = source_path.read_text(
            encoding="utf-8-sig",
            errors="strict",
        )

        cleaned_text = self._normalize_text(text)
        sections = self._extract_sections(cleaned_text)

        cleaned_path.write_text(cleaned_text, encoding="utf-8")

        return ProcessResult(
            source_path=source_path,
            cleaned_path=cleaned_path,
            source_type=self.source_type,
            char_count=len(cleaned_text),
            line_count=len(cleaned_text.splitlines()),
            metadata={
                "encoding": "utf-8",
                "heading_count": sum(
                    1
                    for section in sections
                    if section["heading_line"] is not None
                ),
                "section_count": len(sections),
                "sections": sections,
                "cleaning_strategy": (
                    "normalize_markdown_text_extract_heading_paths"
                ),
            },
        )

    def _normalize_text(self, text: str) -> str:
        """保留行首空白，规范换行、空行和 ATX 标题格式。"""
        text = (
            text.replace("\x00", "")
            .replace("\r\n", "\n")
            .replace("\r", "\n")
        )

        cleaned_lines: list[str] = []

        for raw_line in text.split("\n"):
            line = raw_line.rstrip()

            if not line.strip():
                if cleaned_lines and cleaned_lines[-1] != "":
                    cleaned_lines.append("")
                continue

            heading_match = self.HEADING_PATTERN.match(line)

            if heading_match:
                marks = heading_match.group(1)
                title = heading_match.group(2).strip()
                cleaned_lines.append(f"{marks} {title}")
                continue

            cleaned_lines.append(line)

        while cleaned_lines and cleaned_lines[0] == "":
            cleaned_lines.pop(0)

        while cleaned_lines and cleaned_lines[-1] == "":
            cleaned_lines.pop()

        cleaned_text = "\n".join(cleaned_lines)

        if cleaned_text:
            cleaned_text += "\n"

        return cleaned_text

    def _extract_sections(self, text: str) -> list[dict[str, Any]]:
        """按 ATX 标题切分区段，并记录标题路径与清洗后行范围。"""
        lines = text.splitlines()

        if not lines:
            return []

        sections: list[dict[str, Any]] = []
        heading_stack: list[tuple[int, str]] = []
        current_section: dict[str, Any] | None = None

        for line_number, line in enumerate(lines, start=1):
            match = self.HEADING_PATTERN.match(line)

            if match:
                if current_section is not None:
                    current_section["end_line"] = line_number - 1
                    sections.append(current_section)

                level = len(match.group(1))
                title = match.group(2).strip()

                while heading_stack and heading_stack[-1][0] >= level:
                    heading_stack.pop()

                heading_stack.append((level, title))

                current_section = {
                    "level": level,
                    "title": title,
                    "section_path": [
                        item_title for _, item_title in heading_stack
                    ],
                    "heading_line": line_number,
                    "start_line": line_number,
                    "end_line": line_number,
                }
                continue

            if current_section is None and line.strip():
                current_section = {
                    "level": None,
                    "title": None,
                    "section_path": [],
                    "heading_line": None,
                    "start_line": line_number,
                    "end_line": line_number,
                }

        if current_section is not None:
            current_section["end_line"] = len(lines)
            sections.append(current_section)

        return sections
