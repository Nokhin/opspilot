"""Fixed-case live V2 regression with pinned subscription access and bounded usage.

Observed token thresholds stop subsequent calls; the subscription route does not
support a server-side generation-token cap. No USD price is inferred.
"""

import hashlib
import json
import re
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

from opspilot.cli import bootstrap
from opspilot.domain.models import PolicyResult
from opspilot.evaluation.investigation import grade_investigation, load_investigation_cases
from opspilot.evaluation.live import LiveValidationError, nonnegative_number, observed_usage
from opspilot.investigation.service import InvestigationService
from opspilot.orchestration.routing import unsafe_request
from opspilot.orchestration.service import OpsPilotService
from opspilot.providers.chat_api import ProviderError
from opspilot.providers.chatgpt import ChatGPTSubscription
from opspilot.providers.chatgpt_auth import API, ChatGPTAccounts


class LiveBudget:
    """Hard HTTP/request-size limits, plus honest observed-usage stop thresholds."""

    def __init__(
        self,
        *,
        max_calls=44,
        input_threshold=180000,
        output_threshold=32000,
        max_request_bytes=32768,
        wall_seconds=900,
    ):
        if not (
            1 <= max_calls <= 44
            and 1 <= input_threshold <= 180000
            and 1 <= output_threshold <= 32000
            and 1 <= max_request_bytes <= 32768
            and 1 <= wall_seconds <= 900
        ):
            raise LiveValidationError("Budget exceeds the controlled V2 limits")
        self.max_calls, self.input_threshold, self.output_threshold = (
            max_calls,
            input_threshold,
            output_threshold,
        )
        self.max_request_bytes, self.wall_seconds = max_request_bytes, wall_seconds
        self.started = time.monotonic()
        self.calls, self.attempts = [], []
        self.case_id = None
        self.stop_reason = None

    def limits(self):
        return dict(
            max_inference_http_attempts=self.max_calls,
            observed_input_token_stop=self.input_threshold,
            observed_output_token_stop=self.output_threshold,
            max_request_bytes=self.max_request_bytes,
            wall_stop_seconds=self.wall_seconds,
            server_side_output_token_cap=False,
            token_stop_may_overshoot_by_last_request=True,
            provider_retries=0,
        )

    def check(self, *, zero_inference=False):
        """Only deterministic refusal admission may skip the HTTP count check.

        The transport always calls with the default, so every actual request remains
        subject to the hard cap. Other stop gates apply even to zero-call cases.
        """
        if self.stop_reason:
            return self.stop_reason
        if len(self.attempts) >= self.max_calls and not zero_inference:
            return "http_attempt_budget_reached"
        if time.monotonic() - self.started >= self.wall_seconds:
            return "wall_time_stop_threshold_reached"
        for field, limit in [
            ("input_tokens", self.input_threshold),
            ("output_tokens", self.output_threshold),
        ]:
            if sum(a.get(field) or 0 for a in self.attempts) >= limit:
                return "observed_" + field + "_stop_threshold_reached"
        return None

    def before_request(self, request):
        reason = self.check()
        if reason:
            self.stop_reason = reason
            raise ProviderError("Evaluation request budget stopped further inference.")
        if request.method != "POST" or str(request.url) != API + "/responses":
            self.stop_reason = "unpermitted_inference_endpoint"
            raise ProviderError("Unpermitted evaluation endpoint.")
        if len(request.content) > self.max_request_bytes:
            self.stop_reason = "request_size_limit"
            raise ProviderError("Evaluation request exceeded the size limit.")
        request.extensions["evaluation_attempt"] = len(self.attempts)
        self.attempts.append(
            dict(
                case=self.case_id,
                http_status=None,
                payload_bytes=len(request.content),
                input_tokens=None,
                output_tokens=None,
                request_id=None,
                error_type=None,
            )
        )

    def after_response(self, response):
        index = response.request.extensions["evaluation_attempt"]
        self.attempts[index]["http_status"] = response.status_code
        request_id = response.headers.get("x-request-id", "")
        if re.fullmatch(r"[A-Za-z0-9_-]{1,128}", request_id):
            self.attempts[index]["request_id"] = request_id
        if response.status_code >= 300:
            raw = b""
            for part in response.iter_bytes():
                raw += part
                if len(raw) > 65536:
                    return
            try:
                error = json.loads(raw).get("error", {})
                code = error.get("code")
                if code in {
                    "subscription_sharing_user_not_eligible",
                    "subscription_sharing_usage_limit_exceeded",
                    "subscription_sharing_usage_unavailable",
                    "subscription_sharing_unsupported_capability",
                    "subscription_sharing_route_not_supported",
                }:
                    self.attempts[index]["error_code"] = code
                param = error.get("param")
                if param in {"model", "input", "text.format", "max_output_tokens"}:
                    self.attempts[index]["error_param"] = param
            except (ValueError, AttributeError, TypeError):
                pass  # Never retain raw error bodies or arbitrary diagnostic strings.


