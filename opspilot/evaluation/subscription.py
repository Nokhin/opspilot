"""Bounded, sequential ChatGPT-plan evaluation using the existing frozen graders."""

import json
import time
from collections.abc import Callable
from pathlib import Path

import httpx

from opspilot.config import Settings
from opspilot.evaluation.live import (
    SMOKE_IDS,
    LiveValidationError,
    nonnegative_number,
    observed_usage,
)
from opspilot.evaluation.runner import grade, load_cases, write_report
from opspilot.orchestration.routing import unsafe_request
from opspilot.orchestration.service import OpsPilotService
from opspilot.providers.chatgpt import ChatGPTSubscription
from opspilot.providers.chatgpt_auth import API, ChatGPTAccounts


class RecordedSubscription(ChatGPTSubscription):
    """Record safe call metadata, including usage on rejected structured output."""

    def __init__(self, settings, accounts, profile_id, max_attempts, transport=None):
        self.calls = []
        self.attempts = []
        self.max_attempts = max_attempts
        super().__init__(
            settings,
            accounts,
            profile_id,
            httpx.Client(transport=transport, trust_env=False, follow_redirects=False),
        )

    def complete(self, system, payload, schema):
        if len(self.attempts) >= self.max_attempts:
            raise LiveValidationError("http_attempt_budget_reached")
        record = {
            "operation": "planning" if schema.__name__ == "RoutePlan" else "evidence_selection",
            "status": "failed",
            "latency_ms": None,
        }
        self.calls.append(record)
        start = time.perf_counter()
        try:
            result = super().complete(system, payload, schema)
            record["status"] = "success"
            return result
        finally:
            record["latency_ms"] = (time.perf_counter() - start) * 1000
            observation = dict(self.last_observation)
            if observation.pop("request_started"):
                for key in ["input_tokens", "output_tokens"]:
                    observation[key] = nonnegative_number(observation[key])
                self.attempts.append(
                    {
                        **observation,
                        "call_index": len(self.calls) - 1,
                        "latency_ms": record["latency_ms"],
                        "reported_cost_usd": None,
                    }
                )

    def close(self):
        self.client.close()


def run_subscription_evaluation(
    settings: Settings,
    cases_path: Path,
    output: Path,
    *,
    model: str,
    smoke: bool = False,
    max_http_attempts: int = 120,
    accounts: ChatGPTAccounts | None = None,
    transport=None,
    progress: Callable[[dict], None] | None = None,
) -> dict:
    if not settings.subscription_enabled or settings.embedding_provider != "tfidf":
        raise LiveValidationError("Enable local subscription mode and the fixed TF-IDF index")
    if not 1 <= max_http_attempts <= 200:
        raise LiveValidationError("HTTP attempt budget must be between 1 and 200")
    if output.exists() and any(output.iterdir()):
        raise LiveValidationError("Output directory is not empty; select a new run directory")
    accounts = accounts or ChatGPTAccounts(settings.data_dir)
    profile_id, selected_model = accounts.selected()
    if selected_model != model:
        raise LiveValidationError(
            "Selected account model differs from the requested evaluation model"
        )
    live_settings = settings.model_copy(
        update={
            "llm_provider": "chatgpt_subscription",
            "llm_model": model,
            "input_cost_per_million": None,
            "output_cost_per_million": None,
        }
    )
    cases = load_cases(cases_path)
    if smoke:
        cases = [case for case in cases if case.id in SMOKE_IDS]
    provider = RecordedSubscription(
        live_settings, accounts, profile_id, max_http_attempts, transport
    )
    service = OpsPilotService(live_settings, provider)
    results, executed = [], []
    stop_reason, consecutive_failures = None, 0
    try:
        if not service.ready():
            raise LiveValidationError("Evidence stores unavailable; run offline bootstrap first")
        chunks = {chunk["chunk_id"]: chunk for chunk in service.store.snapshot()["chunks"]}
        output.mkdir(parents=True, exist_ok=True)
        for case in cases:
            call_start, attempt_start = len(provider.calls), len(provider.attempts)
            try:
                response = service.ask(case.question, request_id="subscription-" + case.id)
            except LiveValidationError as error:
                stop_reason = str(error)
                break
            row = grade(case, response, chunks)
            calls = provider.calls[call_start:]
            attempts = provider.attempts[attempt_start:]
            guarded = unsafe_request(case.question)
            provider_ok = (
                not calls
                if guarded
                else bool(calls) and all(call["status"] == "success" for call in calls)
            )
            row["checks"].update(
                live_provider_valid=provider_ok,
                model_selection=response.model == model,
                subscription_mode=response.mode == "chatgpt_subscription",
                policy_selection_valid=not any(
                    "Policy selection failed evidence validation" in text
                    for text in response.limitations
                ),
            )
            row["provider_calls"], row["provider_attempts"] = calls, attempts
            row["failures"] = [key for key, valid in row["checks"].items() if not valid]
            row["passed"] = not row["failures"]
            results.append(row)
            executed.append(case)
            with (output / "progress.jsonl").open("a") as file:
                file.write(json.dumps(row) + "\n")
            if progress:
                progress(
                    {
                        "case": case.id,
                        "passed": row["passed"],
                        "failures": row["failures"],
                        "latency_ms": row["latency_ms"],
                    }
                )
            if any(
                a["http_status"] in {400, 401, 402, 403, 404, 429}
                or a.get("error_type")
                in {
                    "invalid_request_error",
                    "authentication_error",
                    "permission_error",
                    "rate_limit_error",
                }
                for a in attempts
            ):
                stop_reason = "provider_request_rejected_or_usage_limited"
                break
            consecutive_failures = 0 if provider_ok else consecutive_failures + 1
            if consecutive_failures >= 3:
                stop_reason = "three_consecutive_provider_failures"
                break
        live = {
            "scope": "smoke" if smoke else "curated_regression",
            "completed": len(results) == len(cases) and stop_reason is None,
            "requested_cases": len(cases),
            "model": model,
            "endpoint": API + "/responses",
            "billing": "chatgpt_plan",
            "account_pinned": True,
            "transport": "http" if transport is None else "injected_test_transport",
            "stop_reason": stop_reason,
            "max_http_attempts": max_http_attempts,
            "provider_retries": 0,
        }
        metrics = {
            "provider_logical_calls": len(provider.calls),
            "provider_structured_successes": sum(c["status"] == "success" for c in provider.calls),
            "provider_http_attempts": len(provider.attempts),
            "provider_input_tokens": observed_usage(provider.attempts, "input_tokens"),
            "provider_output_tokens": observed_usage(provider.attempts, "output_tokens"),
            "provider_reported_cost_usd": None,
        }
        (output / "provider.json").write_text(
            json.dumps(
                {
                    "live_validation": live,
                    "metrics": metrics,
                    "calls": provider.calls,
                    "attempts": provider.attempts,
                },
                indent=2,
            )
            + "\n"
        )
        if not results:
            raise LiveValidationError("No cases completed; provider.json preserves attempted calls")
        summary = write_report(
            service,
            executed,
            results,
            cases_path,
            output,
            manifest_extra={"live_validation": live, "model": model},
            summary_extra=metrics,
        )
        return {"live_validation": live, "summary": summary, "output": str(output)}
    finally:
        provider.close()
