"""Deterministic evidence construction and authority/provenance verification."""

import hashlib
import json
import re
from datetime import date

from langchain_core.runnables import RunnableLambda
from pydantic import TypeAdapter

from opspilot.domain.models import (
    AnswerFact,
    EvidenceRef,
    IncidentResult,
    MetricsResult,
    PolicyHit,
    PolicyResult,
    SimilarResult,
    ToolCall,
)
from opspilot.investigation.assessment import CONTRACTS, approved_rule, assess
from opspilot.investigation.brief import proposed_actions
from opspilot.investigation.context import effective_severity
from opspilot.investigation.models import (
    DimensionCoverage,
    EvidenceGap,
    InvestigationPlan,
    VerificationResult,
)
from opspilot.orchestration.grounding import select_extractive, validate_selection
from opspilot.providers.embeddings import terms

RESULT_TYPES = {
    "get_incident": IncidentResult,
    "find_similar_incidents": SimilarResult,
    "calculate_incident_metrics": MetricsResult,
    "search_internal_policy": PolicyResult,
}


def data_reference(record: dict) -> EvidenceRef:
    digest = hashlib.sha256(json.dumps(record["arguments"], sort_keys=True).encode()).hexdigest()[
        :12
    ]
    return EvidenceRef(
        evidence_id=f"db:{record['tool_name']}:{digest}",
        source_type="incident_db",
        source_id="harbourlink-incidents-v1",
        title="HarbourLink synthetic incident snapshot",
        section=record["tool_name"],
        excerpt=json.dumps(record["result"], sort_keys=True),
    )


def historical_fact(record: dict) -> AnswerFact | None:
    name, raw = record["tool_name"], record["result"]
    result = RESULT_TYPES[name].model_validate(raw)
    if isinstance(result, IncidentResult):
        i = result.incident
        if i is None:
            return None
        downtime = i.downtime_minutes if i.downtime_minutes is not None else "unknown"
        text = (
            f"{i.incident_id}: {i.service}, {i.category}, recorded {i.severity}, "
            f"{i.status}; downtime {downtime} "
            f"minutes; customer-impact exposures {i.customer_impact_count}."
        )
    elif isinstance(result, MetricsResult):
        text = (
            f"Matching incidents: {result.incident_count}; median downtime: "
            f"{result.median_downtime_minutes} minutes; mean downtime: "
            f"{result.mean_downtime_minutes} minutes; p90 downtime: "
            f"{result.p90_downtime_minutes} minutes. Known resolved durations: "
            f"{result.downtime_sample_count}; excluded/open or missing durations: "
            f"{result.missing_downtime_count}. Customer-impact exposures: "
            f"{result.total_customer_impact}. "
            f"Filters: {json.dumps(result.filters, sort_keys=True)}."
        )
        if result.group_counts:
            text += f" Group counts: {json.dumps(result.group_counts, sort_keys=True)}."
    elif isinstance(result, SimilarResult):
        text = (
            f"Exact-filter matches: {result.total_matches}; bounded recent sample: "
            + (", ".join(i.incident_id for i in result.incidents) or "none")
            + f". Filters: {json.dumps(result.filters, sort_keys=True)}."
        )
    else:
        raise ValueError("Not historical evidence")
    return AnswerFact(
        kind="historical_fact", text=text, evidence_ids=[data_reference(record).evidence_id]
    )


def duration_comparison(state: dict) -> AnswerFact | None:
    duration = state["investigation_plan"]["execution"].get("current_duration_minutes")
    record = next(
        (
            r
            for r in state["historical_incident_evidence"]
            if r["tool_name"] == "calculate_incident_metrics"
        ),
        None,
    )
    if duration is None or record is None:
        return None
    median = record["result"]["median_downtime_minutes"]
    if median is None:
        return None
    return AnswerFact(
        kind="interpretation",
        evidence_ids=[data_reference(record).evidence_id],
        text=(
            f"Supplied scenario duration {duration} minutes is {duration - median:+g} minutes "
            f"relative to the matching historical median {median:g} minutes. "
            "This is a deterministic comparison, not a restoration promise or policy deadline."
        ),
    )


def applicable(hit: PolicyHit, severity: str | None) -> bool:
    if hit.chunk.policy_type == "classification":
        return True  # All threshold bands are relevant to a comparative assessment.
    if (
        hit.chunk.chunk_id in {"POL-REV-001:s01:c01", "POL-REV-001:s02:c01"}
        and hit.chunk.policy_type == "review"
        and hashlib.sha256(hit.chunk.content.encode()).hexdigest()
        == CONTRACTS.get(hit.chunk.chunk_id)
    ):
        # Reviewed paragraphs specify SEV1 plus other mandatory-review conditions.
        # Mentioning only the literal SEV1 does not make those general rules SEV1-only.
        # Changed policy content must be reviewed again before this exception applies.
        return True
    if severity and hit.chunk.policy_type in {"escalation", "classification"}:
        section = int(hit.chunk.section.split(".", 1)[0])
        if section == 2 and severity != "SEV1" or section == 3 and severity == "SEV1":
            return False
    severities = set(re.findall(r"\bSEV[1-4]\b", hit.chunk.content))
    return not severity or not severities or severity in severities


