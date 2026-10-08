import calendar
import re
from datetime import UTC, datetime, timedelta

from opspilot.domain.models import RoutePlan

CATEGORY_PATTERNS = [
    ("payment_failure", r"payment|transaction failure"),
    ("digital_outage", r"digital|booking portal"),
    ("facility_disruption", r"facility|facilities|equipment"),
    ("customer_impact", r"customer[- ]impact incident|notification incident"),
    ("data_integrity", r"data[- ]integrity|reconciliation incident"),
    ("vendor_disruption", r"vendor disruption|supplier disruption|vendor connectivity"),
]


def unsafe_request(question: str) -> bool:
    q = question.lower()
    if re.search(
        r"\b(bypass|sudo|shell|execute sql|drop table|delete from|api key|system prompt)\b"
        r"|ignore.{0,30}(instruction|rule|policy)|(?:send|post).{0,40}https?://",
        q,
    ):
        return True
    write = re.search(
        r"\b(close|delete|erase|update|modify|create|send|execute|run|write|insert|"
        r"refund|restart|disable|activate)\b",
        q,
    )
    explanation = re.match(r"\s*(what|when|which|who|explain)\b", q)
    return bool(write and not explanation)


def shift_months(value: datetime, months: int) -> datetime:
    index = value.year * 12 + value.month - 1 + months
    year, month = divmod(index, 12)
    month += 1
    return value.replace(
        year=year, month=month, day=min(value.day, calendar.monthrange(year, month)[1])
    )


def infer_filters(question: str, reference: datetime) -> dict:
    q = question.lower()
    filters = {"since": shift_months(reference, -12).isoformat(), "until": reference.isoformat()}
    for category, pattern in CATEGORY_PATTERNS:
        if re.search(pattern, q):
            filters["category"] = category
            break
    severity = re.search(r"\b(?:severity\s*|sev[- ]?)([1-4])\b", q)
    if severity:
        filters["severity"] = "SEV" + severity[1]
    for unit in [
        "Operations",
        "Customer Service",
        "Digital Services",
        "Facilities",
        "Risk & Compliance",
    ]:
        if re.search(r"(?:in|from|business unit)\s+" + re.escape(unit.lower()), q):
            filters["business_unit"] = unit
    for service in [
        "Payment Gateway",
        "Booking Portal",
        "Queue System",
        "Site Equipment",
        "Customer Notifications",
        "Contact Centre",
        "Reconciliation Feed",
        "Vendor Connectivity",
    ]:
        if service.lower() in q:
            filters["service"] = service
    if "vendor-related" in q or "vendor related" in q:
        filters["vendor_related"] = True
    if "non-vendor" in q:
        filters["vendor_related"] = False
    for status in ["open", "investigating", "resolved"]:
        if re.search(r"\b" + status + r"\s+incidents?\b", q):
            filters["status"] = status
    minimum = re.search(r"(?:at least|minimum)\s+(\d+)\s+(?:affected )?customers", q)
    if minimum:
        filters["min_customer_impact"] = int(minimum[1])
    for name, pattern in [
        ("since", r"(?:since|from)\s+(\d{4}-\d{2}-\d{2})"),
        ("until", r"(?:until|before)\s+(\d{4}-\d{2}-\d{2})"),
    ]:
        if match := re.search(pattern, q):
            filters[name] = datetime.fromisoformat(match[1]).replace(tzinfo=UTC).isoformat()
    numbers = {"one": 1, "six": 6, "twelve": 12, "thirty": 30}
    window = re.search(r"last\s+(\d+|one|six|twelve|thirty)\s+(days?|months?)", q)
    if window:
        count = numbers.get(window[1]) or int(window[1])
        start = (
            reference - timedelta(days=count)
            if window[2].startswith("day")
            else shift_months(reference, -count)
        )
        filters["since"] = start.isoformat()
    if "last year" in q or "last twelve months" in q:
        filters["since"] = shift_months(reference, -12).isoformat()
    if "this year" in q:
        filters["since"] = reference.replace(month=1, day=1).isoformat()
    for month in range(1, 13):
        match = re.search(r"\b" + calendar.month_name[month].lower() + r"\s+(\d{4})\b", q)
        if match:
            start = datetime(int(match[1]), month, 1, tzinfo=UTC)
            filters.update(since=start.isoformat(), until=shift_months(start, 1).isoformat())
    return filters


class DeterministicPlanner:
    """Transparent English-query baseline; the API planner handles wider paraphrases."""

    def plan(self, question: str, reference: datetime, top_k: int) -> RoutePlan:
        q = question.lower()
        if unsafe_request(q):
            return RoutePlan(route="unsupported")
        if not re.search(
            r"inc-\d{3}|incident|policy|sop|severity|sev[1-4]|payment|digital|outage|facility|equipment|"
            r"customer|vendor|supplier|recovery|evidence|log|retention|continuity|review|"
            r"reconcil|escalat|notification|compensation|insurance|password|holiday|evacuation",
            q,
        ):
            return RoutePlan(route="unsupported")
        incident_ids = re.findall(r"\bINC-\d{3}\b", question.upper())
        if len(set(incident_ids)) > 1:
            return RoutePlan(route="unsupported")
        data = bool(
            incident_ids
            or re.search(
                r"how many|\b(counts?|median|mean|average|p90|historical|history|dataset|"
                r"similar|compare|"
                r"comparison|distribution|breakdown|metrics)\b"
                r"|list.{0,20}incidents",
                q,
            )
        )
        policy = bool(
            re.search(
                r"\b(policy|policies|sop|procedure|must|should|require|required|thresholds?|"
                r"retention|notice|cadence|"
                r"continuity|compensation|insurance|password|holiday|evacuation)\b|escalat|notify|"
                r"notification deadline|communicat|reconcil|review|classif|observe|"
                r"who |when ",
                q,
            )
        )
        if not data and not policy:
            policy = bool(re.search(r"supplier|vendor|evidence|recovery|severity|log", q))
        if not data and not policy:
            return RoutePlan(route="unsupported")
        route = "mixed" if data and policy else "data_only" if data else "policy_only"
        calls = []
        if incident_ids:
            calls.append(
                {"tool_name": "get_incident", "arguments": {"incident_id": incident_ids[0]}}
            )
        if policy:
            calls.append(
                {
                    "tool_name": "search_internal_policy",
                    "arguments": {"query": question, "top_k": top_k},
                }
            )
        if data:
            filters = infer_filters(question, reference)
            similar = bool(re.search(r"\bsimilar\b|list.{0,20}incidents", q))
            if similar:
                calls.append({"tool_name": "find_similar_incidents", "arguments": filters})
            if re.search(
                r"how many|count|median|mean|average|p90|compare|comparison|distribution|"
                r"breakdown|metrics|total|history|historical",
                q,
            ) or not (similar or incident_ids):
                for group in ["category", "severity", "business unit", "service", "status"]:
                    if "by " + group in q or group + " distribution" in q:
                        filters["group_by"] = group.replace(" ", "_")
                calls.append({"tool_name": "calculate_incident_metrics", "arguments": filters})
        duration = re.search(r"(?:for|lasted|down|duration(?: is| of)?)\s+(\d+)\s+minutes", q)
        return RoutePlan.model_validate(
            {
                "route": route,
                "calls": calls,
                "current_duration_minutes": int(duration[1]) if duration else None,
            }
        )
