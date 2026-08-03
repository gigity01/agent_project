"""受控目录下日分割 JSONL 的只读查询 Repository。"""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.modules.operations.application.dto import JsonlScanPage
from app.modules.operations.application.errors import OperationsQueryError
from app.modules.operations.application.ports import LogPredicate


@dataclass(frozen=True)
class JsonlLogSource:
    source_id: str
    directory: Path
    file_prefix: str


@dataclass(frozen=True)
class _IndexedEvent:
    event: dict[str, Any]
    sort_key: tuple[str, str, str, str, int]


class JsonlLogRepository:
    """只扫描 Bootstrap 注入的固定目录和文件前缀。"""

    def __init__(self, sources: tuple[JsonlLogSource, ...]) -> None:
        self._sources = sources

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
        if limit < 1:
            raise OperationsQueryError(400, "limit 必须大于 0")
        cursor_key = self._decode_cursor(cursor, ascending=ascending)
        indexed: list[_IndexedEvent] = []
        for source in self._sources:
            indexed.extend(
                self._read_source(
                    source,
                    predicate=predicate,
                    created_from=created_from,
                    created_to=created_to,
                )
            )
        indexed.sort(key=lambda item: item.sort_key, reverse=not ascending)
        if cursor_key is not None:
            if ascending:
                indexed = [item for item in indexed if item.sort_key > cursor_key]
            else:
                indexed = [item for item in indexed if item.sort_key < cursor_key]

        page = indexed[: limit + 1]
        has_more = len(page) > limit
        page = page[:limit]
        next_cursor = None
        if has_more and page:
            next_cursor = self._encode_cursor(
                page[-1].sort_key,
                ascending=ascending,
            )
        return JsonlScanPage(
            events=[item.event for item in page],
            next_cursor=next_cursor,
        )

    def _read_source(
        self,
        source: JsonlLogSource,
        *,
        predicate: LogPredicate,
        created_from: datetime | None,
        created_to: datetime | None,
    ) -> list[_IndexedEvent]:
        directory = source.directory.resolve()
        if not directory.is_dir():
            return []
        events: list[_IndexedEvent] = []
        pattern = f"{source.file_prefix}-*.jsonl"
        try:
            paths = sorted(directory.glob(pattern))
        except OSError:
            raise OperationsQueryError(503, "日志目录读取失败") from None
        for path in paths:
            if path.is_symlink() or not path.is_file():
                continue
            resolved = path.resolve()
            if resolved.parent != directory:
                continue
            events.extend(
                self._read_file(
                    source,
                    resolved,
                    predicate=predicate,
                    created_from=created_from,
                    created_to=created_to,
                )
            )
        return events

    def _read_file(
        self,
        source: JsonlLogSource,
        path: Path,
        *,
        predicate: LogPredicate,
        created_from: datetime | None,
        created_to: datetime | None,
    ) -> list[_IndexedEvent]:
        events: list[_IndexedEvent] = []
        try:
            with path.open("r", encoding="utf-8") as file:
                for line_number, line in enumerate(file, start=1):
                    indexed = self._parse_line(
                        source,
                        path.name,
                        line_number,
                        line,
                    )
                    if indexed is None:
                        continue
                    created_at = self._parse_datetime(
                        indexed.event.get("created_at")
                    )
                    if created_at is None:
                        continue
                    if created_from is not None and created_at < self._utc(
                        created_from
                    ):
                        continue
                    if created_to is not None and created_at > self._utc(
                        created_to
                    ):
                        continue
                    if predicate(indexed.event):
                        events.append(indexed)
        except OSError:
            raise OperationsQueryError(503, "日志文件读取失败") from None
        return events

    def _parse_line(
        self,
        source: JsonlLogSource,
        filename: str,
        line_number: int,
        line: str,
    ) -> _IndexedEvent | None:
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            return None
        if not isinstance(event, dict):
            return None
        created_at = self._parse_datetime(event.get("created_at"))
        if created_at is None:
            return None
        event_id = str(event.get("event_id") or "")
        return _IndexedEvent(
            event=event,
            sort_key=(
                created_at.isoformat(),
                event_id,
                source.source_id,
                filename,
                line_number,
            ),
        )

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if not isinstance(value, str):
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return JsonlLogRepository._utc(parsed)

    @staticmethod
    def _utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _encode_cursor(
        self,
        sort_key: tuple[str, str, str, str, int],
        *,
        ascending: bool,
    ) -> str:
        payload = json.dumps(
            {
                "version": 1,
                "ascending": ascending,
                "sources": self._source_signature,
                "key": sort_key,
            },
            separators=(",", ":"),
        ).encode("utf-8")
        return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")

    def _decode_cursor(
        self,
        cursor: str | None,
        *,
        ascending: bool,
    ) -> tuple[str, str, str, str, int] | None:
        if cursor is None:
            return None
        try:
            padding = "=" * (-len(cursor) % 4)
            payload = json.loads(
                base64.urlsafe_b64decode(cursor + padding).decode("utf-8")
            )
            key = payload["key"]
            if (
                payload.get("version") != 1
                or payload.get("ascending") is not ascending
                or payload.get("sources") != self._source_signature
                or not isinstance(key, list)
                or len(key) != 5
                or not isinstance(key[4], int)
                or not all(isinstance(value, str) for value in key[:4])
            ):
                raise ValueError
            return key[0], key[1], key[2], key[3], key[4]
        except (
            ValueError,
            KeyError,
            TypeError,
            UnicodeDecodeError,
            binascii.Error,
            json.JSONDecodeError,
        ):
            raise OperationsQueryError(400, "日志查询 cursor 无效") from None

    @property
    def _source_signature(self) -> list[str]:
        return [
            f"{source.source_id}:{source.file_prefix}"
            for source in self._sources
        ]
