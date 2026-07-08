# app/constants/document_status.py

from enum import Enum


class DocumentStatus(str, Enum):
    UPLOADED = "uploaded"      # 已上传：源文件已保存
    PROCESSING = "processing"  # 处理中：清洗 / 转换 / 解析中
    CHUNKING = "chunking"      # 切块中：文档正在切分
    INDEXED = "indexed"        # 已入库：已写入知识库 / 向量库，可检索

    FAILED = "failed"          # 失败：上传、处理、切块、入库任一阶段失败
    EXPIRED = "expired"        # 已过期：旧版本被新版本替代，不再作为有效文档