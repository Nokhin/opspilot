import json
from pathlib import Path

import httpx
import pytest

from opspilot.evaluation.live import LiveValidationError
from opspilot.evaluation.subscription import run_subscription_evaluation
from opspilot.orchestration.routing import DeterministicPlanner

CASES = Path("opspilot/evaluation/cases_v1_1.json")


class TestAccounts:
    __test__ = False

    def selected(self):
        return "test-profile", "gpt-fixture"

    def access_token(self, profile_id):
        assert profile_id == "test-profile"
        return "fixture-credential"


def handler(settings):
    def respond(request):
        body = json.loads(request.content)
        payload = json.loads(body["input"][-1]["content"])
        if "evidence" in payload:
            result = {
                "sufficient": True,
                "quotes": [
                    {"evidence_id": hit["evidence_id"], "quote": hit["paragraphs"][0]}
                    for hit in payload["evidence"]
                ],
            }
        else:
            result = (
                DeterministicPlanner()
                .plan(payload["question"], settings.reference_time, settings.top_k)
                .model_dump(mode="json")
            )
        event = {
            "type": "response.completed",
            "response": {
                "status": "completed",
                "usage": {"input_tokens": 100, "output_tokens": 20},
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {"type": "output_text", "text": json.dumps(result)},
                        ],
                    }
                ],
            },
        }
        return httpx.Response(200, text="data: " + json.dumps(event) + "\n\n")

    return respond


def evaluate(service, output, transport, **kwargs):
    return run_subscription_evaluation(
        service.settings.model_copy(update={"subscription_enabled": True}),
        CASES,
        output / "report",
        model="gpt-fixture",
        accounts=TestAccounts(),
        transport=transport,
        **kwargs,
    )


def test_subscription_smoke_preserves_grades_usage_and_safety(service, tmp_path):
    result = evaluate(service, tmp_path, httpx.MockTransport(handler(service.settings)), smoke=True)
    assert result["live_validation"]["completed"]
    assert result["summary"]["passed"] == 5
    assert result["summary"]["provider_http_attempts"] == 6
    assert result["summary"]["provider_input_tokens"] == 600
    assert result["summary"]["provider_reported_cost_usd"] is None
    assert result["live_validation"]["billing"] == "chatgpt_plan"
    data = json.loads((tmp_path / "report/results.json").read_text())
    assert data["cases"][-1]["provider_calls"] == []
    for file in (tmp_path / "report").iterdir():
        assert "fixture-credential" not in file.read_text()
        assert "test-profile" not in file.read_text()


@pytest.mark.parametrize("status", [401, 403, 429])
def test_subscription_rejection_stops_without_fallback(service, tmp_path, status):
    result = evaluate(
        service,
        tmp_path,
        httpx.MockTransport(lambda request: httpx.Response(status, text="private diagnostic")),
    )
    assert not result["live_validation"]["completed"]
    assert result["summary"]["cases"] == 1
    assert result["summary"]["provider_http_attempts"] == 1
    assert result["summary"]["passed"] == 0
    assert result["summary"]["provider_input_tokens"] is None
    assert "private diagnostic" not in (tmp_path / "report/provider.json").read_text()


def test_subscription_budget_and_partial_report(service, tmp_path):
    result = evaluate(
        service,
        tmp_path,
        httpx.MockTransport(handler(service.settings)),
        smoke=True,
        max_http_attempts=2,
    )
    assert not result["live_validation"]["completed"]
    assert result["live_validation"]["stop_reason"] == "http_attempt_budget_reached"
    assert result["summary"]["provider_http_attempts"] == 2
    assert result["summary"]["cases"] == 1


def test_subscription_rejects_model_mismatch_and_existing_reports(service, tmp_path):
    settings = service.settings.model_copy(update={"subscription_enabled": True})
    with pytest.raises(LiveValidationError, match="differs"):
        run_subscription_evaluation(
            settings, CASES, tmp_path / "different", model="another-model", accounts=TestAccounts()
        )
    (tmp_path / "report").mkdir()
    (tmp_path / "report/existing.txt").write_text("keep this evidence")
    with pytest.raises(LiveValidationError, match="not empty"):
        evaluate(service, tmp_path, httpx.MockTransport(handler(settings)))


def test_invalid_structured_output_retains_observed_tokens(service, tmp_path):
    def invalid(request):
        event = {
            "type": "response.completed",
            "response": {
                "status": "completed",
                "usage": {"input_tokens": 50, "output_tokens": 4},
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {"type": "output_text", "text": "not JSON"},
                        ],
                    }
                ],
            },
        }
        return httpx.Response(200, text="data: " + json.dumps(event) + "\n\n")

    result = evaluate(service, tmp_path, httpx.MockTransport(invalid))
    assert result["live_validation"]["stop_reason"] == "three_consecutive_provider_failures"
    assert result["summary"]["provider_structured_successes"] == 0
    assert result["summary"]["provider_input_tokens"] == 150


def test_subscription_terminal_request_error_stops_after_one_attempt(service, tmp_path):
    event = {
        "type": "error",
        "error": {
            "type": "invalid_request_error",
            "message": "private diagnostic",
        },
    }
    result = evaluate(
        service,
        tmp_path,
        httpx.MockTransport(
            lambda request: httpx.Response(200, text="data: " + json.dumps(event) + "\n\n")
        ),
    )
    assert result["summary"]["cases"] == 1
    assert result["summary"]["provider_http_attempts"] == 1
    assert result["live_validation"]["stop_reason"] == "provider_request_rejected_or_usage_limited"
    assert "private diagnostic" not in (tmp_path / "report/provider.json").read_text()
