"""Sequential, bounded provider validation; no mock/offline fallback in the CLI."""

import json
import math
import os
import time
from collections.abc import Callable
from pathlib import Path

import httpx
from dotenv import dotenv_values
from pydantic import ValidationError

from opspilot.config import Settings
from opspilot.evaluation.runner import grade, load_cases, write_report
from opspilot.orchestration.routing import unsafe_request
from opspilot.orchestration.service import OpsPilotService
from opspilot.providers.chat_api import ChatAPI, ProviderError

SMOKE_IDS = ("policy_01", "data_01", "mixed_01", "unsupported_01", "safety_01")


class LiveValidationError(RuntimeError):
    """Only sanitised configuration or stop reasons may reach the CLI."""


def load_live_settings(env_file: Path) -> Settings:
    values = dotenv_values(env_file) if env_file.is_file() else {}
    missing = [
        name
        for name in ("OPSPILOT_LLM_BASE_URL", "OPSPILOT_LLM_MODEL", "OPSPILOT_LLM_API_KEY")
        if not (os.environ.get(name) or values.get(name))
    ]
    if missing:
        raise LiveValidationError("Missing local settings: " + ", ".join(missing))
    try:
        # Hold the evidence planes fixed: this task validates the LLM, not dense retrieval.
        return Settings(_env_file=env_file, llm_provider="chat_api", embedding_provider="tfidf")
    except ValidationError as error:
        fields = sorted({str(e["loc"][0]) if e["loc"] else "configuration" for e in error.errors()})
        raise LiveValidationError("Invalid local settings: " + ", ".join(fields)) from None


def nonnegative_number(value):
    if isinstance(value, int | float) and not isinstance(value, bool):
        return value if math.isfinite(value) and value >= 0 else None
    return None


class RecordedChatAPI(ChatAPI):
    """Record actions/usage only, including retries and rejected JSON responses."""

    def __init__(self, settings: Settings, max_attempts: int, transport=None):
        self.attempts: list[dict] = []
        self.calls: list[dict] = []
        self.max_attempts = max_attempts
        self.current_call = 0
        self.current_schema = None
        client = httpx.Client(
            timeout=settings.provider_timeout_seconds,
            transport=transport,
            event_hooks={"request": [self.before_request], "response": [self.after_response]},
        )
        super().__init__(settings, client)

    def before_request(self, request: httpx.Request):
        if len(self.attempts) >= self.max_attempts:
            raise LiveValidationError("http_attempt_budget_reached")
        request.extensions["opspilot_attempt"] = len(self.attempts)
        request.extensions["opspilot_started"] = time.perf_counter()
        self.attempts.append(
            {
                "call_index": self.current_call,
                "http_status": None,
                "latency_ms": None,
                "input_tokens": None,
                "output_tokens": None,
                "reported_cost_usd": None,
            }
        )

    def after_response(self, response: httpx.Response):
        record = self.attempts[response.request.extensions["opspilot_attempt"]]
        record["http_status"] = response.status_code
        response.read()
        record["latency_ms"] = (
            time.perf_counter() - response.request.extensions["opspilot_started"]
        ) * 1000
        try:
            data = response.json()
            usage = data.get("usage") or {}
            if not isinstance(usage, dict):
                return
            record["input_tokens"] = nonnegative_number(usage.get("prompt_tokens"))
            record["output_tokens"] = nonnegative_number(usage.get("completion_tokens"))
            record["reported_cost_usd"] = nonnegative_number(usage.get("cost"))
            choices = data.get("choices") or []
            if choices:
                choice = choices[0]
                finish = choice.get("finish_reason")
                record["finish_reason"] = (
                    finish if finish in {"stop", "length", "tool_calls", "content_filter"} else None
                )
                content = (choice.get("message") or {}).get("content")
                if isinstance(content, str):
                    schema = self.current_schema.model_json_schema()
                    known_locations = set(schema.get("properties", {}))
                    for definition in schema.get("$defs", {}).values():
                        known_locations.update(definition.get("properties", {}))
                    allowed = {
                        "search_internal_policy",
                        "get_incident",
                        "find_similar_incidents",
                        "calculate_incident_metrics",
                    }
                    known_locations.update(allowed)
                    try:
                        self.current_schema.model_validate_json(content)
                        record["schema_errors"] = []
                    except ValidationError as error:
                        record["schema_errors"] = [
                            {
                                "type": e["type"],
                                "location": [
                                    part
                                    if isinstance(part, int) or part in known_locations
                                    else "unknown_field"
                                    for part in e["loc"]
                                ],
                            }
                            for e in error.errors()
                        ]
                    try:
                        parsed = json.loads(content)
                        if isinstance(parsed, dict) and isinstance(parsed.get("calls"), list):
                            record["proposed_tools"] = [
                                call.get("tool_name")
                                if isinstance(call, dict) and call.get("tool_name") in allowed
                                else "non_allowlisted"
                                for call in parsed["calls"][:8]
                            ]
                    except ValueError:
                        pass
        except (ValueError, AttributeError):
            pass

    def complete(self, system, payload, schema):
        self.current_call = len(self.calls)
        self.current_schema = schema
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
        except (ProviderError, LiveValidationError):
            raise
        finally:
            record["latency_ms"] = (time.perf_counter() - start) * 1000

    def close(self):
        self.client.close()


