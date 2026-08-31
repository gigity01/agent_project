"""文档文件解析、清洗与格式转换基础设施子包。

包含：
- base.py: BaseProcessor 抽象基类。
- text.py: TxtProcessor（纯文本 NUL 剔除、换行归一化与空行折叠）。
- markdown.py: MdProcessor（Markdown ATX 标题层级解析与规范化）。
- csv.py: CsvProcessor（CSV 编码自动嗅探、方言检测与标准逗号分隔符归一化）。
- docling_client.py: DoclingClient（办公/复杂格式 PDF, DOCX, PPTX 转 Markdown 的 HTTP 客户端）。
- factory.py: get_processor 与 get_processor_output_type 处理器工厂函数。
"""
