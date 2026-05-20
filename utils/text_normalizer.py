import re


class TextNormalizer:
    """文本标准化工具（所有文件分块前必须经过）"""
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def clean(self, text: str) -> str:
        if not text:
            return ""
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = text.strip()
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = '\n'.join([line.strip() for line in text.split('\n')])
        text = re.sub(r'[\x00-\x09\x0b\x0c\x0e-\x1f]', '', text)
        return text

    def merge_short_paragraphs(self, paragraphs: list, min_len: int = 100) -> list:
        """短段落合并（<100字符合并下一段）"""
        if not paragraphs:
            return []
        merged = []
        current = paragraphs[0]
        for p in paragraphs[1:]:
            if len(current) < min_len:
                current += "\n" + p
            else:
                merged.append(current)
                current = p
        merged.append(current)
        return merged


normalizer = TextNormalizer()