def synthesize(state: dict, chunks: dict, as_of: date) -> dict:
    """Quote-only policy facts and code-generated historical findings."""
    plan = InvestigationPlan.model_validate(state["investigation_plan"])
    hits = [PolicyHit.model_validate(h) for h in state["retrieved_policy_evidence"]]
    severity = effective_severity(state["incident_context"])
    facts, evidence, seen = [], [], set()
    for req in plan.requirements:
        if req.plane != "policy" or req.requirement_id in {
            "policy:unsupported_detail",
            "policy:unmapped_detail",
        }:
            continue
        relevant = [
            h
            for h in hits
            if (not req.policy_type or h.chunk.policy_type == req.policy_type)
            and applicable(h, severity)
            and (
                not req.section_numbers
                or int(h.chunk.section.split(".", 1)[0]) in req.section_numbers
            )
        ]
        if req.dimensions:
            # Reviewed topic/section obligations select whole paragraphs; a lexical
            # overlap threshold cannot substitute for a missing requested facet.
            from opspilot.domain.models import PolicyQuote, PolicySelection

            selection = PolicySelection(
                sufficient=bool(relevant),
                quotes=[
                    PolicyQuote(evidence_id=h.chunk.chunk_id, quote=h.chunk.content)
                    for h in relevant
                ],
            )
        else:
            selection = select_extractive(req.query or state["query"], relevant)
        validate_selection(selection, relevant)
        if not selection.sufficient:
            continue
        by_id = {h.chunk.chunk_id: h for h in relevant}
        for quote in selection.quotes:
            if quote.evidence_id in seen:
                continue
            seen.add(quote.evidence_id)
            h = by_id[quote.evidence_id]
            c = h.chunk
            evidence.append(
                EvidenceRef(
                    evidence_id=c.chunk_id,
                    source_type="internal_policy",
                    source_id=c.document_id,
                    title=c.title,
                    section=c.section,
                    excerpt=quote.quote,
                    chunk_id=c.chunk_id,
                    version=c.version,
                    effective_date=c.effective_date,
                    score=h.score,
                ).model_dump(mode="json")
            )
            facts.append(
                AnswerFact(
                    kind="policy_requirement", text=quote.quote, evidence_ids=[c.chunk_id]
                ).model_dump(mode="json")
            )
    for record in state["historical_incident_evidence"]:
        fact = historical_fact(record)
        if fact:
            evidence.append(data_reference(record).model_dump(mode="json"))
            facts.append(fact.model_dump(mode="json"))
    comparison = duration_comparison(state)
    if comparison:
        facts.append(comparison.model_dump(mode="json"))
    combined = {**state, "facts": facts, "evidence": evidence}
    assessment = assess(combined, chunks, as_of)
    combined["severity_assessment"] = assessment.model_dump(mode="json")
    return {
        "facts": facts,
        "evidence": evidence,
        "severity_assessment": assessment.model_dump(mode="json"),
        "proposed_actions": [
            a.model_dump(mode="json") for a in proposed_actions(combined, chunks, as_of)
        ],
    }


