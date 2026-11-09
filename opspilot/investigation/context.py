"""Bounded context intake and field-specific clarification, without model inference."""

import re

from opspilot.investigation.models import IncidentContext
from opspilot.orchestration.routing import CATEGORY_PATTERNS

QUESTIONS = {
    "incident_id": "Which incident ID should be investigated? Alternatively provide a category.",
    "category": "Which incident category is affected? Alternatively provide an incident ID.",
    "customer_facing": "Is this an interruption to a customer-facing service?",
    "downtime_minutes": "How many minutes has the service been continuously unavailable?",
    "customer_impact_count": "How many customers are affected? Leave unknown if unverified.",
    "immediate_danger": "Is there credible immediate danger to people?",
    "multi_site_essential_closure": "Does a multi-site closure prevent essential customer service?",
    "single_site_disruption": "Is this a single-site operational disruption?",
    "duplicate_capture_confirmed": "Has duplicate payment capture been confirmed?",
    "workaround_available": "Is a safe workaround available for the local degradation?",
    "integrity_concern": "Is there a safety or financial-integrity concern?",
    "no_customer_interruption": "Is there no current customer interruption?",
    "local_degradation": "Is the impact a local degradation?",
    "minor_operational_defect": "Is this a minor operational defect?",
    "threshold_detected_at": (
        "When was the relevant severity threshold first detected? Supply an explicit timezone."
    ),
}


def explicit_positive(query: str, match: re.Match | None) -> bool:
    """Reject locally negated or qualified prose; typed clarification resolves ambiguity."""
    if not match:
        return False
    prefix = query[max(0, match.start() - 40) : match.start()]
    return not re.search(
        r"\b(?:not|no|never|unknown|unverified|possibly|suspected|may|might)\b|n't\b",
        prefix,
        re.I,
    )


def parse_context(query: str, supplied: dict) -> dict:
    """Only explicit bounded values are extracted. Unknown never becomes zero/false."""
    values = dict(supplied)
    ids = set(re.findall(r"\bINC-\d{3}\b", query.upper()))
    if len(ids) == 1:
        values.setdefault("incident_id", next(iter(ids)))
    severity = set(re.findall(r"\b(?:sev\s*|severity\s+)([1-4])\b", query, re.I))
    if len(severity) == 1:
        values.setdefault("severity", "SEV" + next(iter(severity)))
    scenario = bool(
        re.search(
            r"\binvestigat|\bthis (?:incident|outage)|\b(?:a|our) .{0,60}(?:outage|has been down)"
            r"|\bclassify\b|\bassess (?:the )?severity",
            query,
            re.I,
        )
    )
    if scenario or supplied:
        for category, pattern in CATEGORY_PATTERNS:
            if re.search(pattern, query, re.I):
                values.setdefault("category", category)
                break
        duration = re.search(
            r"(?:for|lasted|down|duration(?: is| of)?)\s+(\d+)\s+minutes", query, re.I
        )
        if explicit_positive(query, duration):
            values.setdefault("downtime_minutes", int(duration[1]))
        impact = re.search(
            r"(?:affects?|affecting|impacts?)\s+(\d+)\s+(?:customers|users)", query, re.I
        )
        if explicit_positive(query, impact):
            values.setdefault("customer_impact_count", int(impact[1]))
        if explicit_positive(query, re.search(r"customer[- ]facing", query, re.I)):
            values.setdefault("customer_facing", True)
    return IncidentContext.model_validate(values).model_dump(mode="json", exclude_none=True)


def needs_assessment(query: str, context: dict) -> bool:
    facts = any(k != "severity" and k != "source" for k in context)
    if re.search(r"classif|severity assess|assess.{0,20}severity|reassess", query, re.I):
        return bool(facts or re.search(r"\bthis\b|\bclassify\b|\bassess\b|reassess", query, re.I))
    return bool(
        re.search(r"\binvestigat|\bthis incident|\bhas been down|\boutage.{0,20}last", query, re.I)
    )


