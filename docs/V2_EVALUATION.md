# V2 evaluation methodology

V1 reports, release tag and both 50-case datasets remain unchanged. The current
working-tree baseline before V2 was 115 passing tests, including both offline
regressions. Existing subscription-provider work was already present and is not
counted as new V2 functionality.

## Datasets and evidence boundaries

`investigation_dev.json` contains 22 development cases. It covers policy/data/mixed
paths, multiple policy dimensions, deterministic numbers and duration comparisons,
unknown policy detail, missing incidents, write/bypass refusal, explicit retrieval
faults, exhausted retry, persistent clarification/review and conflicting context.
Nine suitable common questions also run through V1, retaining full comparative
responses, routes, source sets, call counts and service latency. Different contracts
and evidence criteria are reported, not collapsed into a claim of universal superiority.

`investigation_heldout.json` contains 12 reserved cases with distinct IDs, authored
before its first acceptance run. It is excluded from the tuning test. The same
engineer authored both splits: this is a reserved synthetic regression check, not an
independently authored, blind or representative enterprise benchmark. After the first
reserved run its outputs must be retained; later modifications turn it into regression
coverage rather than a fresh unbiased holdout. CI reruns are explicitly regression.

The JSON reports record split, case/corpus hashes, snapshot reference, all responses
without ownership tokens, per-case checks/failures, traces, usage, latency and common
V1 comparisons. Explicit fault fields identify test-only source unavailability; they
are not presented as natural production failures. Output directories must be fresh.

## Deterministic acceptance checks

Per-case checks cover terminal status, route, expected dimensions/chunk citations,
complete-paragraph provenance, frozen reference values, retry count, tool-call bounds,
read-only names, human completion and proposed-only recommendations. Unit/integration
checks additionally cover malformed plans, tampered quotes/metadata/numbers, prompt
injection, severity applicability, authorization, schema rejection, wrong/replayed
resume, process restart, source drift, expiry/capacity, file permissions, serializer
restrictions and concurrent checkpoint ownership.

Numerical reference points are fixed from V1's independent expectations and synthetic
snapshot facts, not recalculated by the tool under test. V2 findings are verified
against code-generated tool-result text. The unit suite tests the grader with an
incorrect number and fabricated source metadata. End-to-end passing requires all
applicable case checks, not only a successful graph exit.

## Reproduction

```bash
pytest -q
ruff check .
ruff format --check .
python -m opspilot.cli evaluate-investigations --split development --output var/v2/dev-new
python -m opspilot.cli evaluate-investigations --split heldout --output var/v2/reserved-new
```

The V2 evaluation command forces local TF-IDF/extractive providers and does not read
the local `.env` file. Environment-selected data/corpus locations remain configurable.
Use a separate data directory if an API process already owns its checkpoint store.
It exits nonzero for failed cases. CI runs both V1 suites plus the V2 suites with
locked dependencies on Python 3.11/3.13; hosted CI execution is a separate fact from
local checks and is not implied before an authorized push.

## Results and limitations

First development run: 22/22. The section-focused synthesis revision also passed
22/22 with fewer displayed policy paragraphs; both private development reports are
retained. Earlier failed safety assertions/conditional-routing fixes are recorded
in the ignored local task log and development failure receipt. See
[V2 acceptance](V2_ACCEPTANCE.md) for the final measured tests, reserved score,
packaging/UI checks and remaining gates.

Offline latency is local graph/tool/checkpoint execution time, excluding human wait
and model/network latency. At the original offline acceptance, no paid V2 inference was authorized or executed. Zero
model tokens applies to offline mode only. Configured-provider transport is tested
with fixtures. Accepted planning usage is reported; `usage_complete=false` indicates
that a failed configured call may have unobserved usage. Failed provider calls and
embedding charges are not claimed to have zero cost. A paid live V2 evaluation,
provider-quality assessment, independent human review, adversarial coverage and
actual VPS/load testing remain separate gates.

## Functional completion regression — 2026-11-09

The previous 158-test / 22-of-22 development / first 12-of-12 reserved evidence is
preserved unchanged. The starting 158-test suite passed again before this slice.
The current full suite passes 189 tests, including 30 focused completion tests and
one additional typed API test; both V1 50-case offline regressions still pass.

