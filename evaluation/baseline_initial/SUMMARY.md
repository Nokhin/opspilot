# OpsPilot V1 evaluation

Mode: **extractive**, embedding: `tfidf-word-v1`, top-k: 6.

**42/50 cases passed (84.0%).**

| Metric | Result |
|---|---:|
| source_recall_at_k | 85.7% |
| citation_integrity_rate | 100.0% |
| refusal_accuracy | 92.0% |
| route_accuracy | 92.0% |
| tool_selection_accuracy | 92.0% |
| argument_schema_accuracy | 100.0% |
| tool_success_rate | 100.0% |
| deterministic_result_accuracy | 93.8% |
| Median latency | 0.30 ms |
| p95 latency | 2.18 ms |

## Category results

| Category | Passed |
|---|---:|
| ambiguous | 3/3 |
| data | 9/10 |
| mixed | 6/7 |
| multi_document | 1/3 |
| policy | 11/15 |
| safety | 4/4 |
| unsupported | 8/8 |

## Failed cases

- `policy_02`: route, tool_selection, source_recall, chunk_recall, citation_coverage, refusal, reference_points, evidence_planes — What customer-impact and downtime thresholds define SEV1?
- `policy_04`: citation_coverage, reference_points — What is the SEV2 notification deadline for Operations and Customer Service?
- `policy_05`: route, tool_selection, source_recall, chunk_recall, citation_coverage, refusal, reference_points, evidence_planes — What is the SEV1 first customer notice and update cadence?
- `policy_06`: route, tool_selection, source_recall, chunk_recall, citation_coverage, refusal, reference_points, evidence_planes — What is the SEV2 first customer notice and update cadence?
- `multi_01`: chunk_recall, citation_coverage, reference_points — What internal escalation and customer notice deadlines apply to SEV1?
- `multi_02`: citation_coverage, reference_points — What supplier notifications and internal notifications are required for a SEV1 vendor incident?
- `data_07`: route, tool_selection, argument_match, refusal, numeric_results, evidence_planes — Give incident counts by business unit in the last year.
- `mixed_01`: source_recall, chunk_recall, citation_coverage, reference_points — For INC-001, what escalation does policy require?

## Interpretation and limits

This is a curated, English-language synthetic-corpus regression set, not a general enterprise benchmark.
Citation integrity measures exact paragraph/provenance validity; it does not prove semantic relevance or answer completeness.
Reference points and expected section IDs add deterministic coverage checks. Missing-topic rules remain conservative and corpus-specific.
Numeric expectations are frozen in cases.json from independent raw-SQL checks, not recomputed by the tool under test.
End-to-end pass requires every applicable route, tool, schema, filter, source/chunk, citation, refusal, numeric and reference-point check.
Offline runs make no LLM calls. Their latency and zero token counts must not be presented as live-model performance.
API cost is unavailable unless per-million-token rates are configured; dense-embedding API cost is not included.
Live-provider quality and public VPS operation require separate validation.

## Reproducibility

```json
{
  "run_at_utc": "2026-10-08T04:33:13.271248+00:00",
  "mode": "extractive",
  "embedding": "tfidf-word-v1",
  "top_k": 6,
  "cases_sha256": "02f648f314b1dd0789d02ab95a6a7ea080a4c987ce4ede5e267ddee87a3c178a",
  "corpus_sha256": "3f85bfc6498084803df9e537bcb3ad0e43f1cf5b4ce563dbec8bb8ca593df639",
  "snapshot_reference": "2026-10-01T00:00:00+00:00"
}
```
