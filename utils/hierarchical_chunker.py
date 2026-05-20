from config.settings import CHILD_CHUNK_MAX_LEN, PARENT_CHUNK_MAX_LEN
from utils.text_normalizer import normalizer


class HierarchicalChunker:
    """
    Parent-Child 分层分块 + 标题路径增强 + 表格/代码整块保护
    """
    # 严格按你的标准
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def build_chunks(self, structure_blocks: list) -> list:
        """
        输出最终格式（直接用于向量入库）
        [{
            "parent": "完整语义块",
            "children": ["小块1","小块2"],
            "type": "section/table/code",
            "section_path": ["用户系统","登录流程"],  # 你的标题路径
            "source": "文本来源"
        }]
        """
        result = []
        for block in structure_blocks:
            content = normalizer.clean(block["content"])
            block_type = block["type"]
            path = block.get("path", [])

            # 1. 表格/代码 → 整块 Parent+Child（不切割）
            if block_type in ["table", "code"]:
                result.append({
                    "parent": content,
                    "children": [content],
                    "type": block_type,
                    "section_path": path
                })
                continue

            # 2. 章节 → 生成 Parent + 子块
            children = self._split_child(content)
            result.append({
                "parent": content,
                "children": children,
                "type": block_type,
                "section_path": path
            })
        return result

    def _split_child(self, text: str) -> list:
        """按200token切分子块（你的标准）"""
        if len(text) <= CHILD_CHUNK_MAX_LEN:
            return [text]
        chunks = []
        current = ""
        for line in text.split("\n"):
            if len(current) + len(line) < PARENT_CHUNK_MAX_LEN:
                current += line + "\n"
            else:
                chunks.append(current.strip())
                current = line + "\n"
        if current:
            chunks.append(current.strip())
        return chunks


chunker = HierarchicalChunker()
