"""New development fixtures, not reconstructions of missing historical live plans."""

import copy
import json

import httpx
import pytest

from opspilot.domain.models import RoutePlan
from opspilot.investigation.models import InvestigationRequest, ResumeRequest
from opspilot.investigation.planning import PlanningRejected, validate_proposed_plan
from opspilot.investigation.service import InvestigationError, InvestigationService
from opspilot.providers.chatgpt import ChatGPTSubscription

POLICY = {
    "tool_name": "search_internal_policy",
    "arguments": {"query": "escalation notification SEV1", "top_k": 6},
}
INCIDENT = {"tool_name": "get_incident", "arguments": {"incident_id": "INC-002"}}
METRICS = {"tool_name": "calculate_incident_metrics", "arguments": {}}


class Accounts:
    def selected(self):
        return "fixture-profile", "gpt-6-luna"

    def access_token(self, profile):
        assert profile == "fixture-profile"
        return "fixture-token"


@pytest.fixture
def model_fixture(service):
    """Hand-authored model replies over the real adapter; no baseline-planner echo."""
    service.settings.subscription_enabled = True
    seen = []
    reply = {"plan": {"route": "mixed", "calls": [INCIDENT, POLICY, METRICS]}}

    def handler(request):
        body = json.loads(request.content)
        seen.append(body)
        text = reply.get("raw", json.dumps(reply["plan"]))
        event = {
            "type": "response.completed",
            "response": {
                "status": "completed",
                "usage": {"input_tokens": 123, "output_tokens": 34},
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": text}],
                    }
                ],
            },
        }
        return httpx.Response(200, text="data: " + json.dumps(event) + "\n\n")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:

        def factory(settings, accounts, profile):
            return ChatGPTSubscription(settings, accounts, profile, client=client)

        store = InvestigationService(
            service, accounts=Accounts(), subscription_provider_factory=factory
        )
        original_close, closed = store.close, False

        def close_once():
            nonlocal closed
            if not closed:
                original_close()
                closed = True

        # Restart tests close the original early; fixture teardown must not close it twice.
        store.close = close_once
        try:
            yield store, seen, reply, factory
        finally:
            store.close()


@pytest.mark.parametrize(
    "question,route,calls",
    [
        ("What escalation policy applies to SEV1?", "policy_only", [POLICY]),
        ("Show INC-002", "data_only", [INCIDENT]),
        ("Which escalation policy applies to INC-002?", "mixed", [INCIDENT, POLICY]),
        (
            "Compare INC-002 with historical incidents and applicable escalation policy",
            "mixed",
            [INCIDENT, POLICY, METRICS],
        ),
    ],
)
def test_hand_authored_plans_receive_contract_and_execute(model_fixture, question, route, calls):
    store, seen, reply, _ = model_fixture
    reply["plan"] = {"route": route, "calls": calls}
    r = store.create(InvestigationRequest(user_request=question, mode="chatgpt_subscription"))
    assert r.completion_status == "completed"
    assert r.route == route and r.planning_diagnostic is None
    assert r.provider_call_count == len(seen) == 1
    payload = json.loads(seen[0]["input"][-1]["content"])
    contract = payload["planning_contract"]
    assert contract["required_route"] == route
    assert set(contract["required_tools"]) == {c["tool_name"] for c in calls}
    assert contract["allowed_incident_ids"] == (["INC-002"] if "INC-002" in question else [])
    assert contract["allowed_duration_minutes"] == []
    assert "planning_contract is mandatory" in seen[0]["instructions"]
    assert len(r.tool_traces) <= 5 and r.usage_complete


