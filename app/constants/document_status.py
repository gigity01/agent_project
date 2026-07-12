"""上传生命周期日志使用的文档阶段枚举。"""

from enum import Enum


class DocumentStatus(str, Enum):
    """表示文档在上传、处理、切块和索引流程中的阶段。"""
    UPLOADED = "uploaded"      # 已上传：源文件已保存
    PROCESSING = "processing"  # 处理中：清洗 / 转换 / 解析中
    PROCESSED = "processed"    # 已处理：已有 cleaned 文件，可进入切块
    CHUNKING = "chunking"      # 切块中：文档正在切分
    INDEXED = "indexed"        # 已入库：已写入知识库 / 向量库，可检索

    FAILED = "failed"          # 失败：上传、处理、切块、入库任一阶段失败
    EXPIRED = "expired"        # 已过期：旧版本被新版本替代，不再作为有效文档