Re-running the unchanged development cases initially produced 20/22: missing
cross-topic facets and a scenario now requiring clarification. The single combined
changed retrieval fixed the cross-topic gap, yielding 21/22. `mixed_comparison`
remains a recorded failed case under its original immediate-completion expectation:
its question never confirms the service is customer-facing. The new behavior pauses
rather than assumes this severity prerequisite. A separate integration test confirms
completion after a typed customer-facing response. Original labels and reports were
not edited to manufacture 22/22. The test of report generation explicitly expects
this known discrepancy; a green unit suite does not mean all development cases pass.
The existing CLI/CI development evaluation still exits nonzero for this case. Updating
the evaluation protocol and CI expectation belongs to the next evaluation slice;
release readiness is not claimed from this functional acceptance.

New coverage includes SEV1–4 boundaries and missing higher-severity prerequisites,
recorded/reported/proposed conflicts, unknown/zero/false handling, two-round restart,
unrequested fields, exact dimension gaps, changed policy content, decision/owner/
deadline tampering, threshold versus opened-at clocks, absent holiday calendars,
retrospective actions and conservative negative/uncertain prose intake.

See [current receipt](../evaluation/v2_completion_1_5/ACCEPTANCE.json),
[preserved development observations](../evaluation/v2_completion_1_5/OBSERVATIONS.md)
and [passing JUnit](../evaluation/v2_completion_1_5/pytest.xml). No reserved cases were
executed or tuned in this slice; the old 12/12 result is historical, not acceptance
of changed code. No new representative benchmark, live quality/cost result or
production accuracy is claimed. Offline model tokens and inference calls remain zero.

## Expanded completion evaluation — tasks 6–7

Two additional versioned suites are now available: 28 development cases in
`investigation_completion_dev.json` and 16 new reserved cases in
`investigation_completion_reserved.json`. Inputs were authored/frozen before execution;
the [preregistration](../evaluation/v2_completion_6_7/PREREGISTRATION.json) records
hashes. The [graph/grader freeze](../evaluation/v2_completion_6_7/RESERVED_FREEZE.json)
precedes the first reserved run. The same engineer authored both sets: this is a
separate reserved synthetic check, not independent human authorship or representative
enterprise generalisation. The reserved results were not used for code/prompt tuning.

The grader now checks proposed/recorded/reported severity, strict unknown/false/zero
provenance, individual supported/missing dimensions, explicit gaps, expected action
roles/deadlines/citations, absent absolute clocks and interrupt sequence. Negative
unit cases deliberately tamper with severity, owner, deadline, clock, dimension,
provenance, citation and interrupt history. Reports include per-check applicable
numerators/denominators so an unused expectation is not reported as tested coverage.
These bounded expectations do not establish general semantic correctness of every
possible recommendation. Missing fields are not filled by an LLM judge.

| Current run | Passed | Interpretation |
|---|---|---|
| New development, initial and final | 28/28 | Engineer-authored development regression |
| New reserved, first run | 14/16 | First result retained; no tuning/retry on these outcomes |
| Original development rerun | 21/22 | Known missing customer-facing clarification remains |
| Original 12-case reserved rerun | 11/12 | Regression only; initial historical 12/12 remains unchanged |
| Full tests | 204 | Includes six subscription fixture cases and nine new grader/development checks |

New reserved failures: `res-two-policy` correctly returns partial when communication
timing evidence is missing; `res-business-date` returns insufficient rather than the
labelled partial because it has no validated review evidence plus no holiday calendar.
The old `reserved_clarify` still has severity prerequisites missing after its supplied
answer, so returns partial. These are retained failures against frozen labels, not
silently relabelled passes. No failed response claims complete verification.

Reproduce with fresh output/data directories:

```bash
python -m opspilot.cli evaluate-investigations --suite completion --split development --output var/v2/completion-dev-new
python -m opspilot.cli evaluate-investigations --suite completion --split heldout --output var/v2/completion-reserved-regression-new
```

The default `--suite legacy` preserves original inputs and exit behavior. Both legacy
CLI suites currently exit nonzero for their recorded discrepancies; the new reserved
suite also exits nonzero for its two failures. Hosted CI/release readiness is not
claimed. Future reruns of the new reserved set are regression, not a fresh holdout.
A later improvement should use new development cases and retain these first results.

Six subscription fixtures exercise the real existing SSE/structured transport over
`httpx.MockTransport`, pinned account/model after restart, usage, invalid JSON, 429,
logout, safety/offline isolation and local API guards. Browser validation used only
a synthetic account and the same mock transport; displayed 101/19 counters are
fixture values, not measured token consumption. No real credentials, account catalog
or live inference were used. Paid/subscription live evaluation remains task 9.

