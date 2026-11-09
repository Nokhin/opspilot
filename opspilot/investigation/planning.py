"""Deterministic requirements independent of model-proposed execution plans."""

import re

from opspilot.domain.models import RoutePlan
from opspilot.investigation.context import effective_severity, needs_assessment, severity_candidate
from opspilot.investigation.models import (
    EvidenceDimension,
    EvidenceRequirement,
    InvestigationPlan,
    PlanningRejectionCode,
)
from opspilot.orchestration.grounding import explicitly_missing

# Topic coverage is intentionally explicit and inspectable for this fictional corpus.
TOPICS = (
    (
        "classification",
        r"classif|severity assess|severity threshold|sev[1-4] threshold",
        "severity classification thresholds",
    ),
    (
        "escalation",
        r"escalat|who.{0,30}notif|notification deadline",
        "escalation notify notification deadline",
    ),
    (
        "communication",
        r"communicat|customer (?:notice|update)|first notice|cadence",
        "customer communication first notice update cadence",
    ),
    ("recovery", r"recover|restor|observ", "service recovery validation observation"),
    ("continuity", r"continuity", "business continuity activation"),
    (
        "vendor",
        r"supplier|vendor escalat|vendor notif",
        "vendor supplier escalation acknowledgement",
    ),
    ("review", r"post.incident|\breview\b", "post incident review requirements"),
    (
        "retention",
        r"retention|preserv|\blogs?\b|evidence handl",
        "evidence log retention preservation",
    ),
    ("payment", r"duplicate|reconcil", "payment duplicate capture reconciliation"),
    ("facility", r"physical|facility|facilities|equipment", "facility disruption safety"),
)


# Each requested facet has its own source obligation. A shared document is not coverage.
FACETS = {
    "classification": [
        ("thresholds", r"threshold|classif|assess|severity", [2, 3], "severity thresholds"),
        (
            "review",
            r"reclassif|downgrad|upgrade|classification review",
            [4],
            "classification review",
        ),
        ("ownership", r"owner|responsib|who", [5], "classification ownership"),
    ],
    "escalation": [
        (
            "notifications",
            r"who|when|deadline|within|recipients?|notify|timeframe|time limit",
            [2, 3],
            "notification recipients deadlines",
        ),
        (
            "clock",
            r"clock|start.{0,20}(?:time|deadline)|threshold detection",
            [1],
            "notification clock threshold detection",
        ),
        ("acknowledgement", r"acknowledg|alternate|no response", [4], "missing acknowledgement"),
        (
            "content",
            r"content|includ|fields|contain|information|details",
            [5],
            "notification content boundaries",
        ),
        ("handover", r"handover|shift change", [6], "handover procedures"),
    ],
    "communication": [
        ("ownership", r"owner|who|approv|responsib", [1], "communication ownership"),
        (
            "timing",
            r"cadence|notice|update|deadline|time|frequency|how often",
            [1, 2],
            "communication ownership first notice update cadence",
        ),
        ("content", r"content|includ|contain|information|details|wording", [3], "message content"),
        ("restoration", r"restor", [4], "restoration message"),
        ("audience", r"accessib|audience|alternatives|signage", [5], "audience accessibility"),
        ("evidence", r"retain|evidence|review", [6], "communication evidence review"),
    ],
    "recovery": [
        ("containment", r"contain|workaround|rollback", [1], "initial containment"),
        ("observation", r"observ|stabil|restor", [2], "restoration observation"),
        ("reconciliation", r"reconcil|integrity", [3], "reconciliation integrity"),
        ("resolution", r"resolution|approv|close|prerequisit", [4], "resolution decision"),
        ("metrics", r"metrics|downtime definition|denominator", [5], "recovery metrics"),
    ],
    "continuity": [
        ("activation", r"activat|threshold|when|assess", [2], "continuity activation thresholds"),
        ("capacity", r"capacity|alternatives|redirect", [3], "alternative service capacity"),
        ("ownership", r"owner|who|coordinat", [4], "continuity coordination ownership"),
        ("return", r"return|normal operation", [5], "return to normal operation"),
    ],
    "vendor": [
        ("notification", r"notif|deadline|contact|when", [2], "supplier notification deadlines"),
        (
            "acknowledgement",
            r"acknowledg|no response|missing response",
            [3],
            "missing supplier response",
        ),
        ("sharing", r"shar|diagnostic|sensitive", [4], "sharing diagnostic evidence"),
        ("recovery", r"recover|restor", [5], "vendor recovery ownership"),
    ],
    "review": [
        ("criteria", r"require|criteria|mandatory|trigger", [1], "mandatory review criteria"),
        (
            "timetable",
            r"time|when|deadline|days|schedule|\bdue\b|\bdates?\b|\bcalendar\b",
            [2],
            "review timetable business days resolution",
        ),
        ("content", r"content|includ|contain|details|information", [3], "required review content"),
        ("actions", r"corrective|action owner|verification", [4], "action ownership"),
        ("repeat", r"repeat|rolling|30.day", [5], "repeat incident analysis"),
        ("retention", r"retention|disseminat", [6], "review retention dissemination"),
    ],
    "retention": [
        ("capture", r"captur|checksum|collect", [1], "evidence capture"),
        ("period", r"period|retain|how long|hold|retention", [2], "retention period legal hold"),
        ("access", r"access|minimi|authoris", [3], "access data minimisation"),
        ("sharing", r"shar|custody|extern", [4], "sharing chain of custody"),
        ("disposal", r"dispos|delet|erase", [5], "disposal control"),
        ("trace", r"trace|log content|audit", [6], "audit traces"),
    ],
    "payment": [
        ("duplicate", r"duplicate", [2], "duplicate payment containment"),
        ("reconciliation", r"reconcil", [3], "payment reconciliation checks"),
    ],
    "facility": [
        ("safety", r"safety|danger|hazard", [1], "safety first triage"),
        ("escalation", r"escalat", [2], "facility operational escalation"),
        ("closure", r"closure|alternatives|close", [3], "site closure alternatives"),
    ],
}
DEFAULT_FACET = {
    "classification": "thresholds",
    "escalation": "notifications",
    "communication": "timing",
    "recovery": "observation",
    "continuity": "activation",
    "vendor": "notification",
    "review": "criteria",
    "retention": "period",
    "payment": "reconciliation",
    "facility": "safety",
}


