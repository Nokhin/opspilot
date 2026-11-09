"""Separate offline V2 development/reserved suites with explicit fault injection."""

import hashlib
import json
import statistics
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import Field, TypeAdapter

from opspilot.domain.models import Contract, PolicyResult
from opspilot.investigation.models import (
    Completion,
    ContextObservation,
    InvestigationRequest,
    ResumeRequest,
)
from opspilot.investigation.service import InvestigationService


class ActionExpectation(Contract):
    text_contains: str
    owner_contains: str | None = None
    deadline_minutes: int | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    retrospective: bool | None = None


class InvestigationCase(Contract):
    id: str
    category: str
    request: InvestigationRequest
    expected_status: Completion
    expected_route: str
    expected_requirements: list[str] = Field(default_factory=list)
    expected_chunks: list[str] = Field(default_factory=list)
    expected_text: list[str] = Field(default_factory=list)
    expected_retry_count: int | None = None
    max_tools: int = Field(default=5, ge=0, le=5)
    responses: list[ResumeRequest] = Field(default_factory=list, max_length=2)
    restart_before_resume: bool = False
    fault: Literal[
        "none",
        "first_policy_empty",
        "all_policy_empty",
        "no_communication",
        "data_unavailable",
        "no_escalation_content",
    ] = "none"
    common_v1: bool = False
    expected_severity: Literal["SEV1", "SEV2", "SEV3", "SEV4", "none"] | None = None
    expected_assessment: str | None = None
    expected_recorded_severity: str | None = None
    expected_reported_severity: str | None = None
    expected_dimensions: list[str] = Field(default_factory=list)
    expected_missing_dimensions: list[str] = Field(default_factory=list)
    expected_gaps: list[str] = Field(default_factory=list)
    expected_observations: list[ContextObservation] = Field(default_factory=list)
    expected_actions: list[ActionExpectation] = Field(default_factory=list)
    forbidden_action_text: list[str] = Field(default_factory=list)
    no_absolute_deadlines: bool = False
    expected_interrupts: list[Literal["clarify", "review"]] | None = None


def load_investigation_cases(path: Path):
    cases = TypeAdapter(list[InvestigationCase]).validate_json(path.read_bytes())
    if not cases or len({c.id for c in cases}) != len(cases):
        raise ValueError("Investigation cases require unique IDs")
    if any(c.request.mode != "offline" for c in cases):
        raise ValueError("This runner is offline only")
    return cases


