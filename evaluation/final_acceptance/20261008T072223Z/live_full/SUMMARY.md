# OpsPilot V1 evaluation

Mode: **chat_api**, embedding: `tfidf-word-v1`, top-k: 6.

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
| Median latency | 11245.66 ms |
| p95 latency | 43433.28 ms |

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
  "run_at_utc": "2026-10-08T07:35:48.937747+00:00",
  "mode": "chat_api",
  "embedding": "tfidf-word-v1",
  "top_k": 6,
  "cases_sha256": "e3310ab655fdb8fe45a553fadf2fe220364f370ec4c7e2be9a2d0c67e7179ef1",
  "corpus_sha256": "3f85bfc6498084803df9e537bcb3ad0e43f1cf5b4ce563dbec8bb8ca593df639",
  "snapshot_reference": "2026-10-01T00:00:00+00:00",
  "live_validation": {
    "scope": "curated_regression",
    "completed": true,
    "requested_cases": 50,
    "model": "x-ai/grok-4.7",
    "endpoint": "https://openrouter.ai/api/v1",
    "transport": "http",
    "stop_reason": null,
    "max_http_attempts": 120,
    "provider_retries": 1,
    "selected_case_ids": [
      "policy_01",
      "policy_02",
      "policy_03",
      "policy_04",
      "policy_05",
      "policy_06",
      "policy_07",
      "policy_08",
      "policy_09",
      "policy_10",
      "policy_11",
      "policy_12",
      "policy_13",
      "policy_14",
      "policy_15",
      "multi_01",
      "multi_02",
      "multi_03",
      "ambiguous_01",
      "ambiguous_02",
      "ambiguous_03",
      "unsupported_01",
      "unsupported_02",
      "unsupported_03",
      "unsupported_04",
      "unsupported_05",
      "unsupported_06",
      "unsupported_07",
      "unsupported_08",
      "data_01",
      "data_02",
      "data_03",
      "data_04",
      "data_05",
      "data_06",
      "data_07",
      "data_08",
      "data_09",
      "data_10",
      "mixed_01",
      "mixed_02",
      "mixed_03",
      "mixed_04",
      "mixed_05",
      "mixed_06",
      "mixed_07",
      "safety_01",
      "safety_02",
      "safety_03",
      "safety_04"
    ]
  }
}
```


## Live provider verification

Scope: **curated_regression**; completed: **True**; executed/requested cases: 50/50.
Model: `x-ai/grok-4.7`; endpoint: `https://openrouter.ai/api/v1`.
Stop reason: none.
HTTP attempts: 74; successful structured calls: 74/74.
Provider-reported input/output tokens: 240832 / 45883.
Provider-reported cost (USD): 0.62467400.
Usage includes HTTP responses rejected for invalid structured output; missing usage is recorded as unknown, not zero. Partial runs must not be presented as a full-suite pass.
Unsafe requests are rejected before a model call. All other cases require a successful live planning call, and any provider/evidence-validation failure fails the case.