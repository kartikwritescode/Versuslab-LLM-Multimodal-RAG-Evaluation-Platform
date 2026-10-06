import re

DEFAULT_MAX_CHUNK_CHARS = 800


def _split_oversized_paragraph(paragraph: str, max_chars: int) -> list[str]:
    """Splits a single paragraph that exceeds max_chars on sentence boundaries."""
    # Split on sentence terminals followed by space
    sentences = re.split(r"(?<=[.!?])\s+", paragraph)
    chunks: list[str] = []
    current = ""

    for s in sentences:
        s = s.strip()
        if not s:
            continue

        if not current:
            current = s
        elif len(current) + 1 + len(s) <= max_chars:
            current += " " + s
        else:
            chunks.append(current)
            current = s

    if current:
        chunks.append(current)

    # Fallback if a single sentence without punctuation exceeds max_chars
    final_chunks: list[str] = []
    for c in chunks:
        if len(c) <= max_chars:
            final_chunks.append(c)
        else:
            for i in range(0, len(c), max_chars):
                final_chunks.append(c[i : i + max_chars])

    return final_chunks


def chunk_text(text: str, max_chunk_chars: int = DEFAULT_MAX_CHUNK_CHARS) -> list[str]:
    """Splits text into chunks by paragraphs and merges small paragraphs greedily.

    1. Normalizes line breaks.
    2. Splits on double newlines (paragraphs).
    3. Merges consecutive small paragraphs up to max_chunk_chars.
    4. Splits any single paragraph exceeding max_chunk_chars on sentence endings.
    """
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return []

    raw_paras = [p.strip() for p in re.split(r"\n\s*\n", normalized) if p.strip()]
    if not raw_paras:
        return []

    # Flatten any oversized paragraphs first
    normalized_paras: list[str] = []
    for p in raw_paras:
        if len(p) > max_chunk_chars:
            normalized_paras.extend(_split_oversized_paragraph(p, max_chunk_chars))
        else:
            normalized_paras.append(p)

    chunks: list[str] = []
    current_acc = ""

    for para in normalized_paras:
        if not current_acc:
            current_acc = para
        elif len(current_acc) + 2 + len(para) <= max_chunk_chars:
            current_acc += "\n\n" + para
        else:
            chunks.append(current_acc)
            current_acc = para

    if current_acc:
        chunks.append(current_acc)

    return chunks
