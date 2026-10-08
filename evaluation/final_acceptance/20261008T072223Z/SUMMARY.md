# Final local OpsPilot V1 acceptance

**PASS — complete current-build live regression: 50/50.**

| Gate | Result |
|---|---|
| Real OpenRouter curated live cases | 50/50 |
| Valid structured calls | 74/74 |
| pytest / Ruff / pip check | 70 passed / passed / passed |
| Legacy/current offline regressions | 50/50 each |
| Native ARM64 Docker, network disabled | 50/50 |
| Actual loopback API smoke | 5/5 |
| Latest Compose demo | Ready; source matches; evidence stores preserved |
| Provider input/output tokens | 240,832/45,883 |
| Provider-reported cost, this run | USD 0.624674 |
| Median/p95 shared-service latency | 11.246/43.433 seconds |

No application, golden, corpus or evidence-store change was made during acceptance. The executor guard was observed in mixed_05; explicit similarity and historical filters remained supported. Four safety cases made zero calls/tools. Earlier failures, 47/50, 49/50 and targeted runs remain preserved.

[Acceptance JSON](ACCEPTANCE.json), [full live JSON](live_full/results.json), [CSV](live_full/cases.csv), [live summary](live_full/SUMMARY.md), [hygiene](hygiene.json).
[Detailed acceptance scope](../../../docs/FINAL_ACCEPTANCE.md).

This is a tuned synthetic English regression, not held-out semantic accuracy or production reliability. Twelve qualitative response spot checks are Codex inspection, not independent blinded human review. Live timing is sequential CLI/shared-service timing; API smoke used offline mode. Public release/license and actual VPS/HTTPS/load remain separate tasks.
