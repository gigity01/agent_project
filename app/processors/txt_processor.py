"""纯文本文件的换行、空白行标准化处理器。"""

from pathlib import Path

from app.processors.base import BaseProcessor, ProcessResult


class TxtProcessor(BaseProcessor):
    """保留段落边界并清理多余空白的 TXT 处理器。"""
    source_type = "txt"

    def process(self, source_path: Path, cleaned_path: Path) -> ProcessResult:
        """读取 UTF-8 文本，清洗后写入目标路径。"""

        source_path = self.validate_source_path(source_path)
        cleaned_path = self.prepare_cleaned_path(cleaned_path)

        text = source_path.read_text(encoding="utf-8", errors="replace")
        cleaned_text = self._clean_text(text)

        cleaned_path.write_text(cleaned_text, encoding="utf-8")

        return ProcessResult(
            source_path=source_path,
            cleaned_path=cleaned_path,
            source_type=self.source_type,
            char_count=len(cleaned_text),
            line_count=len(cleaned_text.splitlines()),
            metadata={
                "encoding": "utf-8",
                "cleaning_strategy": "normalize_newlines_strip_lines_keep_paragraphs",
            }
        )

    def _clean_text(self, text: str) -> str:
        """统一换行，去除行首尾空白并最多保留一个空行。"""
        text = text.replace("\r\n", "\n").replace("\r", "\n")

        cleaned_lines = []
        blank_line_count = 0
        for line in text.split("\n"):
            line = line.strip()
            if not line:
                blank_line_count += 1
                if blank_line_count <= 1:
                    cleaned_lines.append("")
                continue
            blank_line_count = 0
            cleaned_lines.append(line)
        cleaned_text = "\n".join(cleaned_lines)
        return cleaned_text
