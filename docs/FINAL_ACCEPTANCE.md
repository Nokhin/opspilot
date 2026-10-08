# Final local V1 acceptance — 2026-10-08

**PASS.** The current V1 completed all 50 curated live cases through OpenRouter
`x-ai/grok-4.7`, with 74/74 valid structured model calls. This is a complete run
after the retained executor guard, not a score assembled from targeted reruns.
Application code, both golden files, the policy corpus and existing evidence stores
were unchanged during acceptance. Actual VPS operation requires separate validation.

## Acceptance gates

| Gate | Observed result |
|---|---|
| Complete current-build live regression | 50/50; 74 HTTP attempts, all structured calls valid |
| pytest | 70 passed; no errors/failures |
| Ruff lint / format | Passed; 35 Python files formatted |
| Dependency integrity | `pip check` passed |
| Preserved legacy offline dataset | 50/50 |
| Current clarified offline dataset | 50/50 |
| Native ARM64 Docker, fresh stores, network disabled | 50/50; UID 10001; database/root writes rejected |
| Actual loopback API smoke | 5/5 policy/data/mixed/insufficiency/write-refusal journeys |
| API/UI contracts | Request IDs match; four read-only tool schemas; UI assets served; 422 invalid input; 404 absent upload endpoint |
| Existing Compose demo refresh | Healthy loopback service; current source; offline mode; DB/index checksums preserved |
| Response/source spot checks | 12 inspected curated responses; qualitative Codex inspection, not independent blinded human evaluation |

The existing Starlette TestClient/HTTPX deprecation warning remains; tests pass.
An initial temporary API smoke was interrupted because the inherited HTTP proxy
routed loopback requests. A direct request returned 200; rerunning the loopback
harness with `trust_env=False` passed. The application and live runner were unchanged.
The diagnostic is preserved alongside the successful API report.

## Complete live measurement

| Metric | Result |
|---|---:|
| End-to-end cases | 50/50 (100%) |
| Expected document Recall@6 | 100% |
| Paragraph/provenance citation integrity | 100% |
| Refusal / routing / exact executed tool selection | 100% |
| Executed argument schema / tool success / frozen numeric checks | 100% |
| Median / p95 shared-service latency | 11.246 / 43.433 seconds |
| Provider input / output tokens | 240,832 / 45,883 |
| Provider-reported cost for this run | USD 0.624674 |
| Safety cases | 4/4; zero provider calls and zero tools |

Categories: policy 15/15, multi-document 3/3, ambiguous 3/3, unsupported 8/8,
data 10/10, mixed 7/7 and safety 4/4. No failed case, provider retry or
retry-until-pass loop occurred in this run; the configured HTTP budget was 120.
Latency includes sequential planning/selection, tools and provider/network time.
It is not a concurrent FastAPI/UI or VPS performance measurement. The slower
p95 than the earlier broad run is retained rather than replaced by its earlier value.

`mixed_05` actually proposed policy search, similarity and metrics. The retained
executor guard ran policy plus metrics only and recorded the omitted unrequested
sample in limitations. `mixed_02` retained explicitly requested similarity and
whole-cohort metrics, without treating the scenario's 500-person impact as a
historical restriction. `data_09` and `data_10` preserved requested sample filters.

## Provenance and reproducibility

The same `cases_v1_1.json` used for the earlier 49/50 run was used here. There was
no additional question/label change. That revision clarifies only the historical
SEV1 scope of `mixed_07`; the legacy input and all numeric labels remain preserved.
See [golden provenance](../evaluation/GOLDEN_PROVENANCE.md).

- Current case SHA-256: `e3310ab655fdb8fe45a553fadf2fe220364f370ec4c7e2be9a2d0c67e7179ef1`.
- Corpus SHA-256: `3f85bfc6498084803df9e537bcb3ad0e43f1cf5b4ce563dbec8bb8ca593df639`.
- Logical incident SHA-256: `734cb1b898b986bd70a1532a8f042fc97cf594b5a281fcc0c7635ab7d8ed78b8`.
- Planner/provider SHA-256: `4d2761ca61ab4a2745f168e65ad3e340ec3f134c7fe45305c681ed9c4e7cbb75`.
- Executor SHA-256: `3e91073ab0c7016f1466c341146d6657c96b48e6488ad23b3f20731e6b0e45fa`.

[Machine-readable acceptance](../evaluation/final_acceptance/20261008T072223Z/ACCEPTANCE.json)
records gates, source/evidence hashes and limits.
[Full live JSON](../evaluation/final_acceptance/20261008T072223Z/live_full/results.json),
[CSV](../evaluation/final_acceptance/20261008T072223Z/live_full/cases.csv) and
[Markdown](../evaluation/final_acceptance/20261008T072223Z/live_full/SUMMARY.md)
preserve all 50 responses and checks. The same directory contains JUnit, both offline
reports, Docker/API/Compose evidence and qualitative spot checks.

The earlier original 47/50, revised 49/50, targeted 4/4 and failed/partial trials
remain unchanged. Across all 12 preserved real-HTTP runs: 296 attempts,
919,056 input / 182,305 output tokens, USD 2.297574 provider-reported cost.
That total includes earlier diagnoses; the cost of this acceptance run is USD 0.624674.
The [living usage ledger](../evaluation/live_openrouter/VALIDATION.json) includes the new
run; its [previous snapshot](../evaluation/live_openrouter/VALIDATION_before_final_acceptance.json)
preserves the earlier 11-run accounting.

To reproduce, select a fresh output directory; existing live reports are never overwritten:

```bash
python -m opspilot.cli evaluate-live --env-file .env.live \
  --cases opspilot/evaluation/cases_v1_1.json --output evaluation/live/new-acceptance
pytest -q
ruff check .
ruff format --check .
```

## Scope of the sign-off

V1's local functional acceptance is complete: grounded internal policy, validated
SQLite data, four typed read-only tools, four routes, mixed evidence, structured
responses/traces, curated evaluation and CPU-only Docker/API/UI operation.
No new graph, MCP or privileged business action is implemented.

These are tuned synthetic English regression results. Citation equality proves
paragraph/provenance integrity, not general semantic relevance or completeness;
confidence is not a calibrated probability. Held-out paraphrases, independent human
review, other providers and optional dense-embedding quality require separate evidence.
Actual VPS/HTTPS, concurrent load and production operations are unverified.

The public evidence is a metadata-normalized copy of the recorded acceptance:
JUnit machine identifiers are removed, its timezone-aware timestamp is UTC, and
public artifact hashes are recalculated. Case results and application/corpus/golden
files are unchanged. Publication checks and CI are separate from the recorded
70-test functional acceptance; no paid inference was rerun for publication.
