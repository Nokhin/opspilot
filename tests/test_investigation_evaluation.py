"""Independent V2 report contracts, frozen reference failures and offline gates."""

from pathlib import Path

import pytest

from opspilot.evaluation.investigation import (
    InvestigationCase,
    grade_investigation,
    load_investigation_cases,
    run_investigation_evaluation,
)
from opspilot.investigation.models import InvestigationRequest
from opspilot.investigation.service import InvestigationService


def test_development_suite_and_preserved_reports(service, tmp_path):
    cases = Path("opspilot/evaluation/investigation_dev.json")
    output = tmp_path / "report"
    summary = run_investigation_evaluation(service, cases, output, split="development")
    # Keep the original case labels and report the intentional behavior change:
    # the non-explicit customer-facing scenario now pauses for clarification.
    assert summary["cases"] == 22
    assert summary["passed"] == 21
    assert summary["failure_ids"] == ["mixed_comparison"]
    assert summary["input_tokens"] == summary["paid_inference_calls"] == 0
    assert summary["common_v1_tasks"] == 9
    assert (output / "progress.jsonl").is_file()
    assert "owner_token" not in (output / "results.json").read_text()
    with pytest.raises(ValueError, match="new output"):
        run_investigation_evaluation(service, cases, output, split="development")


def test_v2_grader_rejects_invented_source_and_wrong_number(service):
    store = InvestigationService(service)
    try:
        r = store.create(InvestigationRequest(user_request="Show INC-001"))
        chunks = {c["chunk_id"]: c for c in service.store.snapshot()["chunks"]}
        case = InvestigationCase(
            id="bad",
            category="data",
            request={"user_request": "Show INC-001"},
            expected_status="completed",
            expected_route="data_only",
            expected_text=["9999 minutes"],
        )
        assert not grade_investigation(case, r, chunks)["checks"]["frozen_reference_points"]
        p = store.create(
            InvestigationRequest(user_request="What escalation policy applies to SEV1?")
        )
        p.investigation_brief.source_citations[0].title = "Invented"
        assert not grade_investigation(case, p, chunks)["checks"]["citation_integrity"]
    finally:
        store.close()


def test_reserved_ids_are_disjoint_and_live_runner_is_rejected(service, tmp_path):
    dev = load_investigation_cases(Path("opspilot/evaluation/investigation_dev.json"))
    reserved = load_investigation_cases(Path("opspilot/evaluation/investigation_heldout.json"))
    assert not {c.id for c in dev} & {c.id for c in reserved}
    service.provider = object()
    with pytest.raises(ValueError, match="offline"):
        run_investigation_evaluation(
            service,
            Path("opspilot/evaluation/investigation_dev.json"),
            tmp_path,
            split="development",
        )


def test_completion_development_protocol_and_frozen_reserved(service, tmp_path):
    import hashlib
    import json

    base = Path("opspilot/evaluation")
    manifest = json.loads(Path("evaluation/v2_completion_6_7/PREREGISTRATION.json").read_text())
    for filename, expected in manifest["cases_sha256"].items():
        assert hashlib.sha256((base / filename).read_bytes()).hexdigest() == expected
    groups = [
        load_investigation_cases(base / filename)
        for filename in (
            "investigation_dev.json",
            "investigation_heldout.json",
            "investigation_completion_dev.json",
            "investigation_completion_reserved.json",
        )
    ]
    assert len(set().union(*(set(c.id for c in group) for group in groups))) == sum(
        map(len, groups)
    )
    assert len(groups[2]) == 28 and len(groups[3]) == 16
    # Only development is executed in the tuning test. Reserved cases remain a separate command.
    summary = run_investigation_evaluation(
        service,
        base / "investigation_completion_dev.json",
        tmp_path / "completion",
        split="completion-development",
    )
    assert summary["passed"] == summary["cases"] == 28
    assert summary["expectation_coverage"]["proposed_severity"]["evaluated"] < 28
    assert summary["expectation_coverage"]["action_contract"]["evaluated"] > 0
    assert summary["input_tokens"] == summary["output_tokens"] == 0


@pytest.mark.parametrize(
    "mutation,check",
    [
        ("severity", "proposed_severity"),
        ("owner", "action_contract"),
        ("deadline", "action_contract"),
        ("clock", "clock_integrity"),
        ("dimension", "dimension_coverage"),
        ("provenance", "context_provenance"),
        ("citation", "recommendation_citations"),
        ("interrupt", "interrupt_sequence"),
    ],
)
def test_completion_grader_detects_semantic_contract_failures(service, mutation, check):
    from datetime import UTC, datetime

    from opspilot.evaluation.investigation import ActionExpectation
    from opspilot.investigation.models import ContextObservation

    store = InvestigationService(service)
    try:
        r = store.create(InvestigationRequest(user_request="Investigate INC-001"))
        case = InvestigationCase(
            id="negative-completion",
            category="negative",
            request={"user_request": "Investigate INC-001"},
            expected_status="completed",
            expected_route="mixed",
            expected_severity="SEV1",
            expected_dimensions=["policy:classification:thresholds"],
            no_absolute_deadlines=True,
            expected_observations=[
                ContextObservation(
                    field="customer_impact_count", value=620, origin="incident_snapshot"
                )
            ],
            expected_actions=[
                ActionExpectation(
                    text_contains="notification to Operations Duty Manager",
                    owner_contains="Responsible employee",
                    deadline_minutes=5,
                )
            ],
            expected_interrupts=[],
        )
        chunks = {c["chunk_id"]: c for c in service.store.snapshot()["chunks"]}
        assert grade_investigation(case, r, chunks)["passed"]
        action = next(
            a
            for a in r.investigation_brief.recommended_next_steps
            if "notification to Operations Duty Manager" in a.text
        )
        if mutation == "severity":
            r.severity_assessment.proposed_severity = "SEV4"
        elif mutation == "owner":
            action.owner_role = "Invented autonomous executor"
        elif mutation == "deadline":
            action.deadline_minutes = 120
        elif mutation == "clock":
            action.due_at = datetime(2026, 9, 29, 10, 5, tzinfo=UTC)
        elif mutation == "dimension":
            r.verification_result.dimension_coverage = []
        elif mutation == "provenance":
            r.severity_assessment.context_observations = [
                o
                for o in r.severity_assessment.context_observations
                if o.field != "customer_impact_count"
            ]
        elif mutation == "citation":
            action.evidence_ids = ["fabricated"]
        kwargs = {"interrupts": ["clarify"]} if mutation == "interrupt" else {}
        graded = grade_investigation(case, r, chunks, **kwargs)
        assert not graded["passed"] and not graded["checks"][check]
    finally:
        store.close()
