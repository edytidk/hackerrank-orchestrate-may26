from __future__ import annotations

import re
from pathlib import Path

from .models import Chunk


FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]+\)")
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


def load_corpus(data_dir: Path) -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in sorted(data_dir.rglob("*.md")):
        chunks.extend(_load_document(path, data_dir))
    return _link_neighbors(chunks)


def _load_document(path: Path, data_dir: Path) -> list[Chunk]:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    metadata, body = _parse_frontmatter(raw)
    rel = path.relative_to(data_dir)
    parts = rel.parts
    company = _normalize_company(parts[0] if parts else "")
    product_area = _infer_product_area(company, parts, metadata)
    title = metadata.get("title") or _title_from_path(path)
    breadcrumbs = tuple(_parse_breadcrumbs(metadata))
    source_url = metadata.get("source_url") or metadata.get("final_url") or ""
    doc_id = str(rel)
    sections = _split_sections(_clean_markdown(body))

    chunks: list[Chunk] = []
    chunk_index = 0
    for heading_path, text in sections:
        for piece in _chunk_text(text, target_words=320, overlap_words=60):
            chunk_id = f"{doc_id}#{chunk_index}"
            chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    doc_id=doc_id,
                    company=company,
                    product_area=product_area,
                    title=title,
                    breadcrumbs=breadcrumbs,
                    source_url=source_url,
                    file_path=str(path),
                    heading_path=tuple(heading_path),
                    chunk_index=chunk_index,
                    text=piece,
                )
            )
            chunk_index += 1
    return chunks


def _parse_frontmatter(raw: str) -> tuple[dict[str, str], str]:
    match = FRONTMATTER_RE.match(raw)
    if not match:
        return {}, raw
    frontmatter = match.group(1)
    body = raw[match.end() :]
    metadata: dict[str, str] = {}
    for line in frontmatter.splitlines():
        if ":" not in line or line.startswith("  -"):
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip().strip('"')
    return metadata, body


def _parse_breadcrumbs(metadata: dict[str, str]) -> list[str]:
    raw = metadata.get("breadcrumbs", "")
    if not raw:
        return []
    return [part.strip().strip('"') for part in raw.split(">") if part.strip()]


def _normalize_company(value: str) -> str:
    lowered = value.lower()
    if "hackerrank" in lowered:
        return "HackerRank"
    if "claude" in lowered:
        return "Claude"
    if "visa" in lowered:
        return "Visa"
    return value.title() if value else "Unknown"


def _infer_product_area(
    company: str, parts: tuple[str, ...], metadata: dict[str, str]
) -> str:
    breadcrumbs = metadata.get("breadcrumbs", "")
    if breadcrumbs:
        first = breadcrumbs.split(">")[0].strip().strip('"')
        if first:
            return _slug(first)
    if company == "Visa":
        joined = "/".join(parts).lower()
        if "traveler" in joined or "traveller" in joined or "travel-support" in joined:
            return "travel_support"
        if "fraud" in joined:
            return "fraud_protection"
        if "dispute" in joined:
            return "dispute_resolution"
        if "merchant" in joined or "visa-rules" in joined or parts[-1] == "support.md":
            return "general_support"
        if len(parts) >= 3:
            return _slug(parts[2])
    if len(parts) >= 2:
        area = _slug(parts[1])
        if area == "hackerrank_community":
            return "community"
        if area == "general_help":
            return "general_help"
        return area
    return ""


def _title_from_path(path: Path) -> str:
    stem = re.sub(r"^\d+-", "", path.stem)
    return stem.replace("-", " ").replace("_", " ").title()


def _slug(value: str) -> str:
    value = value.lower().replace("&", "and")
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")


def _clean_markdown(text: str) -> str:
    text = HTML_COMMENT_RE.sub(" ", text)
    text = IMAGE_RE.sub(" ", text)
    text = LINK_RE.sub(r"\1", text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"[*_]{1,3}([^*_]+)[*_]{1,3}", r"\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _split_sections(text: str) -> list[tuple[list[str], str]]:
    sections: list[tuple[list[str], str]] = []
    heading_stack: list[str] = []
    current_lines: list[str] = []

    for line in text.splitlines():
        match = HEADING_RE.match(line)
        if match:
            if current_lines:
                sections.append((heading_stack[:], "\n".join(current_lines).strip()))
                current_lines = []
            level = len(match.group(1))
            heading = match.group(2).strip()
            heading_stack = heading_stack[: max(0, level - 1)] + [heading]
            current_lines.append(heading)
        else:
            current_lines.append(line)

    if current_lines:
        sections.append((heading_stack[:], "\n".join(current_lines).strip()))
    return [(headings, body) for headings, body in sections if body]


def _chunk_text(text: str, target_words: int, overlap_words: int) -> list[str]:
    words = text.split()
    if len(words) <= target_words:
        return [text.strip()]
    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = min(len(words), start + target_words)
        chunks.append(" ".join(words[start:end]).strip())
        if end == len(words):
            break
        start = max(end - overlap_words, start + 1)
    return chunks


def _link_neighbors(chunks: list[Chunk]) -> list[Chunk]:
    by_doc: dict[str, list[Chunk]] = {}
    for chunk in chunks:
        by_doc.setdefault(chunk.doc_id, []).append(chunk)

    previous_next: dict[str, tuple[str | None, str | None]] = {}
    for doc_chunks in by_doc.values():
        ordered = sorted(doc_chunks, key=lambda item: item.chunk_index)
        for index, chunk in enumerate(ordered):
            previous_next[chunk.chunk_id] = (
                ordered[index - 1].chunk_id if index > 0 else None,
                ordered[index + 1].chunk_id if index < len(ordered) - 1 else None,
            )

    return [
        Chunk(
            chunk_id=chunk.chunk_id,
            doc_id=chunk.doc_id,
            company=chunk.company,
            product_area=chunk.product_area,
            title=chunk.title,
            breadcrumbs=chunk.breadcrumbs,
            source_url=chunk.source_url,
            file_path=chunk.file_path,
            heading_path=chunk.heading_path,
            chunk_index=chunk.chunk_index,
            text=chunk.text,
            prev_chunk_id=previous_next[chunk.chunk_id][0],
            next_chunk_id=previous_next[chunk.chunk_id][1],
        )
        for chunk in chunks
    ]
