import math

import httpx

from opspilot.config import Settings
from opspilot.providers.chat_api import ProviderError


class APIEmbeddings:
    """Optional dense API vectors; no SDK or vendor types in RAG/domain code."""

    def __init__(self, settings: Settings, client: httpx.Client | None = None):
        self.settings = settings
        self.client = client
        self.fingerprint = f"embedding_api:{settings.embedding_base_url}:{settings.embedding_model}"

    def fit(self, texts: list[str]) -> dict:
        return {}

    def encode(self, texts: list[str], state: dict) -> list[dict[str, float]]:
        owned = self.client is None
        client = self.client or httpx.Client(timeout=self.settings.provider_timeout_seconds)
        try:
            result = client.post(
                self.settings.embedding_base_url.rstrip("/") + "/embeddings",
                headers={
                    "Authorization": "Bearer " + self.settings.embedding_api_key.get_secret_value()
                },
                json={"model": self.settings.embedding_model, "input": texts},
                timeout=self.settings.provider_timeout_seconds,
            )
            result.raise_for_status()
            rows = sorted(result.json()["data"], key=lambda row: row["index"])
            if [row["index"] for row in rows] != list(range(len(texts))):
                raise ValueError("Embedding batch mismatch")
            vectors = []
            dimensions = set()
            for row in rows:
                values = [float(v) for v in row["embedding"]]
                dimensions.add(len(values))
                norm = math.sqrt(sum(v * v for v in values))
                if not norm or not math.isfinite(norm):
                    raise ValueError("Invalid embedding")
                vectors.append({str(i): v / norm for i, v in enumerate(values)})
            if len(dimensions) != 1:
                raise ValueError("Inconsistent embedding dimensions")
            dimension = dimensions.pop()
            if state.get("dimensions", dimension) != dimension:
                raise ValueError("Embedding dimensions changed; rebuild index")
            state["dimensions"] = dimension
            return vectors
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
            raise ProviderError("Embedding provider unavailable or invalid") from error
        finally:
            if owned:
                client.close()
