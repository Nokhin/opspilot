"""Policy-derived development checks for communication ownership and review timetables."""

import copy
from pathlib import Path

import pytest

from opspilot.domain.models import GetIncidentArgs, PolicyHit, SimilarIncidentArgs
from opspilot.evaluation.investigation import run_investigation_evaluation
from opspilot.investigation.evidence import applicable
from opspilot.investigation.models import InvestigationRequest
from opspilot.investigation.service import InvestigationService


@pytest.fixture
def store(service):
    with_store = InvestigationService(service)
    yield with_store
    with_store.close()


def ask(store, query):
    return store.create(InvestigationRequest(user_request=query))


def test_new_development_cases(service, tmp_path):
    path = Path("opspilot/evaluation/investigation_evidence_gaps_dev.json")
    result = run_investigation_evaluation(service, path, tmp_path / "report", split="development")
    assert result["passed"] == result["cases"] == 8, result["failure_ids"]


@pytest.mark.parametrize("band", ["SEV2", "SEV3", "SEV4"])
@pytest.mark.parametrize("section", [1, 2])
def test_review_general_rules_remain_applicable_but_content_changes_fail_closed(
    service, band, section
):
    chunk = next(
        c
        for c in service.store.snapshot()["chunks"]
        if c["chunk_id"] == f"POL-REV-001:s0{section}:c01"
    )
    hit = PolicyHit(chunk=chunk, score=0.5)
    assert applicable(hit, band)
    modified = hit.model_copy(deep=True)
    modified.chunk.content += " This content has not been reviewed."
    assert not applicable(modified, band)


def test_severity_specific_escalation_remains_excluded(service):
    chunk = next(
        c for c in service.store.snapshot()["chunks"] if c["chunk_id"] == "POL-INC-002:s02:c01"
    )
    assert applicable(PolicyHit(chunk=chunk, score=0.5), "SEV1")
    assert not applicable(PolicyHit(chunk=chunk, score=0.5), "SEV2")


def test_retry_recovers_missing_ownership_without_relaxing_coverage(store, service, monkeypatch):
    original = service.tools.search_internal_policy
    calls = []

    def first_missing(args):
        calls.append(args.model_dump(mode="json"))
        result = original(args)
        if len(calls) == 1:
            result.hits = [
                h
                for h in result.hits
                if h.chunk.chunk_id not in {"POL-COM-001:s01:c01", "POL-INC-002:s03:c01"}
            ]
        return result

    monkeypatch.setattr(service.tools, "search_internal_policy", first_missing)
    r = ask(store, "For SEV2, give escalation notifications and customer communication cadence.")
    assert r.completion_status == "completed" and r.retry_count == 1 and len(calls) == 2
    assert calls[0] != calls[1]
    assert "Customer Communication Standard" in calls[1]["query"]
    assert "Communication ownership" in calls[1]["query"]
    assert not calls[1]["query"].endswith("SEV2")
    coverage = next(
        d
        for d in r.verification_result.dimension_coverage
        if d.dimension_id == "policy:communication:timing"
    )
    assert coverage.status == "supported" and not coverage.missing_sections
    assert "POL-COM-001:s01:c01" in coverage.evidence_ids
    action = next(
        a for a in r.investigation_brief.recommended_next_steps if "first customer notice" in a.text
    )
    assert action.owner_role == "Customer Service Lead" and action.deadline_minutes == 30
    assert action.status == "proposed_not_executed"


def test_missing_ownership_still_blocks_completion(store, service, monkeypatch):
    original = service.tools.search_internal_policy

    def always_missing(args):
        result = original(args)
        result.hits = [h for h in result.hits if h.chunk.chunk_id != "POL-COM-001:s01:c01"]
        return result

    monkeypatch.setattr(service.tools, "search_internal_policy", always_missing)
    r = ask(store, "What are the SEV2 first customer notice and update frequency requirements?")
    assert r.completion_status == "partial" and r.retry_count == 1
    assert any(d.missing_sections == [1] for d in r.verification_result.dimension_coverage)
    assert not any(
        "prepare the first customer notice" in a.text
        for a in r.investigation_brief.recommended_next_steps
    )


@pytest.mark.parametrize("resolved", [True, False])
def test_review_calendar_requires_resolution_and_never_uses_opened_at(store, service, resolved):
    if resolved:
        incident = service.tools.get_incident(GetIncidentArgs(incident_id="INC-001")).incident
        assert incident.resolved_at is not None
    else:
        incident = service.tools.find_similar_incidents(
            SimilarIncidentArgs(status="open", limit=1)
        ).incidents[0]
        assert incident.resolved_at is None
    r = ask(
        store,
        f"What exact calendar date is the post-incident review due for {incident.incident_id}?",
    )
    assert r.completion_status == "partial"
    gaps = {g.requirement_id for g in r.verification_result.gaps}
    assert "input:holiday_calendar" in gaps
    assert ("input:resolution_time" in gaps) is not resolved
    assert all(a.due_at is None for a in r.investigation_brief.recommended_next_steps)
    refs = {e.evidence_id for e in r.investigation_brief.source_citations}
    assert {"POL-REV-001:s01:c01", "POL-REV-001:s02:c01"} <= refs


def test_review_relative_action_tampering_still_fails_authoritative_verifier(store):
    r = ask(store, "Which date is the SEV2 post-incident review due?")
    assert r.completion_status == "partial"
    workflow = store.workflows["offline"]
    state = copy.deepcopy(workflow.graph.get_state(store.config(r.investigation_id)).values)
    action = next(a for a in state["proposed_actions"] if "business days" in a["text"])
    action["due_at"] = "2026-10-08T00:00:00Z"
    verified = workflow.verifier.invoke(state)
    assert verified.integrity_errors and not verified.sufficient


def test_review_timetable_is_not_supported_by_criteria_citation_alone(store, service, monkeypatch):
    original = service.tools.search_internal_policy

    def no_timetable(args):
        result = original(args)
        result.hits = [h for h in result.hits if h.chunk.chunk_id != "POL-REV-001:s02:c01"]
        return result

    monkeypatch.setattr(service.tools, "search_internal_policy", no_timetable)
    r = ask(store, "Which date is the SEV2 post-incident review due?")
    assert r.completion_status == "partial" and r.retry_count == 1
    assert any(
        d.dimension_id == "policy:review:timetable" and d.status == "missing"
        for d in r.verification_result.dimension_coverage
    )
    assert not any(
        "schedule it within" in a.text for a in r.investigation_brief.recommended_next_steps
    )
