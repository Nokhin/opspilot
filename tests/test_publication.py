"""Ensure redacting the latest tree cannot hide unsafe historical content."""

import os
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from scripts.check_publication import (
    audit_directory,
    audit_repository,
    content_violations,
    public_path,
)
from scripts.sanitize_junit import sanitize_junit


def run_git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, env={**os.environ, "TZ": "UTC"}
    )


def repository(root: Path) -> None:
    run_git(root, "init", "-b", "main")
    run_git(root, "config", "user.name", "Example Maintainer")
    run_git(root, "config", "user.email", "123+example@users.noreply.github.com")
    run_git(root, "config", "commit.gpgsign", "false")


def commit(root: Path) -> None:
    run_git(root, "add", ".")
    run_git(root, "commit", "-m", "Example snapshot")


def test_publication_scope_excludes_private_context() -> None:
    for name in (
        "private/originals/README.md",
        "AGENTS.md",
        "docs/TASKS.md",
        ".env.live",
        "evaluation/secret.db",
    ):
        assert not public_path(name)
    assert public_path("docs/ARCHITECTURE.md")
    assert public_path("evaluation/final_acceptance/run/pytest.xml")


def test_history_check_detects_removed_sensitive_blob(tmp_path: Path) -> None:
    repository(tmp_path)
    address = "sample" + "@" + "invalid.test"
    readme = tmp_path / "README.md"
    readme.write_text(address)
    commit(tmp_path)
    readme.write_text("Public documentation\n")
    commit(tmp_path)
    report = audit_repository(tmp_path)
    assert not report["passed"]
    assert any(row["reason"] == "non_placeholder_email" for row in report["violations"])
    assert address not in str(report)


def test_history_check_detects_removed_private_file(tmp_path: Path) -> None:
    repository(tmp_path)
    draft = tmp_path / "private" / "draft.md"
    draft.parent.mkdir()
    draft.write_text("Unpublished context\n")
    commit(tmp_path)
    draft.unlink()
    (tmp_path / "README.md").write_text("Public documentation\n")
    commit(tmp_path)
    assert not audit_repository(tmp_path)["passed"]


def test_history_check_rejects_non_noreply_identity(tmp_path: Path) -> None:
    repository(tmp_path)
    run_git(tmp_path, "config", "user.email", "sample" + "@" + "invalid.test")
    (tmp_path / "README.md").write_text("Public documentation\n")
    commit(tmp_path)
    report = audit_repository(tmp_path)
    assert any(row["reason"] == "identity_requires_noreply" for row in report["violations"])


def test_clean_history_passes_with_annotated_tag(tmp_path: Path) -> None:
    repository(tmp_path)
    (tmp_path / "README.md").write_text("Public documentation\n")
    commit(tmp_path)
    run_git(tmp_path, "tag", "-a", "v1", "-m", "Example release")
    report = audit_repository(tmp_path)
    assert report["passed"]
    assert report["commits"] == 1


def test_history_check_requires_utc_metadata(tmp_path: Path) -> None:
    repository(tmp_path)
    (tmp_path / "README.md").write_text("Public documentation\n")
    run_git(tmp_path, "add", ".")
    subprocess.run(
        ["git", "commit", "-m", "Example snapshot"],
        cwd=tmp_path,
        env={**os.environ, "TZ": "Pacific/Tahiti"},
        check=True,
        capture_output=True,
    )
    report = audit_repository(tmp_path)
    assert any(row["reason"] == "identity_requires_utc" for row in report["violations"])


def test_directory_guard_rejects_symlink(tmp_path: Path) -> None:
    (tmp_path / "README.md").symlink_to("unpublished.txt")
    report = audit_directory(tmp_path, public_scope=True)
    assert not report["passed"]
    assert report["violations"][0]["reason"] == "symlink"


def test_local_sensitive_values_do_not_echo_matches() -> None:
    value = "unpublished-identifier"
    assert content_violations(value.encode(), {"local_sensitive_value": [value]}) == [
        "local_sensitive_value"
    ]


def test_junit_normalization_preserves_test_results(tmp_path: Path) -> None:
    path = tmp_path / "pytest.xml"
    path.write_text(
        '<testsuite hostname="example-device.local" timestamp="2026-01-02T10:00:00+02:00" '
        'tests="1" failures="0" time="1.5"><testcase name="example" time="1.5"/></testsuite>'
    )
    sanitize_junit(path)
    suite = ET.parse(path).getroot()
    assert "hostname" not in suite.attrib
    assert suite.attrib["timestamp"] == "2026-01-02T08:00:00Z"
    assert suite.attrib["tests"] == "1"
    assert suite.attrib["failures"] == "0"
    assert suite.attrib["time"] == "1.5"
    assert suite[0].attrib == {"name": "example", "time": "1.5"}
