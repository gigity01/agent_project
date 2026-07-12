"""将纯文本按段落构造父块，再按长度构造子块。"""

from app.chunkers.base import (
    BaseChunker,
    ChunkBuildResult,
    ParentBlockData,
    ChildChunkData,
)
from app.chunkers.common import (
    split_paragraphs,
    split_text_to_child_chunks,
    build_embedding_text,
)


class TextChunker(BaseChunker):
    """纯文本切块策略。"""
    def build(
        self,
        text: str,
        document_title: str,
        business_scene: str | None,
    ) -> ChunkBuildResult:
        """按空行划分父块，并为每个段落生成可检索子块。"""
        paragraphs = split_paragraphs(text)

        parents: list[ParentBlockData] = []
        children_by_parent_index: dict[int, list[ChildChunkData]] = {}

        for parent_index, paragraph in enumerate(paragraphs):
            parent = ParentBlockData(
                block_type="paragraph",
                title=None,
                section_path=None,
                content=paragraph,
                block_index=parent_index,
            )
            parents.append(parent)

            child_texts = split_text_to_child_chunks(paragraph)
            children: list[ChildChunkData] = []

            for child_index, child_text in enumerate(child_texts):
                embedding_text = build_embedding_text(

                    section_path=None,
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
