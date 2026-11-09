# OpsPilot V2 — Stateful, Evidence-Verified Incident Investigation

V2 extends the working V1 operational copilot with persistent investigations. It
investigates fictional HarbourLink incidents using authoritative internal policy
and deterministic historical evidence. All policies and 240 incident records remain
synthetic; no business action, notification or record mutation is implemented.

## Implemented behavior

An investigation accepts a bounded request, optional typed incident facts and an
optional human-review requirement. A real LangGraph workflow plans permitted tools,
collects policy and historical evidence, synthesizes quote-backed findings, verifies
evidence dimensions and conditionally performs one targeted policy retrieval.
Missing critical incident context interrupts execution for clarification. Requested
review or conflicting supplied/snapshot context interrupts before finalization.
Both interruptions survive a process restart and accept narrowly typed responses.

Completion statuses are `running`, `awaiting_human`, `completed`, `partial`,
`insufficient` and `failed`. `completed` means the declared deterministic requirements
passed; it is not a claim of semantic certainty, calibrated confidence or production
reliability. A reviewer cannot turn an evidence gap into a verified fact.

## Investigation brief

The structured brief contains an executive summary, incident context and recorded or
reported severity, applicable internal policies, historical comparison, key findings,
proposed next steps, unresolved gaps, citations, status, tool/workflow traces and
limitations. It does not independently certify severity, root cause or compliance.
Policy findings quote complete original paragraphs. Aggregate findings and duration
comparisons are computed in Python from the existing typed tools. Recommendations
are explicitly `proposed_not_executed` and cannot invoke business actions.

## Compatibility and access

`POST /api/chat` retains the V1 request/response contract and executor. V2 adds:

- `POST /api/investigations`: create a server-owned investigation; returns its ID and
  one random ownership token, which is not reissued by later reads.
- `GET /api/investigations/{id}`: retrieve the bounded public view using
  `Authorization: Bearer <owner_token>`.
- `POST /api/investigations/{id}/resume`: submit a typed clarification or review
  decision with the same ownership token. No arbitrary graph state/config is accepted.

The existing UI offers V1 answers and V2 briefs. The V2 default is offline, regardless
of the V1 subscription preference. The optional configured V2 provider uses the
existing chat API abstraction for one structured planning call. This path is tested
with injected transports/providers; no paid V2 inference is part of acceptance.
V2 also offers an explicit `chatgpt_subscription` mode, using the existing local
account/model selection. It remains opt-in and does not alter the offline default.

Ownership tokens are a bounded synthetic-demo authorization mechanism, not enterprise
identity, roles or multi-tenancy. Keep the service behind loopback or an independently
controlled proxy. Browser tokens are held in tab-scoped session storage, not URLs;
restoring requires the same browser tab or a client retaining its creation token.

## Explicit boundaries

There is no external web fallback, model-authored SQL, network/shell/filesystem tool,
write tool, MCP server, multi-agent architecture or automated business execution.
MCP is deferred: a future adapter may map the four typed capabilities to read-only
MCP tools while preserving schemas, permissions, provenance and tests. Such an adapter
must demonstrate a concrete interoperability benefit before it is introduced.

## Functional completion 1–5 — 2026-11-09

Severity assessment now separates `recorded_severity`, `reported_severity` and
`proposed_severity`. Proposed classification applies reviewed policy thresholds to
explicit facts, with cited basis and `supported`, `provisional`, `insufficient` or
`not_requested` status. It is a reproducible proposal, not an independent certification.
User reports and snapshot observations remain separately inspectable. Conflicting
severity, category, impact or duration requires review; acceptance retains the gap.

Evidence requirements now declare individual dimensions such as recipients, clock,
message content, ownership, communication timing and restoration prerequisites.
A nearby citation or a matching document alone cannot cover a missing dimension.
All facts and proposed owners/deadlines are revalidated before finalization.

Critical missing facts use at most two typed clarification rounds, with explicit
unknown values. Unknown is never zero or false. Only fields requested by the pending
interrupt may be supplied, and negative/qualified prose is conservatively excluded
from automatic numeric/boolean intake. After the bound, unresolved facts yield a
partial/insufficient brief rather than repeated questions or invented certainty.

The executive summary now identifies the incident/scenario, known impact/duration,
severity basis, historical cohort and duration denominators, and unresolved gaps.
Proposed actions include source citations, owner role, applicability trigger and
policy-relative timing. Absolute minute deadlines require an explicit timezone-aware
threshold-detection time; incident opening time is not substituted. Business-day
review dates require an absent holiday calendar and remain unresolved. Resolved
snapshot incidents are labelled retrospective, not fresh notifications to execute.

## Subscription investigations — tasks 6–7

A subscription investigation pins the selected account reference and exact model at
creation, including while awaiting initial clarification. Later global account/model
changes affect new investigations only. Resume resolves the original account and
never substitutes another account, model or API-key billing path. An unavailable
original account fails safely when inference is needed. Completed findings can still
be read/reviewed without additional inference after sign-out.

The model performs at most one validated LangChain planning call; policy synthesis,
severity, arithmetic, verification and proposed actions remain deterministic. Planning
usage, model and attempted call count are visible in API/UI; missing usage is marked
incomplete. Subscription usage is not converted to a fabricated USD price. The initial integration was fixture-validated. The first live regression later
executed 23/44 cases with 16 passes before a safety stop; full mixed/historical live
acceptance remains outstanding. See the dated acceptance receipt.

Planning failures expose bounded developer diagnostics through owner-authorized API
responses: rejection code/stage and required/proposed route/tool names. User text,
raw model plans, arguments and provider errors are excluded from these diagnostics.
The model receives server-derived minimum requirements before proposing its plan;
rejected proposals still stop without tool execution or an automatic model retry.
The subsequent fixed-model live regression completed 44 cases with 42 passes,
including all six mixed cases. Two evidence/expectation failures remain; this is
synthetic regression evidence rather than production accuracy or full sign-off.

The subsequent evidence-gap correction completes the unchanged 44-case offline/live
regressions with 44 passes. Communication proposals require both ownership and
cadence citations. Review-date questions include applicability and timetable evidence,
conditional relative business-day deadlines and missing-calendar/verified-resolution
gaps; they remain partial where an exact date cannot be supported. No holiday calendar
or blanket lower-severity review requirement is invented. See the latest dated receipt.
