import json
from datetime import datetime
from pathlib import Path
from typing import Any
from utils.times import now_utc_iso

class JsonlEventWriter:
    def __init__(self, log_dir: Path, file_prefix: str) -> None:
        self.log_dir = log_dir
        self.file_prefix = file_prefix

    def write(self, event: dict[str, Any]) -> None:
        self.log_dir.mkdir(parents=True, exist_ok=True)


        log_path = self._get_log_path()

        event.setdefault("created_at", now_utc_iso())

        with log_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(event, ensure_ascii=False, default=str))
            file.write("\n")

    def _get_log_path(self) -> Path:
        date_text = datetime.now().strftime("%Y-%m-%d")
        return self.log_dir / f"{self.file_prefix}-{date_text}.jsonl"