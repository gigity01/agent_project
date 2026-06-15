import hashlib
import re

from config.settings import CHILD_CHUNK_MAX_LEN




def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def md5_text(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def split_paragraphs(text: str) -> list[str]:
    text = normalize_text(text)
    paragraphs = re.split(r"\n\s*\n", text)
    return [p.strip() for p in paragraphs if p.strip()]


def split_text_to_child_chunks(
    text: str,
    max_len: int = CHILD_CHUNK_MAX_LEN,
) -> list[str]:
    """
    v1 子块切分规则：
    1. 优先按句末标点切。
    2. 单句过长时，按空格切。
    3. 仍然过长时，硬切。
    """
    text = normalize_text(text)

    if not text:
        return []

    sentence_endings = set("。！？；.!?;")
    sentences: list[str] = []
    buffer = ""

    for char in text:
        buffer += char
        if char in sentence_endings:
            sentence = buffer.strip()
            if sentence:
                sentences.append(sentence)
            buffer = ""

    if buffer.strip():
        sentences.append(buffer.strip())

    chunks: list[str] = []
    current = ""

    for sentence in sentences:
        if len(sentence) > max_len:
            if current.strip():
                chunks.append(current.strip())
                current = ""

            chunks.extend(_split_long_sentence(sentence, max_len))
            continue

        if len(current) + len(sentence) <= max_len:
            current += sentence
        else:
            if current.strip():
                chunks.append(current.strip())
            current = sentence

    if current.strip():
        chunks.append(current.strip())

    return chunks


def _split_long_sentence(text: str, max_len: int) -> list[str]:
    parts = text.split(" ")

    if len(parts) <= 1:
        return _hard_split(text, max_len)

    chunks: list[str] = []
    current = ""

    for part in parts:
        if len(part) > max_len:
            if current.strip():
                chunks.append(current.strip())
                current = ""
            chunks.extend(_hard_split(part, max_len))
            continue

        candidate = part if not current else current + " " + part

        if len(candidate) <= max_len:
            current = candidate
        else:
            if current.strip():
                chunks.append(current.strip())
            current = part

    if current.strip():
        chunks.append(current.strip())

    return chunks


def _hard_split(text: str, max_len: int) -> list[str]:
    return [
        text[i:i + max_len].strip()
        for i in range(0, len(text), max_len)
        if text[i:i + max_len].strip()
    ]


def build_embedding_text(
    section_path: list[str] | None,
    content: str,
) -> str:
    if section_path:
        return f"标题路径：{'>'.join(section_path)}\n正文：{content}"

    return content