[Detailed observations](../evaluation/v2_completion_6_7/OBSERVATIONS.md),
[first reserved output](../evaluation/v2_completion_6_7/reserved_first/results.json),
[old reserved regression](../evaluation/v2_completion_6_7/legacy_reserved_regression/results.json)
and [passing tests](../evaluation/v2_completion_6_7/pytest.xml) retain the evidence.

## First controlled live regression — task 9, 2026-11-09

The user deferred fresh Docker verification and authorized the controlled live phase.
The existing eligible `gpt-6-luna` ChatGPT-plan selection was reused, with no API-key
fallback or new permissions. The two unchanged completion case files (28 development,
16 previously inspected reserved cases) and graph/grader hashes were fixed before
inference. Paired offline baseline remained 28/28 and 14/16. These are regression
cases, not a new independent holdout.

| Measurement | Result |
|---|---|
| Requested / executed / unexecuted | 44 / 23 / 21 |
| Executed cases passed / failed | 16 / 7 |
| Same 23 cases, paired offline | 23/23 |
| Inference HTTP / valid structured responses | 23 / 23 |
| Reported input / output tokens | 97,313 / 3,610 |
| Median / p95 service latency | 4.663 / 8.801 seconds |
| Full offline unit/integration suite | 219 passed |
| Reserved cases executed live | 0/16 |

The run is **incomplete**, stopped by its predeclared three-consecutive-provider-or-
planning-failure gate. Do not present 16/23 as a complete 44-case result, or pair it
with the full 42/44 offline denominator as if the subsets matched. No automatic
retry, model/account/billing switch or post-result tuning occurred. No further live
calls were made after the stop.

All seven failed cases reached the planning/validation failure path despite valid
structured transport responses. Exact rejected plans and individual validation reason
codes were not retained, so route/tool omission or invented-argument explanations
remain hypotheses. The next diagnostic change should add bounded rejection codes
and safe plan summaries, then develop new offline cases before another separately
frozen live run. Do not weaken verification merely to improve a score.

Passing cases cover policy-based SEV1–4 assessment, explicit unknowns, scripted
clarification/restart, targeted retrieval recovery and appropriate partial/insufficient
results under labelled retrieval faults. All passing live cases are policy-only.
Mixed/historical end-to-end live acceptance and the two adversarial write cases were
not established by this stopped run. Scripted human responses are not independent
human review. Fixture/unit passes do not prove stochastic live planning compliance.

Budget controls were a hard maximum of 44 inference HTTP attempts, 32 KiB request
bodies, zero inference retries, existing read/stream/response-size limits, and observed
180k input / 32k output token stop thresholds. Per the official
[subscription preview limitations](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations),
`max_output_tokens` is unsupported on this route. Observed thresholds can overshoot
by the last completed request; they are not a server-side generation cap. The run
stopped on planning failures, below token thresholds. The adapter obtained no usable
USD pricing; do not infer zero cost from subscription usage.

Reproduction after a separately authorized run:

```bash
python -m opspilot.cli evaluate-investigations-live --suite completion --model gpt-6-luna --max-http-attempts 44 --input-token-stop 180000 --output-token-stop 32000 --output var/live_v2/new-run
```

The new runner injects an operator-owned recording provider factory into the existing
service; clients cannot supply it. It records safe HTTP/usage metadata and retains
partial reports, stops on account/quota/unknown-usage errors, source/case drift and
request/token/time limits. All checks except the explicit provider-mode/call budget
remain the original deterministic graders. No policy, case label, prompt or tool
permission was changed for this evaluation. V1 provider/executor code is unchanged.

[Live summary](../evaluation/v2_live_task9/SUMMARY.md),
[protocol](../evaluation/v2_live_task9/PROTOCOL.json),
[results](../evaluation/v2_live_task9/results.json),
[failed cases](../evaluation/v2_live_task9/FAILURES.json) and
[paired analysis](../evaluation/v2_live_task9/ANALYSIS.json) preserve this incomplete run.
Public copies normalize repository-absolute metadata paths only; case content, model
outputs and metrics are unchanged. Credentials, ownership tokens and runtime/checkpoint
files are excluded; complete raw reports remain in ignored runtime storage.

## Offline planner contract follow-up

A later offline planner-contract increment is recorded separately in
[its receipt](../evaluation/v2_planner_contract/SUMMARY.md). It adds 18 hand-authored
HTTP/control fixtures (237 total tests) and preserves the existing 28/28, 14/16,
21/22 and 11/12 evaluation outcomes. These fixtures are development evidence, not a
reconstruction of the seven unrecorded rejected plans or evidence of improved live
success. Future reports include bounded `planning_diagnostic` codes and route/tool
summaries; full model output and arguments are not logged for rejection diagnosis.

