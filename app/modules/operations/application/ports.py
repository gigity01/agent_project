"""Operations Application 外部能力 Port。"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from app.modules.operations.application.dto import JsonlScanPage


LogPredicate = Callable[[dict], bool]


class JsonlLogQueryPort(Protocol):
    def scan(
        self,
        *,
        predicate: LogPredicate,
        created_from: datetime | None,
        created_to: datetime | None,
        limit: int,
        cursor: str | None = None,
        ascending: bool = False,
    ) -> JsonlScanPage:
        ...