def severity_candidate(context: dict) -> tuple[str | None, list[str], list[str]]:
    """A search/triage hint only; a publishable assessment additionally requires policy evidence."""
    impact, duration = context.get("customer_impact_count"), context.get("downtime_minutes")
    customer_facing = context.get("customer_facing") is True
    digital = context.get("category") in {"digital_outage", "payment_failure"}
    reasons = []
    if impact is not None and impact >= 500:
        reasons.append("At least 500 affected customers were reported/recorded.")
    if digital and customer_facing and duration is not None and duration >= 30:
        reasons.append(
            "A customer-facing digital/payment service has been unavailable for at "
            "least 30 minutes."
        )
    if context.get("immediate_danger") is True:
        reasons.append("Credible immediate danger to people was reported.")
    if context.get("multi_site_essential_closure") is True:
        reasons.append("A multi-site closure prevents essential customer service.")
    if reasons:
        return "SEV1", reasons, []
    missing = [
        name
        for name in ("immediate_danger", "multi_site_essential_closure")
        if context.get(name) is None
    ]
    if impact is None:
        missing.append("customer_impact_count")
    if digital:
        if context.get("customer_facing") is None:
            missing.append("customer_facing")
        if context.get("customer_facing") is not False and duration is None:
            missing.append("downtime_minutes")
    elif context.get("single_site_disruption") is None:
        missing.append("single_site_disruption")
    sev2 = []
    if impact is not None and 100 <= impact < 500:
        sev2.append("Reported/recorded customer impact is in the 100–499 band.")
    if customer_facing and duration is not None and 10 <= duration < 30:
        sev2.append("A customer-facing outage duration is in the 10–29 minute band.")
    if context.get("single_site_disruption") is True and context.get("immediate_danger") is False:
        sev2.append("A single-site disruption without immediate danger was reported.")
    if context.get("duplicate_capture_confirmed") is True:
        sev2.append("Confirmed duplicate payment capture requires at least SEV2.")
    if sev2:
        return "SEV2", sev2, list(dict.fromkeys(missing))
    if (
        context.get("category") == "payment_failure"
        and context.get("duplicate_capture_confirmed") is None
    ):
        missing.append("duplicate_capture_confirmed")
    if (
        context.get("minor_operational_defect") is True
        and context.get("no_customer_interruption") is True
        and impact == 0
        and context.get("integrity_concern") is False
    ):
        return (
            "SEV4",
            [
                (
                    "A minor defect with zero affected customers and no current "
                    "interruption was reported."
                )
            ],
            list(dict.fromkeys(missing)),
        )
    if (
        impact is not None
        and impact < 100
        and context.get("local_degradation") is True
        and context.get("workaround_available") is True
        and context.get("integrity_concern") is False
        and context.get("immediate_danger") is False
    ):
        return (
            "SEV3",
            ["Fewer than 100 customers, a workaround and no reported safety/integrity concern."],
            list(dict.fromkeys(missing)),
        )
    if impact is not None and impact < 100:
        missing += [
            n
            for n in (
                "workaround_available",
                "integrity_concern",
                "no_customer_interruption",
                "local_degradation",
                "minor_operational_defect",
            )
            if context.get(n) is None
        ]
    return None, [], list(dict.fromkeys(missing))


def effective_severity(context: dict) -> str | None:
    candidate, _, _ = severity_candidate(context)
    # Keep the highest observed/reported/candidate severity; no silent downgrade.
    values = [v for v in (context.get("severity"), candidate) if v]
    return min(values) if values else None


def clarification_fields(state: dict) -> list[str]:
    context, query = state["incident_context"], state["user_request"]
    if state.get("clarification_done"):
        return []
    if context.get("incident_id"):
        return []  # Recorded snapshot context is fetched by the existing typed tool.
    assessment = needs_assessment(query, context)
    if not assessment:
        return []
    if not context.get("category"):
        return ["incident_id", "category"]
    _, _, missing = severity_candidate(context)
    if re.search(
        r"exact (?:notification )?deadline|due (?:at|time)|what (?:clock )?time"
        r"|overdue|minutes (?:left|remaining)",
        query,
        re.I,
    ) and not context.get("threshold_detected_at"):
        missing.append("threshold_detected_at")
    return list(dict.fromkeys(missing))
