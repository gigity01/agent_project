import re

def clean_text(text: str) -> str:
    if not text:
        return ""

    text = re.sub(r"\n+", "\n", text)

    text = re.sub(r" +", " ", text)

    pattern = r"[^\u4e00-\u9fa5a-zA-Z0-9\s，。、；：？！‘’“”（）《》【】……——\.,;:!?\(\)\[\]\{\}/+\-=_]"
    text = re.sub(pattern, "", text)
    return text.strip()

def deduplicate_lines(text: str) -> str:
    """按行去重、过滤空行"""
    lines = [line.strip() for line in text.splitlines()]
    unique_lines = list(dict.fromkeys([l for l in lines if l]))
    return "\n".join(unique_lines)