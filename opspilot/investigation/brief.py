"""Business-readable summaries and policy-gated proposed actions."""

from datetime import date, datetime, timedelta

from opspilot.investigation.assessment import approved_rule, observations
from opspilot.investigation.context import effective_severity
from opspilot.investigation.models import ProposedAction


def proposed_actions(state: dict, chunks: dict, as_of: date) -> list[ProposedAction]:
    evidence = state.get("evidence", [])
    context = state["incident_context"]
    severity = effective_severity(context)
    retrospective = state.get("recorded_context", {}).get("status") == "resolved"
    label = context.get("incident_id") or context.get(
        "category", "any incident meeting these policy conditions"
    ).replace("_", " ")
    actions = []

    def add(eids, owner, instruction, trigger, minutes=None, basis=None):
        if not all(approved_rule(eid, evidence, chunks, as_of) for eid in eids):
            return
        due = None
        if (
            minutes is not None
            and basis == "threshold detection"
            and context.get("threshold_detected_at")
        ):
            due = datetime.fromisoformat(context["threshold_detected_at"]) + timedelta(
                minutes=minutes
            )
        prefix = "Proposed retrospective review" if retrospective else "Proposed"
        action = ProposedAction(
            text=f"{prefix} for {label}: {instruction} Human confirmation required; not executed.",
            evidence_ids=eids,
            owner_role=owner,
            trigger=trigger,
            deadline_minutes=minutes,
            deadline_basis=basis,
            due_at=due,
            retrospective=retrospective,
        )
        if action not in actions:
            actions.append(action)

    classification = "POL-INC-001:s04:c01"
    add(
        [classification],
        "Operations Duty Manager",
        "review severity at discovery and whenever impact, duration or safety changes.",
        "Discovery or a change in classification facts",
    )
    if severity in {"SEV1", "SEV2"}:
        section = "POL-INC-002:s02:c01" if severity == "SEV1" else "POL-INC-002:s03:c01"
        clock = [section] if severity == "SEV1" else [section, "POL-INC-002:s01:c01"]
        for recipient, deadline in (
            [
                ("Operations Duty Manager and relevant recovery team", 5),
                ("Customer Service Lead", 10),
                ("Risk & Compliance", 15),
                ("Executive Duty Sponsor", 30),
            ]
            if severity == "SEV1"
            else [("Operations Duty Manager and recovery team", 15), ("Customer Service Lead", 30)]
        ):
            add(
                clock,
                "Responsible employee / incident coordinator",
                (
                    f"check or prepare the unsent notification to {recipient} within "
                    f"{deadline} minutes of threshold detection."
                ),
                f"If {severity} applies to this incident",
                deadline,
                "threshold detection",
            )
        if severity == "SEV2" and context.get("integrity_concern") is True:
            add(
                clock,
                "Responsible employee / incident coordinator",
                (
                    "include Risk & Compliance within 30 minutes when an integrity concern "
                    "is confirmed."
                ),
                "SEV2 with confirmed integrity concern",
                30,
                "threshold detection",
            )
    elif severity in {"SEV3", "SEV4"}:
        add(
            ["POL-INC-002:s03:c01"],
            "Assigned service owner",
            "manage the event during the operating shift and record handover if unresolved.",
            f"If {severity} applies",
        )
    add(
        ["POL-INC-002:s05:c01"],
        "Responsible employee",
        (
            "prepare an unsent escalation draft with incident ID, severity "
            "triggers, services/sites, discovery time, downtime, impact, recovery "
            "owner, current actions and next update time."
        ),
        "When an escalation notification is required",
    )
    if severity in {"SEV1", "SEV2"}:
        first, cadence = (15, 30) if severity == "SEV1" else (30, 60)
        add(
            ["POL-COM-001:s01:c01", "POL-COM-001:s02:c01"],
            "Customer Service Lead",
            (
                f"prepare the first customer notice within {first} minutes of threshold "
                f"detection; propose subsequent updates at least every {cadence} minutes "
                f"while impact continues."
            ),
            f"If {severity} customer impact applies and continues",
            first,
            "threshold detection",
        )
        observe = 30 if severity == "SEV1" else 15
        add(
            ["POL-REC-001:s02:c01"],
            "Recovery owner",
            (
                f"validate restoration and observe service for at least {observe} "
                f"minutes before recommending resolution."
            ),
            f"After restoration of a {severity} service",
            observe,
            "validated service restoration",
        )
        vendor = 10 if severity == "SEV1" else 30
        add(
            ["POL-VEN-001:s02:c01"],
            "Service owner",
            (
                f"prepare supplier contact within {vendor} minutes of threshold "
                f"detection using the approved supplier channel."
            ),
            f"Only if vendor involvement and {severity} are confirmed",
            vendor,
            "threshold detection",
        )
    add(
        ["POL-BCP-001:s02:c01"],
        "Operations Duty Manager",
        (
            "assess continuity immediately for unsafe sites/multi-site "
            "essential-service closure, or decide on the continuity plan when a "
            "customer-facing digital/payment outage reaches 60 minutes."
        ),
        "Only when the cited safety, closure or 60-minute outage condition applies",
    )
    if severity:
        schedule, draft = (2, 5) if severity == "SEV1" else (5, 10)
        add(
            ["POL-REV-001:s01:c01", "POL-REV-001:s02:c01"],
            "Incident coordinator",
            (
                f"if review is mandatory, schedule it within {schedule} business days of "
                f"resolution and publish the draft within {draft} business days. Confirm "
                f"the absent holiday calendar before calculating calendar dates."
            ),
            "After resolution, if a review is required",
        )
    add(
        ["POL-EVD-001:s02:c01"],
        "Authorised human evidence owner",
        (
            "retain evidence throughout investigation and for 180 days after "
            "resolution; a legal hold suspends disposal until Risk & Compliance "
            "releases it."
        ),
        "Resolution recorded and any legal-hold conditions verified by a human",
    )
    # Other selected dimensions retain a specific human-review task without invented roles/timing.
    covered_ids = {eid for a in actions for eid in a.evidence_ids}
    for ref in evidence:
        eid = ref["evidence_id"]
        if ref["source_type"] == "internal_policy" and eid not in covered_ids and len(actions) < 12:
            add(
                [eid],
                "Responsible human owner (confirmation required)",
                (
                    f"review {ref['title']} — {ref['section']} against the known incident "
                    f"facts and record unresolved prerequisites."
                ),
                "Only if this cited policy dimension applies",
            )
    return actions[:12]


