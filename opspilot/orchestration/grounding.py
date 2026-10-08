import re

from opspilot.domain.models import PolicyHit, PolicyQuote, PolicySelection
from opspilot.providers.embeddings import terms


def policy_question(question: str) -> str:
    # Remove an explicit historical comparison clause, not other policy topics.
    return re.split(
        r"\band (?:how does|how do|compare|what (?:was|is) the (?:median|average))\b",
        question,
        maxsplit=1,
        flags=re.I,
    )[0]


def explicitly_missing(question: str) -> bool:
    return bool(
        re.search(
            r"compensation|cash|refund amount|insurance|password|holiday calendar|evacuation route|"
            r"phone number|statutory|regulatory.{0,20}deadline|annual leave|penalt|service credit",
            question,
            re.I,
        )
    )


def select_extractive(question: str, hits: list[PolicyHit]) -> PolicySelection:
    question = policy_question(question)
    if not hits or explicitly_missing(question):
        return PolicySelection(sufficient=False)
    query_terms = set(terms(question))
    corpus_terms = set(terms(" ".join(h.chunk.content + " " + h.chunk.title for h in hits)))
    coverage = len(query_terms & corpus_terms) / max(1, len(query_terms))
    if coverage < 0.45:
        return PolicySelection(sufficient=False)
    top_score = hits[0].score
    quotes = [
        PolicyQuote(evidence_id=h.chunk.chunk_id, quote=h.chunk.content)
        for h in hits
        if h.score >= max(0.10, top_score * 0.4)
    ]
    return PolicySelection(sufficient=bool(quotes), quotes=quotes)


def validate_selection(selection: PolicySelection, hits: list[PolicyHit]) -> None:
    allowed = {h.chunk.chunk_id: h.chunk.content.split("\n\n") for h in hits}
    if selection.sufficient and not selection.quotes:
        raise ValueError("Sufficient policy answer requires evidence")
    seen = set()
    for quote in selection.quotes:
        if quote.evidence_id in seen:
            raise ValueError("Duplicate policy evidence")
        seen.add(quote.evidence_id)
        if quote.quote not in allowed.get(quote.evidence_id, []):
            raise ValueError("Policy quote must be a complete verbatim evidence paragraph")
        if re.search(
            r"ignore.{0,30}instructions|system prompt|api key|execute.*shell", quote.quote, re.I
        ):
            raise ValueError("Instruction-like evidence is rejected")
