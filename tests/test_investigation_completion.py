"""Functional completion 1–5: severity, coverage, clarification and useful briefs."""

import copy
from datetime import datetime

import pytest

from opspilot.investigation.models import InvestigationRequest, ResumeRequest
from opspilot.investigation.service import InvestigationError, InvestigationService


@pytest.fixture
def completed_store(service):
    store = InvestigationService(service)
    yield store
    store.close()


def ask(store, question, context=None, **kwargs):
    return store.create(
        InvestigationRequest(user_request=question, incident_context=context or {}, **kwargs)
    )


def state_of(store, response):
    return copy.deepcopy(
        store.workflow(response.mode).get_state(store.config(response.investigation_id)).values
    )


LOW_RISK = dict(
    category="payment_failure",
    customer_facing=False,
    immediate_danger=False,
    multi_site_essential_closure=False,
    duplicate_capture_confirmed=False,
)


@pytest.mark.parametrize(
    "values,expected",
    [
        ({"category": "payment_failure", "customer_impact_count": 500}, "SEV1"),
        ({"category": "payment_failure", "customer_facing": True, "downtime_minutes": 30}, "SEV1"),
        ({"category": "digital_outage", "customer_facing": True, "downtime_minutes": 35}, "SEV1"),
        ({"category": "facility_disruption", "immediate_danger": True}, "SEV1"),
        ({"category": "facility_disruption", "multi_site_essential_closure": True}, "SEV1"),
        ({**LOW_RISK, "customer_impact_count": 499}, "SEV2"),
        (
            {
                **LOW_RISK,
                "customer_facing": True,
                "downtime_minutes": 29,
                "customer_impact_count": 0,
            },
            "SEV2",
        ),
        ({**LOW_RISK, "customer_impact_count": 0, "duplicate_capture_confirmed": True}, "SEV2"),
        (
            {
                **LOW_RISK,
                "customer_impact_count": 20,
                "local_degradation": True,
                "workaround_available": True,
                "integrity_concern": False,
                "no_customer_interruption": False,
            },
            "SEV3",
        ),
        (
            {
                **LOW_RISK,
                "customer_impact_count": 0,
                "minor_operational_defect": True,
                "no_customer_interruption": True,
                "integrity_concern": False,
            },
            "SEV4",
        ),
    ],
)
def test_thresholds_require_policy_support_and_preserve_unknown(completed_store, values, expected):
    r = ask(completed_store, "Assess severity for this incident", values)
    assert r.completion_status == "completed", r.model_dump_json(exclude={"owner_token"})
    a = r.severity_assessment
    assert a.proposed_severity == expected and a.status == "supported"
    assert a.recorded_severity is None
    assert "POL-INC-001:s02:c01" in a.evidence_ids
    if expected != "SEV1":
        assert "POL-INC-001:s03:c01" in a.evidence_ids
    refs = {e.evidence_id for e in r.investigation_brief.source_citations}
    assert set(a.evidence_ids) <= refs
    observed = {o.field: o.value for o in a.context_observations}
    if "customer_impact_count" not in values:
        assert "customer_impact_count" not in observed


def test_recorded_reported_and_proposed_are_separate(completed_store):
    r = ask(completed_store, "Investigate INC-001", {"severity": "SEV4"})
    assert r.completion_status == "awaiting_human"
    a = r.severity_assessment
    assert (a.recorded_severity, a.reported_severity, a.proposed_severity) == (
        "SEV1",
        "SEV4",
        "SEV1",
    )
    r = completed_store.resume(
        r.investigation_id, r.owner_token, ResumeRequest(action="review", decision="accept")
    )
    assert r.completion_status == "partial"
    assert all(
        a.status == "proposed_not_executed" for a in r.investigation_brief.recommended_next_steps
    )


def test_unknown_is_not_zero_and_clarification_stops(completed_store):
    r = ask(
        completed_store, "Assess severity for this payment outage", {"category": "payment_failure"}
    )
    assert r.completion_status == "awaiting_human"
    pending = r.clarification_request
    token = r.owner_token
    identifier = r.investigation_id
    r = completed_store.resume(
        identifier,
        token,
        ResumeRequest(action="clarify", unknown_fields=pending["accepted_fields"]),
    )
    assert r.completion_status in {"partial", "insufficient"}
    assert r.severity_assessment.proposed_severity is None
    assert r.severity_assessment.status == "insufficient"
    assert any(
        o.field == "customer_impact_count" and o.value is None
        for o in r.severity_assessment.context_observations
    )
    assert r.workflow_trace.count("request_clarification") == 1
    assert r.retry_count <= 1 and len(r.tool_traces) <= 5


