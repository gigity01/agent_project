"""文档分词与切块基础设施子包。

实现父级语义块（Parent Block，最大 4000 字符）与可向量化子块（Child Chunk，最大 600 字符；CSV 最大 8000 字符）的分层切块。
包含：
- base.py: BaseChunker 抽象基类。
- common.py: 共享文本归一化、标点/段落/硬切分与向量待编码文本拼接工具。
- text.py: TextChunker（纯文本按空行/段落切分）。
- markdown.py: MarkdownChunker（按 Markdown 标题维护 section_path 与章节父块）。
- csv.py: CsvChunker（按 CSV 数据行切子块，最多 50 行/12000 字符批处理聚合父块）。
- factory.py: get_chunker 工厂函数。
"""
