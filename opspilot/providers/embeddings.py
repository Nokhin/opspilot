import math
import re
from collections import Counter
from typing import Protocol

STOPWORDS = set(
    "a an the our company internal policy procedure standard sop what which when who how why "
    "is are was were be been being do does did must should would could can have has had "
    "for of to in on at by from with and or as it its this that these those according "
    "please tell me about required requirements need needs use using more than per "
    "before after also get give show under within during applies apply exact "
    "now current currently question answer enterprise fictional".split()
)


def terms(text: str) -> list[str]:
    result = []
    for token in re.findall(r"[a-z][a-z0-9]+", text.lower()):
        if token in STOPWORDS:
            continue
        if token.endswith("ies") and len(token) > 5:
            token = token[:-3] + "y"
        elif token.endswith("s") and not token.endswith("ss") and len(token) > 4:
            token = token[:-1]
        result.append(token)
    return result


class Embeddings(Protocol):
    fingerprint: str

    def fit(self, texts: list[str]) -> dict: ...
    def encode(self, texts: list[str], state: dict) -> list[dict[str, float]]: ...


class TfidfEmbeddings:
    """Deterministic lexical vectors; deliberately not a semantic neural encoder."""

    fingerprint = "tfidf-word-v1"

    def fit(self, texts: list[str]) -> dict:
        counts: Counter = Counter()
        for text in texts:
            counts.update(set(terms(text)))
        return {
            "idf": {t: math.log((1 + len(texts)) / (1 + n)) + 1 for t, n in sorted(counts.items())}
        }

    def encode(self, texts: list[str], state: dict) -> list[dict[str, float]]:
        vectors = []
        for text in texts:
            counts = Counter(terms(text))
            weights = {
                t: (1 + math.log(n)) * state["idf"][t]
                for t, n in sorted(counts.items())
                if t in state["idf"]
            }
            norm = math.sqrt(sum(v * v for v in weights.values()))
            vectors.append({t: v / norm for t, v in weights.items()} if norm else {})
        return vectors
