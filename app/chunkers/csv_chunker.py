"""将标准化 CSV 按数据记录生成子块，并按相邻记录批量构造父块。"""

import csv
import json

from app.chunkers.base import (
    BaseChunker,
    ChildChunkData,
    ChunkBuildInput,
    ChunkBuildResult,
    ParentBlockData,
)
from app.chunkers.common import (
    CSV_CHILD_MAX_CHARS,
    CSV_PARENT_MAX_CHARS,
    CSV_PARENT_MAX_ROWS,
)


def build_csv_child_content(record: dict[str, str]) -> str:
    """将完整记录序列化为稳定 JSON，保留空字段。"""
    return json.dumps(
        record,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def build_csv_embedding_text(record: dict[str, str]) -> str:
    """将非空字段转换为适合向量化的字段-值文本。"""
    return "\n".join(
        f"{field}：{value}"
        for field, value in record.items()
        if value
    )


class CsvChunker(BaseChunker):
    """一条 CSV 数据记录对应一个 child，相邻记录批量组成 parent。"""

    def build(self, input_data: ChunkBuildInput) -> ChunkBuildResult:
        """流式读取标准 CSV，并同时遵守父块行数和字符数上限。"""
        expected_headers = input_data.process_metadata.get("headers")

        parents: list[ParentBlockData] = []
        children_by_parent_index: dict[int, list[ChildChunkData]] = {}

        block_index = 0
        batch_records: list[dict[str, str]] = []
        batch_children: list[ChildChunkData] = []
        batch_start_row = 1

        with input_data.cleaned_path.open(
            "r",
            encoding="utf-8",
            errors="strict",
            newline="",
        ) as stream:
            reader = csv.DictReader(stream)
            headers = reader.fieldnames

            if not headers:
                raise ValueError("CSV cleaned 文件缺少表头")

            if expected_headers and headers != expected_headers:
                raise ValueError("CSV cleaned 文件表头与处理产物元信息不一致")

            for source_row_index, raw_record in enumerate(reader, start=1):
                record = {
                    header: raw_record.get(header) or ""
                    for header in headers
                }
                child_content = build_csv_child_content(record)

                if len(child_content) > CSV_CHILD_MAX_CHARS:
                    raise ValueError(
                        f"CSV 第 {source_row_index} 条记录内容过大"
                    )

                child = ChildChunkData(
                    content=child_content,
                    embedding_text=build_csv_embedding_text(record),
                    chunk_index=len(batch_children),
                    section_path=None,
                    source_row_index=source_row_index,
                    chunk_type="csv_row",
                )

                candidate_records = [*batch_records, record]
                candidate_content = self._build_parent_content(
                    headers=headers,
                    row_start=batch_start_row,
                    row_end=source_row_index,
                    records=candidate_records,
                )
                exceeds_row_limit = (
                    len(candidate_records) > CSV_PARENT_MAX_ROWS
                )
                exceeds_char_limit = (
                    len(candidate_content) > CSV_PARENT_MAX_CHARS
                )

                if batch_records and (exceeds_row_limit or exceeds_char_limit):
                    block_index = self._flush_batch(
                        parents=parents,
                        children_by_parent_index=children_by_parent_index,
                        block_index=block_index,
                        headers=headers,
                        row_start=batch_start_row,
                        row_end=source_row_index - 1,
                        records=batch_records,
                        children=batch_children,
                    )
                    batch_records = []
                    batch_children = []
                    batch_start_row = source_row_index
                    child.chunk_index = 0

                    candidate_content = self._build_parent_content(
                        headers=headers,
                        row_start=batch_start_row,
                        row_end=source_row_index,
                        records=[record],
                    )

                if (
                    not batch_records
                    and len(candidate_content) > CSV_PARENT_MAX_CHARS
                ):
                    raise ValueError(
                        f"CSV 第 {source_row_index} 条记录超过父块大小限制"
                    )

                batch_records.append(record)
                batch_children.append(child)

        if batch_records:
            self._flush_batch(
                parents=parents,
                children_by_parent_index=children_by_parent_index,
                block_index=block_index,
                headers=headers,
                row_start=batch_start_row,
                row_end=batch_start_row + len(batch_records) - 1,
                records=batch_records,
                children=batch_children,
            )

        return ChunkBuildResult(
            parents=parents,
            children_by_parent_index=children_by_parent_index,
        )

    def _flush_batch(
        self,
        *,
        parents: list[ParentBlockData],
        children_by_parent_index: dict[int, list[ChildChunkData]],
        block_index: int,
        headers: list[str],
        row_start: int,
        row_end: int,
        records: list[dict[str, str]],
        children: list[ChildChunkData],
    ) -> int:
        """将当前记录批次固化为一个父块，并返回下一个全局块序号。"""
        parent_content = self._build_parent_content(
            headers=headers,
            row_start=row_start,
            row_end=row_end,
            records=records,
        )

        parents.append(
            ParentBlockData(
                block_type="csv_rows",
                title=f"第 {row_start}-{row_end} 行",
                section_path=None,
                content=parent_content,
                block_index=block_index,
                semantic_group_index=block_index,
                segment_index=0,
            )
        )
        children_by_parent_index[block_index] = children

        return block_index + 1

    def _build_parent_content(
        self,
        *,
        headers: list[str],
        row_start: int,
        row_end: int,
        records: list[dict[str, str]],
    ) -> str:
        """构造带 schema 和记录范围的紧凑父块 JSON。"""
        return json.dumps(
            {
                "schema": headers,
                "row_start": row_start,
                "row_end": row_end,
                "records": records,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
