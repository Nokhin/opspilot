# Full controlled V2 live regression — 2026-11-09

The frozen 44-case protocol completed: **42/44 passed**, matching its paired offline
42/44. Execution is complete; quality/product acceptance still has two unresolved
cases. Inputs and labels are unchanged. These are previously inspected, engineer-authored
synthetic regression cases, not a fresh independent holdout or production accuracy.

| Check | Actual result |
|---|---|
| Model / inference path | Fixed `gpt-6-luna`, existing pinned subscription; no billing fallback |
| Development / reserved regression | 28/28 and 14/16 |
| Full executed / unexecuted | 44 / 0 |
| HTTP attempts / valid structured outputs | 42 / 42; no planning rejections |
| Mixed / data-only / unsupported cases | 6/6, 1/1 and 2/2 |
| Citation integrity among citation-bearing cases | 38/38 |
| Maximum planning / tool calls per case | 1 / 3 |
| Median / p95 service latency | 7.050 / 10.999 seconds |
| Full-run input / output tokens | 183,606 / 6,119 |
| Current pytest | 239 passed; includes both V1 50/50 offline suites |
| Incident database / index after all three runs | Byte-identical to each preregistered snapshot |

The same 23 cases executed by the first live run now pass **23/23**, versus its
preserved 16/23. The targeted eight-request probe separately passed all eight executed
cases; its original planned safety case was not reached and that report remains 8/9
incomplete. A separate zero-inference safety check and the full regression both test
the refusal path. See [probe observations](../v2_planner_live_probe/OBSERVATIONS.md).

## Preserved failures

- `res-two-policy`: partial rather than completed; missing SEV2 communication timing
  evidence. The verifier exposes the missing dimension after the bounded retry.
- `res-business-date`: insufficient rather than frozen expected partial; review-policy
  evidence and an approved holiday calendar are missing. No exact business-day date
  is invented. The label remains unchanged for this regression.

Both also fail the paired offline baseline. No case, grader, prompt, permission or
evidence authority was changed during either live run. Passing a conflict/unknown
case can mean a correctly limited partial/insufficient result, not completed evidence.
The original seven rejected plans were not retained, so their exact historical
validation causes remain unknown despite the subsequent passing observations.

## Budget and interpretation

The full run allowed 44 HTTP attempts, 32 KiB/request, 900 seconds and observed
180,000/32,000 input/output token stops, with no provider retry. The final, 42nd
request first crossed the input threshold, overshooting by **3,606 tokens**. No
inference followed. This is the preregistered last-call overshoot, not a server-side
token cap. USD cost is unavailable and is not assumed zero.

This work slice used **50 inference HTTP requests**, reporting **218,653 input /
7,714 output tokens** across the eight-request probe and 42-request full run. Account
preflight/normal refresh is separate from inference counts. A local export helper
initially lacked the repository module path; rerunning only the export via `runpy`
resolved it without repeating inference or changing raw reports.

[Preregistration](PREREGISTRATION.json), [protocol](PROTOCOL.json),
[full results](results.json), [failures](FAILURES.json), [analysis](ANALYSIS.json),
[passing JUnit](pytest.xml) and both paired-offline directories retain the evidence.
Public JSON copies normalize repository-absolute metadata prefixes only. Runtime
checkpoints, credentials, account references and ownership capabilities are excluded.

The fresh Docker task remains deferred. Communication retrieval and the review-date
evidence/expectation discrepancy remain follow-ups; Git/public release and deployment
acceptance are not claimed. No push, merge, tag/release or deployment occurred.

Final incremental publication review covers 323 public-scope files: 288 byte-identical
to the prior passed review and 35 new/changed content reviews. All 532 stored Git
objects pass; zero scope/content violations or broken local Markdown links. All 210
pre-existing frozen artifacts/protected files remain unchanged. These hygiene checks
do not resolve the two remaining functional/evaluation discrepancies.
