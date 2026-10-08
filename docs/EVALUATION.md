# V1 evaluation methodology

50 authored cases: 15 policy, 3 multi-document, 3 ambiguous, 8 unsupported, 10 data,
7 mixed and 4 safety. Policy sections/reference points were labelled before the
first run. `evaluation/GOLDEN_PROVENANCE.md` describes independent raw-SQL calculations
frozen in `cases.json`; the runner does not derive expected values from the tool.

Default dataset: `cases_v1_1.json`. Only the wording of `mixed_07` was clarified after
a live run exposed ambiguous historical scope; all numeric/route/source labels and
the other 49 questions remain unchanged. The legacy `cases.json` remains available
with its original hash/reports. See [golden provenance](../evaluation/GOLDEN_PROVENANCE.md).

Run `python -m opspilot.cli evaluate` for JSON with full responses/checks and manifest,
CSV case results, and Markdown summary. The manifest records mode, embedding, top-k,
corpus/case hashes, snapshot reference and UTC run time. Failure groups remain visible.

## Deterministic checks

Pass requires expected route/exact tool set, successful execution, schema and filter
matches, source/section recall, citation coverage/integrity, refusal flag, numeric
results, reference phrases and required evidence planes. Safety cases require zero tools.
Document Recall@K averages expected source coverage per labelled case. Section recall
and citation coverage are stricter per-case checks. Numeric tolerance is 1e-4.

Citation integrity checks complete verbatim paragraphs plus document/title/section/version;
historical and interpretation claims must cite incident data. Negative grader tests
prove fabricated quotations and wrong numeric expectations fail. These are proxies,
not proof of semantic relevance, completeness or general prompt-injection robustness.
No semantic unsupported-claim rate or calibrated confidence probability is claimed.

## Before / after

Initial: 42/50; document Recall@6 85.7%; route/tool-selection 92%; deterministic
results 93.75%. The data miss was plural `counts` routing, not wrong arithmetic.
Policy misses included `thresholds` / `notice` intent, an aggressive selection cutoff,
and escalation queries lacking notification terms.

Refined: include plurals and notice/cadence; lower relative selection cutoff 0.5 → 0.4;
append `notify notification` to escalation queries. This bounded domain alias makes
no additional model/retrieval call and was added after the measured recall gap.
The same unchanged golden set reached 50/50 and 100% document Recall@6. Both reports remain.

This is a **tuned regression set**, not held-out evaluation. Broader LLM-quality
claims still need unseen paraphrases and manual review. The recorded
live-provider procedure/results are in [LIVE_LLM_VALIDATION.md](LIVE_LLM_VALIDATION.md).
Offline latency/token counts exclude model/network calls. Token costs require both
operator-supplied rates and exclude embedding API charges. Optional dense embeddings
have mock transport/dimension tests, not a measured live retrieval-quality score.

## Live-provider checks

`evaluate-live` uses a versioned golden file and fixed TF-IDF/SQLite stores.
Each unguarded case must make a successful HTTP planning call, and every model
call must produce valid structured output. A schema/provenance failure is not a
correct refusal, even when the expected route is unsupported. Safety guards act
before inference and must make zero calls. Executed argument-schema accuracy is
separate from provider structured-call success: a rejected model plan executes
no invalid arguments, but still fails the live case.

Full, five-case smoke and explicit targeted reports have distinct scopes and
denominators. Partial execution never becomes a full-suite pass. Provider usage
includes rejected JSON and retries, so it may exceed accepted response usage;
missing token/cost metadata remains unknown. This measures model planning and
evidence selection with deterministic tools, not free-form semantic answer quality.
The first completed legacy run scored 47/50. Its failures are retained, including
one ambiguous question; revised-suite comparisons must disclose that input change.

Final current-build acceptance reran the same revised suite once after the executor
guard: **50/50**, with **74/74** valid structured calls and no HTTP retries. No further
golden/application/corpus change was made during acceptance. Earlier 47/50, 49/50
and targeted results remain unchanged; see [final acceptance](FINAL_ACCEPTANCE.md).
This closes the full-run verification gap without changing the regression/semantic
quality limits above.

## Future changes

New policies/generator versions require reviewing frozen facts and hashes. Preserve
before/after reports and real failures. LLM-as-judge may supplement deterministic
schema, numeric, permission and provenance checks later; it must not replace them.
LangGraph retries and advanced retrieval are not required to run this V1 baseline.

## Public evidence metadata

Recorded case responses, grades, numeric labels, latency and usage are preserved.
Machine-specific JUnit attributes are removed; timezone-aware JUnit timestamps are
normalized to UTC. Acceptance evidence hashes identify these public artifact bytes.
This metadata normalization is not a new model run or a changed evaluation score.
The publication guard checks complete Git history and artifact contents; CI uploads
artifacts only after that guard succeeds.
