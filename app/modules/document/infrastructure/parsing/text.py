"""文档模块纯文本文件标准化处理器。"""

from pathlib import Path

from app.modules.document.infrastructure.parsing.base import (
    BaseProcessor,
    ProcessResult,
)


class TxtProcessor(BaseProcessor):
    """保留行首缩进和段落边界的 TXT 处理器。"""

    source_type = "txt"

    def process(
        self,
        source_path: Path,
        cleaned_path: Path,
    ) -> ProcessResult:
        """严格读取 UTF-8 文本，清洗后写入目标路径。"""
        source_path = self.validate_source_path(source_path)
        cleaned_path = self.prepare_cleaned_path(cleaned_path)

        text = source_path.read_text(
            encoding="utf-8-sig",
            errors="strict",
        )
        cleaned_text, metadata = self._clean_text(text)

        cleaned_path.write_text(cleaned_text, encoding="utf-8")

        return ProcessResult(
            source_path=source_path,
            cleaned_path=cleaned_path,
            source_type=self.source_type,
            char_count=len(cleaned_text),
            line_count=len(cleaned_text.splitlines()),
            metadata=metadata,
        )

    def _clean_text(self, text: str) -> tuple[str, dict]:
        """规范换行和空行，仅移除每行行尾空白。"""
        text = (
            text.replace("\x00", "")
            .replace("\r\n", "\n")
            .replace("\r", "\n")
        )

        cleaned_lines: list[str] = []
        blank_line_count = 0

        for raw_line in text.split("\n"):
            line = raw_line.rstrip()

            if not line.strip():
                blank_line_count += 1

                if cleaned_lines and cleaned_lines[-1] != "":
                    cleaned_lines.append("")

                continue

            cleaned_lines.append(line)

        while cleaned_lines and cleaned_lines[0] == "":
            cleaned_lines.pop(0)

        while cleaned_lines and cleaned_lines[-1] == "":
            cleaned_lines.pop()

        cleaned_text = "\n".join(cleaned_lines)

        if cleaned_text:
            cleaned_text += "\n"

        paragraph_count = len(
            [
                paragraph
                for paragraph in cleaned_text.strip().split("\n\n")
                if paragraph.strip()
            ]
        )

        return cleaned_text, {
            "encoding": "utf-8",
            "paragraph_count": paragraph_count,
            "blank_line_count": blank_line_count,
            "cleaning_strategy": (
                "normalize_newlines_remove_nul_"
                "rstrip_lines_collapse_blank_lines"
            ),
        }
