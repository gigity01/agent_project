"""按日期写入 JSONL 运维事件的基础设施组件。"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.shared.time import now_utc_iso


logger = logging.getLogger(__name__)


class JsonlEventWriter:
    """将结构化事件追加到指定目录下的日分割 JSONL 文件。"""

    def __init__(self, log_dir: Path, file_prefix: str) -> None:
        """设置日志目录和生成日志文件名时使用的前缀。"""
        self.log_dir = log_dir
        self.file_prefix = file_prefix

    def write(self, event: dict[str, Any]) -> bool:
        """尽力将事件以单行 JSON 追加写入，不反向阻断业务流程。

        每个事件独占一行，便于日志采集器流式读取和故障时跳过损坏行；未知对象
        通过 ``default=str`` 降级序列化。写入失败时转交标准日志并返回 ``False``。
        """
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            log_path = self._get_log_path()

            # 不修改调用方持有的字典，避免观测组件产生隐藏副作用。
            payload = dict(event)
            payload.setdefault("created_at", now_utc_iso())

            line = json.dumps(
                payload,
                ensure_ascii=False,
                default=str,
            ) + "\n"
            with log_path.open("a", encoding="utf-8") as file:
                file.write(line)
            return True
        except Exception:
            logger.exception(
                "JSONL 事件日志写入失败",
                extra={
                    "log_dir": str(self.log_dir),
                    "file_prefix": self.file_prefix,
                    "event_name": event.get("event"),
                },
            )
            return False

    def _get_log_path(self) -> Path:
        """生成当天对应的 JSONL 日志文件路径。"""
        date_text = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return self.log_dir / f"{self.file_prefix}-{date_text}.jsonl"
