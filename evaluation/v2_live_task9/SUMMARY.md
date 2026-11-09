# First V2 live subscription evaluation — incomplete

The fixed 44-case run stopped after 23 executed cases under its preregistered
three-consecutive-failure gate. 16 passed; 7 failed; 21 were not executed. None of
the 16 reserved cases reached live execution. Do not report this as a complete
44-case evaluation or general accuracy result.

| Measurement | Observed result |
|---|---|
| Model / billing path | gpt-6-luna / existing ChatGPT plan |
| Inference HTTP attempts | 23; zero retries or billing fallback |
| Structured RoutePlan responses | 23/23 valid |
| Executed-case pass count | 16/23 |
| Same executed subset, paired offline | 23/23 |
| Reported input / output tokens | 97,313 / 3,610 |
| Median / p95 service latency | 4.663 / 8.801 seconds |
| Estimated USD price | Unavailable; not assumed zero |
| Offline test suite | 219 passed |

Seven cases fail at the planning/validation stage despite schema-valid provider
responses. The three last failures trigger the configured stop; no further calls
were made. Their generic failure view does not retain the rejected plans or exact
validation branch, so this run cannot identify a proven root cause. Model planning
has multiple checks, including required routes/tools, supplied IDs and scenario
duration. Do not infer which one failed without additional offline diagnostics.

Passing cases demonstrate cited policy classification, explicit unknown handling,
two-round scripted clarification, one targeted retrieval recovery, and safe partial/
insufficient behavior under labelled retrieval faults. All successful live cases are
policy-only; historical/mixed end-to-end live acceptance is not established. Live
adversarial write cases and the new reserved cases were not executed. Their earlier
offline/fixture results must not be called live evidence.

This evaluates the LangChain planning call within the real LangGraph pipeline;
briefs, numbers, severity rules and evidence verification remain deterministic.
Typed human replies are scripted case inputs, not independent human assessment.
Previously inspected synthetic cases are regression, not an unbiased new holdout.

The hard limit is 44 inference requests with a 32 KiB request envelope, zero retries
and the existing stream/read limits. Observed usage stops are 180k input and 32k
output tokens. Subscription preview rejects max_output_tokens, so these are not a
provider-side generation cap and can overshoot by the last completed request. The
run stopped on planning failures before any usage threshold. Docker verification
was deferred and no deployment, push or release occurred.

Repository-absolute metadata paths are normalized in this public evidence. Metrics,
case content, model outputs and outcomes are unchanged; raw reports and private
checkpoint/ownership data remain in ignored runtime storage.
