import hashlib
import json
import os
import random
import sqlite3
from datetime import UTC, datetime, timedelta
from importlib.resources import files
from pathlib import Path

from opspilot.domain.models import Incident

SNAPSHOT_END = datetime(2026, 10, 1, tzinfo=UTC)
SEED = 42
ROW_COUNT = 240
PATTERNS = [
    ("digital_outage", "Booking Portal", "Digital Services", "capacity regression"),
    ("payment_failure", "Payment Gateway", "Digital Services", "gateway timeout"),
    ("facility_disruption", "Site Equipment", "Facilities", "power supply fault"),
    ("customer_impact", "Customer Notifications", "Customer Service", "notification backlog"),
    ("data_integrity", "Reconciliation Feed", "Risk & Compliance", "batch validation gap"),
    ("vendor_disruption", "Vendor Connectivity", "Operations", "supplier network interruption"),
]
SITES = ["Island Centre", "Kowloon Centre", "Tuen Mun Centre", "Sha Tin Centre"]


def utc_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def generate_incidents(seed: int = SEED, count: int = ROW_COUNT) -> list[Incident]:
    """Fixed snapshot; category-specific durations, outliers and unresolved recent records."""
    if not 150 <= count <= 400:
        raise ValueError("Synthetic snapshot supports 150–400 rows")
    rng = random.Random(seed)
    incidents = []
    for index in range(1, count + 1):
        category, service, unit, cause = PATTERNS[(index - 1) % len(PATTERNS)]
        # Payment incidents are more common in the final quarter of this snapshot.
        days = rng.randrange(90 if category == "payment_failure" and index % 12 == 2 else 365)
        opened = SNAPSHOT_END - timedelta(days=days, minutes=rng.randrange(1, 1440))
        base = {
            "digital_outage": 24,
            "payment_failure": 38,
            "facility_disruption": 70,
            "customer_impact": 12,
            "data_integrity": 9,
            "vendor_disruption": 50,
        }[category]
        duration = max(0, int(rng.lognormvariate(0, 0.65) * base))
        if index % 37 == 0:
            duration = 480
        impact = rng.randrange(5, 180) * (
            4 if category in {"payment_failure", "digital_outage"} else 1
        )
        severity = (
            "SEV1"
            if impact >= 500
            or (category in {"payment_failure", "digital_outage"} and duration >= 30)
            else "SEV2"
            if impact >= 100 or duration >= 10
            else "SEV3"
        )
        if index % 23 == 0 and category not in {"payment_failure", "digital_outage"}:
            severity, duration, impact = "SEV4", 0, 0
        vendor = category == "vendor_disruption" or (
            category in {"payment_failure", "digital_outage"} and index % 4 == 0
        )
        unresolved = index > count - 12
        if unresolved:
            opened = SNAPSHOT_END - timedelta(hours=(count - index + 1) * 3)
        resolved = None if unresolved else opened + timedelta(minutes=duration + 45)
        downtime = None if unresolved or index % 29 == 0 else duration
        incidents.append(
            Incident(
                incident_id=f"INC-{index:03}",
                opened_at=opened,
                resolved_at=resolved,
                category=category,
                subcategory=cause,
                severity=severity,
                business_unit=unit,
                service=service,
                site=rng.choice(SITES)
                if category == "facility_disruption"
                else ("Online" if unit == "Digital Services" else "Shared Services"),
                customer_impact_count=impact,
                downtime_minutes=downtime,
                estimated_cost=None if unresolved or index % 7 == 0 else round(impact * 1.8, 2),
                root_cause=None if unresolved else cause,
                vendor_related=vendor,
                status=("open" if index % 2 else "investigating") if unresolved else "resolved",
                resolution_summary=None if unresolved else "Owner validated recovery and handover.",
                post_incident_review_required=severity == "SEV1"
                or category in {"payment_failure", "data_integrity"},
            )
        )
    # Curated anchor records support repeatable incident investigations.
    incidents[0] = Incident(
        incident_id="INC-001",
        opened_at=datetime(2026, 9, 29, 10, tzinfo=UTC),
        resolved_at=datetime(2026, 9, 29, 11, 30, tzinfo=UTC),
        category="payment_failure",
        subcategory="gateway timeout",
        severity="SEV1",
        business_unit="Digital Services",
        service="Payment Gateway",
        site="Online",
        customer_impact_count=620,
        downtime_minutes=45,
        estimated_cost=1116,
        root_cause="supplier connection pool exhaustion",
        vendor_related=True,
        status="resolved",
        resolution_summary="Gateway restored; reconciliation verified.",
        post_incident_review_required=True,
    )
    return incidents


def seed_database(path: Path, *, reset: bool = False) -> dict:
    if path.is_symlink() or (path.exists() and not reset):
        raise ValueError(
            "Database exists or is a symlink; use explicit --reset for a snapshot rebuild"
        )
    incidents = generate_incidents()
    canonical = json.dumps([i.model_dump(mode="json") for i in incidents], sort_keys=True)
    metadata = {
        "synthetic": True,
        "generator_version": 1,
        "seed": SEED,
        "rows": len(incidents),
        "as_of": utc_timestamp(SNAPSHOT_END),
        "content_sha256": hashlib.sha256(canonical.encode()).hexdigest(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    if tmp.exists():
        tmp.unlink()
    try:
        with sqlite3.connect(tmp) as con:
            con.executescript(files("opspilot.data").joinpath("schema.sql").read_text())
            for incident in incidents:
                row = incident.model_dump()
                row["opened_at"] = utc_timestamp(incident.opened_at)
                row["resolved_at"] = (
                    utc_timestamp(incident.resolved_at) if incident.resolved_at else None
                )
                names = list(row)
                con.execute(
                    f"INSERT INTO incidents ({','.join(names)}) "
                    f"VALUES ({','.join('?' for _ in names)})",
                    list(row.values()),
                )
            con.executemany(
                "INSERT INTO dataset_meta VALUES (?,?)",
                [(k, json.dumps(v)) for k, v in metadata.items()],
            )
        con.close()
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()
    return metadata