def test_typed_clarification_contract_and_review_persist_without_replanning(model_fixture, service):
    store, seen, _, factory = model_fixture
    r = store.create(
        InvestigationRequest(
            user_request="Investigate this incident",
            mode="chatgpt_subscription",
            require_review=True,
        )
    )
    identifier, token = r.investigation_id, r.owner_token
    assert r.completion_status == "awaiting_human" and not seen
    r = store.resume(
        identifier,
        token,
        ResumeRequest(action="clarify", incident_context={"incident_id": "INC-002"}),
    )
    assert r.completion_status == "awaiting_human" and r.human_review_status == "pending"
    payload = json.loads(seen[0]["input"][-1]["content"])
    assert payload["planning_contract"]["required_route"] == "mixed"
    assert set(payload["planning_contract"]["required_tools"]) == {
        "get_incident",
        "search_internal_policy",
        "calculate_incident_metrics",
    }
    assert payload["planning_contract"]["allowed_incident_ids"] == ["INC-002"]
    store.close()
    restarted = InvestigationService(
        service, accounts=Accounts(), subscription_provider_factory=factory
    )
    try:
        r = restarted.resume(identifier, token, ResumeRequest(action="review", decision="accept"))
        assert r.completion_status == "partial" and r.planning_diagnostic is None
        assert r.severity_assessment.missing_fields  # Human acceptance cannot create missing facts.
        assert len(seen) == r.provider_call_count == 1
    finally:
        restarted.close()


@pytest.mark.parametrize(
    "mutation,code",
    [
        ("policy_only", "route_mismatch"),
        ("omit_metrics", "missing_required_tools"),
        ("invent_id", "unreported_incident_id"),
        ("invent_duration", "unreported_duration"),
    ],
)
def test_domain_rejections_are_bounded_persistent_and_never_repaired(
    model_fixture, service, mutation, code
):
    store, seen, reply, factory = model_fixture
    plan = copy.deepcopy(reply["plan"])
    if mutation == "policy_only":
        plan = copy.deepcopy({"route": "policy_only", "calls": [POLICY]})
    elif mutation == "omit_metrics":
        plan["calls"] = plan["calls"][:2]
    elif mutation == "invent_id":
        plan["calls"][0]["arguments"]["incident_id"] = "INC-099"
    else:
        plan["current_duration_minutes"] = 999
    # This model-controlled search text must not enter rejection diagnostics/logs.
    for call in plan["calls"]:
        if call["tool_name"] == "search_internal_policy":
            call["arguments"] = {"query": "sensitive fixture canary", "top_k": 6}
    reply["plan"] = plan
    r = store.create(
        InvestigationRequest(
            user_request="Compare INC-002 with historical incidents and escalation policy",
            mode="chatgpt_subscription",
        )
    )
    identifier, token = r.investigation_id, r.owner_token
    assert r.completion_status == "failed" and not r.tool_traces
    d = r.planning_diagnostic
    assert d.code == code and d.stage == "validation" and d.required_route == "mixed"
    assert len(d.proposed_tools) <= 4 and len(d.required_tools) <= 4
    assert "sensitive fixture canary" not in r.model_dump_json()
    assert "fixture-profile" not in r.model_dump_json()
    assert len(d.model_dump_json()) < 700
    assert r.usage_complete and (r.usage.input_tokens, r.usage.output_tokens) == (123, 34)
    assert r.provider_call_count == len(seen) == 1
    store.close()
    restarted = InvestigationService(
        service, accounts=Accounts(), subscription_provider_factory=factory
    )
    try:
        assert restarted.get(identifier, token).planning_diagnostic == d
        with pytest.raises(InvestigationError):
            restarted.get(identifier, "wrong-owner")
        assert len(seen) == 1
    finally:
        restarted.close()


@pytest.mark.parametrize("raw", ["private invalid canary", '{"route":"mixed","calls":[]}'])
def test_output_failures_do_not_guess_domain_cause_or_leak_raw_text(model_fixture, raw):
    store, seen, reply, _ = model_fixture
    reply["raw"] = raw
    r = store.create(InvestigationRequest(user_request="Show INC-002", mode="chatgpt_subscription"))
    assert r.completion_status == "failed" and not r.tool_traces and len(seen) == 1
    d = r.planning_diagnostic
    assert d.code == "provider_or_output_failure" and d.stage == "provider"
    assert d.proposed_route is None and not d.proposed_tools
    assert "private invalid canary" not in r.model_dump_json()
    assert r.usage.input_tokens == 123 and r.usage.output_tokens == 34


