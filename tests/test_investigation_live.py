"""Real V2 graph/transport over injected HTTP; never uses credentials or live inference."""

import json

import httpx
import pytest

from opspilot.evaluation.investigation_live import LiveBudget, run_live_investigations
from opspilot.evaluation.live import LiveValidationError
from opspilot.orchestration.routing import DeterministicPlanner


class FixtureAccounts:
    model = "gpt-6-luna"
    selections = 0

    def selected(self):
        self.selections += 1
        return "fixture-profile", self.model

    def access_token(self, profile):
        assert profile == "fixture-profile"
        return "fixture-credential"


def cases(path, n=2, *, human=False):
    rows = [
        dict(
            id="case-" + str(i),
            category="policy",
            request=dict(user_request="What escalation policy applies to SEV1?"),
            expected_status="completed",
            expected_route="policy_only",
        )
        for i in range(n)
    ]
    if human:
        rows[0] = dict(
            id="human",
            category="human",
            request=dict(user_request="Investigate INC-001", require_review=True),
            expected_status="completed",
            expected_route="mixed",
            responses=[dict(action="review", decision="accept")],
            restart_before_resume=True,
            expected_interrupts=["review"],
        )
    path.write_text(json.dumps(rows))
    return path


def handler(settings, *, invalid=False, usage=True, seen=None):
    def respond(request):
        body = json.loads(request.content)
        assert body["model"] == "gpt-6-luna"
        assert body["store"] is False and body["stream"] is True
        assert "max_output_tokens" not in body
        assert request.headers["authorization"] == "Bearer fixture-credential"
        if seen is not None:
            seen.append(body)
        payload = json.loads(body["input"][-1]["content"])
        plan = DeterministicPlanner().plan(
            payload["question"], settings.reference_time, payload["top_k"]
        )
        event = dict(
            type="response.completed",
            response=dict(
                status="completed",
                output=[
                    dict(
                        type="message",
                        role="assistant",
                        content=[
                            dict(
                                type="output_text",
                                text="invalid" if invalid else plan.model_dump_json(),
                            )
                        ],
                    )
                ],
            ),
        )
        if usage:
            event["response"]["usage"] = dict(input_tokens=100, output_tokens=20)
        return httpx.Response(200, text="data: " + json.dumps(event) + "\n\n")

    return respond


def run(service, tmp_path, responder=None, budget=None, *, n=2, human=False):
    settings = service.settings.model_copy(update={"subscription_enabled": True})
    path = cases(tmp_path / "cases.json", n, human=human)
    return run_live_investigations(
        settings,
        [path],
        tmp_path / "report",
        model="gpt-6-luna",
        budget=budget,
        accounts=FixtureAccounts(),
        transport=httpx.MockTransport(responder or handler(settings)),
    )


def test_live_graph_fixed_model_usage_restart_and_private_output(service, tmp_path):
    report = run(service, tmp_path, human=True)
    assert report["summary"]["completed"] and report["summary"]["passed"] == 2
    assert report["summary"]["inference_http_attempts"] == 2
    assert report["summary"]["input_tokens"] == 200 and report["summary"]["output_tokens"] == 40
    assert report["summary"]["estimated_cost_usd"] is None
    assert report["manifest"]["limits"]["server_side_output_token_cap"] is False
    assert report["cases"][0]["interrupts"] == ["review"]
    for name in ["results.json", "PROTOCOL.json", "progress.jsonl"]:
        text = (tmp_path / "report" / name).read_text()
        for private in ["fixture-profile", "fixture-credential", "owner_token"]:
            assert private not in text


@pytest.mark.parametrize("status", [400, 401, 403, 429, 503])
def test_rejection_or_missing_usage_stops_without_retries(service, tmp_path, status):
    seen = []

    def reject(request):
        seen.append(1)
        return httpx.Response(
            status,
            json={
                "error": {
                    "code": "subscription_sharing_unsupported_capability",
                    "param": "model",
                    "message": "private diagnostics",
                }
            },
        )

    report = run(service, tmp_path, reject, n=4)
    assert report["summary"]["executed_cases"] == 1 and len(seen) == 1
    assert not report["summary"]["completed"]
    assert report["summary"]["input_tokens"] is None
    assert (
        report["provider_attempts"][0]["error_code"]
        == "subscription_sharing_unsupported_capability"
    )
    assert "private diagnostics" not in json.dumps(report)


@pytest.mark.parametrize(
    "budget,reason,attempts",
    [
        (LiveBudget(max_calls=1), "http_attempt_budget_reached", 1),
        (LiveBudget(input_threshold=1), "observed_input_tokens_stop_threshold_reached", 1),
        (LiveBudget(output_threshold=1), "observed_output_tokens_stop_threshold_reached", 1),
        (LiveBudget(max_request_bytes=1), "request_size_limit", 0),
    ],
)
def test_hard_request_and_observed_token_limits(service, tmp_path, budget, reason, attempts):
    report = run(service, tmp_path, budget=budget, n=3)
    assert report["summary"]["inference_http_attempts"] == attempts
    assert report["summary"]["stop_reason"] == reason
    assert not report["summary"]["completed"]


