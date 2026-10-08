import json
import sqlite3

import httpx
import pytest

from opspilot.config import Settings
from opspilot.domain.models import RoutePlan
from opspilot.providers.chat_api import ChatAPI, ProviderError
from opspilot.providers.embedding_api import APIEmbeddings


def api_settings():
    return Settings(
        _env_file=None,
        llm_provider="chat_api",
        llm_model="configured-test-model",
        llm_api_key="test-placeholder",
        provider_retries=0,
    )


def test_config_and_optional_empty_cost():
    assert Settings(_env_file=None, input_cost_per_million="").input_cost_per_million is None
    with pytest.raises(ValueError):
        Settings(_env_file=None, llm_provider="chat_api")
    with pytest.raises(ValueError):
        Settings(_env_file=None, top_k=99)
    with pytest.raises(ValueError):
        Settings(_env_file=None, llm_base_url="https://example.test/v1?key=sensitive")
    with pytest.raises(ValueError):
        Settings(_env_file=None, llm_base_url="http://remote.example/v1")


def test_chat_api_schema_and_usage():
    def handler(request):
        body = json.loads(request.content)
        assert body["model"] == "configured-test-model"
        assert body["response_format"] == {"type": "json_object"}
        assert "untrusted" in body["messages"][0]["content"]
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "route": "data_only",
                                    "calls": [
                                        {
                                            "tool_name": "get_incident",
                                            "arguments": {"incident_id": "INC-001"},
                                        }
                                    ],
                                }
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 100, "completion_tokens": 20},
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        provider = ChatAPI(api_settings(), client)
        plan, usage = provider.plan("Show INC-001")
    assert plan.route == "data_only" and usage.input_tokens == 100


@pytest.mark.parametrize(
    "status,payload",
    [
        (500, {"secret": "do-not-expose"}),
        (400, {"error": "do-not-expose"}),
        (
            200,
            {
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"route":"data_only","calls":['
                                '{"tool_name":"shell","arguments":{}}]}'
                            )
                        }
                    }
                ]
            },
        ),
        (200, {"choices": [{"message": {"content": "not-json do-not-expose"}}]}),
    ],
)
def test_provider_failures_are_sanitised(status, payload):
    with httpx.Client(
        transport=httpx.MockTransport(lambda req: httpx.Response(status, json=payload))
    ) as client:
        with pytest.raises(ProviderError) as error:
            ChatAPI(api_settings(), client).plan("Show INC-001")
    assert "do-not-expose" not in str(error.value)


def test_retry_is_bounded(monkeypatch):
    attempts = []
    monkeypatch.setattr("opspilot.providers.chat_api.time.sleep", lambda n: None)

    def handler(request):
        attempts.append(request)
        return httpx.Response(503)

    settings = api_settings()
    settings.provider_retries = 1
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ProviderError):
            ChatAPI(settings, client).complete("prompt", {}, RoutePlan)
    assert len(attempts) == 2


def test_dense_embeddings_normalisation_and_dimension_guard():
    settings = Settings(
        _env_file=None,
        embedding_provider="embedding_api",
        embedding_model="test",
        embedding_base_url="https://example.test/v1",
        embedding_api_key="placeholder",
    )

    def handler(request):
        inputs = json.loads(request.content)["input"]
        return httpx.Response(
            200, json={"data": [{"index": i, "embedding": [3, 4]} for i in range(len(inputs))]}
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        provider = APIEmbeddings(settings, client)
        state = provider.fit(["a"])
        assert provider.encode(["a"], state) == [{"0": 0.6, "1": 0.8}]
        assert state["dimensions"] == 2
        with pytest.raises(ProviderError):
            provider.encode(["a"], {"dimensions": 3})


def test_api_planner_executes_only_validated_tools_and_records_cost(service):
    from opspilot.orchestration.service import OpsPilotService

    settings = service.settings.model_copy(
        update={
            "llm_provider": "chat_api",
            "llm_model": "configured-test-model",
            "input_cost_per_million": 1.0,
            "output_cost_per_million": 2.0,
        }
    )

    def handler(request):
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "route": "data_only",
                                    "calls": [
                                        {
                                            "tool_name": "get_incident",
                                            "arguments": {"incident_id": "INC-001"},
                                        }
                                    ],
                                }
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 100, "completion_tokens": 20},
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        response = OpsPilotService(settings, ChatAPI(settings, client)).ask(
            "Retrieve INC-001 details"
        )
    assert response.mode == "chat_api"
    assert response.tool_trace[0].tool_name == "get_incident"
    assert response.usage.estimated_cost_usd == pytest.approx(0.00014)


