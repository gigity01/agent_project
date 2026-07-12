"""按日期写入 JSONL 审计事件的基础设施组件。"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from utils.times import now_utc_iso

class JsonlEventWriter:
    """将结构化事件追加到指定目录下的日分割 JSONL 文件。"""
    def __init__(self, log_dir: Path, file_prefix: str) -> None:
        """设置日志目录和生成日志文件名时使用的前缀。"""
        self.log_dir = log_dir
        self.file_prefix = file_prefix

    def write(self, event: dict[str, Any]) -> None:
        """为事件补充创建时间并以单行 JSON 追加写入。"""
        self.log_dir.mkdir(parents=True, exist_ok=True)


        log_path = self._get_log_path()

        event.setdefault("created_at", now_utc_iso())

        with log_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(event, ensure_ascii=False, default=str))
            file.write("\n")

    def _get_log_path(self) -> Path:
        """生成当天对应的 JSONL 日志文件路径。"""
        date_text = datetime.now().strftime("%Y-%m-%d")
        return self.log_dir / f"{self.file_prefix}-{date_text}.jsonl"