def test_two_typed_clarification_rounds_persist(service):
    store = InvestigationService(service)
    try:
        r = ask(store, "Assess severity for this incident")
        identifier, token = r.investigation_id, r.owner_token
        r = store.resume(
            identifier,
            token,
            ResumeRequest(action="clarify", incident_context={"category": "payment_failure"}),
        )
        assert r.completion_status == "awaiting_human" and r.clarification_request["round"] == 2
        assert not r.tool_traces
        store.close()
        store = InvestigationService(service)
        r = store.resume(
            identifier,
            token,
            ResumeRequest(action="clarify", incident_context={"customer_impact_count": 500}),
        )
        assert (
            r.completion_status == "completed" and r.severity_assessment.proposed_severity == "SEV1"
        )
        assert r.workflow_trace.count("request_clarification") == 1
    finally:
        store.close()


def test_false_and_zero_clarifications_are_retained(completed_store):
    r = ask(
        completed_store,
        "Assess severity for this incident",
        {"category": "payment_failure", "customer_facing": False, "customer_impact_count": 110},
    )
    pending = r.clarification_request
    assert "customer_impact_count" not in pending["accepted_fields"]
    r = completed_store.resume(
        r.investigation_id,
        r.owner_token,
        ResumeRequest(
            action="clarify",
            incident_context={"immediate_danger": False, "multi_site_essential_closure": False},
        ),
    )
    assert (
        r.severity_assessment.status == "supported"
        and r.severity_assessment.proposed_severity == "SEV2"
    )
    assert any(
        o.field == "immediate_danger" and o.value is False
        for o in r.severity_assessment.context_observations
    )


def test_each_requested_escalation_dimension_is_covered(completed_store):
    r = ask(
        completed_store,
        "For SEV1, who must be notified, when does the notification clock start, "
        "and what must escalation content include?",
    )
    assert r.completion_status == "completed"
    coverage = {d.dimension_id: d for d in r.verification_result.dimension_coverage}
    for name in ("notifications", "clock", "content"):
        assert coverage["policy:escalation:" + name].status == "supported"
    assert "POL-INC-002:s05:c01" in coverage["policy:escalation:content"].evidence_ids


def test_nearby_citation_cannot_cover_missing_content(completed_store, monkeypatch):
    tools = completed_store.service.tools
    original = tools.search_internal_policy

    def missing(args):
        result = original(args)
        result.hits = [h for h in result.hits if h.chunk.chunk_id != "POL-INC-002:s05:c01"]
        return result

    monkeypatch.setattr(tools, "search_internal_policy", missing)
    r = ask(
        completed_store, "For SEV1, who must be notified and what must escalation content include?"
    )
    assert r.completion_status == "partial" and r.retry_count == 1
    coverage = {d.dimension_id: d for d in r.verification_result.dimension_coverage}
    assert coverage["policy:escalation:notifications"].status == "supported"
    assert coverage["policy:escalation:content"].status == "missing"


def test_changed_rule_contract_cannot_drive_a_severity(completed_store, monkeypatch):
    tools = completed_store.service.tools
    original = tools.search_internal_policy

    def changed(args):
        result = original(args)
        for hit in result.hits:
            if hit.chunk.chunk_id == "POL-INC-001:s02:c01":
                hit.chunk.content = hit.chunk.content.replace("500 customers", "5 customers")
        return result

    monkeypatch.setattr(tools, "search_internal_policy", changed)
    r = ask(
        completed_store,
        "Assess severity for this incident",
        {"category": "payment_failure", "customer_impact_count": 500},
    )
    assert r.completion_status == "failed"
    assert r.severity_assessment is None
    assert not r.investigation_brief.recommended_next_steps


def test_deadlines_have_cited_roles_triggers_and_real_clock(completed_store):
    r = ask(
        completed_store,
        "Investigate this incident",
        {
            "category": "payment_failure",
            "customer_impact_count": 620,
            "threshold_detected_at": "2026-09-29T10:00:00Z",
        },
    )
    assert r.completion_status == "completed"
    actions = r.investigation_brief.recommended_next_steps
    operations = next(a for a in actions if "notification to Operations Duty Manager" in a.text)
    assert operations.deadline_minutes == 5 and operations.deadline_basis == "threshold detection"
    assert operations.due_at == datetime.fromisoformat("2026-09-29T10:05:00+00:00")
    assert operations.owner_role and operations.trigger
    assert "POL-INC-002:s02:c01" in operations.evidence_ids
    assert all(a.status == "proposed_not_executed" for a in actions)
    assert "620" in r.investigation_brief.executive_summary
    assert "historical cohort" in r.investigation_brief.executive_summary


def test_opened_at_is_not_threshold_detection_or_new_action(completed_store):
    r = ask(completed_store, "Investigate INC-001")
    assert r.completion_status == "completed"
    assert all(a.due_at is None for a in r.investigation_brief.recommended_next_steps)
    assert all(a.retrospective for a in r.investigation_brief.recommended_next_steps)
    assert any("retrospective" in s.lower() for s in r.severity_assessment.limitations)


