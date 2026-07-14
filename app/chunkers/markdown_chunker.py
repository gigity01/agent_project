"""按 Markdown 标题层级构造章节父块和子块。"""

import re

from app.chunkers.base import (
    BaseChunker,
    ChunkBuildInput,
    ChunkBuildResult,
    ParentBlockData,
    ChildChunkData,
)
from app.chunkers.common import (
    split_text_to_parent_segments,
    split_text_to_child_chunks,
    build_embedding_text,
)


HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


class MarkdownChunker(BaseChunker):
    """
    MarkdownChunker v1 前提：
    - 暂不特殊处理代码块
    - 暂不特殊处理表格
    - 按 heading 维护 section_path
    """

    def build(
        self,
        input_data: ChunkBuildInput,
    ) -> ChunkBuildResult:
        """解析标题路径，并按章节生成父块与长度受限的子块。"""
        text = input_data.cleaned_path.read_text(
            encoding="utf-8",
            errors="strict",
        )
        lines = text.splitlines()

        sections = input_data.process_metadata.get("sections")

        if not sections:
            sections = self._parse_sections(lines)

        parents: list[ParentBlockData] = []
        children_by_parent_index: dict[int, list[ChildChunkData]] = {}
        block_index = 0

        for semantic_group_index, section in enumerate(sections):
            section_content = self._extract_section_content(lines, section)

            if not section_content:
                continue

            section_path = section.get("section_path") or None
            parent_segments = split_text_to_parent_segments(section_content)

            for segment_index, parent_content in enumerate(parent_segments):
                parent = ParentBlockData(
                    block_type="section",
                    title=section.get("title"),
                    section_path=section_path,
                    content=parent_content,
                    block_index=block_index,
                    semantic_group_index=semantic_group_index,
                    segment_index=segment_index,
                )
                parents.append(parent)

                child_texts = split_text_to_child_chunks(parent_content)
                children: list[ChildChunkData] = []

                for child_index, child_text in enumerate(child_texts):
                    embedding_text = build_embedding_text(
                        section_path=section_path,
                        content=child_text,
                    )

                    children.append(
                        ChildChunkData(
                            content=child_text,
                            embedding_text=embedding_text,
                            chunk_index=child_index,
                            section_path=section_path,
                            source_row_index=None,
                            chunk_type="text",
                        )
                    )

                children_by_parent_index[block_index] = children
                block_index += 1

        return ChunkBuildResult(
            parents=parents,
            children_by_parent_index=children_by_parent_index,
        )

    def _extract_section_content(
        self,
        lines: list[str],
        section: dict,
    ) -> str:
        """依据 Processor 的 1-based 行范围提取章节正文，不包含标题行。"""
        heading_line = section.get("heading_line")
        start_line = section["start_line"]
        end_line = section["end_line"]

        if heading_line is not None:
            content_start_line = heading_line + 1
        else:
            content_start_line = start_line

        return "\n".join(
            lines[content_start_line - 1:end_line]
        ).strip()

    def _parse_sections(self, lines: list[str]) -> list[dict]:
        """缺少 Processor 元信息时，按相同的 1-based 行范围重新解析章节。"""
        if not lines:
            return []

        heading_stack: list[tuple[int, str]] = []
        sections: list[dict] = []
        current_section: dict | None = None

        for line_number, line in enumerate(lines, start=1):
            match = HEADING_PATTERN.match(line)

            if match:
                if current_section is not None:
                    current_section["end_line"] = line_number - 1
                    sections.append(current_section)

                level = len(match.group(1))
                title = match.group(2).strip()

                # 栈只保留当前标题的祖先；同级或更深标题出现时，先移除已结束的
                # 分支，再由剩余栈构造稳定的 section_path。
                while heading_stack and heading_stack[-1][0] >= level:
                    heading_stack.pop()

                heading_stack.append((level, title))

                current_section = {
                    "level": level,
                    "title": title,
                    "section_path": [item[1] for item in heading_stack],
                    "heading_line": line_number,
                    "start_line": line_number,
                    "end_line": line_number,
                }
                continue

            if current_section is None and line.strip():
                current_section = {
                    "level": None,
                    "title": None,
                    "section_path": [],
                    "heading_line": None,
                    "start_line": line_number,
                    "end_line": line_number,
                }

        if current_section is not None:
            current_section["end_line"] = len(lines)
            sections.append(current_section)

        return sections
