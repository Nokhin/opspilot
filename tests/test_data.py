import sqlite3
from contextlib import closing
from datetime import UTC, datetime

import pytest

from opspilot.data.repository import IncidentRepository
from opspilot.data.seed import generate_incidents, seed_database
from opspilot.domain.models import Incident, MetricsArgs, SimilarIncidentArgs


@pytest.fixture
def repo(tmp_path):
    path = tmp_path / "incidents.sqlite"
    seed_database(path)
    return IncidentRepository(path)


def test_seed_is_reproducible_and_has_patterns(tmp_path):
    assert generate_incidents() == generate_incidents()
    rows = generate_incidents()
    assert len(rows) == 240
    assert len({r.category for r in rows}) == 6
    assert len({r.business_unit for r in rows}) == 5
    assert len({r.severity for r in rows}) == 4
    assert sum(r.status != "resolved" for r in rows) == 12
    path = tmp_path / "data.sqlite"
    first = seed_database(path)
    with pytest.raises(ValueError):
        seed_database(path)
    assert seed_database(path, reset=True) == first


def test_read_only_and_parameterised_lookup(repo):
    assert repo.get("INC-001").downtime_minutes == 45
    assert repo.get("INC-999") is None
    assert repo.get("' OR 1=1 --") is None
    with closing(repo._connect()) as con:
        with pytest.raises(sqlite3.OperationalError):
            con.execute("DELETE FROM incidents")


def test_metrics_independent_of_repository_implementation(repo):
    rows = generate_incidents()
    result = repo.metrics(MetricsArgs(category="payment_failure"))
    matches = [r for r in rows if r.category == "payment_failure"]
    durations = sorted(
        r.downtime_minutes
        for r in matches
        if r.status == "resolved" and r.downtime_minutes is not None
    )
    assert result.incident_count == len(matches)
    assert result.mean_downtime_minutes == round(sum(durations) / len(durations), 4)
    assert result.total_customer_impact == sum(r.customer_impact_count for r in matches)
    assert result.missing_downtime_count == len(matches) - len(durations)


def test_half_open_timezone_window_and_zero_values(repo):
    start = datetime(2026, 9, 29, 10, tzinfo=UTC)
    end = datetime(2026, 9, 29, 10, 0, 1, tzinfo=UTC)
    assert repo.metrics(MetricsArgs(since=start, until=end)).incident_count == 1
    assert repo.metrics(MetricsArgs(until=start)).incident_count < 240
    assert (
        repo.metrics(MetricsArgs(since=end)).incident_count
        < repo.metrics(MetricsArgs(since=start)).incident_count
    )
    empty = repo.metrics(MetricsArgs(service="Does not exist"))
    assert empty.incident_count == 0 and empty.median_downtime_minutes is None
    assert repo.metrics(MetricsArgs(status="open")).downtime_sample_count == 0
    sev4 = repo.metrics(MetricsArgs(severity="SEV4"))
    assert sev4.mean_downtime_minutes == 0


def test_filters_and_limit_disclose_total(repo):
    result = repo.find_similar(SimilarIncidentArgs(category="payment_failure", limit=2))
    assert len(result.incidents) == 2
    assert result.total_matches > 2
    assert all(r.category == "payment_failure" for r in result.incidents)
    groups = repo.metrics(MetricsArgs(group_by="category"))
    assert sum(groups.group_counts.values()) == 240


@pytest.mark.parametrize(
    "change",
    [
        {"customer_impact_count": -1},
        {"downtime_minutes": -1},
        {"severity": "critical"},
        {"status": "closed"},
        {"opened_at": "not a timestamp"},
        {"opened_at": "2026-01-01T00:00:00"},
        {"resolved_at": "2020-01-01T00:00:00Z"},
        {"status": "open"},
        {"estimated_cost": float("nan")},
    ],
)
def test_domain_rejects_invalid_records(change):
    record = generate_incidents()[0].model_dump()
    record.update(change)
    with pytest.raises(ValueError):
        Incident.model_validate(record)


def test_filter_validation():
    with pytest.raises(ValueError):
        MetricsArgs(since="2026-10-01T00:00:00Z", until="2026-01-01T00:00:00Z")
    with pytest.raises(ValueError):
        MetricsArgs(sql="DELETE FROM incidents")
    with pytest.raises(ValueError):
        SimilarIncidentArgs(limit=100)


@pytest.mark.parametrize(
    "column,value",
    [
        ("downtime_minutes", -1),
        ("severity", "critical"),
        ("opened_at", "nonsense"),
        ("customer_impact_count", -5),
        ("status", "open"),
    ],
)
def test_sqlite_checks_defend_against_invalid_seed_write(repo, column, value):
    with sqlite3.connect(repo.path) as con:
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(f"UPDATE incidents SET {column}=? WHERE incident_id='INC-001'", (value,))
