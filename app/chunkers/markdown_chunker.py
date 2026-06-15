import re

from app.chunkers.base import (
    BaseChunker,
    ChunkBuildResult,
    ParentBlockData,
    ChildChunkData,
)
from app.chunkers.common import (
    normalize_text,
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
        text: str,
        document_title: str,
        business_scene: str | None,
    ) -> ChunkBuildResult:
        text = normalize_text(text)
        lines = text.split("\n")

        sections = self._parse_sections(lines)

        parents: list[ParentBlockData] = []
        children_by_parent_index: dict[int, list[ChildChunkData]] = {}

        for parent_index, section in enumerate(sections):
            parent = ParentBlockData(
                block_type="section",
                title=section["title"],
                section_path=section["section_path"],
                content=section["content"],
                block_index=parent_index,
            )
            parents.append(parent)

            child_texts = split_text_to_child_chunks(section["content"])
            children: list[ChildChunkData] = []

            for child_index, child_text in enumerate(child_texts):
                embedding_text = build_embedding_text(
                    section_path=section["section_path"],
                    content=child_text,
                )

                children.append(
                    ChildChunkData(
                        content=child_text,
                        embedding_text=embedding_text,
                        chunk_index=child_index,
                    )
                )

            children_by_parent_index[parent_index] = children

        return ChunkBuildResult(
            parents=parents,
            children_by_parent_index=children_by_parent_index,
        )

    def _parse_sections(self, lines: list[str]) -> list[dict]:
        heading_stack: list[tuple[int, str]] = []
        current_title: str | None = None
        current_path: list[str] = []
        current_content_lines: list[str] = []

        sections: list[dict] = []

        def flush_current_section() -> None:
            nonlocal current_title, current_path, current_content_lines

            content = "\n".join(current_content_lines).strip()

            if current_title and content:
                sections.append(
                    {
                        "title": current_title,
                        "section_path": current_path.copy(),
                        "content": content,
                    }
                )

            current_content_lines = []

        for line in lines:
            match = HEADING_PATTERN.match(line)

            if match:
                flush_current_section()

                level = len(match.group(1))
                title = match.group(2).strip()

                while heading_stack and heading_stack[-1][0] >= level:
                    heading_stack.pop()

                heading_stack.append((level, title))

                current_title = title
                current_path = [item[1] for item in heading_stack]
                continue

            current_content_lines.append(line)

        flush_current_section()

        # 如果整篇 md 没有 heading，降级成一个普通 section
        if not sections:
            content = "\n".join(lines).strip()
            if content:
                sections.append(
                    {
                        "title": None,
                        "section_path": None,
                        "content": content,
                    }
                )

        return sections