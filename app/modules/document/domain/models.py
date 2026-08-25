"""文档处理与切块领域的内存数据模型定义。

包含文本清洗结果、Markdown 转换结果、切块输入参数以及未持久化的父语义块/子切块实体。
本模块纯粹基于 Python 标准库与 Pydantic/dataclasses，不依赖外部数据库与存储实现。
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProcessResult(BaseModel):
    """文档格式转换与文本清洗阶段的输出结果对象。

    Attributes:
        source_path: 处理所针对的源文件绝对路径。
        cleaned_path: 清洗后生成的标准化文本文件绝对路径（通常位于 staging 目录中）。
        source_type: 源文件的标准化扩展名格式（如 'txt', 'md', 'csv' 等）。
        char_count: 清洗后文本的总字符数统计。
        line_count: 清洗后文本的总行数统计。
        metadata: 清洗过程中提取或记录的附加元数据（如编码格式、分行统计等）。
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)
    source_path: Path
    cleaned_path: Path
    source_type: str
    char_count: int = 0
    line_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class MarkdownConvertResult(BaseModel):
    """外部文档解析转换服务（如 Docling）将复杂办公格式转为 Markdown 后的中间结果对象。

    Attributes:
        source_path: 被转换的原始文件路径（PDF/DOCX/PPTX 等）。
        source_format: 原始文件格式。
        markdown: 转换后提取出的 Markdown 纯文本正文内容。
        provider: 转换提供方标识（如 'docling'）。
        status: 转换执行状态（如 'succeeded', 'failed'）。
        metadata: 转换器输出的额外信息（如提取的页数、表格数、版面结构等）。
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)
    source_path: Path
    source_format: str
    markdown: str
    provider: str
    status: str
    metadata: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True)
class ChunkBuildInput:
    """切块引擎构建父子语义块所需的输入上下文。

    Attributes:
        cleaned_path: 已清洗完成的标准文本文件绝对路径。
        document_title: 文档标题（用于丰富子块 embedding_text 上下文）。
        business_scene: 业务场景标识（用于特定场景下的上下文构造）。
        process_metadata: 处理阶段传递下来的元数据字典。
    """

    cleaned_path: Path
    document_title: str
    business_scene: str | None
    process_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParentBlockData:
    """内存中尚未持久化的父级语义块（Parent Block）数据。

    父块承载较大颗粒度的完整语义上下文（如一个完整的标题章节或段落组），供检索重排或大模型生成时引用。

    Attributes:
        block_type: 父块类型（如 'section', 'paragraph_group', 'table_group' 等）。
        title: 父块标题或章节名称。
        section_path: 从根到当前层级的章节层级面包屑路径列表。
        content: 父块完整正文内容。
        block_index: 在文档所有父块中的全局 0-based 连续序号。
        semantic_group_index: 语义分组序号。
        segment_index: 文档大段分片序号。
    """

    block_type: str
    title: str | None
    section_path: list[str] | None
    content: str
    block_index: int
    semantic_group_index: int
    segment_index: int


@dataclass
class ChildChunkData:
    """内存中尚未持久化、用于向量化检索的子切块（Child Chunk）数据。

    子块由父块进一步细分切分而成，用于精确的 Embedding 计算与高维向量相似度检索。

    Attributes:
        content: 子块原始正文内容。
        embedding_text: 实际送入 Embedding 模型计算向量的富文本（通常包含文档标题、路径前缀与正文）。
        chunk_index: 在该文档所有子块中的全局 0-based 连续序号。
        section_path: 子块所属的标题路径层级。
        source_row_index: 若源为 CSV/表格，记录对应的原始数据行号。
        chunk_type: 子块类型（默认为 'text'，CSV 则为 'csv_row' 等）。
    """

    content: str
    embedding_text: str
    chunk_index: int
    section_path: list[str] | None = None
    source_row_index: int | None = None
    chunk_type: str = "text"


@dataclass
class ChunkBuildResult:
    """切块引擎单次切块产生的完整父块集合与子块关联映射。

    Attributes:
        parents: 构建出的父级语义块列表。
        children_by_parent_index: 按父块序号（ParentBlockData.block_index）索引的子块列表字典。
    """

    parents: list[ParentBlockData]
    children_by_parent_index: dict[int, list[ChildChunkData]]