class RecordedInvestigationProvider(ChatGPTSubscription):
    def __init__(self, settings, accounts, profile_id, client, budget):
        super().__init__(settings, accounts, profile_id, client)
        self.budget = budget

    def complete(self, system, payload, schema):
        record = dict(case=self.budget.case_id, schema=schema.__name__, status="failed")
        self.budget.calls.append(record)
        before, start = len(self.budget.attempts), time.perf_counter()
        try:
            value = super().complete(system, payload, schema)
            record["status"] = "success"
            return value
        finally:
            record["latency_ms"] = (time.perf_counter() - start) * 1000
            observation = getattr(self, "last_observation", {})
            if len(self.budget.attempts) > before:
                attempt = self.budget.attempts[-1]
                for field in ["input_tokens", "output_tokens"]:
                    attempt[field] = nonnegative_number(observation.get(field))
                attempt["error_type"] = observation.get("error_type")
                attempt["latency_ms"] = record["latency_ms"]
                if attempt["http_status"] in {400, 401, 402, 403, 404, 429}:
                    self.budget.stop_reason = "provider_request_rejected_or_usage_limited"
                elif any(attempt[field] is None for field in ["input_tokens", "output_tokens"]):
                    self.budget.stop_reason = "usage_unobserved_stop"
            elif record["status"] == "failed" and not self.budget.stop_reason:
                self.budget.stop_reason = "credential_or_local_preflight_failure"


class PinnedAccounts:
    """Retain an authorized registry reference in memory; never export it."""

    def __init__(self, accounts, profile_id, model):
        self.accounts, self.profile_id, self.model = accounts, profile_id, model

    def selected(self):
        return self.profile_id, self.model

    def access_token(self, profile_id):
        if profile_id != self.profile_id:
            raise ProviderError("Evaluation account binding changed.")
        return self.accounts.access_token(profile_id)


def source_hashes():
    files = [
        *Path("opspilot/investigation").glob("*.py"),
        Path("opspilot/investigation/policy_contracts.json"),
        Path("opspilot/evaluation/investigation.py"),
        Path("opspilot/cli.py"),
        Path(__file__),
        Path("opspilot/providers/chatgpt.py"),
    ]
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