def grade_investigation(case, response, chunks, *, interrupts=(), subscription=False):
    brief = response.investigation_brief
    refs = {e.evidence_id: e for e in brief.source_citations} if brief else {}
    facts = brief.key_findings if brief else []
    integrity = True
    for fact in facts:
        if not fact.evidence_ids or not set(fact.evidence_ids) <= set(refs):
            integrity = False
            continue
        for eid in fact.evidence_ids:
            ref = refs[eid]
            if fact.kind == "policy_requirement":
                c = chunks.get(eid)
                integrity &= bool(
                    c
                    and ref.source_type == "internal_policy"
                    and fact.text in c["content"].split("\n\n")
                    and fact.text == ref.excerpt
                    and ref.source_id == c["document_id"]
                    and ref.section == c["section"]
                    and ref.title == c["title"]
                    and ref.version == c["version"]
                )
            else:
                integrity &= ref.source_type == "incident_db"
    covered = (
        response.verification_result.covered_requirements if response.verification_result else []
    )
    checks = {
        "status": response.completion_status == case.expected_status,
        "route": response.route == case.expected_route,
        "required_dimensions": set(case.expected_requirements) <= set(covered),
        "required_citations": set(case.expected_chunks) <= set(refs),
        "citation_integrity": bool(integrity),
        "frozen_reference_points": all(
            t in "\n".join(f.text for f in facts) for t in case.expected_text
        ),
        "tool_efficiency": len(response.tool_traces) <= case.max_tools,
        "retry": case.expected_retry_count is None
        or response.retry_count == case.expected_retry_count,
        "read_only": all(
            t.tool_name
            in {
                "search_internal_policy",
                "get_incident",
                "find_similar_incidents",
                "calculate_incident_metrics",
            }
            for t in response.tool_traces
        ),
        "human_completion": response.completion_status != "awaiting_human"
        if case.responses
        else True,
        **(
            {"subscription": response.mode == "chatgpt_subscription"}
            if subscription
            else {
                "offline": response.usage.input_tokens == response.usage.output_tokens == 0,
            }
        ),
        "proposed_actions_only": all(
            a.status == "proposed_not_executed" for a in brief.recommended_next_steps
        )
        if brief
        else True,
        "no_integrity_errors": not response.verification_result.integrity_errors
        if response.verification_result
        else response.completion_status == "awaiting_human" and not facts,
    }
    assessment = response.severity_assessment
    actions = brief.recommended_next_steps if brief else []
    coverage = (
        {c.dimension_id: c for c in response.verification_result.dimension_coverage}
        if response.verification_result
        else {}
    )
    gaps = (
        {g.requirement_id for g in response.verification_result.gaps}
        if response.verification_result
        else set()
    )
    checks.update(
        {
            "proposed_severity": case.expected_severity is None
            or (
                assessment is not None
                and assessment.proposed_severity
                == (None if case.expected_severity == "none" else case.expected_severity)
            ),
            "assessment_status": case.expected_assessment is None
            or (assessment is not None and assessment.status == case.expected_assessment),
            "recorded_severity": case.expected_recorded_severity is None
            or (
                assessment is not None
                and assessment.recorded_severity == case.expected_recorded_severity
            ),
            "reported_severity": case.expected_reported_severity is None
            or (
                assessment is not None
                and assessment.reported_severity == case.expected_reported_severity
            ),
            "dimension_coverage": all(
                name in coverage
                and coverage[name].status == "supported"
                and coverage[name].evidence_ids
                for name in case.expected_dimensions
            ),
            "missing_dimensions": all(
                name in coverage and coverage[name].status == "missing"
                for name in case.expected_missing_dimensions
            ),
            "explicit_gaps": set(case.expected_gaps) <= gaps,
            "context_provenance": all(
                assessment is not None
                and any(
                    actual.field == wanted.field
                    and actual.origin == wanted.origin
                    and type(actual.value) is type(wanted.value)
                    and actual.value == wanted.value
                    for actual in assessment.context_observations
                )
                for wanted in case.expected_observations
            ),
            "action_contract": all(
                any(
                    wanted.text_contains in actual.text
                    and (
                        wanted.owner_contains is None or wanted.owner_contains in actual.owner_role
                    )
                    and (
                        wanted.deadline_minutes is None
                        or wanted.deadline_minutes == actual.deadline_minutes
                    )
                    and set(wanted.evidence_ids) <= set(actual.evidence_ids)
                    and (
                        wanted.retrospective is None or wanted.retrospective == actual.retrospective
                    )
                    for actual in actions
                )
                for wanted in case.expected_actions
            ),
            "no_forbidden_recommendations": not any(
                text.lower() in a.text.lower()
                for text in case.forbidden_action_text
                for a in actions
            ),
            "clock_integrity": not case.no_absolute_deadlines
            or all(a.due_at is None for a in actions),
            "interrupt_sequence": case.expected_interrupts is None
            or list(interrupts) == case.expected_interrupts,
            "provider_budget": response.provider_call_count <= 1
            if subscription
            else response.provider_call_count == 0,
            "recommendation_citations": all(
                action.evidence_ids
                and set(action.evidence_ids) <= set(refs)
                and all(refs[eid].source_type == "internal_policy" for eid in action.evidence_ids)
                for action in actions
            ),
        }
    )
    optional = {
        "required_dimensions": bool(case.expected_requirements),
        "required_citations": bool(case.expected_chunks),
        "frozen_reference_points": bool(case.expected_text),
        "retry": case.expected_retry_count is not None,
        "human_completion": bool(case.responses),
        "proposed_actions_only": bool(actions),
        "recommendation_citations": bool(actions),
        "proposed_severity": case.expected_severity is not None,
        "assessment_status": case.expected_assessment is not None,
        "recorded_severity": case.expected_recorded_severity is not None,
        "reported_severity": case.expected_reported_severity is not None,
        "dimension_coverage": bool(case.expected_dimensions),
        "missing_dimensions": bool(case.expected_missing_dimensions),
        "explicit_gaps": bool(case.expected_gaps),
        "context_provenance": bool(case.expected_observations),
        "action_contract": bool(case.expected_actions),
        "no_forbidden_recommendations": bool(case.forbidden_action_text),
        "clock_integrity": case.no_absolute_deadlines,
        "interrupt_sequence": case.expected_interrupts is not None,
    }
    return {
        "id": case.id,
        "category": case.category,
        "passed": all(checks.values()),
        "checks": checks,
        "failures": [k for k, v in checks.items() if not v],
        "latency_ms": response.latency_ms,
        "tool_calls": len(response.tool_traces),
        "response": response.model_dump(mode="json", exclude={"owner_token"}),
        "interrupts": list(interrupts),
        "applicable_checks": [name for name in checks if optional.get(name, True)],
    }


