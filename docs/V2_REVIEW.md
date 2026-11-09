# V2 local review candidate — 2026-11-09

Implementation and local closeout are prepared for operator review. Nothing in this
receipt means a commit, push, tag, hosted CI run, release or deployment occurred.
The package version remains `2.0.0.dev0`; release metadata is not promoted.

## Current functionality and evidence

The real LangGraph workflow plans and executes bounded policy/history investigation,
verifies evidence, performs at most one changed retrieval retry, pauses/resumes human
clarification/review and produces cited structured briefs. V1's API and four typed
read-only tools remain available. All ten policies and 240 incidents are synthetic.

- Local closeout tests: **257 passed**, five Git-history tests intentionally excluded.
  Git process launches are prohibited by the local test runner. These exclusions do
  not count as passes, and no current Git-object/history audit is claimed.
- Completion offline: **44/44**; evidence-gap development: **8/8**.
- Latest recorded live `gpt-6-luna`: **44/44**, 42 valid structured calls; no new
  inference is needed or performed for this CI/documentation closeout.
- Both V1 offline protocols: **50/50**. Prior failed/stopped results remain unchanged.
- See [latest functional evidence](../evaluation/v2_evidence_gap_fix/VALIDATION.md)
  and [local closeout receipt](../evaluation/v2_closeout_review/VALIDATION.md).

## CI contract

The workflow now requires completion development/reserved and evidence development
suites to pass completely. It also runs both original legacy suites with their
unchanged labels and strict nonzero CLI exits. The separate
[report gate](../scripts/check_v2_reports.py) accepts exactly these documented
contract differences, without changing their original scores:

| Original case | Preserved score | Required current behavior |
|---|---|---|
| `mixed_comparison` | Development remains 21/22 | Await typed customer-facing clarification; no tools/provider call |
| `reserved_clarify` | Reserved remains 11/12 | Partial with explicit missing severity facts; no integrity error |

New failures, altered prerequisite behavior, omitted cases, changed input hashes,
inference usage or inconsistent score/check metadata fail the gate. The gate's
success is not a claim that the original legacy scores are 22/22 or 12/12.
Hosted GitHub Actions is pending; local CLI-equivalent evidence is recorded separately.

## Publication privacy scope

V1's allow-list, deterministic content checks and JUnit sanitization are reused for
the proposed working-tree export. Private originals/instructions/planning, `.env`,
runtime databases/indexes/checkpoints, account bindings, tokens and caches are excluded.
Only reviewed source, technical documentation and synthetic evaluation evidence belong
in the local export. The export is a review copy, not a published release archive.

Git/history inspection is deferred under the no-Git review boundary. Earlier history
receipts remain historical evidence only. A complete fresh history audit is still
required after Git operations are authorized and before any publication.

Content checks cover configured patterns, exact supplied sensitive values and selected
metadata markers. They do not universally detect names, phone/identity numbers or
sensitive text inside images. Runtime ingestion/indexes/checkpoints are not automatically
redacted or anonymized; default data remains synthetic. This review does not add PII
processing capability or enterprise identity controls.

## Holds and known limits

- Fresh Docker/base-image/target-platform validation remains deferred.
- No Git mutation or read-only Git command, hosted CI, release, remote deployment or
  load test is performed during local review.
- Ownership is a per-demo investigation capability; checkpoints are not encrypted
  at rest. Source/snapshot changes reject old resumes without destructive migration.
- Missing approved holiday calendar/verified resolution retains partial date guidance.
- Some policy paraphrases encounter the conservative existing write-word guard.
- Synthetic inspected regression is not independent held-out or production accuracy.

Next external steps remain held until operator confirmation of the concrete candidate.

Final source/artifact privacy review: 361 candidate files; zero configured-pattern/
exact-value findings, raw sensitive JSON fields or broken local Markdown links.
Six retained synthetic screenshots reviewed; 307 original source/corpus/evaluation
files unchanged. No Git/history inspection or publication performed. Full history
review remains pending after operator authorization; this is not universal PII assurance.
