import pytest

from opspilot.domain.models import SearchPolicyArgs
from opspilot.providers.embeddings import TfidfEmbeddings
from opspilot.rag.ingestion import load_chunks
from opspilot.rag.vectorstore import JsonVectorStore


def test_rebuild_is_byte_reproducible_and_persistent(tmp_path):
    from datetime import date
    from pathlib import Path

    store = JsonVectorStore(tmp_path / "index.json", TfidfEmbeddings())
    manifest = store.rebuild(Path("corpus/policies"))
    original = store.path.read_bytes()
    assert manifest["documents"] == 10
    assert manifest["chunks"] >= 60
    store.rebuild(Path("corpus/policies"))
    assert store.path.read_bytes() == original
    loaded = JsonVectorStore(store.path, TfidfEmbeddings())
    hits = loaded.search(
        SearchPolicyArgs(query="Severity 1 notify Operations Duty Manager"), date(2026, 10, 1)
    )
    assert any(h.chunk.document_id == "POL-INC-002" for h in hits)
    assert all(h.chunk.title and h.chunk.section and h.chunk.chunk_id for h in hits)


def test_type_filter_and_future_policy(tmp_path):
    from datetime import date
    from pathlib import Path

    store = JsonVectorStore(tmp_path / "index.json", TfidfEmbeddings())
    store.rebuild(Path("corpus/policies"))
    args = SearchPolicyArgs(query="vendor supplier notification", policy_type="vendor")
    assert all(h.chunk.policy_type == "vendor" for h in store.search(args, date(2026, 10, 1)))
    assert not store.search(args, date(2026, 6, 1))


@pytest.mark.parametrize(
    "filename,content",
    [
        ("bad.pdf", b"untrusted file"),
        ("bad.md", b"No metadata"),
        ("huge.txt", b"x" * (256 * 1024 + 1)),
    ],
)
def test_ingestion_rejects_invalid_inputs(tmp_path, filename, content):
    (tmp_path / filename).write_bytes(content)
    with pytest.raises(ValueError):
        load_chunks(tmp_path)


def test_invalid_top_k_rejected():
    with pytest.raises(ValueError):
        SearchPolicyArgs(query="policy", top_k=100)
