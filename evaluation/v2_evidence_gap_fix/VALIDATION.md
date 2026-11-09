# Evidence-gap fixes — 2026-11-09

Both reported cases now pass their original frozen expectations. The unchanged
44-case live regression changes from **42/44 to 44/44**: development **28/28** and
reserved regression **16/16**, matching paired offline. These previously inspected,
engineer-authored synthetic cases are regression evidence, not independent held-out
generalisation or production accuracy. Historical failed reports remain unchanged.

## Corrected behavior

- **SEV2 communication:** the brief now cites ownership and cadence sections, identifies
  the Customer Service Lead and proposes the first notice within 30 minutes with
  updates at least every 60 minutes while impact continues. The original case is
  completed. Missing ownership still produces partial, and no communication is sent.
- **Review date:** due/date/calendar wording now requests the timetable plus mandatory
  review criteria. Reviewed general-review paragraphs apply to lower severity bands
  conditionally, despite mentioning only the literal SEV1. The brief cites the
  applicability and timetable, with proposed SEV2 scheduling within 5 business days
  and a draft within 10 business days **if review is mandatory**. The original exact-date
  case is partial: the approved holiday calendar and verified resolution timestamp
  are absent. No calendar date, review requirement or execution is invented.

The retry query now uses document title plus missing-section title without the
global severity suffix that diluted cross-document ownership retrieval. It still
uses the same typed read-only search tool, authority, top-k/budget limits and maximum
one changed retry. Required sections and deterministic verification are unchanged.

Only the two existing, content-hash-reviewed review paragraphs receive the general
applicability treatment. Changed content fails closed under the original severity
filter. Relative review proposals require both criteria and timetable citations;
missing timetable evidence cannot support a deadline. Exact dates use neither
incident opening nor snapshot reference time as a substitute for resolution.

Source changes are limited to [planning](../../opspilot/investigation/planning.py),
[graph retry](../../opspilot/investigation/graph.py),
[evidence verification](../../opspilot/investigation/evidence.py) and
[brief proposals](../../opspilot/investigation/brief.py), plus
[new tests](../../tests/test_investigation_evidence_gaps.py),
[development cases](../../opspilot/evaluation/investigation_evidence_gaps_dev.json)
and technical documentation. No dependency, V1 tool, API contract or provider change.

## Measured checks

| Check | Actual result |
|---|---|
| Starting / current pytest | 239 / 253 passed |
| New development cases | 8/8 after the documented question revision |
| Existing completion offline / live | 44/44 and 44/44 |
| Legacy development / reserved regression | 21/22 and 11/12; existing prerequisite discrepancies retained |
| V1 current / legacy offline | 50/50 and 50/50, included in pytest |
| Native offline HTTP | Both original questions, citations, proposed owners/relative timing and owner isolation passed |
| Model / HTTP / structured planning | Fixed `gpt-6-luna`; 42/42 calls; no planning rejection |
| Citation integrity among cited cases | 39/39 |
| Maximum planning / tool calls per case | 1 / 3 |
| Input / output tokens | 183,606 / 5,886 |
| Median / p95 service latency | 7.444 / 10.701 seconds |
| Read-only incident database / policy index | Unchanged after live execution |
| Existing corpus, cases, reports and protected components | 241 files unchanged |

The final, 42nd request first crossed the observed 180,000 input-token threshold by
3,606. No inference followed. The protocol allowed last-call overshoot and does not
claim a provider-side token cap. USD price is unavailable, not assumed zero. No
API-key billing fallback or provider retry was used.

## Preserved development failures and limits

The new development suite first passed 7/8. A policy phrase containing `update
frequency` with a non-leading question was rejected by the existing conservative
V1 unsafe-request guard. That failed report and input remain in
[development-first](development-first/results.json). The development prompt was
revised to an explicit What-question, retaining its expected behavior and all safety
controls; this is transparent development revision, not a fresh held-out result.
The initial focused tests also exposed the same phrase issue and an unused import.
An export-helper syntax error was corrected without repeating inference or changing
raw reports. Existing guard paraphrase limitations remain outside these two fixes.

The original 42/44 and earlier stopped runs are not relabelled. Older legacy cases
still encounter missing incident prerequisites, and cross-version checkpoints fail
closed without deletion/migration. Fresh Docker validation remains deferred; Git,
hosted CI/release and deployment closure remain separate and unperformed.

[Preregistration](PREREGISTRATION.json), [protocol](PROTOCOL.json),
[live results](results.json), [target briefs/checks](TARGET_CASES.json),
[analysis](ANALYSIS.json), [JUnit](pytest.xml), [HTTP receipt](api-smoke.json)
and all five offline regression directories retain the evidence. Raw credentials,
account bindings, ownership tokens and checkpoint files are excluded; exported JSON
only removes repository-absolute metadata prefixes.

Final incremental publication review covers 349 public-scope files (284 byte-identical
to the prior passed review and 65 new/changed content reviews), plus all 576 stored
Git objects. Zero content/scope violations or broken local Markdown links. All 241
preserved corpus/case/report/protected files remain unchanged. No publication occurred.