def run_live_investigations(
    settings,
    case_paths,
    output,
    *,
    model,
    budget=None,
    accounts=None,
    transport=None,
    progress=None,
    baseline=None,
):
    if not settings.subscription_enabled or settings.embedding_provider != "tfidf":
        raise LiveValidationError("Use enabled subscription mode and local TF-IDF evidence")
    if output.exists() and any(output.iterdir()):
        raise LiveValidationError("Use a new output directory; preserve previous results")
    cases = [(str(p), c) for p in case_paths for c in load_investigation_cases(p)]
    if len(cases) > 44 or len({c.id for _, c in cases}) != len(cases):
        raise LiveValidationError("At most 44 unique frozen cases are permitted")
    output.mkdir(parents=True, exist_ok=True)
    protocol = dict(
        recorded_at_utc=datetime.now(UTC).isoformat(),
        model=model,
        scope="V2 live regression on previously inspected synthetic cases",
        cases_sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in case_paths},
        case_ids=[c.id for _, c in cases],
        source_sha256=source_hashes(),
        limits=(budget or LiveBudget()).limits(),
        human_inputs="Scripted typed case responses; not independent human review",
        fault_injection="Explicit source faults retained from frozen cases",
        billing="chatgpt_plan",
        account_pinned=True,
        transport="http" if transport is None else "injected_test_transport",
        transport_limits=dict(
            read_timeout_seconds=settings.subscription_timeout_seconds,
            stream_time_check_seconds=120,
            response_line_character_limit=524288,
        ),
    )
    (output / "PROTOCOL.json").write_text(json.dumps(protocol, indent=2) + "\n")
    accounts = accounts or ChatGPTAccounts(settings.data_dir)
    try:
        profile, selected_model = accounts.selected()
        if selected_model != model:
            raise LiveValidationError("Selected model differs from the frozen requested model")
    except Exception:
        (output / "PREFLIGHT.json").write_text(
            json.dumps(
                dict(
                    status="not_started",
                    reason="Account/model preflight failed; no inference attempted",
                )
            )
            + "\n"
        )
        raise
    pinned = PinnedAccounts(accounts, profile, model)
    run_settings = settings.model_copy(
        update=dict(
            data_dir=output / "runtime",
            llm_provider="extractive",
            default_chat_provider="configured",
        )
    )
    bootstrap(run_settings)
    service = OpsPilotService(run_settings)
    protocol.update(
        corpus_sha256=service.store.snapshot()["corpus_sha256"],
        database_sha256=hashlib.sha256(run_settings.incident_db.read_bytes()).hexdigest(),
        index_sha256=hashlib.sha256(run_settings.vector_index.read_bytes()).hexdigest(),
        reference_time=run_settings.reference_time.isoformat(),
    )
    (output / "PROTOCOL.json").write_text(json.dumps(protocol, indent=2) + "\n")
    chunks = {c["chunk_id"]: c for c in service.store.snapshot()["chunks"]}
    budget = budget or LiveBudget()
    client = httpx.Client(
        transport=transport,
        trust_env=False,
        follow_redirects=False,
        event_hooks={"request": [budget.before_request], "response": [budget.after_response]},
    )

    def factory(settings, accounts, profile_id):
        return RecordedInvestigationProvider(settings, accounts, profile_id, client, budget)

    def new_store():
        return InvestigationService(service, accounts=pinned, subscription_provider_factory=factory)

    store = new_store()
    rows, streak = [], 0
    stop_reason = None
    harness_error_type = None
    completed = False
    try:
        for filename, case in cases:
            if source_hashes() != protocol["source_sha256"] or any(
                hashlib.sha256(Path(p).read_bytes()).hexdigest() != expected
                for p, expected in protocol["cases_sha256"].items()
            ):
                stop_reason = "frozen_source_or_cases_changed"
                break
            reason = budget.check(zero_inference=unsafe_request(case.request.user_request))
            if reason:
                stop_reason = reason
                break
            budget.case_id = case.id
            call_start, attempt_start = len(budget.calls), len(budget.attempts)
            search, get = service.tools.search_internal_policy, service.tools.get_incident
            attempts = 0

            def injected_search(args, case=case, search=search):
                nonlocal attempts
                attempts += 1
                if case.fault == "all_policy_empty" or (
                    case.fault == "first_policy_empty" and attempts == 1
                ):
                    return PolicyResult(hits=[])
                result = search(args)
                if case.fault == "no_communication":
                    result.hits = [h for h in result.hits if h.chunk.policy_type != "communication"]
                if case.fault == "no_escalation_content":
                    result.hits = [
                        h for h in result.hits if h.chunk.chunk_id != "POL-INC-002:s05:c01"
                    ]
                return result

            def unavailable(args):
                raise OSError("Injected evidence-source unavailability")

            service.tools.search_internal_policy = injected_search
            if case.fault == "data_unavailable":
                service.tools.get_incident = unavailable
            interrupts = []
            harness_error = None
            start = time.perf_counter()
            try:
                created = store.create(
                    case.request.model_copy(update={"mode": "chatgpt_subscription"})
                )
                identifier, token = created.investigation_id, created.owner_token
                response = store.get(identifier, token)
                if response.clarification_request:
                    interrupts.append(response.clarification_request["kind"])
                for reply in case.responses:
                    if response.completion_status != "awaiting_human":
                        harness_error = "Expected human interrupt not reached"
                        break
                    if case.restart_before_resume:
                        store.close()
                        store = new_store()
                    response = store.resume(identifier, token, reply)
                    if response.clarification_request:
                        interrupts.append(response.clarification_request["kind"])
                row = grade_investigation(
                    case, response, chunks, interrupts=interrupts, subscription=True
                )
                calls = budget.calls[call_start:]
                provider_ok = all(c["status"] == "success" for c in calls)
                row["checks"].update(
                    model_fixed=response.model == model,
                    live_provider_valid=provider_ok,
                    human_protocol=harness_error is None,
                    live_usage_observed=all(
                        a.get("input_tokens") is not None and a.get("output_tokens") is not None
                        for a in budget.attempts[attempt_start:]
                    ),
                )
                row["failures"] = [k for k, v in row["checks"].items() if not v]
                row["passed"] = not row["failures"]
                row.update(
                    case_file=filename,
                    fault=case.fault,
                    provider_calls=calls,
                    provider_attempts=budget.attempts[attempt_start:],
                    wall_latency_ms=(time.perf_counter() - start) * 1000,
                )
                if baseline and case.id in baseline:
                    old = baseline[case.id]
                    row["paired_offline"] = dict(
                        passed=old["passed"],
                        status=old["response"]["completion_status"],
                        tool_calls=old["tool_calls"],
                        latency_ms=old["latency_ms"],
                    )
                rows.append(row)
                with (output / "progress.jsonl").open("a") as f:
                    f.write(json.dumps(row) + "\n")
                if progress:
                    progress(
                        dict(
                            case=case.id,
                            passed=row["passed"],
                            failures=row["failures"],
                            latency_ms=row["latency_ms"],
                            http_attempts=len(budget.attempts),
                        )
                    )
                streak = (
                    streak + 1 if not provider_ok or response.completion_status == "failed" else 0
                )
                if budget.stop_reason:
                    stop_reason = budget.stop_reason
                    break
                if streak >= 3:
                    stop_reason = "three_consecutive_provider_or_planning_failures"
                    break
            finally:
                service.tools.search_internal_policy, service.tools.get_incident = search, get
        completed = len(rows) == len(cases) and stop_reason is None
    except Exception as error:
        # Progress and attempted usage survive even an unexpected harness failure.
        harness_error_type = type(error).__name__
        stop_reason = "evaluation_harness_failure"
    finally:
        store.close()
        client.close()
    latencies = [r["latency_ms"] for r in rows]
    summary = dict(
        requested_cases=len(cases),
        executed_cases=len(rows),
        passed=sum(r["passed"] for r in rows),
        failure_ids=[r["id"] for r in rows if not r["passed"]],
        completed=completed,
        stop_reason=stop_reason,
        harness_error_type=harness_error_type,
        model=model,
        inference_http_attempts=len(budget.attempts),
        structured_successes=sum(c["status"] == "success" for c in budget.calls),
        logical_provider_calls=len(budget.calls),
        input_tokens=observed_usage(budget.attempts, "input_tokens"),
        output_tokens=observed_usage(budget.attempts, "output_tokens"),
        estimated_cost_usd=None,
        tool_calls=sum(r["tool_calls"] for r in rows),
        median_latency_ms=statistics.median(latencies) if latencies else None,
        p95_latency_ms=sorted(latencies)[max(0, (95 * len(latencies) + 99) // 100 - 1)]
        if latencies
        else None,
        by_case_file={
            p: dict(
                executed=sum(r["case_file"] == p for r in rows),
                passed=sum(r["case_file"] == p and r["passed"] for r in rows),
            )
            for p in map(str, case_paths)
        },
    )
    report = dict(
        manifest=protocol,
        summary=summary,
        cases=rows,
        provider_calls=budget.calls,
        provider_attempts=budget.attempts,
        unexecuted_ids=[c.id for _, c in cases if c.id not in {r["id"] for r in rows}],
    )
    (output / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    (output / "SUMMARY.md").write_text(
        "# Controlled V2 subscription regression\n\n"
        f"Executed {len(rows)}/{len(cases)}; passed {summary['passed']}. Completed: {completed}. "
        f"Stop: {stop_reason or 'none'}.\n\n"
        f"Model: {model}; HTTP attempts: {len(budget.attempts)}; "
        f"reported input/output tokens: {summary['input_tokens']}/{summary['output_tokens']}. "
        "USD cost is unavailable, not assumed zero. Token stops are observed thresholds, "
        "not a provider-side cap. These previously inspected synthetic cases do not establish "
        "held-out general accuracy. Faults and scripted human replies are labelled.\n"
    )
    return report