def run_investigation_evaluation(service, cases_path: Path, output: Path, *, split: str):
    if service.provider is not None or service.settings.embedding_provider != "tfidf":
        raise ValueError("V2 offline evaluation requires extractive/local providers")
    cases = load_investigation_cases(cases_path)
    if output.exists() and any(output.iterdir()):
        raise ValueError("Use a new output directory; failed reports are preserved")
    output.mkdir(parents=True, exist_ok=True)
    chunks = {c["chunk_id"]: c for c in service.store.snapshot()["chunks"]}
    rows, comparisons = [], []
    store = InvestigationService(service)
    try:
        for case in cases:
            tools = service.tools
            search, get = tools.search_internal_policy, tools.get_incident
            attempts = 0

            def injected_search(args, case=case, search=search):
                nonlocal attempts
                attempts += 1
                if (
                    case.fault == "all_policy_empty"
                    or case.fault == "first_policy_empty"
                    and attempts == 1
                ):
                    return PolicyResult(hits=[])
                result = search(args)
                if case.fault == "no_communication":
                    result.hits = [h for h in result.hits if h.chunk.policy_type != "communication"]
                if case.fault == "no_escalation_content":
                    result.hits = [
                        h for h in result.hits if h.chunk.chunk_id != "POL-INC-002:s05:c01"
                    ]
                return result

            def unavailable(args):
                raise OSError("Injected evidence-source unavailability")

            tools.search_internal_policy = injected_search
            if case.fault == "data_unavailable":
                tools.get_incident = unavailable
            try:
                created = store.create(case.request)
                identifier, token = created.investigation_id, created.owner_token
                response = store.get(identifier, token)
                interrupts = []
                if response.clarification_request:
                    interrupts.append(response.clarification_request["kind"])
                for reply in case.responses:
                    if case.restart_before_resume:
                        store.close()
                        store = InvestigationService(service)
                    response = store.resume(identifier, token, reply)
                    if response.clarification_request:
                        interrupts.append(response.clarification_request["kind"])
                row = grade_investigation(case, response, chunks, interrupts=interrupts)
                rows.append(row)
                with (output / "progress.jsonl").open("a") as file:
                    file.write(json.dumps(row) + "\n")
            finally:
                tools.search_internal_policy, tools.get_incident = search, get
            if case.common_v1 and case.fault == "none":
                v1 = service.ask(case.request.user_request)
                comparisons.append(
                    {
                        "id": case.id,
                        "question": case.request.user_request,
                        "v1_route": v1.route,
                        "v2_route": response.route,
                        "v1_evidence_sufficiency": v1.evidence_sufficiency,
                        "v2_status": response.completion_status,
                        "v1_tools": len(v1.tool_trace),
                        "v2_tools": len(response.tool_traces),
                        "v1_latency_ms": v1.latency_ms,
                        "v2_latency_ms": response.latency_ms,
                        "v1_sources": sorted({e.source_id for e in v1.evidence}),
                        "v2_sources": sorted(
                            {
                                e.source_id
                                for e in (
                                    response.investigation_brief.source_citations
                                    if response.investigation_brief
                                    else []
                                )
                            }
                        ),
                        "v1_response": v1.model_dump(mode="json"),
                    }
                )
    finally:
        store.close()
    latencies = sorted(r["latency_ms"] for r in rows)
    summary = {
        "cases": len(cases),
        "executed": len(rows),
        "passed": sum(r["passed"] for r in rows),
        "failure_ids": [r["id"] for r in rows if not r["passed"]],
        "median_latency_ms": statistics.median(latencies),
        "max_latency_ms": max(latencies),
        "tool_calls": sum(r["tool_calls"] for r in rows),
        "input_tokens": 0,
        "output_tokens": 0,
        "paid_inference_calls": 0,
        "common_v1_tasks": len(comparisons),
        "checks_passed": {
            name: sum(bool(row["checks"][name]) for row in rows) for name in rows[0]["checks"]
        },
        "expectation_coverage": {
            name: {
                "evaluated": sum(name in row["applicable_checks"] for row in rows),
                "passed": sum(
                    name in row["applicable_checks"] and bool(row["checks"][name]) for row in rows
                ),
            }
            for name in rows[0]["checks"]
        },
    }
    report = {
        "manifest": {
            "split": split,
            "run_at_utc": datetime.now(UTC).isoformat(),
            "cases_sha256": hashlib.sha256(cases_path.read_bytes()).hexdigest(),
            "corpus_sha256": service.store.snapshot()["corpus_sha256"],
            "reference_time": service.settings.reference_time.isoformat(),
            "mode": "offline",
            "fault_injection_explicit": True,
            "investigation_source_sha256": {
                p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(Path("opspilot/investigation").glob("*"))
                if p.is_file() and p.suffix in {".py", ".json"}
            },
            "interpretation": (
                "Engineer-authored synthetic regression; "
                "reserved cases are not an independent benchmark."
            ),
        },
        "summary": summary,
        "cases": rows,
        "v1_common_tasks": comparisons,
    }
    (output / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    (output / "SUMMARY.md").write_text(
        f"# V2 {split} offline evaluation\n\n"
        f"{summary['passed']}/{summary['cases']} cases passed. "
        f"Failures: {', '.join(summary['failure_ids']) or 'none'}.\n\n"
        f"Median / maximum latency: {summary['median_latency_ms']:.2f} / "
        f"{summary['max_latency_ms']:.2f} ms. Tool calls: {summary['tool_calls']}.\n\n"
        f"Common V1 tasks: {len(comparisons)}. Zero paid inference calls. "
        "Offline latency excludes LLM/network time. Fault injection is labelled per case. "
        "These cases measure graph behavior and deterministic evidence controls, not "
        "production accuracy or independent semantic generalisation.\n"
    )
    return summary
