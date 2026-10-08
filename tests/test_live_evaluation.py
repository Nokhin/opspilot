import json
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr

from opspilot.evaluation.live import (
    LiveValidationError,
    RecordedChatAPI,
    load_live_settings,
    run_live_evaluation,
)
from opspilot.orchestration.routing import DeterministicPlanner
from opspilot.providers.chat_api import ProviderError

CASES = Path("opspilot/evaluation/cases_v1_1.json")


def live_settings(service):
    return service.settings.model_copy(
        update={
            "llm_provider": "chat_api",
            "llm_base_url": "https://openrouter.ai/api/v1",
            "llm_model": "unit-test-model",
            "llm_api_key": SecretStr("private-unit-test-key"),
            "provider_retries": 0,
        }
    )


def valid_handler(settings):
    def handler(request):
        body = json.loads(request.content)
        assert request.url.path == "/api/v1/chat/completions"
        assert body["response_format"] == {"type": "json_object"}
        payload = json.loads(body["messages"][1]["content"])
        if "evidence" in payload:
            if "INC-001" in payload["question"]:
                assert payload["incident_context"]["severity"] == "SEV1"
                assert payload["incident_context"]["category"] == "payment_failure"
                assert "root_cause" not in payload["incident_context"]
            result = {
                "sufficient": True,
                "quotes": [
                    {"evidence_id": e["evidence_id"], "quote": e["paragraphs"][0]}
                    for e in payload["evidence"]
                ],
            }
        else:
            result = (
                DeterministicPlanner()
                .plan(payload["question"], settings.reference_time, settings.top_k)
                .model_dump(mode="json")
            )
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps(result)}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 20, "cost": 0.0002},
            },
        )

    return handler


def test_live_smoke_uses_http_contract_and_records_usage(service, tmp_path):
    settings = live_settings(service)
    output = tmp_path / "report"
    result = run_live_evaluation(
        settings,
        CASES,
        output,
        smoke=True,
        transport=httpx.MockTransport(valid_handler(settings)),
    )
    assert result["summary"]["passed"] == 5
    assert result["live_validation"]["scope"] == "smoke"
    assert result["live_validation"]["transport"] == "injected_test_transport"
    assert result["live_validation"]["completed"]
    assert result["summary"]["provider_http_attempts"] == 6
    assert result["summary"]["provider_input_tokens"] == 600
    assert result["summary"]["provider_reported_cost_usd"] == pytest.approx(0.0012)
    data = json.loads((output / "results.json").read_text())
    assert data["cases"][-1]["provider_calls"] == []  # Safety is enforced before inference.
    for path in output.iterdir():
        assert "private-unit-test-key" not in path.read_text()


def test_auth_failure_stops_after_one_case_and_is_not_a_pass(service, tmp_path):
    output = tmp_path / "report"
    result = run_live_evaluation(
        live_settings(service),
        CASES,
        output,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                401, json={"error": "private-unit-test-key must never be written"}
            )
        ),
    )
    assert not result["live_validation"]["completed"]
    assert result["live_validation"]["requested_cases"] == 50
    assert result["summary"]["cases"] == 1 and result["summary"]["passed"] == 0
    assert result["summary"]["provider_http_attempts"] == 1
    assert result["summary"]["provider_reported_cost_usd"] is None
    assert "private-unit-test-key" not in (output / "provider.json").read_text()


def test_invalid_json_keeps_billed_usage_and_unknown_cost(service, tmp_path):
    output = tmp_path / "report"
    result = run_live_evaluation(
        live_settings(service),
        CASES,
        output,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "not JSON"}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 3},
                },
            )
        ),
    )
    assert result["live_validation"]["stop_reason"] == "three_consecutive_provider_failures"
    assert result["summary"]["provider_structured_successes"] == 0
    assert result["summary"]["provider_input_tokens"] == 30
    assert result["summary"]["provider_output_tokens"] == 9
    assert result["summary"]["provider_reported_cost_usd"] is None


def test_budget_stops_before_extra_http_request_and_preserves_partial_report(service, tmp_path):
    settings = live_settings(service)
    output = tmp_path / "report"
    result = run_live_evaluation(
        settings,
        CASES,
        output,
        smoke=True,
        max_http_attempts=2,
        transport=httpx.MockTransport(valid_handler(settings)),
    )
    assert result["live_validation"]["stop_reason"] == "http_attempt_budget_reached"
    assert result["summary"]["cases"] == 1
    assert result["summary"]["provider_http_attempts"] == 2
    assert not result["live_validation"]["completed"]
    assert (output / "progress.jsonl").is_file()


