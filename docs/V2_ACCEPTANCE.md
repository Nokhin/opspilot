# V2 local acceptance — 2026-11-08

V2's graph, evidence verification, bounded correction, persistent human review and
additive API/UI are implemented. This receipt distinguishes local functional
acceptance from paid-model, fresh-base-image and public deployment gates.

| Check | Measured result |
|---|---|
| Starting working-tree baseline | 115 tests passed |
| Final macOS Python 3.13.9 suite | 158 tests passed |
| Fresh locked virtualenv, offline installation | 158 tests passed; pip check passed |
| Ruff lint / formatting | Passed |
| V1 current / legacy offline regressions | 50/50 and 50/50; original reports/tag unchanged |
| V2 development | 22/22; 38 tool calls; median 5.57 ms |
| First reserved V2 run | 12/12; 16 tool calls; median 5.37 ms |
| Linux ARM64 / Python 3.11.17 cached-runtime image | 149 tests passed; nine Git publication tests excluded |
| Linux offline evaluation | V1 50/50 + 50/50; V2 22/22 + 12/12 |
| Real container HTTP/restart journey | 12/12 checks passed; no repeated tools; incident DB unchanged |
| Browser UI | Clarification, review, reload/restore and completed brief verified; zero console errors |
| Inference cost | No paid V2 inference; zero offline model tokens |
| Publication/export checks | 221 reviewed files; zero scope violations or broken local Markdown links |

The native ARM64 validation container ran as UID 10001, with a read-only root,
dropped capabilities, no-new-privileges, 1.5 CPU and 2 GiB limits. Tests and evaluations
ran with networking disabled. A separate loopback HTTP container proved that a human
review can resume after container restart with the same ownership capability.
This is local container evidence, not a VPS or throughput benchmark.

## Inspectable evidence

- [Machine receipt and source hashes](../evaluation/v2/ACCEPTANCE.json)
- [Final development responses/checks and nine V1 common tasks](../evaluation/v2/development_final/results.json)
- [First development run](../evaluation/v2/development_initial/results.json)
- [First reserved run, preserved unchanged](../evaluation/v2/heldout_first/results.json)
- [Container HTTP/restart checks](../evaluation/v2/container-api.json)
- [Sanitized full macOS JUnit](../evaluation/v2/pytest-macos.xml)
- [Preserved development failures and corrections](../evaluation/v2/DEVELOPMENT_OBSERVATIONS.md)
- [Completed UI brief](../evaluation/v2/brief-completed.jpg)

## Interpretation and remaining gates

Both suites are engineer-authored synthetic regression. The reserved set was authored
before first execution and was not used for tuning; it is not an independent or
representative semantic benchmark. Repeated Linux/CI runs are regression checks.
Offline service latency excludes model/network time and human waiting. The nine
common V1 tasks report routes, source sets, tool counts and latency under different
response contracts; all nine routes agree. The common mixed comparison used one
additional V2 retrieval call. These observations do not establish that V2 is universally
more accurate or more efficient.

Fresh `Dockerfile` builds were attempted twice and blocked while resolving
`python:3.11-slim` by registry HTTP 503. To test Linux compatibility without concealing
that failure, a separate image used the existing local V1 validation runtime plus
the current source and locked Linux wheels, built with network disabled. The original
Dockerfile/Compose path is updated and Compose syntax passes; a fresh base-image build
still needs rerunning when registry access recovers. The cached-runtime validation
must not be represented as that fresh build. It is ARM64 only; new AMD64 acceptance
is not claimed.

No paid V2 provider evaluation, hosted CI run, push, merge, tag/release, VPS deployment,
production authentication, independent human-quality review or load test occurred.
Configured planning has provider/transport fixture coverage. Tokens provide per-demo
investigation ownership, not enterprise user identity. Retention is lazily enforced;
checkpoints are not encrypted at rest. Section/topic verification remains bounded to
this versioned corpus. See [architecture](V2_ARCHITECTURE.md) and
[evaluation methodology](V2_EVALUATION.md) for the full limits and reproduction path.

## Functional completion 1–5 receipt — 2026-11-09

The table above records the earlier graph baseline. This slice completes five
functional follow-ups; it does not constitute full V2 product/release sign-off.

