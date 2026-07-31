"""文档模块切块器共享的文本切分和向量文本组装函数。"""

import re

from app.modules.document.domain.policies import md5_text

PARENT_BLOCK_MAX_CHARS = 4_000
CHILD_CHUNK_MAX_CHARS = 600

CSV_PARENT_MAX_ROWS = 50
CSV_PARENT_MAX_CHARS = 12_000
CSV_CHILD_MAX_CHARS = 8_000


def normalize_text(text: str) -> str:
    """仅统一换行符并移除首尾空白，不改写 cleaned 正文格式。"""
    return (
        text.replace("\r\n", "\n")
        .replace("\r", "\n")
        .strip()
    )


def split_paragraphs(text: str) -> list[str]:
    """按空行划分非空段落。"""
    text = normalize_text(text)
    paragraphs = re.split(r"\n\s*\n", text)
    return [p.strip() for p in paragraphs if p.strip()]


def split_text_to_child_chunks(
    text: str,
    max_len: int = CHILD_CHUNK_MAX_CHARS,
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

        candidate = sentence if not current else f"{current} {sentence}"

        if len(candidate) <= max_len:
            current = candidate
        else:
            if current.strip():
                chunks.append(current.strip())
            current = sentence

    if current.strip():
        chunks.append(current.strip())

    return chunks


def split_text_to_parent_segments(
    text: str,
    max_chars: int = PARENT_BLOCK_MAX_CHARS,
) -> list[str]:
    """优先按段落切分父块，并为超长单段提供字符上限保护。"""
    text = text.strip()

    if not text:
        return []

    if len(text) <= max_chars:
        return [text]

    paragraphs = [
        item.strip()
        for item in text.split("\n\n")
        if item.strip()
    ]

    segments: list[str] = []
    current_parts: list[str] = []
    current_length = 0

    for paragraph in paragraphs:
        separator_length = 2 if current_parts else 0
        addition_length = separator_length + len(paragraph)

        if current_parts and current_length + addition_length > max_chars:
            segments.append("\n\n".join(current_parts))
            current_parts = []
            current_length = 0

        if len(paragraph) <= max_chars:
            separator_length = 2 if current_parts else 0
            current_parts.append(paragraph)
            current_length += separator_length + len(paragraph)
            continue

        if current_parts:
            segments.append("\n\n".join(current_parts))
            current_parts = []
            current_length = 0

        segments.extend(
            split_text_to_child_chunks(
                paragraph,
                max_len=max_chars,
            )
        )

    if current_parts:
        segments.append("\n\n".join(current_parts))

    return segments


def _split_long_sentence(text: str, max_len: int) -> list[str]:
    """优先在空格处分割超长句；无空格语言则交由硬切分保证长度上限。"""
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
    """在没有可用语义边界时按字符数切分，作为最后的长度保护。"""
    return [
        text[i:i + max_len].strip()
        for i in range(0, len(text), max_len)
        if text[i:i + max_len].strip()
    ]


def build_embedding_text(
    section_path: list[str] | None,
    content: str,
) -> str:
    """将章节上下文拼入待向量化文本，提升检索语义完整性。"""
    # 父块正文仍保存原始内容；这里只为检索向量补入章节语境，避免同名术语
    # 在不同章节中被编码为难以区分的孤立片段。
    if section_path:
        return f"标题路径：{'>'.join(section_path)}\n正文：{content}"

    return content