def executive_summary(state: dict, status: str) -> str:
    context = state["incident_context"]
    assessment = state.get("severity_assessment", {})
    parts = []
    if state.get("recorded_context") or any(k not in {"severity", "source"} for k in context):
        origin = "Snapshot incident" if state.get("recorded_context") else "Reported incident"
        label = context.get("incident_id") or context.get(
            "category", "category unconfirmed"
        ).replace("_", " ")
        details = []
        if context.get("downtime_minutes") is not None:
            details.append(f"{context['downtime_minutes']} minutes downtime")
        if context.get("customer_impact_count") is not None:
            details.append(f"{context['customer_impact_count']} customer-impact exposures")
        parts.append(
            f"{origin} {label}"
            + (": " + "; ".join(details) if details else ": impact/duration not fully known")
            + "."
        )
    else:
        dimensions = [
            d["description"]
            for r in state["investigation_plan"]["requirements"]
            for d in r.get("dimensions", [])
        ]
        parts.append(
            "Policy/history investigation: "
            + (", ".join(dimensions[:4]) or state["route"].replace("_", " "))
            + "."
        )
    if assessment.get("proposed_severity"):
        parts.append(
            f"Proposed {assessment['proposed_severity']} assessment is "
            f"{assessment['status']}; recorded severity is "
            f"{assessment.get('recorded_severity') or 'not available'} and "
            f"user-reported severity is "
            f"{assessment.get('reported_severity') or 'not supplied'}."
        )
        if assessment.get("basis"):
            parts.append(assessment["basis"][0])
    elif assessment.get("status") == "insufficient":
        parts.append(
            "A proposed severity cannot be established from the available facts and "
            "policy evidence."
        )
    metrics = next(
        (
            r["result"]
            for r in state["historical_incident_evidence"]
            if r["tool_name"] == "calculate_incident_metrics"
        ),
        None,
    )
    if metrics:
        parts.append(
            f"The filtered historical cohort contains {metrics['incident_count']} "
            f"incidents; median downtime is {metrics['median_downtime_minutes']} "
            f"minutes, with {metrics['downtime_sample_count']} known resolved "
            f"durations and {metrics['missing_downtime_count']} excluded/open or "
            f"missing durations."
        )
    gaps = state["verification_result"]["gaps"]
    if gaps:
        parts.append("Unresolved: " + "; ".join(g["description"] for g in gaps[:3]) + ".")
    parts.append(
        f"Investigation status: {status}. Proposed actions require human "
        f"confirmation and have not been executed."
    )
    return " ".join(parts)


def context_summary(state: dict) -> str:
    values = observations(state)
    return (
        "; ".join(
            f"{v.field.replace('_', ' ')}={v.value if v.value is not None else 'unknown'} "
            f"({v.origin.replace('_', ' ')})"
            for v in values
        )
        or "No specific incident context supplied."
    )
