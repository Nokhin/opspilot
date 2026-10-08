# OpsPilot V1 evaluation

Mode: **chat_api**, embedding: `tfidf-word-v1`, top-k: 6.

**13/18 cases passed (72.2%).**

| Metric | Result |
|---|---:|
| source_recall_at_k | 72.2% |
| citation_integrity_rate | 100.0% |
| refusal_accuracy | 72.2% |
| route_accuracy | 83.3% |
| tool_selection_accuracy | 83.3% |
| argument_schema_accuracy | 100.0% |
| tool_success_rate | 100.0% |
| deterministic_result_accuracy | N/A |
| Median latency | 8053.92 ms |
| p95 latency | 45422.45 ms |

## Category results

| Category | Passed |
|---|---:|
| multi_document | 0/3 |
| policy | 13/15 |

## Failed cases

- `policy_04`: source_recall, chunk_recall, citation_coverage, refusal, reference_points, evidence_planes — What is the SEV2 notification deadline for Operations and Customer Service?
- `policy_11`: source_recall, chunk_recall, citation_coverage, refusal, reference_points, evidence_planes — When must supplier escalation use an alternate channel after missing SEV1 acknowledgement?
- `multi_01`: route, tool_selection, source_recall, chunk_recall, citation_coverage, refusal, reference_points, evidence_planes, live_provider_valid — What internal escalation and customer notice deadlines apply to SEV1?
- `multi_02`: route, tool_selection, source_recall, chunk_recall, citation_coverage, refusal, reference_points, evidence_planes, live_provider_valid — What supplier notifications and internal notifications are required for a SEV1 vendor incident?
- `multi_03`: route, tool_selection, source_recall, chunk_recall, citation_coverage, refusal, reference_points, evidence_planes, live_provider_valid — What evidence retention and post-incident review timing apply after SEV1 resolution?

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
  "run_at_utc": "2026-10-08T06:17:29.339913+00:00",
  "mode": "chat_api",
  "embedding": "tfidf-word-v1",
  "top_k": 6,
  "cases_sha256": "02f648f314b1dd0789d02ab95a6a7ea080a4c987ce4ede5e267ddee87a3c178a",
  "corpus_sha256": "3f85bfc6498084803df9e537bcb3ad0e43f1cf5b4ce563dbec8bb8ca593df639",
  "snapshot_reference": "2026-10-01T00:00:00+00:00",
  "live_validation": {
    "scope": "curated_regression",
    "completed": false,
    "requested_cases": 50,
    "model": "x-ai/grok-4.7",
    "endpoint": "https://openrouter.ai/api/v1",
    "transport": "http",
    "stop_reason": "three_consecutive_provider_failures",
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

Scope: **curated_regression**; completed: **False**; executed/requested cases: 18/50.
Model: `x-ai/grok-4.7`; endpoint: `https://openrouter.ai/api/v1`.
Stop reason: three_consecutive_provider_failures.
HTTP attempts: 33; successful structured calls: 30/33.
Provider-reported input/output tokens: 90519 / 12253.
Provider-reported cost (USD): 0.18601200.
Usage includes HTTP responses rejected for invalid structured output; missing usage is recorded as unknown, not zero. Partial runs must not be presented as a full-suite pass.
Unsafe requests are rejected before a model call. All other cases require a successful live planning call, and any provider/evidence-validation failure fails the case.