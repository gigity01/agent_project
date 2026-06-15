# app/processors/txt_processor.py

from pathlib import Path

from app.processors.base import BaseProcessor, ProcessResult


class TxtProcessor(BaseProcessor):
    source_type = "txt"

    def process(self, source_path: Path, cleaned_path: Path) -> ProcessResult:

        self.validate_source_path(source_path)

        text = source_path.read_text(encoding="utf-8", errors="replace")
        cleaned_text = self._clean_text(text)

        cleaned_path.parent.mkdir(parents=True, exist_ok=True)
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