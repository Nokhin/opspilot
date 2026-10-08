import math
import sqlite3
import statistics
from collections import Counter
from contextlib import closing
from pathlib import Path

from opspilot.data.seed import utc_timestamp
from opspilot.domain.models import (
    Incident,
    IncidentFilters,
    MetricsArgs,
    MetricsResult,
    SimilarIncidentArgs,
    SimilarResult,
)


class IncidentRepository:
    """No writable connection or arbitrary SQL is exposed to model-facing tools."""

    def __init__(self, path: Path):
        self.path = path

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA query_only=ON")
        return con

    @staticmethod
    def _where(filters: IncidentFilters) -> tuple[str, list]:
        clauses, values = [], []
        # SQL identifiers come only from this code, values are always bound parameters.
        for name in (
            "category",
            "severity",
            "business_unit",
            "service",
            "status",
            "vendor_related",
        ):
            value = getattr(filters, name)
            if value is not None:
                clauses.append(f"{name} = ?")
                values.append(value)
        if filters.since:
            clauses.append("opened_at >= ?")
            values.append(utc_timestamp(filters.since))
        if filters.until:
            clauses.append("opened_at < ?")
            values.append(utc_timestamp(filters.until))
        if filters.min_customer_impact is not None:
            clauses.append("customer_impact_count >= ?")
            values.append(filters.min_customer_impact)
        return (" WHERE " + " AND ".join(clauses) if clauses else ""), values

    @staticmethod
    def _incident(row: sqlite3.Row) -> Incident:
        return Incident.model_validate(dict(row))

    def get(self, incident_id: str) -> Incident | None:
        with closing(self._connect()) as con:
            row = con.execute(
                "SELECT * FROM incidents WHERE incident_id = ?", (incident_id,)
            ).fetchone()
        return self._incident(row) if row else None

    def planning_catalog(self) -> list[dict[str, str]]:
        """Bounded read-only entity metadata; never model-authored SQL."""
        with closing(self._connect()) as con:
            rows = con.execute(
                "SELECT DISTINCT service, category FROM incidents "
                "ORDER BY service, category LIMIT 100"
            ).fetchall()
        return [
            IncidentFilters(service=row["service"], category=row["category"]).model_dump(
                exclude_none=True
            )
            for row in rows
        ]

    def _all_matching(self, args: IncidentFilters) -> list[Incident]:
        where, values = self._where(args)
        with closing(self._connect()) as con:
            rows = con.execute(
                "SELECT * FROM incidents" + where + " ORDER BY opened_at DESC, incident_id", values
            ).fetchall()
        return [self._incident(row) for row in rows]

    def find_similar(self, args: SimilarIncidentArgs) -> SimilarResult:
        incidents = self._all_matching(args)
        filters = args.model_dump(mode="json", exclude={"limit"}, exclude_none=True)
        return SimilarResult(
            incidents=incidents[: args.limit], filters=filters, total_matches=len(incidents)
        )

    def metrics(self, args: MetricsArgs) -> MetricsResult:
        records = self._all_matching(args)
        durations = sorted(
            i.downtime_minutes
            for i in records
            if i.status == "resolved" and i.downtime_minutes is not None
        )
        count, n = len(records), len(durations)
        impact = sum(i.customer_impact_count for i in records)
        services = Counter(i.service for i in records)
        return MetricsResult(
            filters=args.model_dump(mode="json", exclude_none=True),
            incident_count=count,
            resolved_count=sum(i.status == "resolved" for i in records),
            downtime_sample_count=n,
            missing_downtime_count=count - n,
            mean_downtime_minutes=round(statistics.mean(durations), 4) if n else None,
            median_downtime_minutes=statistics.median(durations) if n else None,
            p90_downtime_minutes=durations[math.ceil(0.9 * n) - 1] if n else None,
            total_customer_impact=impact,
            mean_customer_impact=round(impact / count, 4) if count else None,
            severity_distribution=dict(sorted(Counter(i.severity for i in records).items())),
            group_counts=dict(sorted(Counter(getattr(i, args.group_by) for i in records).items()))
            if args.group_by
            else {},
            repeat_incident_count_by_service={k: v for k, v in sorted(services.items()) if v > 1},
        )