| Current check | Measured result |
|---|---|
| Pre-change baseline rerun | 158 passed |
| Full current offline suite | 189 passed |
| Focused completion cases | 30 passed; one further typed API test included in full suite |
| V1 current / legacy offline cases | 50/50 and 50/50 in the full suite |
| Original V2 development cases | 21/22; `mixed_comparison` now pauses for a missing prerequisite |
| Ruff / format / JavaScript / dependencies | Passed |
| Offline wheel | Reviewed policy contracts packaged successfully |
| Browser journeys | Two typed clarification rounds; supported SEV1 with unknowns retained; review/reload/restore/accept/completed; no console warnings/errors |
| Live inference / new reserved / Docker / hosted CI | Not run in this slice |

Severity is policy-gated and separates recorded/reported/proposed values. Explicit
evidence dimensions must be covered. Missing facts use bounded typed clarification.
Briefs contain incident-specific findings and cited proposed owners/triggers/timing.
Unknown threshold clocks do not become absolute deadlines; resolved snapshots are
retrospective. Proposed actions remain read-only and unexecuted.

[Machine receipt](../evaluation/v2_completion_1_5/ACCEPTANCE.json),
[development discrepancy and corrections](../evaluation/v2_completion_1_5/OBSERVATIONS.md),
[passing JUnit](../evaluation/v2_completion_1_5/pytest.xml) and
[current completed brief](../evaluation/v2_completion_1_5/brief-completed.jpg)
record this slice separately. Frozen V1/V2 reports and case inputs are unchanged.
A current reserved-set result is deliberately not claimed. Remaining tasks 6–10,
fresh-base-image validation, paid-model quality and public release remain outstanding.

Final privacy review: 239 public-scope export files and all 374 Git objects passed
the publication guard; zero broken local Markdown file links. All 135 frozen
baseline corpus/evaluation files and 11 pre-existing V1/provider files match their
starting hashes. No objects were published or history changed.

## Tasks 6–7 receipt — 2026-11-09

Subscription integration and expanded evaluation are implemented; live model/release
acceptance remains separate. The offline default and V1 provider/transport are preserved.

- Full suite: **204 passed**, including six real-transport subscription fixtures and
  nine added evaluation/development checks. Both V1 suites remain **50/50**.
- New development: **28/28**. First new reserved: **14/16**.
- Unchanged original development/reserved regression: **21/22** and **11/12**.
  Original historical 22/22 and 12/12 artifacts remain byte-identical.
- Browser fixture: selected subscription controls, review, reload/restore and completion
  with one planning call; zero console errors/warnings. This is mocked inference.
- Ruff/format, JavaScript syntax, dependency and source-freeze checks passed.

The new failures identify incomplete communication timing retrieval and an overoptimistic
partial-status expectation for missing review evidence; the old reserved clarification
still lacks severity facts. First results/labels remain unchanged and were not used
for tuning. A green test suite must not be presented as all evaluation cases passing.
The default CLI/CI evaluation remains nonzero; full product sign-off is outstanding.

[Machine receipt](../evaluation/v2_completion_6_7/ACCEPTANCE.json),
[preregistration](../evaluation/v2_completion_6_7/PREREGISTRATION.json),
[freeze](../evaluation/v2_completion_6_7/RESERVED_FREEZE.json) and
[observations](../evaluation/v2_completion_6_7/OBSERVATIONS.md) document this slice.
No live inference, credential changes, new Docker/hosted CI run, commit/push, release
or deployment occurred. Tasks 8–10 remain outside this slice.

Final checks: 264 reviewed public-scope files, all 404 stored Git objects and local
Markdown links passed (zero violations/broken links). All 148 pre-existing frozen
corpus/evaluation files and 15 protected V1/provider/configuration files match their
starting hashes. The offline wheel includes both frozen new case suites.

## Task 9 first live receipt — incomplete, 2026-11-09

The user deferred task 8 and authorized live evaluation using the existing ChatGPT
plan and fixed `gpt-6-luna`. The 44-case protocol stopped after 23 cases when three
consecutive planning-stage failures reached the configured gate. **16 passed, 7 failed;
21 were not executed.** No reserved live cases were executed.

