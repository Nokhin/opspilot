"""Check publication scope, Git objects, identities, and artifact contents.

This is a deterministic publication guard, not a universal PII detector. Optional
local sensitive values strengthen the check without recording them in reports.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path, PurePosixPath

PUBLIC_ROOT_FILES = frozenset(
    {
        ".dockerignore",
        ".env.example",
        ".env.live.example",
        ".gitignore",
        "Dockerfile",
        "README.md",
        "THIRD_PARTY_NOTICES.md",
        "compose.yaml",
        "pyproject.toml",
        "requirements-dev.lock",
        "requirements.lock",
    }
)
PUBLIC_DOCUMENTS = frozenset(
    {
        "docs/ARCHITECTURE.md",
        "docs/DEPLOYMENT.md",
        "docs/EVALUATION.md",
        "docs/FICTIONAL_ENTERPRISE.md",
        "docs/FINAL_ACCEPTANCE.md",
        "docs/LIVE_LLM_VALIDATION.md",
        "docs/releases/v1.0-rag-tools-evals.md",
    }
)
PUBLIC_SCRIPTS = frozenset(
    {
        "scripts/__init__.py",
        "scripts/check_publication.py",
        "scripts/sanitize_junit.py",
    }
)
PUBLIC_PREFIXES = ("opspilot/", "corpus/policies/", "tests/", "evaluation/")
PUBLIC_SUFFIXES = frozenset(
    {
        ".py",
        ".sql",
        ".md",
        ".txt",
        ".json",
        ".jsonl",
        ".csv",
        ".xml",
        ".html",
        ".js",
        ".css",
        ".jpg",
        ".png",
    }
)
EMAIL = re.compile(r"[A-Za-z0-9_.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PATTERNS = {
    "academic_or_career_context": re.compile(
        r"\bcourse\s*\d+\b|\bcoursera\b|\bprofessional certificate\b|\bCV[- ]ready\b",
        re.IGNORECASE,
    ),
    "personal_home_path": re.compile(r"(?:/Users|/home)/[A-Za-z0-9_.-]+/"),
    "personal_device_hostname": re.compile(r"\b[\w.-]*MacBook[\w.-]*\.local\b", re.IGNORECASE),
    "credential_literal": re.compile(r"\b(?:sk-[A-Za-z0-9_-]{24,}|gh[pousr]_[A-Za-z0-9]{24,})\b"),
}


def public_path(name: str) -> bool:
    """Allow only reviewed source, documentation, and synthetic evidence paths."""
    path = PurePosixPath(name)
    if path.is_absolute() or any(
        part in {"..", "private", ".git", "__pycache__"} for part in path.parts
    ):
        return False
    if name in PUBLIC_ROOT_FILES | PUBLIC_DOCUMENTS | PUBLIC_SCRIPTS:
        return True
    if name == ".github/workflows/ci.yml":
        return True
    return name.startswith(PUBLIC_PREFIXES) and path.suffix in PUBLIC_SUFFIXES


def content_violations(
    data: bytes, sensitive_values: dict[str, list[str]] | None = None
) -> list[str]:
    """Return categories only; never echo a matching credential or identifier."""
    violations = []
    for label, values in (sensitive_values or {}).items():
        if any(value and value.encode() in data for value in values):
            violations.append(label)
    if data.startswith(b"\xff\xd8") or data.startswith(b"\x89PNG"):
        if any(
            marker in data for marker in (b"Exif\x00\x00", b"http://ns.adobe.com/xap/", b"eXIf")
        ):
            violations.append("image_metadata")
        return violations
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return violations + ["unexpected_binary_content"]
    for label, pattern in PATTERNS.items():
        if pattern.search(text):
            violations.append(label)
    for address in EMAIL.findall(text):
        domain = address.rsplit("@", 1)[1].lower()
        if domain not in {"example.test", "example.com", "example.org", "users.noreply.github.com"}:
            violations.append("non_placeholder_email")
            break
    return sorted(set(violations))


def git(repository: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=repository, stderr=subprocess.PIPE)


def audit_repository(
    repository: Path, sensitive_values: dict[str, list[str]] | None = None
) -> dict:
    """Inspect all stored objects, including unreachable objects, and every commit tree."""
    objects = [
        row.split()
        for row in git(
            repository,
            "cat-file",
            "--batch-all-objects",
            "--batch-check=%(objectname) %(objecttype)",
        )
        .decode()
        .splitlines()
    ]
    commits = [oid for oid, kind in objects if kind == "commit"]
    reachable = git(repository, "rev-list", "--all").decode().splitlines()
    violations = []
    if not reachable:
        violations.append({"location": "repository", "reason": "no_commits"})
    if set(commits) != set(reachable):
        violations.append({"location": "repository", "reason": "unreachable_commits"})
    paths = set()
    for commit in commits:
        for row in git(repository, "ls-tree", "-rz", "--full-tree", commit).split(b"\0"):
            if not row:
                continue
            metadata, raw_name = row.split(b"\t", 1)
            name = raw_name.decode()
            paths.add(name)
            mode = metadata.split()[0]
            if mode not in {b"100644", b"100755"} or not public_path(name):
                violations.append(
                    {"location": f"{commit}:{name}", "reason": "unapproved_path_or_mode"}
                )
    for oid, kind in objects:
        if kind not in {"blob", "commit", "tag"}:
            continue
        raw = git(repository, "cat-file", kind, oid)
        for reason in content_violations(raw, sensitive_values):
            violations.append({"location": f"{kind}:{oid}", "reason": reason})
        if kind in {"commit", "tag"}:
            identities = [
                line
                for line in raw.decode().splitlines()
                if line.startswith(("author ", "committer ", "tagger "))
            ]
            for identity in identities:
                match = re.search(r"<([^<>]+)>", identity)
                if not match or not match[1].endswith("@users.noreply.github.com"):
                    violations.append(
                        {"location": f"{kind}:{oid}", "reason": "identity_requires_noreply"}
                    )
                if not identity.endswith(" +0000"):
                    violations.append(
                        {"location": f"{kind}:{oid}", "reason": "identity_requires_utc"}
                    )
    return {
        "passed": not violations,
        "commits": len(commits),
        "reachable_commits": len(reachable),
        "objects": len(objects),
        "historical_paths": len(paths),
        "violations": violations,
    }


def audit_directory(
    directory: Path,
    public_scope: bool = False,
    sensitive_values: dict[str, list[str]] | None = None,
) -> dict:
    """Check a clean export or artifact directory without following symlinks."""
    violations = []
    files = 0
    for path in sorted(directory.rglob("*")):
        relative = path.relative_to(directory)
        if ".git" in relative.parts:
            continue
        name = relative.as_posix()
        if path.is_symlink():
            violations.append({"location": name, "reason": "symlink"})
        elif path.is_file():
            files += 1
            if public_scope and not public_path(name):
                violations.append({"location": name, "reason": "unapproved_path"})
            for reason in content_violations(path.read_bytes(), sensitive_values):
                violations.append({"location": name, "reason": reason})
    return {"passed": not violations, "files": files, "violations": violations}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--repository", type=Path)
    target.add_argument("--directory", type=Path)
    parser.add_argument("--public-scope", action="store_true")
    parser.add_argument(
        "--sensitive-values", type=Path, help="Ignored local JSON; values are never echoed"
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    values = json.loads(args.sensitive_values.read_text()) if args.sensitive_values else None
    if args.repository:
        result = audit_repository(args.repository, values)
    else:
        result = audit_directory(args.directory, args.public_scope, values)
    rendered = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    print(rendered, end="")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