@pytest.mark.parametrize("field", ["severity", "deadline", "owner"])
def test_verifier_rejects_generated_decision_tampering(completed_store, field):
    r = ask(completed_store, "Investigate INC-001")
    state = state_of(completed_store, r)
    if field == "severity":
        state["severity_assessment"]["proposed_severity"] = "SEV4"
    elif field == "deadline":
        state["proposed_actions"][0]["deadline_minutes"] = 1
    else:
        state["proposed_actions"][0]["owner_role"] = "Invented executive"
    result = completed_store.workflows["offline"].verifier.invoke(state)
    assert not result.sufficient and result.integrity_errors


def test_unrequested_resume_fields_are_rejected_without_consuming_interrupt(completed_store):
    r = ask(
        completed_store,
        "Assess severity for this payment outage",
        {
            "category": "payment_failure",
            "customer_facing": True,
            "downtime_minutes": 12,
            "customer_impact_count": 110,
        },
    )
    with pytest.raises(InvestigationError) as error:
        completed_store.resume(
            r.investigation_id,
            r.owner_token,
            ResumeRequest(action="clarify", incident_context={"incident_id": "INC-001"}),
        )
    assert error.value.status == 422
    assert (
        completed_store.get(r.investigation_id, r.owner_token).completion_status == "awaiting_human"
    )


def test_review_calendar_is_not_fabricated(completed_store):
    r = ask(completed_store, "What exact calendar date is the SEV1 post-incident review due date?")
    assert r.completion_status in {"partial", "insufficient"}
    assert any(g.requirement_id == "input:holiday_calendar" for g in r.verification_result.gaps)
    assert not any(a.due_at for a in r.investigation_brief.recommended_next_steps)


def test_existing_scenario_completes_after_customer_facing_clarification(completed_store):
    question = (
        "A payment service has been down for 45 minutes. What escalation does policy require, "
        "and how does this duration compare with similar incidents over the last year?"
    )
    r = ask(completed_store, question)
    assert r.completion_status == "awaiting_human"
    assert "customer_facing" in r.clarification_request["accepted_fields"]
    unknown = [f for f in r.clarification_request["accepted_fields"] if f != "customer_facing"]
    r = completed_store.resume(
        r.investigation_id,
        r.owner_token,
        ResumeRequest(
            action="clarify", incident_context={"customer_facing": True}, unknown_fields=unknown
        ),
    )
    assert r.completion_status == "completed"
    assert r.severity_assessment.proposed_severity == "SEV1"
    assert any(
        "Supplied scenario duration 45 minutes" in f.text
        for f in r.investigation_brief.key_findings
    )
    assert r.retry_count <= 1 and len(r.tool_traces) <= 5


def test_one_retry_can_target_missing_facets_across_documents(completed_store):
    r = ask(
        completed_store, "What escalation policy and customer communication cadence apply to SEV1?"
    )
    assert r.completion_status == "completed"
    assert r.retry_count <= 1
    assert all(d.status == "supported" for d in r.verification_result.dimension_coverage)
    queries = [t.arguments for t in r.tool_traces if t.tool_name == "search_internal_policy"]
    assert len(queries) <= 2 and len({str(q) for q in queries}) == len(queries)


def test_owner_token_is_not_in_debug_representation(completed_store):
    r = ask(completed_store, "Show INC-001")
    assert r.owner_token not in repr(r)


def test_lower_proposal_is_not_hidden_by_a_reported_high_severity(completed_store):
    values = {**LOW_RISK, "severity": "SEV1", "customer_impact_count": 110}
    r = ask(completed_store, "Assess severity for this incident", values)
    assert r.completion_status == "awaiting_human"
    assert r.severity_assessment.proposed_severity == "SEV2"
    assert r.severity_assessment.reported_severity == "SEV1"
    assert {"POL-INC-001:s02:c01", "POL-INC-001:s03:c01"} <= set(r.severity_assessment.evidence_ids)


def test_conflicting_impact_facts_trigger_review(completed_store):
    r = ask(
        completed_store,
        "Investigate INC-001",
        {"customer_impact_count": 10, "downtime_minutes": 12},
    )
    assert r.completion_status == "awaiting_human"
    assert any(
        g.requirement_id == "context:customer_impact_count_conflict"
        for g in r.verification_result.gaps
    )
    assert any(
        g.requirement_id == "context:downtime_minutes_conflict" for g in r.verification_result.gaps
    )
    a = r.severity_assessment
    assert a.proposed_severity == "SEV1"
    assert any(
        o.field == "customer_impact_count" and o.value == 10 and o.origin == "user_reported"
        for o in a.context_observations
    )
    assert any(
        o.field == "customer_impact_count" and o.value == 620 and o.origin == "incident_snapshot"
        for o in a.context_observations
    )


def test_negated_or_uncertain_prose_does_not_supply_severity_facts():
    from opspilot.investigation.context import parse_context

    context = parse_context(
        "Assess severity for this payment outage. It is not customer-facing. "
        "It does not affect 500 customers. It may have been down for 35 minutes.",
        {},
    )
    assert context["category"] == "payment_failure"
    assert not {"customer_facing", "customer_impact_count", "downtime_minutes"} & context.keys()
