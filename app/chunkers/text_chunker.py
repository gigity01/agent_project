"""将纯文本按段落构造父块，再按长度构造子块。"""

from app.chunkers.base import (
    BaseChunker,
    ChunkBuildInput,
    ChunkBuildResult,
    ParentBlockData,
    ChildChunkData,
)
from app.chunkers.common import (
    split_paragraphs,
    split_text_to_parent_segments,
    split_text_to_child_chunks,
)


class TextChunker(BaseChunker):
    """纯文本切块策略。"""
    def build(
        self,
        input_data: ChunkBuildInput,
    ) -> ChunkBuildResult:
        """按空行划分父块，并为每个段落生成可检索子块。"""
        text = input_data.cleaned_path.read_text(
            encoding="utf-8",
            errors="strict",
        )
        paragraphs = split_paragraphs(text)

        parents: list[ParentBlockData] = []
        children_by_parent_index: dict[int, list[ChildChunkData]] = {}
        block_index = 0

        for semantic_group_index, paragraph in enumerate(paragraphs):
            parent_segments = split_text_to_parent_segments(paragraph)

            for segment_index, parent_content in enumerate(parent_segments):
                parent = ParentBlockData(
                    block_type="paragraph",
                    title=None,
                    section_path=None,
                    content=parent_content,
                    block_index=block_index,
                    semantic_group_index=semantic_group_index,
                    segment_index=segment_index,
                )
                parents.append(parent)

                child_texts = split_text_to_child_chunks(parent_content)
                children = [
                    ChildChunkData(
                        content=child_text,
                        embedding_text=child_text,
                        chunk_index=child_index,
                        section_path=None,
                        source_row_index=None,
                        chunk_type="text",
                    )
                    for child_index, child_text in enumerate(child_texts)
                ]

                children_by_parent_index[block_index] = children
                block_index += 1

        return ChunkBuildResult(
            parents=parents,
            children_by_parent_index=children_by_parent_index,
        )