def test_catalog_failure_is_not_mislabelled_as_provider_request(
    model_fixture, service, monkeypatch
):
    store, seen, _, _ = model_fixture

    def unavailable():
        raise OSError("private catalog canary")

    monkeypatch.setattr(service.tools.incidents, "planning_catalog", unavailable)
    r = store.create(InvestigationRequest(user_request="Show INC-002", mode="chatgpt_subscription"))
    assert r.completion_status == "failed" and not seen and r.provider_call_count == 0
    assert r.usage_complete
    assert r.planning_diagnostic.code == "evidence_source_unavailable"
    assert r.planning_diagnostic.stage == "requirements"
    assert "private catalog canary" not in r.model_dump_json()


def test_current_duration_from_typed_context_is_allowed(model_fixture):
    store, seen, reply, _ = model_fixture
    reply["plan"] = {"route": "policy_only", "calls": [POLICY], "current_duration_minutes": 37}
    r = store.create(
        InvestigationRequest(
            user_request="Assess severity for this payment incident",
            incident_context={
                "category": "payment_failure",
                "customer_facing": True,
                "downtime_minutes": 37,
            },
            mode="chatgpt_subscription",
        )
    )
    assert r.completion_status == "completed" and r.severity_assessment.proposed_severity == "SEV1"
    payload = json.loads(seen[0]["input"][-1]["content"])
    assert payload["planning_contract"]["allowed_duration_minutes"] == [37]


def test_tool_budget_stays_authoritative_and_id_requires_full_token():
    proposed = RoutePlan.model_validate({"route": "mixed", "calls": [INCIDENT, POLICY]})
    with pytest.raises(PlanningRejected, match="tool_budget_exceeded"):
        validate_proposed_plan(proposed, proposed, "INC-002 escalation policy", 1)
    single = RoutePlan.model_validate({"route": "data_only", "calls": [INCIDENT]})
    with pytest.raises(PlanningRejected, match="unreported_incident_id"):
        validate_proposed_plan(single, RoutePlan(route="unsupported"), "INC-0029", 4)


def test_graph_tool_budget_rejects_without_dispatch(model_fixture, service):
    store, seen, _, _ = model_fixture
    service.settings.max_tool_calls = 2
    # Refresh identity after changing operator configuration, before any investigation exists.
    store.identity = store.current_identity()
    r = store.create(
        InvestigationRequest(
            user_request="Compare INC-002 with historical incidents and escalation policy",
            mode="chatgpt_subscription",
        )
    )
    assert r.completion_status == "failed" and not r.tool_traces
    assert r.planning_diagnostic.code == "tool_budget_exceeded" and len(seen) == 1


def test_graph_provider_call_budget_cannot_trigger_a_second_request(model_fixture):
    store, seen, reply, _ = model_fixture
    reply["plan"] = {"route": "data_only", "calls": [INCIDENT]}
    r = store.create(InvestigationRequest(user_request="Show INC-002", mode="chatgpt_subscription"))
    graph = store.workflow(r.mode, r.investigation_id)
    state = graph.get_state(store.config(r.investigation_id)).values
    workflow = store.workflows[(r.mode, r.investigation_id)]
    result = workflow.plan_investigation(state)
    assert result["failed"] and result["planning_diagnostic"]["stage"] == "provider"
    assert result["planning_diagnostic"]["code"] == "provider_call_budget_exhausted"
    assert result["provider_call_count"] == len(seen) == 1
    assert result["usage_complete"]


def test_clients_cannot_supply_trusted_planning_contract_or_diagnostics():
    for field in ("planning_contract", "planning_diagnostic"):
        with pytest.raises(ValueError):
            InvestigationRequest.model_validate({"user_request": "Show INC-002", field: {}})
