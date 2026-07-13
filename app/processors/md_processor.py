"""尽量保留 Markdown 标题和表格结构的清洗处理器。"""

import re
from pathlib import Path

from app.processors.base import BaseProcessor, ProcessResult


class MdProcessor(BaseProcessor):
    """对 Markdown 执行空白规范化，同时保留标题与表格语义。"""
    source_type = "md"

    HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+)$")
    TABLE_SEPARATOR_PATTERN = re.compile(
        r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$"
    )

    def process(self, source_path: Path, cleaned_path: Path) -> ProcessResult:
        """读取 Markdown、清洗并记录标题和表格数量。"""
        self.validate_source_path(source_path)

        text = source_path.read_text(encoding="utf-8", errors="replace")

        cleaned_text, metadata = self._clean_markdown(text)

        cleaned_path.parent.mkdir(parents=True, exist_ok=True)
        cleaned_path.write_text(cleaned_text, encoding="utf-8")

        return ProcessResult(
            source_path=source_path,
            cleaned_path=cleaned_path,
            source_type=self.source_type,
            char_count=len(cleaned_text),
            line_count=len(cleaned_text.splitlines()),
            metadata=metadata,
        )

    def _clean_markdown(self, text: str) -> tuple[str, dict]:
        """规范正文、标题和连续表格行，返回清洗内容及统计信息。"""
        text = text.replace("\r\n", "\n").replace("\r", "\n")

        lines = text.split("\n")
        cleaned_lines: list[str] = []

        heading_count = 0
        table_count = 0
        blank_line_count = 0

        index = 0

        while index < len(lines):
            line = lines[index].rstrip()
            stripped_line = line.strip()

            if not stripped_line:
                blank_line_count += 1

                if blank_line_count <= 1:
                    cleaned_lines.append("")

                index += 1
                continue

            blank_line_count = 0

            # 表格按完整块处理，防止逐行空白清洗破坏列分隔符和表格连续性。
            if self._is_table_start(lines, index):
                table_lines, next_index = self._collect_table_block(lines, index)
                cleaned_lines.extend(table_lines)
                cleaned_lines.append("")

                table_count += 1
                index = next_index
                continue

            heading_match = self.HEADING_PATTERN.match(stripped_line)

            if heading_match:
                heading_count += 1

                heading_marks = heading_match.group(1)
                heading_text = heading_match.group(2).strip()

                cleaned_lines.append(f"{heading_marks} {heading_text}")
                index += 1
                continue

            cleaned_lines.append(stripped_line)
            index += 1

        cleaned_text = "\n".join(cleaned_lines).strip() + "\n"

        metadata = {
            "heading_count": heading_count,
            "table_count": table_count,
            "cleaning_strategy": "markdown_structure_preserved",
        }

        return cleaned_text, metadata

    def _is_table_start(self, lines: list[str], index: int) -> bool:
        """通过表头后的分隔行判断当前位置是否为 Markdown 表格。"""
        if index + 1 >= len(lines):
            return False

        current_line = lines[index].strip()
        next_line = lines[index + 1].strip()

        if "|" not in current_line:
            return False

        return bool(self.TABLE_SEPARATOR_PATTERN.match(next_line))

    def _collect_table_block(
        self,
        lines: list[str],
        start_index: int,
    ) -> tuple[list[str], int]:
        """收集连续表格行，并返回下一段正文的起始下标。"""
        table_lines: list[str] = []
        index = start_index

        # 仅连续收集含竖线的行；遇到空行或普通正文后交回外层循环继续处理。
        while index < len(lines):
            line = lines[index].strip()

            if not line:
                break

            if "|" not in line:
                break

            table_lines.append(self._clean_table_line(line))
            index += 1

        return table_lines, index

    def _clean_table_line(self, line: str) -> str:
        """统一单行表格单元格两侧的空白和竖线格式。"""
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]

        return "| " + " | ".join(cells) + " |"