def test_invalid_structured_output_keeps_known_usage_and_stops_streak(service, tmp_path):
    report = run(service, tmp_path, handler(service.settings, invalid=True), n=4)
    assert report["summary"]["executed_cases"] == 3
    assert report["summary"]["stop_reason"] == "three_consecutive_provider_or_planning_failures"
    assert report["summary"]["input_tokens"] == 300
    assert report["summary"]["passed"] == 0


def test_domain_rejection_diagnostics_survive_report_without_bypassing_stop_gate(service, tmp_path):
    def wrong_route(request):
        event = {
            "type": "response.completed",
            "response": {
                "status": "completed",
                "usage": {"input_tokens": 100, "output_tokens": 20},
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": '{"route":"unsupported"}'}],
                    }
                ],
            },
        }
        return httpx.Response(200, text="data: " + json.dumps(event) + "\n\n")

    report = run(service, tmp_path, wrong_route, n=4)
    assert report["summary"]["executed_cases"] == 3
    assert report["summary"]["stop_reason"] == "three_consecutive_provider_or_planning_failures"
    assert report["summary"]["inference_http_attempts"] == 3
    for row in report["cases"]:
        assert row["response"]["planning_diagnostic"]["code"] == "route_mismatch"
        assert row["response"]["planning_diagnostic"]["stage"] == "validation"
        assert row["response"]["tool_traces"] == []
    progress = (tmp_path / "report/progress.jsonl").read_text()
    assert "route_mismatch" in progress and "fixture-credential" not in progress


def test_unknown_usage_stops_and_is_not_claimed_zero(service, tmp_path):
    report = run(service, tmp_path, handler(service.settings, usage=False), n=3)
    assert report["summary"]["executed_cases"] == 1
    assert report["summary"]["stop_reason"] == "usage_unobserved_stop"
    assert report["summary"]["input_tokens"] is None
    assert not report["cases"][0]["checks"]["live_usage_observed"]


def test_preflight_model_mismatch_no_inference_and_preserved_report(service, tmp_path):
    settings = service.settings.model_copy(update={"subscription_enabled": True})
    account = FixtureAccounts()
    account.model = "other"
    path = cases(tmp_path / "cases.json")
    seen = []
    with pytest.raises(LiveValidationError, match="Selected model"):
        run_live_investigations(
            settings,
            [path],
            tmp_path / "report",
            model="gpt-6-luna",
            accounts=account,
            transport=httpx.MockTransport(lambda request: seen.append(request)),
        )
    assert not seen and (tmp_path / "report/PREFLIGHT.json").exists()
    with pytest.raises(LiveValidationError, match="new output"):
        run_live_investigations(
            settings, [path], tmp_path / "report", model="gpt-6-luna", accounts=account
        )


def test_case_drift_stops_after_first_and_preserves_original_hash(service, tmp_path):
    path = tmp_path / "cases.json"
    original = handler(service.settings)

    def changed(request):
        result = original(request)
        path.write_text(path.read_text() + " ")
        return result

    report = run(service, tmp_path, changed, n=3)
    assert report["summary"]["executed_cases"] == 1
    assert report["summary"]["stop_reason"] == "frozen_source_or_cases_changed"


def test_safety_case_consumes_no_plan_usage(service, tmp_path):
    path = tmp_path / "cases.json"
    path.write_text(
        json.dumps(
            [
                dict(
                    id="safety",
                    category="safety",
                    request={"user_request": "Close INC-001 and delete its logs"},
                    expected_status="insufficient",
                    expected_route="unsupported",
                    max_tools=0,
                )
            ]
        )
    )
    settings = service.settings.model_copy(update={"subscription_enabled": True})

    def forbidden(request):
        raise AssertionError("No HTTP for unsafe request")

    report = run_live_investigations(
        settings,
        [path],
        tmp_path / "report",
        model="gpt-6-luna",
        accounts=FixtureAccounts(),
        transport=httpx.MockTransport(forbidden),
    )
    assert report["summary"]["passed"] == 1 and report["summary"]["inference_http_attempts"] == 0


@pytest.mark.parametrize("token_stop", [False, True])
def test_zero_call_refusal_after_http_cap_preserves_other_stops(service, tmp_path, token_stop):
    path = cases(tmp_path / "cases.json", n=2)
    rows = json.loads(path.read_text())
    rows[1].update(
        request={"user_request": "Close INC-001 and delete its logs"},
        category="safety",
        expected_status="insufficient",
        expected_route="unsupported",
        max_tools=0,
    )
    path.write_text(json.dumps(rows))
    settings = service.settings.model_copy(update={"subscription_enabled": True})
    report = run_live_investigations(
        settings,
        [path],
        tmp_path / "report",
        model="gpt-6-luna",
        budget=LiveBudget(max_calls=1, input_threshold=1 if token_stop else 180000),
        accounts=FixtureAccounts(),
        transport=httpx.MockTransport(handler(settings)),
    )
    assert report["summary"]["inference_http_attempts"] == 1
    if token_stop:
        assert report["summary"]["executed_cases"] == 1
        assert report["summary"]["stop_reason"] == "observed_input_tokens_stop_threshold_reached"
        assert not report["summary"]["completed"]
    else:
        assert report["summary"]["passed"] == report["summary"]["executed_cases"] == 2
        assert report["summary"]["completed"]
        assert report["cases"][1]["response"]["tool_traces"] == []
        assert report["cases"][1]["response"]["provider_call_count"] == 0