def dimensions(topic: str, query: str, context: dict) -> list[EvidenceDimension]:
    entries = FACETS[topic]
    matched = [r for r in entries if re.search(r[1], query, re.I)]
    if not matched:
        matched = [r for r in entries if r[0] == DEFAULT_FACET[topic]]
    if topic == "review" and any(r[0] == "timetable" for r in matched):
        # SEV2–4 do not automatically require a review: retain the applicability
        # criteria alongside any timetable rather than presenting an unconditional due date.
        if not any(r[0] == "criteria" for r in matched):
            matched = [next(r for r in entries if r[0] == "criteria"), *matched]
    severity = effective_severity(context)
    if not severity:
        match = re.search(r"\bsev([1-4])\b|severity ([1-4])", query, re.I)
        severity = "SEV" + next(v for v in match.groups() if v) if match else None
    values = []
    for name, _, sections, description in matched:
        if (topic, name) == ("escalation", "notifications"):
            sections = [1, 2] if severity == "SEV1" else [1, 3] if severity else [1, 2, 3]
        if (topic, name) == ("classification", "thresholds"):
            if needs_assessment(query, context):
                candidate, _, _ = severity_candidate(context)
                sections = [2] if candidate == "SEV1" else [2, 3]
            elif severity == "SEV1":
                sections = [2]
        values.append(
            EvidenceDimension(
                dimension_id=f"policy:{topic}:{name}",
                description=description,
                section_numbers=sections,
            )
        )
    return values


def required_sections(topic: str, query: str, context: dict) -> list[int]:
    return sorted({s for d in dimensions(topic, query, context) for s in d.section_numbers})


