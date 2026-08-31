"""按日期追加写入 JSONL 结构化运维事件的底层基础设施模块。

职责说明：
- 提供 `JsonlEventWriter` 类，负责将字典格式的事件数据序列化为单行 JSON 并按天（如 `prefix-2026-08-25.jsonl`）追加写入文件。
- 采用非阻断设计：即使本地磁盘或文件系统写入失败，亦仅打印标准 logger 告警，绝不反向阻断核心业务流程。
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.shared.time import now_utc_iso

logger = logging.getLogger(__name__)


class JsonlEventWriter:
    """将结构化事件以单行 JSON 追加写入日分割文件的写入器。"""

    def __init__(self, log_dir: Path, file_prefix: str) -> None:
        """初始化 JSONL 事件写入器。

        参数:
            log_dir: 日志输出目录路径。
            file_prefix: 日志文件名前缀（如 `upload`、`process`、`chunk`、`index`、`context`）。
        """
        self.log_dir = log_dir
        self.file_prefix = file_prefix

    def write(self, event: dict[str, Any]) -> bool:
        """尽力将事件字典以单行 JSON 格式追加写入文件，不阻断主业务流程。

        特性：
        - 自动注入 `created_at`（UTC ISO-8601 时间戳）。
        - 使用 `default=str` 降级序列化非标准对象。
        - 异常时捕获并使用标准日志记录错误，返回 False。

        参数:
            event: 事件字段字典。

        返回:
            bool: 写入成功返回 True，失败返回 False。
        """
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            log_path = self._get_log_path()

            # 浅拷贝字典，避免原地修改调用方的参数造成意外副作用
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
        """根据当前 UTC 日期生成当天的 JSONL 日志文件路径。

        返回:
            Path: 如 `<log_dir>/<prefix>-2026-08-25.jsonl` 的文件路径。
        """
        date_text = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return self.log_dir / f"{self.file_prefix}-{date_text}.jsonl"
