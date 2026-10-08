import hashlib
import re
from pathlib import Path

from opspilot.domain.models import PolicyChunk

MAX_FILE_BYTES = 256 * 1024
MAX_CORPUS_FILES = 50


def load_chunks(folder: Path) -> tuple[list[PolicyChunk], str]:
    """Load controlled local Markdown/TXT, both requiring YAML-like scalar metadata."""
    paths = sorted(p for p in folder.iterdir() if p.is_file())
    if not paths or len(paths) > MAX_CORPUS_FILES:
        raise ValueError("Corpus must contain 1–50 documents")
    chunks, digest, identifiers = [], hashlib.sha256(), set()
    for path in paths:
        if path.is_symlink() or path.suffix.lower() not in {".md", ".txt"}:
            raise ValueError("Only regular Markdown/TXT documents are supported")
        if path.stat().st_size > MAX_FILE_BYTES:
            raise ValueError("Document exceeds 256 KiB")
        raw = path.read_bytes()
        digest.update(path.name.encode() + b"\0" + raw + b"\0")
        text = raw.decode("utf-8")
        match = re.match(r"\A---\n(.*?)\n---\n(.*)\Z", text, re.S)
        if not match:
            raise ValueError(f"Missing metadata header: {path.name}")
        metadata = {}
        for line in match[1].splitlines():
            key, sep, value = line.partition(":")
            if not sep or not value.strip() or key.strip() in metadata:
                raise ValueError("Metadata must be unique scalar key: value lines")
            metadata[key.strip()] = value.strip().strip('"')
        required = {
            "document_id",
            "title",
            "version",
            "effective_date",
            "owner",
            "policy_type",
            "status",
        }
        if set(metadata) != required:
            raise ValueError("Missing or unexpected policy metadata")
        if metadata["document_id"] in identifiers:
            raise ValueError("Duplicate document_id")
        identifiers.add(metadata["document_id"])
        if metadata["status"] != "active":
            continue
        sections = re.split(r"(?m)^##\s+(.+)\n", match[2])
        if len(sections) < 3:
            raise ValueError("Documents need level-two section headings")
        for section_number, (heading, body) in enumerate(
            zip(sections[1::2], sections[2::2], strict=True), start=1
        ):
            paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]
            buffers, buffer = [], ""
            for paragraph in paragraphs:
                if len(paragraph) > 1800:
                    raise ValueError("Policy paragraph exceeds 1,800 characters")
                if buffer and len(buffer) + len(paragraph) + 2 > 1800:
                    buffers.append(buffer)
                    buffer = ""
                buffer = "\n\n".join(filter(None, [buffer, paragraph]))
            if buffer:
                buffers.append(buffer)
            for chunk_number, content in enumerate(buffers, start=1):
                chunks.append(
                    PolicyChunk(
                        **metadata,
                        section=heading.strip(),
                        chunk_id=f"{metadata['document_id']}:s{section_number:02}:c{chunk_number:02}",
                        content=content,
                    )
                )
    if not chunks:
        raise ValueError("Corpus has no active policy chunks")
    return chunks, digest.hexdigest()
