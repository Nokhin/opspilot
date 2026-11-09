# Planner contract development receipt — 2026-11-09

The V2 planner now receives server-derived minimum route/tool requirements, a tool
budget and exhaustive allowed incident IDs/durations. Proposals still pass the same
authoritative schema/domain checks before any tool dispatch. Invalid proposals are
rejected, without automatic completion, fallback or another model call. Incident IDs
now require a complete token rather than a substring match.

An optional `planning_diagnostic` persists through owner-authorized API reads and
evaluation reports. It contains a stable rejection code, stage, required/proposed
routes and up to four tool names on each side. It excludes raw plans, tool arguments,
prompts, credentials, account references and exception bodies. Transport and malformed
output remain grouped where the unchanged V1 adapter cannot safely distinguish them.
Known usage remains complete after a successfully parsed plan is rejected by domain
validation; failure before inference does not become an invented provider attempt.

| Check | Measured result |
|---|---|
| Starting / current pytest | 219 / 237 passed |
| New development fixtures | 18 passed; injected HTTP only |
| Completion development | 28/28 |
| Completion reserved regression | 14/16; existing two failures retained |
| Original development / reserved regression | 21/22 and 11/12; existing failures retained |
| V1 current / legacy | 50/50 and 50/50, exercised by full pytest |
| Ruff / formatting / dependency integrity | Passed |
| Native offline HTTP | Completed brief, owner GET 200, wrong owner 404; subscription disabled |
| Pre-existing corpus, cases, reports and protected components | 196 files unchanged |
| Real inference in this slice | Zero calls, zero model tokens |

Hand-authored replies cover policy/data/mixed plans, historical metrics, typed
clarification, review/restart, missing evidence tools, incorrect routes, invented
IDs/durations, malformed output and exhausted budgets. They do not simply echo the
deterministic planner. The live-runner fixture proves that domain diagnostics survive
reporting and that three consecutive failures still stop the run. These fixtures
verify controls and wiring, not model adherence or production accuracy.

The first fixture pass had one overoptimistic completion expectation and five
double-close teardown errors. The fixture was corrected; a missing severity fact
still produces partial after human acceptance. Raw failed test receipts remain in
ignored runtime storage. A local reporting wrapper also used the wrong return shape;
the already-written evaluation result was retained. Sandbox loopback restrictions
were resolved through authorized local checks, without external inference.

The original live run remains **16/23 executed cases**, with seven failures and
21 unexecuted cases. The original rejected plans were not recorded: no exact cause
is retrospectively claimed. Contract disclosure is a testable candidate improvement;
its live effect is still unmeasured. No reserved labels, prompts from the first live
run, original artifacts or evidence/permission checks were weakened or overwritten.

Graph contract 5 fails closed for older pending snapshots; checkpoints are not deleted
or migrated. Task 8 remains deferred, and task 9/10 acceptance remains incomplete.
No push, merge, release or deployment occurred.

[Machine receipt](ACCEPTANCE.json), [passing JUnit](pytest.xml),
[offline HTTP receipt](api-smoke.json) and the four regression subdirectories record
this increment. [Next live proposal](NEXT_LIVE_PROPOSAL.json) is **unapproved and
unexecuted**: nine previously inspected development cases (seven prior failures,
one passing control and one zero-call safety case), at most eight inference HTTP
attempts, fixed `gpt-6-luna`, no retry/fallback, and observed input/output token stop
thresholds of 50,000/8,000. The subscription route has no server-side output token cap;
the final call can overshoot a token/time threshold. USD cost is unavailable. A new
preregistration and explicit approval are required before executing that proposal.

Final hygiene: 297 public-scope files and all 491 stored Git objects passed review;
zero violations/broken local Markdown links. All 196 baseline files and proposed
source hashes remain unchanged. These checks do not establish live acceptance.