def test_invalid_api_plan_never_reaches_tool_executor(service):
    from opspilot.orchestration.service import OpsPilotService

    def handler(request):
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "route": "data_only",
                                    "calls": [
                                        {
                                            "tool_name": "execute_sql",
                                            "arguments": {"sql": "DELETE FROM incidents"},
                                        }
                                    ],
                                }
                            )
                        }
                    }
                ]
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        response = OpsPilotService(service.settings, ChatAPI(api_settings(), client)).ask(
            "Show INC-001"
        )
    assert response.confidence == "insufficient_evidence"
    assert not response.tool_trace
    assert not response.facts


def test_planner_receives_database_catalog_and_keeps_explicit_historical_filters(service):
    from opspilot.orchestration.service import OpsPilotService

    # A locally administered fixture change proves metadata is not hard-coded in the prompt.
    with sqlite3.connect(service.settings.incident_db) as con:
        con.execute("UPDATE incidents SET service='Card Payments' WHERE incident_id='INC-001'")

    def handler(request):
        body = json.loads(request.content)
        payload = json.loads(body["messages"][1]["content"])
        assert {"service": "Card Payments", "category": "payment_failure"} in payload[
            "service_catalog"
        ]
        assert all(set(entry) == {"service", "category"} for entry in payload["service_catalog"])
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "route": "data_only",
                                    "calls": [
                                        {
                                            "tool_name": "calculate_incident_metrics",
                                            "arguments": {
                                                "service": "Card Payments",
                                                "min_customer_impact": 500,
                                                "since": "2025-10-01T00:00:00Z",
                                                "until": "2026-10-01T00:00:00Z",
                                            },
                                        }
                                    ],
                                }
                            )
                        }
                    }
                ]
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        response = OpsPilotService(service.settings, ChatAPI(api_settings(), client)).ask(
            "Calculate Card Payments incidents affecting at least 500 customers in the last year"
        )
    assert response.tool_trace[0].arguments["min_customer_impact"] == 500
    result = response.tool_results[0].result
    assert result["incident_count"] == 1 and result["median_downtime_minutes"] == 45
    assert result["total_customer_impact"] == 620


@pytest.mark.parametrize(
    "question,sample_expected",
    [
        ("Compare median payment downtime in the last six months", False),
        ("Compare payment downtime and list similar examples in the last six months", True),
        ("比較 payment downtime 同列出類似事故例子", True),
    ],
)
def test_executor_limits_samples_without_removing_requested_examples(
    service, question, sample_expected
):
    from opspilot.orchestration.service import OpsPilotService

    # Deliberately over-selected provider plan: only execution semantics change.
    plan = {
        "route": "data_only",
        "calls": [
            {"tool_name": "find_similar_incidents", "arguments": {"category": "payment_failure"}},
            {
                "tool_name": "calculate_incident_metrics",
                "arguments": {"category": "payment_failure"},
            },
        ],
    }
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, json={"choices": [{"message": {"content": json.dumps(plan)}}]}
            )
        )
    ) as client:
        response = OpsPilotService(service.settings, ChatAPI(api_settings(), client)).ask(question)
    names = {t.tool_name for t in response.tool_trace}
    assert "calculate_incident_metrics" in names
    assert ("find_similar_incidents" in names) == sample_expected
    assert response.route == "data_only" and response.confidence == "high"
    assert any("sample was omitted" in s for s in response.limitations) == (not sample_expected)
    assert all(t.status == "success" for t in response.tool_trace)
