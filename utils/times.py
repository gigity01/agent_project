# app/core/time.py

import time
from datetime import datetime, timezone


def now_ms() -> int:
    """
    获取当前 Unix 时间戳，单位：毫秒。
    """
    return time.time_ns() // 1_000_000


def now_utc_iso() -> str:
    """
    获取当前 UTC 时间字符串
    """
    return datetime.now(timezone.utc).isoformat()