def observed_usage(attempts: list[dict], key: str):
    values = [a[key] for a in attempts]
    return sum(values) if values and all(v is not None for v in values) else None


def run_live_evaluation(
    settings: Settings,
    cases_path: Path,
    output: Path,
    *,
    smoke: bool = False,
    case_ids: list[str] | None = None,
    max_http_attempts: int = 120,
    transport=None,
    progress: Callable[[dict], None] | None = None,
) -> dict:
    if settings.llm_provider != "chat_api" or settings.embedding_provider != "tfidf":
        raise LiveValidationError("Live validation requires chat_api and the fixed TF-IDF index")
    if not 1 <= max_http_attempts <= 200:
        raise LiveValidationError("HTTP attempt budget must be between 1 and 200")
    if output.exists() and any(output.iterdir()):
        raise LiveValidationError("Output directory is not empty; select a new run directory")
    cases = load_cases(cases_path)
    if smoke and case_ids:
        raise LiveValidationError("Choose smoke or explicit case IDs, not both")
    if smoke or case_ids:
        by_id = {case.id: case for case in cases}
        ids = list(SMOKE_IDS) if smoke else case_ids
        if len(set(ids)) != len(ids) or any(case_id not in by_id for case_id in ids):
            raise LiveValidationError("Case IDs must be unique members of the curated set")
        cases = [by_id[case_id] for case_id in ids]
    provider = RecordedChatAPI(settings, max_http_attempts, transport)
    service = OpsPilotService(settings, provider)
    results, executed_cases = [], []
    stop_reason = None
    consecutive_failures = 0
    try:
        if not service.ready():
            raise LiveValidationError("Evidence stores unavailable; run offline bootstrap first")
        chunks = {c["chunk_id"]: c for c in service.store.snapshot()["chunks"]}
        output.mkdir(parents=True, exist_ok=True)
        for case in cases:
            call_start, attempt_start = len(provider.calls), len(provider.attempts)
            try:
                response = service.ask(case.question, request_id="live-" + case.id)
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
                else bool(calls)
                and calls[0]["operation"] == "planning"
                and all(call["status"] == "success" for call in calls)
            )
            row["checks"]["live_provider_valid"] = provider_ok
            row["checks"]["policy_selection_valid"] = not any(
                "Policy selection failed evidence validation" in limitation
                for limitation in response.limitations
            )
            row["provider_calls"] = calls
            row["provider_attempts"] = attempts
            row["failures"] = [name for name, passed in row["checks"].items() if not passed]
            row["passed"] = not row["failures"]
            results.append(row)
            executed_cases.append(case)
            with (output / "progress.jsonl").open("a") as stream:
                stream.write(json.dumps(row) + "\n")
            if progress:
                progress({"case": case.id, "passed": row["passed"], "failures": row["failures"]})
            if any(a["http_status"] in {400, 401, 402, 403, 404} for a in attempts):
                stop_reason = "provider_request_rejected"
                break
            consecutive_failures = 0 if provider_ok else consecutive_failures + 1
            if consecutive_failures >= 3:
                stop_reason = "three_consecutive_provider_failures"
                break
        live = {
            "scope": "smoke" if smoke else "targeted" if case_ids else "curated_regression",
            "completed": len(results) == len(cases) and stop_reason is None,
            "requested_cases": len(cases),
            "model": settings.llm_model,
            "endpoint": settings.llm_base_url,
            "transport": "http" if transport is None else "injected_test_transport",
            "stop_reason": stop_reason,
            "max_http_attempts": max_http_attempts,
            "provider_retries": settings.provider_retries,
            "selected_case_ids": [case.id for case in cases],
        }
        metrics = {
            "provider_logical_calls": len(provider.calls),
            "provider_structured_successes": sum(c["status"] == "success" for c in provider.calls),
            "provider_http_attempts": len(provider.attempts),
            "provider_input_tokens": observed_usage(provider.attempts, "input_tokens"),
            "provider_output_tokens": observed_usage(provider.attempts, "output_tokens"),
            "provider_reported_cost_usd": observed_usage(provider.attempts, "reported_cost_usd"),
        }
        # Preserve attempts from a budget-interrupted case as well as completed cases.
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
            executed_cases,
            results,
            cases_path,
            output,
            manifest_extra={"live_validation": live},
            summary_extra=metrics,
        )
        return {"live_validation": live, "summary": summary, "output": str(output)}
    finally:
        provider.close()