- HTTP/structured calls: **23/23**; input/output tokens: **97,313 / 3,610**.
- Median/p95 service latency: **4.663 / 8.801 seconds**. No usable USD price obtained.
- Paired same 23-case subset: offline **23/23**, live **16/23**.
- Full current tests: **219 passed**, including 15 additional bounded-runner fixtures.
- All passing live cases are policy-only. Mixed/historical live acceptance is pending.
- Frozen graph, prompt, grader, cases and permissions were not tuned after results.

[Protocol](../evaluation/v2_live_task9/PROTOCOL.json),
[summary](../evaluation/v2_live_task9/SUMMARY.md),
[results](../evaluation/v2_live_task9/results.json),
[failures](../evaluation/v2_live_task9/FAILURES.json) and
[analysis](../evaluation/v2_live_task9/ANALYSIS.json) are retained. No retry or further
inference followed the stop. This is a partial measurement, not task 9 full acceptance
or a production-readiness claim. Existing offline/frozen reports remain unchanged.

Exact rejected plans/reason codes were not retained, limiting root-cause diagnosis.
A follow-up should instrument bounded, non-sensitive rejection diagnostics and use
fresh development cases before seeking another frozen live evaluation. Neither a
larger request budget nor weakened safety validation is justified by this run alone.
Task 8 remains deferred; task 10, deployment and public release remain unperformed.

Task 9 evidence hygiene: 278 public-scope export files and 459 stored Git objects
passed review, with zero broken local Markdown links. The 172 pre-existing frozen
corpus/evaluation artifacts, both V1 case files and 18 protected components match
starting hashes. Incident database/index bytes are unchanged across the live run.
The native demo was restarted and remains offline; no additional inference followed
the stop. These checks do not turn the incomplete live result into acceptance.

## Offline planner contract follow-up — 2026-11-09

The planner receives explicit server-derived requirements and rejected plans now
retain bounded enum-only diagnosis through checkpoints/API/evaluation. This increment
does not establish the exact cause of the original seven live failures or prove
that live model behavior has improved. Invalid proposals still fail before dispatch;
permissions, schema/citation checks and the one-call planning budget are unchanged.

- **237 tests passed**, up from 219, including 18 new hand-authored HTTP/control cases.
- V1 current/legacy: **50/50 + 50/50**. New development/reserved regression:
  **28/28 + 14/16**. Original development/reserved: **21/22 + 11/12**.
- Ruff, formatting, dependency integrity and offline HTTP ownership smoke passed.
- **196 pre-existing artifacts/protected files unchanged**, including the first live
  run. Zero real inference requests/tokens in this slice. Native demo remains offline.
- Graph contract 5 rejects old pending snapshots without deleting or migrating them.

[Receipt](../evaluation/v2_planner_contract/SUMMARY.md) and
[machine evidence](../evaluation/v2_planner_contract/ACCEPTANCE.json) preserve the
development failures and passing checks. A concrete nine-case, eight-request
[live proposal](../evaluation/v2_planner_contract/NEXT_LIVE_PROPOSAL.json) is prepared
but unapproved/unexecuted. Task 8 remains deferred; task 9 live and task 10 release
acceptance remain incomplete.

Final follow-up hygiene: 297 public-scope files and all 491 stored Git objects
passed review, with zero violations/broken local Markdown links. All 196 protected
baseline files and the proposed source hashes remain unchanged.

## Full subscription regression follow-up — 2026-11-09

Execution now completes **44/44 cases, 42 passed** using a new frozen protocol:
development **28/28**, reserved regression **14/16**, matching paired offline.
All **6/6 mixed** and **1/1 data-only** cases pass. The original common 23-case
subset is now **23/23**, while its historical **16/23** record remains unchanged.
Two evidence/expectation failures remain; completed execution is not full quality
or product/release acceptance.

- **42/42 structured HTTP calls**, one planning call maximum per investigation.
- Full run: **183,606 input / 6,119 output tokens**; median/p95 **7.050/10.999s**.
- Citation integrity among cited cases: **38/38**; both write-request refusals make
  zero provider/tool calls. Incident database/index bytes are unchanged.
