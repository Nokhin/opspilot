# OpsPilot V1 evaluation

Mode: **chat_api**, embedding: `tfidf-word-v1`, top-k: 6.

**5/5 cases passed (100.0%).**

| Metric | Result |
|---|---:|
| source_recall_at_k | 100.0% |
| citation_integrity_rate | 100.0% |
| refusal_accuracy | 100.0% |
| route_accuracy | 100.0% |
| tool_selection_accuracy | 100.0% |
| argument_schema_accuracy | 100.0% |
| tool_success_rate | 100.0% |
| deterministic_result_accuracy | N/A |
| Median latency | 14463.01 ms |
| p95 latency | 21003.06 ms |

## Category results

| Category | Passed |
|---|---:|
| multi_document | 3/3 |
| policy | 2/2 |

## Failed cases

No failed cases in this run.

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
  "run_at_utc": "2026-10-08T06:26:43.727812+00:00",
  "mode": "chat_api",
  "embedding": "tfidf-word-v1",
  "top_k": 6,
  "cases_sha256": "02f648f314b1dd0789d02ab95a6a7ea080a4c987ce4ede5e267ddee87a3c178a",
  "corpus_sha256": "3f85bfc6498084803df9e537bcb3ad0e43f1cf5b4ce563dbec8bb8ca593df639",
  "snapshot_reference": "2026-10-01T00:00:00+00:00",
  "live_validation": {
    "scope": "targeted",
    "completed": true,
    "requested_cases": 5,
    "model": "x-ai/grok-4.7",
    "endpoint": "https://openrouter.ai/api/v1",
    "transport": "http",
    "stop_reason": null,
    "max_http_attempts": 14,
    "provider_retries": 1,
    "selected_case_ids": [
      "policy_04",
      "policy_11",
      "multi_01",
      "multi_02",
      "multi_03"
    ]
  }
}
```


## Live provider verification

Scope: **targeted**; completed: **True**; executed/requested cases: 5/5.
Model: `x-ai/grok-4.7`; endpoint: `https://openrouter.ai/api/v1`.
Stop reason: none.
HTTP attempts: 10; successful structured calls: 10/10.
Provider-reported input/output tokens: 28942 / 6356.
Provider-reported cost (USD): 0.07816400.
Usage includes HTTP responses rejected for invalid structured output; missing usage is recorded as unknown, not zero. Partial runs must not be presented as a full-suite pass.
Unsafe requests are rejected before a model call. All other cases require a successful live planning call, and any provider/evidence-validation failure fails the case.