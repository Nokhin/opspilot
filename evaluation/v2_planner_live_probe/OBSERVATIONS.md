# Targeted live planner probe — 2026-11-09

The prepared nine-case protocol executed eight inference cases: **8 passed**, using
eight `gpt-6-luna` HTTP requests and 35,047 input / 1,595 output tokens. The same eight
cases had one pass in the original live run. All seven earlier failures pass now,
including appropriately partial conflict investigations. This is a repeated synthetic
regression observation, not a controlled causal estimate or fresh held-out accuracy.

The original probe is preserved as **8/9 incomplete**, with `dev-unsafe` unexecuted.
The runner stopped case admission when its HTTP count reached eight, even though the
last safety case needed no inference. The stopped report was not resumed or relabelled.

Two offline fixtures verify a narrow runner correction: deterministic unsafe-request
refusal may be admitted at the HTTP count cap; the actual HTTP hook always enforces
the cap, and token/time/failure/source stops remain active. Full pytest: **239 passed**.
A separately preregistered [safety run](safety/results.json) passed with zero provider,
HTTP and tool calls. Empty provider usage events remain null in its raw report;
zero requests independently establish that no inference occurred.

A separate [full regression](../v2_planner_live_regression/VALIDATION.md) subsequently
executed all 44 cases. The first 23-case run and this incomplete targeted probe remain
unchanged. USD cost is unavailable; no API-key billing fallback was used. Raw checkpoints,
account bindings, credentials and ownership capabilities are excluded from this export.
