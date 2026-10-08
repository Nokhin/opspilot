# Live LLM validation

This validation holds the ten-policy TF-IDF index and 240-record SQLite snapshot fixed
and exercises the configurable JSON planner / verbatim evidence selector through real
HTTP. Deterministic tools still perform incident queries and arithmetic. No native
provider tool execution, web plugin, write capability or LangGraph is introduced.

## Local configuration

Use the separate, Git/Docker-ignored `.env.live`; the existing offline demo is unaffected.

```bash
cp .env.live.example .env.live
chmod 600 .env.live
# Edit key/model locally; never paste or print the key in a chat/report.
python -m opspilot.cli bootstrap
python -m opspilot.cli evaluate-live --env-file .env.live --smoke
python -m opspilot.cli evaluate-live --env-file .env.live
```

OpenRouter endpoint: `https://openrouter.ai/api/v1`.
Set `OPSPILOT_LLM_API_KEY` and `OPSPILOT_LLM_MODEL` to the model being evaluated.
The existing adapter sends `response_format: {"type": "json_object"}` and a schema
in the system message, then validates locally with Pydantic. JSON mode alone does
not guarantee the complete tool schema. See the primary
[OpenRouter chat API](https://openrouter.ai/docs/api/api-reference/chat/create-a-chat-completion)
and [structured-output guidance](https://openrouter.ai/docs/guides/features/structured-outputs).
No model ID is embedded in domain code.

## Procedure and evidence

Start with five representative cases: policy, data, mixed, missing internal detail
and unsafe write request. The original runs used the unchanged 50-case curated suite.
The default dataset is now revision `cases_v1_1.json`, with one ambiguous question
clarified and all numeric labels preserved; see [golden provenance](../evaluation/GOLDEN_PROVENANCE.md).
Use `--cases opspilot/evaluation/cases.json` to rerun the preserved legacy version. The smoke
and full results use different directories. Default output is a timestamped directory
under `evaluation/live/`; `--output` must be empty. Offline results are preserved.
For diagnosis, repeat `--case-id ID` to select existing curated cases. These reports
are labelled `targeted` and retain their own requested denominator; they are not
full-suite results. Explicit IDs and `--smoke` cannot be combined.

For every completed case, save the existing deterministic grade and structured
response, plus sanitised logical-call/HTTP-attempt metadata. `progress.jsonl` is
appended after each case. `provider.json` also preserves attempts from a budget-
interrupted case. `results.json`, `cases.csv` and `SUMMARY.md` describe completed
cases and explicitly identify a partial run and its requested denominator.

Additional checks:

- force `chat_api`; never fall back to offline planning;
- non-guarded cases require a successful real planning call;
- every model call must return valid structured output;
- evidence-selection/provenance failures fail the case even if refusal otherwise matches;
- unsafe requests are refused before an LLM call and execute zero tools;
- missing credentials stop preflight without a network call or a claimed pass.

The runner is sequential. Default budget: 120 HTTP attempts including retries,
hard configurable cap 200. The five-case smoke command can set a smaller budget.
400/401/402/403/404 stop after the affected case; three consecutive provider failures
also stop the run. Timeouts and transport/protocol failures use bounded retries.
There is no retry-until-pass loop.

`provider.json` records operation, status, latency, HTTP status, numeric usage,
allow-listed proposed tool names, finish status and sanitised schema error
types/locations. Unknown field/tool names are redacted. Diagnostics never save
model-generated arguments or raw output.
It never contains authorization headers, keys, raw provider error bodies, model
reasoning or prompts. Structured case results contain only the synthetic evaluation
questions, retrieved evidence, tool outputs and public action trace.

## Usage and interpretation

Record prompt/completion tokens and provider-reported `usage.cost` when available.
HTTP responses rejected for malformed JSON still contribute reported usage. Missing
usage/cost is unknown, not zero. Response-level token estimates remain separate from
observed HTTP accounting; retries or rejected outputs may account for the difference.
Optional configured token prices do not include cache discounts, routing changes,
credit-purchase fees or embedding costs. See
[OpenRouter usage accounting](https://openrouter.ai/blog/announcements/smarter-charts-inline-svgs-and-live-usage-accounting/).

Live latency includes planning, policy selection, deterministic tools and network
time for a service request. The sequential CLI calls the shared domain service and
reuses one provider HTTP client; FastAPI/UI HTTP overhead, concurrent live traffic
and VPS operation require their own measurements. A completed run with some failed cases is still a valid
measurement; it is not an all-pass acceptance claim. The same curated set remains
a regression benchmark, not held-out generalisation or a manual semantic-quality score.
Actual VPS/load/dense-embedding validation remains separate.

## Final current-build acceptance

The complete post-guard run passed **50/50**, with **74/74** valid structured
model calls and no retries. Source Recall@6, paragraph/provenance citation integrity,
refusal, routing, exact executed tool selection, schemas, tool success and frozen
numeric checks all passed. Safety cases made zero provider calls and executed zero
tools. The executor guard actually omitted the unrequested sample in `mixed_05`;
explicit similarity/cohort requests remained intact.

The same revised cases, corpus, SQLite snapshot and application source were retained
during acceptance. Median/p95 shared-service latency: **11.246/43.433 seconds**;
provider input/output: **240,832/45,883 tokens**; run cost: **USD 0.624674**.
This is one complete current-build regression run, with its own 50-case denominator.
Earlier failed/full/targeted scores remain unchanged.

See [final acceptance](FINAL_ACCEPTANCE.md),
[complete JSON](../evaluation/final_acceptance/20261008T072223Z/live_full/results.json)
and [Markdown](../evaluation/final_acceptance/20261008T072223Z/live_full/SUMMARY.md)
for actual responses, provenance, local API/Docker checks and limits.

Across all 12 preserved real-HTTP runs: 296 attempts, 919,056 input / 182,305
output tokens, **USD 2.297574** provider-reported cost. The living
[aggregate JSON](../evaluation/live_openrouter/VALIDATION.json) includes this final run;
the earlier 11-run aggregate is preserved separately. Paid-provider acceptance is
complete for this local V1; held-out semantic, concurrent live UI and VPS performance
remain outside this measurement.

## Earlier runs and fixes

The recorded live measurements use OpenRouter / `x-ai/grok-4.7`. The live
validation uses real HTTP and the same fixed stores. Dataset versions are identified
explicitly; completed original results are preserved alongside the clarified revision.
The [model card](https://openrouter.ai/x-ai/grok-4.7) was checked on 2026-10-08.
Mock test outputs stay in temporary test directories and are labelled as injected
test transport; they are never published as live measurements.

Preserved measurements:

| Run | Completed / requested | Passed | HTTP attempts | Reported USD |
|---|---:|---:|---:|---:|
| [Initial smoke](../evaluation/live_openrouter/smoke_initial/SUMMARY.md) | 5/5 | 4/5 | 6 | 0.036260 |
| [Smoke with incident context](../evaluation/live_openrouter/smoke_anchor_context/SUMMARY.md) | 5/5 | 5/5 | 6 | 0.031904 |
| [First full-suite attempt](../evaluation/live_openrouter/full_initial/SUMMARY.md) | 18/50 | 13/18 | 33 | 0.186012 |
| [Multi-document diagnosis](../evaluation/live_openrouter/diagnose_multi_plan/SUMMARY.md) | 1/1 | 0/1 | 1 | 0.004254 |
| [Refined targeted plans](../evaluation/live_openrouter/targeted_plan_refined/SUMMARY.md) | 5/5 | 5/5 | 10 | 0.078164 |
| [Completed original suite](../evaluation/live_openrouter/full_refined/SUMMARY.md) | 50/50 | 47/50 | 74 | 0.532704 |
| [Historical-scope targets](../evaluation/live_openrouter/targeted_data_scope/SUMMARY.md) | 3/3 | 2/3 | 5 | 0.061018 |
| [Metrics-role target](../evaluation/live_openrouter/targeted_metrics_role/SUMMARY.md) | 1/1 | 1/1 | 2 | 0.025564 |
| [Complete revised suite](../evaluation/live_openrouter/full_final/SUMMARY.md) | 50/50 | 49/50 | 74 | 0.597828 |
| [Reverted prompt-precision trial](../evaluation/live_openrouter/targeted_tool_precision/SUMMARY.md) | 3/3 | 2/3 | 5 | 0.052652 |
| [Retained executor guard](../evaluation/live_openrouter/targeted_executor_guard/SUMMARY.md) | 4/4 | 4/4 | 6 | 0.066540 |

The initial mixed failure lacked the named incident's severity/category in the
selector context. The selector now receives a narrow validated incident snapshot,
excluding free-text root-cause/resolution fields; complete policy paragraphs still
require exact provenance checks.

The first full-suite attempt stopped after three invalid multi-document plans.
A targeted real call confirmed duplicate `search_internal_policy` calls, rejected
by the existing V1 validator. Two other failures used inferred metadata filters
that excluded relevant policies. Prompt/schema guidance now states one call per
tool, a single search across multiple policy documents, and default-null policy
type restrictions. The validator remains enforced; failed results are preserved.
The completed original suite passed 47/50, with all 74 model calls returning valid
structured output. Source recall, routing/tool selection, citation integrity and
refusal checks passed throughout. Failures:

- `data_04`: generic "payment-service" became an invented exact service filter,
  returning zero records instead of the category-level cohort.
- `mixed_02`: the current scenario's customer-impact threshold narrowed the historical
  cohort, although the question did not request that historical restriction.
- `mixed_07`: the question's historical scope was ambiguous. The model returned all
  severities; the frozen label described SEV1 only. The revised question explicitly
  says "SEV1 incidents"; expected numbers and the original failed grade are preserved.

The planner now receives a bounded, validated service/category catalog from read-only
SQLite and uses exact service names only for explicitly named-service requests.
Historical filters apply to the requested cohort; scenario/policy-only qualifiers
do not silently restrict history. This is context/schema guidance, with no extra
model tool, write access, arbitrary SQL or graph. Explicit historical impact filters
remain supported and are tested.

The first historical-scope target run passed 2/3: its remaining comparison used
only the bounded similarity sample and omitted the metrics tool. Tool descriptions
now distinguish recent examples from whole-cohort aggregates. Numeric comparison
requires `calculate_incident_metrics`; comparisons with similar incidents request
both tools with the same historical filters and the explicit scenario duration.
The failed targeted report remains available.

## Pre-guard completed broad run

The revised 50-case run completed with **49/50 (98%)** end-to-end pass and
**74/74** valid structured model calls. Source Recall@6, paragraph/provenance
citation integrity, refusal, routing, executed schemas, tool success and numeric
checks passed. Exact tool-selection accuracy was **98%**.

The sole failed case, `mixed_05`, added `find_similar_incidents` to a question needing
policy plus aggregate metrics only. The returned numbers, policy paragraphs and
duration comparison were correct; the strict exact-tool-set check failed. The extra
tool was bounded and read-only. Its failing grade is preserved.

| Measured broad-run quantity | Result |
|---|---:|
| Median / p95 case latency | 8.727 / 29.081 seconds |
| Provider input / output tokens | 240,537 / 46,275 |
| Provider-reported USD | 0.597828 |
| Safety cases | 4/4; zero model calls and zero tools |

[JSON results](../evaluation/live_openrouter/full_final/results.json),
[CSV](../evaluation/live_openrouter/full_final/cases.csv) and
[Markdown summary](../evaluation/live_openrouter/full_final/SUMMARY.md) retain all
50 public responses and grades. The original unchanged suite's 47/50 and partial
18/50 attempt remain separate. Pass-rate comparisons must disclose the one-question
dataset clarification. These are tuned regression measurements.

After the broad run, a prompt-only precision trial passed 2/3: it fixed `mixed_05`
but omitted the expected similarity tool in `mixed_02`. The
[failed trial](../evaluation/live_openrouter/targeted_tool_precision/SUMMARY.md) is
preserved and that prompt change was reverted. Its source hash matches the measured
broad-run prompt again.

The retained fix is a narrow deterministic executor guard: if metrics are already
planned and the question does not request examples/similar incidents, omit the
unrequested sample and record that action in response limitations. Explicit examples
remain supported. A separate live targeted run checks aggregate-only comparison,
explicit similarity comparison, and sample-only queries with historical impact
filters. Targeted results do not replace the broad **49/50** score. Source hashes
are recorded in `evaluation/live_openrouter/contract_versions.json`.

The retained guard's targeted run passed **4/4** (`mixed_05`, `mixed_02`, `data_09`,
`data_10`), with **6/6** valid structured calls. It preserved explicitly requested
similarity samples and the historical customer-impact filter. The measured complete
suite at that checkpoint was **49/50 before the guard**, with targeted verification
of the then-current executor. The subsequent complete 50/50 acceptance is recorded
above, without replacing either earlier report.

At the earlier 11-run checkpoint: **222 HTTP attempts**, **678,224 input** and
**136,422 output tokens**, and **USD 1.672900** provider-reported cost. This includes
failed/partial attempts and repeated diagnoses; it is not the cost of one 50-case run.
The [historical aggregate](../evaluation/live_openrouter/VALIDATION_before_final_acceptance.json) records those runs,
both dataset hashes, the single changed input field, current source hashes and hygiene
checks. Actual key value was not found in checked source/docs/result artifacts;
the private configuration remains mode 0600 and excluded from the final image.

The final native ARM64 image has matching provider/executor source hashes, runs as
UID 10001 and passes **50/50** offline with network disabled; see
[packaging evidence](../evaluation/live_openrouter/packaging.json).

In the retained live guard check, `mixed_05` proposed policy search, similarity and
metrics; the executor ran policy search and metrics only. The omission was recorded
in response limitations. Final hygiene checks covered 146 files with no actual
key match or broken local Markdown links; image/provider/executor hashes matched.

After the executor fix, **70 tests passed** and Ruff lint/format passed.
The original offline regression passed **50/50** with original golden/corpus hashes; see
[offline regression after live fixes](../evaluation/offline_after_live_fixes/SUMMARY.md).
The existing TestClient dependency deprecation warning remains; it is not a failed test.
