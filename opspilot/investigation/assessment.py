"""Policy-gated severity decisions and explicit context provenance."""

import hashlib
import json
from datetime import date
from importlib.resources import files

from opspilot.investigation.context import needs_assessment, severity_candidate
from opspilot.investigation.models import ContextObservation, SeverityAssessment

CONTRACTS = json.loads(
    files("opspilot.investigation").joinpath("policy_contracts.json").read_text()
)


def approved_rule(evidence_id: str, evidence: list[dict], chunks: dict, as_of: date) -> bool:
    c = chunks.get(evidence_id)
    ref = next((e for e in evidence if e["evidence_id"] == evidence_id), None)
    return bool(
        c
        and ref
        and c["version"] == "1.0"
        and date.fromisoformat(c["effective_date"]) <= as_of
        and c["status"] == "active"
        and hashlib.sha256(c["content"].encode()).hexdigest() == CONTRACTS.get(evidence_id)
        and ref["excerpt"] in c["content"].split("\n\n")
        and ref["source_type"] == "internal_policy"
        and ref["source_id"] == c["document_id"]
        and ref["section"] == c["section"]
        and ref["version"] == c["version"]
        and ref["title"] == c["title"]
    )


def observations(state: dict) -> list[ContextObservation]:
    result = []
    for field, value in state.get("reported_context", {}).items():
        result.append(ContextObservation(field=field, value=value, origin="user_reported"))
    db_refs = [
        e["evidence_id"]
        for e in state.get("evidence", [])
        if e["source_type"] == "incident_db" and e["section"] == "get_incident"
    ]
    for field, value in state.get("recorded_context", {}).items():
        result.append(
            ContextObservation(
                field=field, value=value, origin="incident_snapshot", evidence_ids=db_refs
            )
        )
    for field in state.get("unknown_fields", []):
        result.append(ContextObservation(field=field, value=None, origin="user_reported"))
    return result


def assess(state: dict, chunks: dict, as_of: date) -> SeverityAssessment:
    context = state["incident_context"]
    recorded = state.get("recorded_context", {}).get("severity")
    reported = state.get("reported_context", {}).get("severity")
    common = {
        "recorded_severity": recorded,
        "reported_severity": reported,
        "context_observations": observations(state),
    }
    if state.get("route") == "unsupported" or not needs_assessment(state["user_request"], context):
        return SeverityAssessment(status="not_requested", **common)
    candidate, reasons, missing = severity_candidate(context)
    if not context.get("category") and not context.get("incident_id"):
        missing = ["category", *missing]
    required = ["POL-INC-001:s02:c01"]
    if candidate != "SEV1":
        required.append("POL-INC-001:s03:c01")
    allowed = [
        eid for eid in required if approved_rule(eid, state.get("evidence", []), chunks, as_of)
    ]
    limits = [
        "Proposed assessment only; a human confirms classification. No incident state changed."
    ]
    if recorded:
        limits.append(
            "Current policy is applied retrospectively to snapshot facts; this does "
            "not prove historical compliance or that the recorded severity was "
            "wrong."
        )
    if len(allowed) != len(required):
        return SeverityAssessment(
            status="insufficient",
            missing_fields=missing,
            basis=[
                (
                    "The retrieved/selected policy does not support the reviewed severity "
                    "rule contract."
                )
            ],
            evidence_ids=allowed,
            limitations=limits,
            **common,
        )
    if candidate is None:
        return SeverityAssessment(
            status="insufficient",
            missing_fields=missing,
            basis=[
                (
                    "Known facts do not establish a classification; unknown values were not "
                    "treated as zero/false."
                )
            ],
            evidence_ids=allowed,
            limitations=limits,
            **common,
        )
    return SeverityAssessment(
        proposed_severity=candidate,
        status="provisional" if missing else "supported",
        basis=reasons,
        evidence_ids=allowed,
        missing_fields=missing,
        limitations=limits,
        **common,
    )
