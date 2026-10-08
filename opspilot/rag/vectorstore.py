import json
import os
from datetime import date
from pathlib import Path
from typing import Protocol

from opspilot.domain.models import PolicyChunk, PolicyHit, SearchPolicyArgs
from opspilot.providers.embeddings import Embeddings
from opspilot.rag.ingestion import load_chunks


class VectorStore(Protocol):
    def search(self, args: SearchPolicyArgs, as_of: date) -> list[PolicyHit]: ...


class JsonVectorStore:
    """Small immutable index snapshot with sparse/dense cosine vectors and atomic rebuild."""

    def __init__(self, path: Path, embeddings: Embeddings):
        self.path = path
        self.embeddings = embeddings
        self._snapshot: dict | None = None

    def rebuild(self, corpus: Path) -> dict:
        chunks, digest = load_chunks(corpus)
        texts = [f"{c.title}\n{c.section}\n{c.content}" for c in chunks]
        state = self.embeddings.fit(texts)
        snapshot = {
            "format_version": 1,
            "corpus_sha256": digest,
            "embedding_fingerprint": self.embeddings.fingerprint,
            "embedding_state": state,
            "chunks": [c.model_dump(mode="json") for c in chunks],
            "vectors": self.embeddings.encode(texts, state),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(snapshot, sort_keys=True, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.path)
        self._snapshot = snapshot
        return {
            "chunks": len(chunks),
            "documents": len({c.document_id for c in chunks}),
            "corpus_sha256": digest,
            "embedding": self.embeddings.fingerprint,
        }

    def snapshot(self) -> dict:
        if self._snapshot is None:
            self._snapshot = json.loads(self.path.read_text(encoding="utf-8"))
        snapshot = self._snapshot
        if snapshot["embedding_fingerprint"] != self.embeddings.fingerprint:
            raise ValueError("Embedding configuration changed; rebuild the policy index")
        if snapshot["format_version"] != 1 or len(snapshot["vectors"]) != len(snapshot["chunks"]):
            raise ValueError("Invalid policy index")
        return snapshot

    def search(self, args: SearchPolicyArgs, as_of: date) -> list[PolicyHit]:
        snapshot = self.snapshot()
        query = self.embeddings.encode([args.query], snapshot["embedding_state"])[0]
        hits = []
        for record, vector in zip(snapshot["chunks"], snapshot["vectors"], strict=True):
            chunk = PolicyChunk.model_validate(record)
            if chunk.effective_date > as_of or (
                args.policy_type and args.policy_type != chunk.policy_type
            ):
                continue
            score = min(1.0, max(0.0, sum(v * vector.get(t, 0) for t, v in query.items())))
            if score >= 0.07:
                hits.append(PolicyHit(chunk=chunk, score=score))
        return sorted(hits, key=lambda h: (-h.score, h.chunk.chunk_id))[: args.top_k]