def test_network_retry_is_counted_and_transport_errors_are_sanitised(service, monkeypatch):
    monkeypatch.setattr("opspilot.providers.chat_api.time.sleep", lambda n: None)
    settings = live_settings(service)
    settings.provider_retries = 1
    attempts = []

    def handler(request):
        attempts.append(request)
        if len(attempts) == 1:
            raise httpx.RemoteProtocolError("private transport diagnostic")
        return valid_handler(settings)(request)

    provider = RecordedChatAPI(settings, 2, httpx.MockTransport(handler))
    try:
        plan, _ = provider.plan("Show INC-001")
        assert plan.route == "data_only"
        assert len(provider.attempts) == 2 and len(provider.calls) == 1
        assert provider.attempts[0]["http_status"] is None
        assert provider.calls[0]["status"] == "success"
        assert "private transport diagnostic" not in json.dumps(provider.attempts)
    finally:
        provider.close()


def test_existing_reports_and_offline_mode_are_rejected(service, tmp_path):
    (tmp_path / "keep.txt").write_text("existing offline evidence")
    with pytest.raises(LiveValidationError, match="not empty"):
        run_live_evaluation(live_settings(service), CASES, tmp_path)
    with pytest.raises(LiveValidationError, match="chat_api"):
        run_live_evaluation(service.settings, CASES, tmp_path / "other")
    assert (tmp_path / "keep.txt").read_text() == "existing offline evidence"


def test_missing_live_configuration_never_echoes_a_secret(tmp_path, monkeypatch):
    for name in ["OPSPILOT_LLM_API_KEY", "OPSPILOT_LLM_MODEL", "OPSPILOT_LLM_BASE_URL"]:
        monkeypatch.delenv(name, raising=False)
    path = tmp_path / ".env.live"
    path.write_text("OPSPILOT_LLM_API_KEY=private-value\n")
    with pytest.raises(LiveValidationError) as error:
        load_live_settings(path)
    assert "OPSPILOT_LLM_MODEL" in str(error.value)
    assert "private-value" not in str(error.value)


def test_schema_diagnostics_preserve_duplicate_tools_without_raw_model_text(service):
    content = {
        "route": "policy_only",
        "calls": [
            {"tool_name": "search_internal_policy", "arguments": {"query": "Escalation"}},
            {"tool_name": "search_internal_policy", "arguments": {"query": "Communication"}},
        ],
    }
    provider = RecordedChatAPI(
        live_settings(service),
        1,
        httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {
                                "content": json.dumps(content),
                                "reasoning": "private model reasoning",
                            },
                        }
                    ]
                },
            )
        ),
    )
    try:
        with pytest.raises(ProviderError, match="invalid structured"):
            provider.plan("Explain escalation and communication")
        attempt = provider.attempts[0]
        assert attempt["schema_errors"] == [{"type": "value_error", "location": []}]
        assert attempt["proposed_tools"] == ["search_internal_policy"] * 2
        assert attempt["finish_reason"] == "stop"
        assert "Escalation" not in json.dumps(attempt)
        assert "private model reasoning" not in json.dumps(attempt)
    finally:
        provider.close()


def test_schema_diagnostics_redact_unknown_field_names(service):
    content = {"route": "unsupported", "calls": [], "privateunitsecret": "private-value"}
    provider = RecordedChatAPI(
        live_settings(service),
        1,
        httpx.MockTransport(
            lambda request: httpx.Response(
                200, json={"choices": [{"message": {"content": json.dumps(content)}}]}
            )
        ),
    )
    try:
        with pytest.raises(ProviderError):
            provider.plan("Unknown question")
        assert provider.attempts[0]["schema_errors"] == [
            {"type": "extra_forbidden", "location": ["unknown_field"]}
        ]
        assert "privateunitsecret" not in json.dumps(provider.attempts)
        assert "private-value" not in json.dumps(provider.attempts)
    finally:
        provider.close()


def test_targeted_cases_keep_requested_denominator_and_validate_ids(service, tmp_path):
    settings = live_settings(service)
    result = run_live_evaluation(
        settings,
        CASES,
        tmp_path / "targeted",
        case_ids=["data_01", "safety_01"],
        transport=httpx.MockTransport(valid_handler(settings)),
    )
    assert result["live_validation"]["scope"] == "targeted"
    assert result["live_validation"]["requested_cases"] == 2
    assert result["summary"]["cases"] == result["summary"]["passed"] == 2
    assert result["summary"]["provider_http_attempts"] == 1
    for ids in [["unknown"], ["data_01", "data_01"]]:
        with pytest.raises(LiveValidationError, match="unique members"):
            run_live_evaluation(settings, CASES, tmp_path / "invalid", case_ids=ids)
    with pytest.raises(LiveValidationError, match="not both"):
        run_live_evaluation(settings, CASES, tmp_path / "invalid", smoke=True, case_ids=["data_01"])