def make_plan(query: str, execution: RoutePlan, context: dict | None = None) -> InvestigationPlan:
    requirements = []
    classification_only = bool(
        re.search(
            r"^\s*(?:assess (?:the )?severity|classify|what severity|which severity)", query, re.I
        )
        and not re.search(
            r"escalat|communicat|recover|continuity|retention|containment|supplier|review",
            query,
            re.I,
        )
    )
    if execution.route in {"policy_only", "mixed"}:
        for topic, pattern, search in TOPICS:
            if classification_only and topic != "classification":
                continue
            if (
                re.search(pattern, query, re.I)
                or topic == "classification"
                and needs_assessment(query, context or {})
            ):
                requirements.append(
                    EvidenceRequirement(
                        requirement_id="policy:" + topic,
                        plane="policy",
                        description=search,
                        policy_type=topic,
                        section_numbers=required_sections(topic, query, context or {}),
                        query=(
                            search
                            + " "
                            + " ".join(
                                d.description for d in dimensions(topic, query, context or {})
                            )
                        )[:3000],
                        dimensions=dimensions(topic, query, context or {}),
                    )
                )
        if explicitly_missing(query) or re.search(
            r"\b(?:budget|funding|fee|fees|entitlement|fine)\b", query, re.I
        ):
            requirements.append(
                EvidenceRequirement(
                    requirement_id="policy:unsupported_detail",
                    plane="policy",
                    description="The requested policy detail is absent from this corpus.",
                )
            )
        if not requirements:
            requirements.append(
                EvidenceRequirement(
                    requirement_id="policy:unmapped_detail",
                    plane="policy",
                    description=(
                        "Requested policy dimension is not mapped; clarify the required "
                        "procedure/detail."
                    ),
                    query=query,
                )
            )
    for call in execution.calls:
        if call.tool_name != "search_internal_policy":
            requirements.append(
                EvidenceRequirement(
                    requirement_id="history:" + call.tool_name,
                    plane="history",
                    description="Validated deterministic result from " + call.tool_name,
                    tool_name=call.tool_name,
                )
            )
    return InvestigationPlan(execution=execution, requirements=requirements)


class PlanningRejected(ValueError):
    """Stable rejection code, independent of raw model content and exception details."""

    def __init__(self, code: PlanningRejectionCode):
        self.code = code
        super().__init__(code)


def planning_contract(minimum: RoutePlan, query: str, budget: int) -> dict:
    """Server-derived constraints supplied to the planner, never accepted from clients."""
    return {
        "required_route": minimum.route if minimum.route != "unsupported" else None,
        "required_tools": [c.tool_name for c in minimum.calls],
        "max_tool_calls": budget,
        "allowed_incident_ids": sorted(set(re.findall(r"\bINC-\d{3}\b", query.upper()))),
        "allowed_duration_minutes": sorted(
            {int(m) for m in re.findall(r"\b(\d+)\s+minutes\b", query, re.I)}
        ),
    }


def validate_proposed_plan(proposed: RoutePlan, minimum: RoutePlan, query: str, budget: int):
    """A model cannot remove recognized requirements or invent incident IDs."""
    proposed = RoutePlan.model_validate(proposed.model_dump())
    if len(proposed.calls) > budget:
        raise PlanningRejected("tool_budget_exceeded")
    names = {c.tool_name for c in proposed.calls}
    if minimum.route != "unsupported":
        if proposed.route != minimum.route:
            raise PlanningRejected("route_mismatch")
        if not {c.tool_name for c in minimum.calls} <= names:
            raise PlanningRejected("missing_required_tools")
    constraints = planning_contract(minimum, query, budget)
    for call in proposed.calls:
        if (
            call.tool_name == "get_incident"
            and call.arguments.incident_id not in constraints["allowed_incident_ids"]
        ):
            raise PlanningRejected("unreported_incident_id")
    if (
        proposed.current_duration_minutes is not None
        and proposed.current_duration_minutes not in constraints["allowed_duration_minutes"]
    ):
        raise PlanningRejected("unreported_duration")
    return proposed