The [targeted live proposal](../evaluation/v2_planner_contract/NEXT_LIVE_PROPOSAL.json)
was pending approval and unexecuted at that offline milestone. Its nine cases
reuse previously inspected development inputs with unchanged labels; they are
regression, not a fresh held-out set. Seven prior failures, one passing control and
one safety case are selected before new inference. The proposal fixes source/case
hashes, model, at most eight HTTP attempts, 32 KiB/request, observed 50,000/8,000
input/output token stops and a 300-second elapsed-time stop. Last-call token/time
overshoot remains possible. Original stop gates and failed evidence are preserved.

## Subsequent authorized live regression — 2026-11-09

The targeted protocol later executed eight inference cases, all passing, before its
HTTP cap stopped admission of the remaining zero-call refusal. Its 8/9 incomplete
report is preserved. Two offline fixtures cover a narrow admission correction;
the hard transport cap and all token/time/failure/source gates remain. A separately
frozen safety-only protocol passes without provider/tool/HTTP calls.

A new full protocol then executes all **44/44 cases**, with **42 passes**:
development **28/28**, reserved regression **14/16**, matching paired offline.
All six mixed cases pass. The same 23-case subset changes from the original 16/23
to 23/23; this is a repeated synthetic comparison, not a causal or independent
generalisation estimate. No case labels or deterministic graders were changed.

The two remaining failures are unchanged: communication timing evidence is missing,
and the business-date case is insufficient rather than frozen expected partial.
The first rejected raw plans remain unavailable, so exact historical causes are
not reconstructed. [Full validation](../evaluation/v2_planner_live_regression/VALIDATION.md)
and [analysis](../evaluation/v2_planner_live_regression/ANALYSIS.json) retain all results.

The full run used 42 structured HTTP calls, 183,606 input / 6,119 output tokens,
median/p95 service latency 7.050/10.999 seconds. The final call crossed the observed
180,000 input threshold by 3,606 tokens; no further inference followed. Across both
inference protocols this slice used 50 requests, 218,653/7,714 tokens, with unknown
USD price. The safety-only run has no usage events and zero requests. Full pytest
239 passes; fresh Docker/public-release acceptance is not claimed.
## Evidence-gap correction regression — 2026-11-09

The two previously reported failures are fixed without changing their input cases,
expected labels or deterministic graders. The latest full protocol executes 44/44,
all passing (development 28/28, reserved regression 16/16), matching paired offline.
Communication now has ownership+cadence evidence; the exact review-date case remains
appropriately partial with cited conditional relative deadlines and explicit missing
calendar/resolution gaps. The historical 42/44 record is preserved.

Fourteen added test instances cover reviewed-content applicability, severity-specific
exclusion, retry recovery/exhaustion, missing ownership/timetable, verified resolution
and rejection of fabricated absolute dates. Full pytest is 253 passed. Eight new
development cases first pass 7/8; a question rephrasing for an existing conservative
safety-guard limitation produces 8/8. Both input revisions and the failed first result
are retained. This is development tuning, not independent holdout evidence. Original
legacy regression remains 21/22 and 11/12 for its existing missing prerequisites.

The live run uses 42 successful structured calls and reports 183,606/5,886 tokens;
the final input threshold overshoot is 3,606 with no subsequent request. USD cost
is unavailable. See the [fix receipt](../evaluation/v2_evidence_gap_fix/VALIDATION.md),
[target cases](../evaluation/v2_evidence_gap_fix/TARGET_CASES.json) and
[full analysis](../evaluation/v2_evidence_gap_fix/ANALYSIS.json). No fresh reserved
set, production accuracy, fresh Docker or release acceptance is claimed.
## Current CI closeout contract

CI runs completion development/reserved and evidence-development protocols as strict
all-pass gates. Original legacy cases/labels remain unchanged, including their 21/22
and 11/12 scores. The new [report gate](../scripts/check_v2_reports.py) checks all
case IDs, counts, source hashes, zero inference and score/check consistency, and
accepts exactly the documented awaiting-clarification and partial-severity cases.
Any extra failure or changed expected prerequisite behavior rejects the gate. CLI
evaluation remains strict and returns 1 for those legacy reports; CI validates that
exit explicitly. This is a compatibility contract, not relabelled benchmark success.

See [local closeout](../evaluation/v2_closeout_review/VALIDATION.md). Current local
review runs 257 passing tests and deliberately excludes five tests requiring Git.
Hosted CI/history inspection remain held; no new inference is performed. Existing
synthetic/held-out interpretation limits and historical failure receipts remain.
