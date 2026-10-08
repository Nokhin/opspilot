# OpsPilot V1 evaluation

Mode: **extractive**, embedding: `tfidf-word-v1`, top-k: 6.

**50/50 cases passed (100.0%).**

| Metric | Result |
|---|---:|
| source_recall_at_k | 100.0% |
| citation_integrity_rate | 100.0% |
| refusal_accuracy | 100.0% |
| route_accuracy | 100.0% |
| tool_selection_accuracy | 100.0% |
| argument_schema_accuracy | 100.0% |
| tool_success_rate | 100.0% |
| deterministic_result_accuracy | 100.0% |
| Median latency | 0.35 ms |
| p95 latency | 2.09 ms |

## Category results

| Category | Passed |
|---|---:|
| ambiguous | 3/3 |
| data | 10/10 |
| mixed | 7/7 |
| multi_document | 3/3 |
| policy | 15/15 |
| safety | 4/4 |
| unsupported | 8/8 |

## Failed cases

No failed cases in this run.

## Interpretation and limits

This is a curated, English-language synthetic-corpus regression set, not a general enterprise benchmark.
Citation integrity measures exact paragraph/provenance validity; it does not prove semantic relevance or answer completeness.
Reference points and expected section IDs add deterministic coverage checks. Missing-topic rules remain conservative and corpus-specific.
Numeric expectations are frozen in cases.json from independent raw-SQL checks, not recomputed by the tool under test.
End-to-end pass requires every applicable route, tool, schema, filter, source/chunk, citation, refusal, numeric and reference-point check.
Offline runs make no LLM calls. Their latency and zero token counts must not be presented as live-model performance.
Response-level API cost estimates require configured per-million-token rates. Observed provider HTTP usage/cost, when available, is recorded separately in live reports; dense-embedding API cost is not included.
Held-out/manual semantic quality and public VPS operation require separate validation.

## Reproducibility

```json
{
  "run_at_utc": "2026-10-08T07:24:44.922139+00:00",
  "mode": "extractive",
  "embedding": "tfidf-word-v1",
  "top_k": 6,
  "cases_sha256": "e3310ab655fdb8fe45a553fadf2fe220364f370ec4c7e2be9a2d0c67e7179ef1",
  "corpus_sha256": "3f85bfc6498084803df9e537bcb3ad0e43f1cf5b4ce563dbec8bb8ca593df639",
  "snapshot_reference": "2026-10-01T00:00:00+00:00"
}
```