- Current pytest **239 passed**, including both V1 **50/50** suites; Ruff/format pass.
- Input stop threshold crossed only by the last request, overshooting by **3,606**;
  no requests followed. Observed thresholds are not provider-side caps. USD unknown.

The targeted probe remains **8/9 incomplete**, despite all eight inference cases
passing: its HTTP cap prevented the zero-call final safety case. A narrow runner
admission correction has two offline fixtures, and a separate safety-only protocol
passes without inference. No stopped run was resumed or overwritten. Total this
slice: **50 inference requests**, **218,653 input / 7,714 output tokens**.

[Full validation](../evaluation/v2_planner_live_regression/VALIDATION.md),
[results](../evaluation/v2_planner_live_regression/results.json),
[failures](../evaluation/v2_planner_live_regression/FAILURES.json) and
[targeted probe observations](../evaluation/v2_planner_live_probe/OBSERVATIONS.md)
preserve the distinction. Task 9's full protocol has now executed; communication
retrieval and the review-date evidence/expectation discrepancy remain unresolved.
Task 8 stays deferred, and task 10/public deployment remain unperformed.

Final follow-up hygiene: 323 public-scope files (288 byte-identical prior reviews,
35 new/changed content reviews), all 532 stored Git objects, zero violations/broken
Markdown links. All 210 pre-existing frozen artifacts/protected files are unchanged.
## Two evidence-gap fixes — 2026-11-09

The previously reported communication and review-date cases pass their original
expectations. Current completion offline/live regression is **44/44** (28/28 + 16/16),
up from the preserved 42/44. Communication has ownership and cadence evidence;
review-date output is partial with cited conditional business-day guidance and
explicit missing calendar/verified-resolution gaps. No case label/grader was changed.

- Full pytest **253 passed**; both V1 offline suites **50/50**. New development **8/8**
  after its documented question revision; first 7/8 and fixture failures retained.
- Legacy development/reserved regression remains **21/22 + 11/12**, with existing
  missing-prerequisite discrepancies retained rather than relabelled.
- Live **42/42 structured calls**; input/output **183,606/5,886**, median/p95
  **7.444/10.701s**, citation integrity **39/39** among citation-bearing cases.
- Final-call input threshold overshoot **3,606**, no further inference; USD unknown.
- Native offline HTTP verifies both fixes and ownership. Live database/index and
  **241 pre-existing artifacts/protected components** remain unchanged.

[Detailed validation](../evaluation/v2_evidence_gap_fix/VALIDATION.md),
[machine receipt](../evaluation/v2_evidence_gap_fix/ACCEPTANCE.json) and
[target outputs](../evaluation/v2_evidence_gap_fix/TARGET_CASES.json) record the result.
This is synthetic regression acceptance for the two fixes, not production accuracy
or overall release sign-off. Task 8 remains deferred and task 10 unperformed.

Final incremental publication review covers 349 public-scope files (284 byte-identical
to the prior passed review and 65 new/changed content reviews), plus all 576 stored
Git objects. Zero content/scope violations or broken local Markdown links. All 241
preserved corpus/case/report/protected files remain unchanged. No publication occurred.
## Current local closeout review — 2026-11-09

The current [review candidate](V2_REVIEW.md) has 257 locally passing tests, with five
Git-history tests intentionally not run under the no-Git boundary. Current completion
offline remains 44/44; evidence development 8/8; both V1 CLI protocols 50/50. A separate
gate accepts only the exact original legacy prerequisite differences, retaining
their 21/22 and 11/12 scores and strict nonzero CLI exits. Hosted CI is not triggered.

The [local closeout receipt](../evaluation/v2_closeout_review/VALIDATION.md) records
offline package/source/artifact review. Git history is not freshly audited in this
session; prior history receipts are historical only. Fresh Docker remains deferred,
and all Git, release and deployment steps remain held for operator confirmation.

Final source/artifact privacy review: 361 candidate files; zero configured-pattern/
exact-value findings, raw sensitive JSON fields or broken local Markdown links.
Six retained synthetic screenshots reviewed; 307 original source/corpus/evaluation
files unchanged. No Git/history inspection or publication performed. Full history
review remains pending after operator authorization; this is not universal PII assurance.
