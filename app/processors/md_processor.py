"""规范 Markdown 文本并提取标题路径元信息。"""

import re
from pathlib import Path
from typing import Any

from app.processors.base import BaseProcessor, ProcessResult


class MdProcessor(BaseProcessor):
    """清理 Markdown 文本，并为后续切块提取标题层级与章节范围。"""

    source_type = "md"

    HEADING_PATTERN = re.compile(
        r"^[ \t]{0,3}(#{1,6})[ \t]+(.+?)\s*$"
    )

    def process(self, source_path: Path, cleaned_path: Path) -> ProcessResult:
        """生成标准 UTF-8 Markdown，并返回标题路径等结构元信息。"""

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
        """执行低风险文本规范，并保留正文行首空白。"""

        text = (
            text
            .replace("\r\n", "\n")
            .replace("\r", "\n")
            .replace("\x00", "")
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
                heading_marks = heading_match.group(1)
                heading_text = heading_match.group(2).strip()
                cleaned_lines.append(f"{heading_marks} {heading_text}")
                continue

            cleaned_lines.append(line)

        while cleaned_lines and cleaned_lines[-1] == "":
            cleaned_lines.pop()

        if not cleaned_lines:
            return ""

        return "\n".join(cleaned_lines) + "\n"

    def _extract_sections(self, text: str) -> list[dict[str, Any]]:
        """按标题切分章节边界，并维护每个标题对应的完整路径。"""

        lines = text.splitlines()

        if not lines:
            return []

        sections: list[dict[str, Any]] = []
        heading_stack: list[tuple[int, str]] = []
        current_section: dict[str, Any] | None = None

        for line_number, line in enumerate(lines, start=1):
            heading_match = self.HEADING_PATTERN.match(line)

            if heading_match:
                if current_section is not None:
                    current_section["end_line"] = line_number - 1
                    sections.append(current_section)

                level = len(heading_match.group(1))
                title = heading_match.group(2).strip()

                while heading_stack and heading_stack[-1][0] >= level:
                    heading_stack.pop()

                heading_stack.append((level, title))

                current_section = {
                    "level": level,
                    "title": title,
                    "section_path": [
                        item_title
                        for _, item_title in heading_stack
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