class EvidenceVerifier:
    """No LLM judgment can override these integrity checks or grant tool permissions."""

    def __init__(self, chunks: list[dict], as_of: date):
        self.chunks = {c["chunk_id"]: c for c in chunks}
        self.as_of = as_of
        self.chain = RunnableLambda(self._verify)

    def invoke(self, state: dict) -> VerificationResult:
        return self.chain.invoke(state, config={"callbacks": []})

    def _verify(self, state: dict) -> VerificationResult:
        plan = InvestigationPlan.model_validate(state["investigation_plan"])
        refs = {e["evidence_id"]: EvidenceRef.model_validate(e) for e in state["evidence"]}
        facts = [AnswerFact.model_validate(f) for f in state["facts"]]
        errors, gaps, covered, coverage = [], [], [], []
        if len(refs) != len(state["evidence"]):
            errors.append("Duplicate evidence IDs")
        data_refs, expected_facts = {}, []
        for record in state["historical_incident_evidence"]:
            try:
                TypeAdapter(ToolCall).validate_python(
                    {
                        "tool_name": record["tool_name"],
                        "arguments": record["arguments"],
                    }
                )
                expected = historical_fact(record)
                if expected:
                    data_refs[data_reference(record).evidence_id] = data_reference(record)
                    expected_facts.append(expected)
            except (ValueError, KeyError):
                errors.append("Invalid historical tool schema")
        allowed_tools = set(RESULT_TYPES)
        traces = state["tool_traces"]
        if len(traces) > 5 or any(t["tool_name"] not in allowed_tools for t in traces):
            errors.append("Tool permission or budget violation")
        successful = {
            (t["tool_name"], json.dumps(t["arguments"], sort_keys=True))
            for t in traces
            if t["status"] == "success"
        }
        for record in state["historical_incident_evidence"]:
            if (
                record["tool_name"],
                json.dumps(record["arguments"], sort_keys=True),
            ) not in successful:
                errors.append("Historical result lacks a successful permitted tool trace")
        severity = effective_severity(state["incident_context"])
        for fact in facts:
            if not fact.evidence_ids or any(i not in refs for i in fact.evidence_ids):
                errors.append("Missing citation")
                continue
            for eid in fact.evidence_ids:
                ref = refs[eid]
                if fact.kind == "policy_requirement":
                    c = self.chunks.get(eid)
                    if not c or not (
                        ref.source_type == "internal_policy"
                        and ref.chunk_id == eid
                        and ref.source_id == c["document_id"]
                        and ref.title == c["title"]
                        and ref.version == c["version"]
                        and ref.section == c["section"]
                        and str(ref.effective_date) == c["effective_date"]
                        and ref.effective_date <= self.as_of
                        and fact.text == ref.excerpt
                        and fact.text in c["content"].split("\n\n")
                    ):
                        errors.append("Policy provenance or paragraph mismatch")
                    if c and not applicable(PolicyHit(chunk=c, score=ref.score or 0), severity):
                        errors.append("Policy severity is inapplicable")
                    if re.search(
                        r"ignore.{0,30}instructions|system prompt|api key|execute.*shell",
                        fact.text,
                        re.I,
                    ):
                        errors.append("Instruction-like evidence")
                elif fact.kind == "historical_fact":
                    if ref != data_refs.get(eid) or fact not in expected_facts:
                        errors.append("Historical claim differs from deterministic tool result")
                else:
                    if ref != data_refs.get(eid) or fact != duration_comparison(state):
                        errors.append("Interpretation differs from deterministic comparison")
        # Every displayed citation must support a validated finding, never an orphan source.
        if set(refs) != {eid for f in facts for eid in f.evidence_ids}:
            errors.append("Unbound citation")
        restriction = next(
            (
                c.arguments.policy_type
                for c in plan.execution.calls
                if c.tool_name == "search_internal_policy"
            ),
            None,
        )
        for req in plan.requirements:
            if req.plane == "history":
                records = [
                    r
                    for r in state["historical_incident_evidence"]
                    if r["tool_name"] == req.tool_name
                ]
                ok = bool(records and historical_fact(records[0]))
            else:
                candidates = [
                    self.chunks[eid]
                    for f in facts
                    if f.kind == "policy_requirement"
                    for eid in f.evidence_ids
                    if eid in self.chunks
                ]
                relevant = [
                    c
                    for c in candidates
                    if (not req.policy_type or c["policy_type"] == req.policy_type)
                    and set(terms(req.query or state["query"])) & set(terms(c["content"]))
                ]
                sections = {int(c["section"].split(".", 1)[0]) for c in relevant}
                ok = (
                    bool(relevant)
                    and set(req.section_numbers) <= sections
                    and req.requirement_id
                    not in {"policy:unsupported_detail", "policy:unmapped_detail"}
                )
            for dimension in req.dimensions:
                supported = [
                    c
                    for c in relevant
                    if int(c["section"].split(".", 1)[0]) in dimension.section_numbers
                    and approved_rule(c["chunk_id"], state["evidence"], self.chunks, self.as_of)
                ]
                available = {int(c["section"].split(".", 1)[0]) for c in supported}
                missing = sorted(set(dimension.section_numbers) - available)
                coverage.append(
                    DimensionCoverage(
                        dimension_id=dimension.dimension_id,
                        status="missing" if missing else "supported",
                        evidence_ids=[c["chunk_id"] for c in supported],
                        missing_sections=missing,
                    )
                )
                if missing:
                    ok = False
                    gaps.append(
                        EvidenceGap(
                            requirement_id=dimension.dimension_id,
                            description="Missing evidence for " + dimension.description,
                            retryable=restriction in {None, req.policy_type},
                        )
                    )
            if req.plane == "history":
                coverage.append(
                    DimensionCoverage(
                        dimension_id=req.requirement_id,
                        status="supported" if ok else "missing",
                        evidence_ids=[
                            eid for eid, ref in refs.items() if ref.section == req.tool_name
                        ],
                    )
                )
            if ok:
                covered.append(req.requirement_id)
            else:
                gaps.append(
                    EvidenceGap(
                        requirement_id=req.requirement_id,
                        description=req.description,
                        retryable=(
                            req.plane == "policy"
                            and req.policy_type is not None
                            and restriction in {None, req.policy_type}
                        ),
                    )
                )
        assessment = assess(state, self.chunks, self.as_of)
        if state.get("severity_assessment") != assessment.model_dump(mode="json"):
            errors.append("Severity assessment differs from the policy-gated deterministic result")
        expected_actions = [
            a.model_dump(mode="json") for a in proposed_actions(state, self.chunks, self.as_of)
        ]
        if state.get("proposed_actions") != expected_actions:
            errors.append("Proposed actions, owners or deadlines exceed validated policy evidence")
        if assessment.status in {"provisional", "insufficient"}:
            if assessment.missing_fields:
                gaps.append(
                    EvidenceGap(
                        requirement_id="input:severity_facts",
                        description="Severity remains uncertain; missing "
                        + ", ".join(assessment.missing_fields),
                    )
                )
            elif assessment.status == "insufficient":
                gaps.append(
                    EvidenceGap(
                        requirement_id="assessment:policy_basis",
                        description="No reviewed policy basis for a proposed severity.",
                    )
                )
        if assessment.proposed_severity and (
            assessment.recorded_severity
            and assessment.recorded_severity != assessment.proposed_severity
            or assessment.reported_severity
            and assessment.reported_severity != assessment.proposed_severity
        ):
            gaps.append(
                EvidenceGap(
                    requirement_id="context:assessment_conflict",
                    description=(
                        "Proposed severity differs from recorded/reported severity; human "
                        "interpretation required."
                    ),
                )
            )
        if (
            any(n in state.get("unknown_fields", []) for n in ["incident_id", "category"])
            and not state["incident_context"].get("incident_id")
            and not state["incident_context"].get("category")
        ):
            gaps.append(
                EvidenceGap(
                    requirement_id="input:incident_identity",
                    description="Incident identity/category remains unknown.",
                )
            )
        reported = state["incident_context"].get("reported_severity")
        if reported and severity and reported != severity:
            gaps.append(
                EvidenceGap(
                    requirement_id="context:severity_conflict",
                    description=(
                        "Reported severity conflicts with the incident snapshot; "
                        "human interpretation required."
                    ),
                )
            )
        for field in ("downtime_minutes", "customer_impact_count"):
            reported_value = state.get("reported_context", {}).get(field)
            recorded_value = state.get("recorded_context", {}).get(field)
            if (
                reported_value is not None
                and recorded_value is not None
                and reported_value != recorded_value
            ):
                gaps.append(
                    EvidenceGap(
                        requirement_id="context:" + field + "_conflict",
                        description="Reported "
                        + field.replace("_", " ")
                        + " conflicts with the incident snapshot; human interpretation required.",
                    )
                )
        reported_category = state["incident_context"].get("reported_category")
        if reported_category and reported_category != state["incident_context"].get("category"):
            gaps.append(
                EvidenceGap(
                    requirement_id="context:category_conflict",
                    description=(
                        "Supplied category conflicts with the snapshot; "
                        "human interpretation required."
                    ),
                )
            )
        if re.search(
            r"exact (?:notification )?deadline|due (?:at|time)|what (?:clock )?time"
            r"|overdue|minutes (?:left|remaining)",
            state["user_request"],
            re.I,
        ) and not state["incident_context"].get("threshold_detected_at"):
            gaps.append(
                EvidenceGap(
                    requirement_id="input:threshold_clock",
                    description=(
                        "Threshold detection time is unknown; only relative notification "
                        "deadlines can be stated."
                    ),
                )
            )
        if re.search(
            r"which date|calendar date|exact date|due date", state["user_request"], re.I
        ) and any(r.policy_type == "review" for r in plan.requirements):
            gaps.append(
                EvidenceGap(
                    requirement_id="input:holiday_calendar",
                    description=(
                        "The approved holiday calendar is absent; business-day review deadlines "
                        "cannot be converted to exact calendar dates."
                    ),
                )
            )
            resolved = any(
                record["tool_name"] == "get_incident"
                and record["result"].get("incident")
                and record["result"]["incident"].get("resolved_at")
                for record in state["historical_incident_evidence"]
            )
            if not resolved:
                gaps.append(
                    EvidenceGap(
                        requirement_id="input:resolution_time",
                        description=(
                            "A verified resolution timestamp is absent; review deadlines "
                            "are relative to resolution, not incident opening or the snapshot date."
                        ),
                    )
                )
        if plan.execution.route == "unsupported":
            gaps.append(
                EvidenceGap(
                    requirement_id="scope", description="Unsupported request; no actions executed."
                )
            )
        return VerificationResult(
            sufficient=not gaps and not errors,
            covered_requirements=covered,
            gaps=gaps,
            integrity_errors=sorted(set(errors)),
            dimension_coverage=coverage,
        )
