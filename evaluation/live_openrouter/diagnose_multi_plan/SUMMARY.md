# OpsPilot V1 evaluation

Mode: **chat_api**, embedding: `tfidf-word-v1`, top-k: 6.

**0/1 cases passed (0.0%).**

| Metric | Result |
|---|---:|
| source_recall_at_k | 0.0% |
| citation_integrity_rate | N/A |
| refusal_accuracy | 0.0% |
| route_accuracy | 0.0% |
| tool_selection_accuracy | 0.0% |
| argument_schema_accuracy | 100.0% |
| tool_success_rate | N/A |
| deterministic_result_accuracy | N/A |
| Median latency | 5627.34 ms |
| p95 latency | 5627.34 ms |

## Category results

| Category | Passed |
|---|---:|
| multi_document | 0/1 |

## Failed cases

- `multi_01`: route, tool_selection, source_recall, chunk_recall, citation_coverage, refusal, reference_points, evidence_planes, live_provider_valid — What internal escalation and customer notice deadlines apply to SEV1?

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
  "run_at_utc": "2026-10-08T06:24:40.733128+00:00",
  "mode": "chat_api",
  "embedding": "tfidf-word-v1",
  "top_k": 6,
  "cases_sha256": "02f648f314b1dd0789d02ab95a6a7ea080a4c987ce4ede5e267ddee87a3c178a",
  "corpus_sha256": "3f85bfc6498084803df9e537bcb3ad0e43f1cf5b4ce563dbec8bb8ca593df639",
  "snapshot_reference": "2026-10-01T00:00:00+00:00",
  "live_validation": {
    "scope": "targeted",
    "completed": true,
    "requested_cases": 1,
    "model": "x-ai/grok-4.7",
    "endpoint": "https://openrouter.ai/api/v1",
    "transport": "http",
    "stop_reason": null,
    "max_http_attempts": 4,
    "provider_retries": 1,
    "selected_case_ids": [
      "multi_01"
    ]
  }
}
```


## Live provider verification

Scope: **targeted**; completed: **True**; executed/requested cases: 1/1.
Model: `x-ai/grok-4.7`; endpoint: `https://openrouter.ai/api/v1`.
Stop reason: none.
HTTP attempts: 1; successful structured calls: 0/1.
Provider-reported input/output tokens: 3198 / 411.
Provider-reported cost (USD): 0.00425400.
Usage includes HTTP responses rejected for invalid structured output; missing usage is recorded as unknown, not zero. Partial runs must not be presented as a full-suite pass.
Unsafe requests are rejected before a model call. All other cases require a successful live planning call, and any provider/evidence-validation failure fails the case.