"""CI evidence only; reuse existing tests/guards without changing their behavior."""

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import sqlite3
import ssl
import sys
import xml.etree.ElementTree as ET
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "build/ci"
PROCESS_SUITES = (
    "test_service_process", "test_cli_process", "test_cli_evidence_process",
    "test_cli_monitor_process", "test_cli_annotations_process",
    "test_cli_follow_process", "test_cli_interact_process",
)
LIMITS = (
    "No physical UART/DUT, serial discovery, USB/driver or electrical acceptance.",
    "No safe-open DTR/RTS waveform or glitch acceptance.",
    "No native Windows or production Enhanced backend acceptance.",
    "Enhanced-shaped fixtures establish software neutrality only.",
    "Backend acknowledgement never proves wire transmission or DUT receipt.",
    "Phase 1 remains incomplete; hosted success requires evidence review.",
)
CHECK_COMMANDS = {
    "environment": "uv run --frozen --no-sync python tools/ci_acceptance.py snapshot JOB; "
    "uv --version; uname -a; gcc --version; ld --version; ldd --version",
    "ruff": "uv run --frozen --no-sync ruff check .",
    "mypy": "uv run --frozen --no-sync mypy .",
    "imports": "uv run --frozen --no-sync lint-imports",
    "diff": "git diff --check",
    "pytest": "uv run --frozen --no-sync python tools/ci_acceptance.py test tests",
    "reporter": "uv run --frozen --no-sync python -m pytest -q -W error "
    "tools/test_ci_acceptance.py --junitxml=build/ci/reporter.xml",
}


def write_json(name: str, value: object) -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / name).write_text(json.dumps(value, indent=2) + "\n")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot(job: str) -> None:
    # Only allowlisted metadata: never dump env, accounts, credentials or journals.
    write_json(f"{job}-environment.json", {
        "recorded_at_utc": datetime.now(UTC).isoformat(),
        "system": platform.system(), "kernel": platform.release(),
        "architecture": platform.machine(), "platform": platform.platform(),
        "os_release": platform.freedesktop_os_release()
        if sys.platform == "linux" else {},
        "python": sys.version, "libc": platform.libc_ver(),
        "sqlite": sqlite3.sqlite_version, "openssl": ssl.OPENSSL_VERSION,
        "github": {key: os.environ.get(key, "") for key in (
            "GITHUB_ACTIONS", "GITHUB_REPOSITORY", "GITHUB_SHA", "GITHUB_REF",
            "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "GITHUB_JOB", "RUNNER_OS",
            "RUNNER_ARCH", "ImageOS", "ImageVersion",
        )},
        "packages": dict(sorted(
            (d.metadata["Name"], d.version)
            for d in importlib.metadata.distributions()
        )),
        "inputs_sha256": {name: digest(ROOT / name) for name in (
            ".python-version", "uv.lock", "pyproject.toml",
            ".github/workflows/ci.yml", "tools/ci_acceptance.py",
        )},
    })


class ArchiveEvidence:
    """Copy only archives returned by the unchanged installed-test builders."""

    def __init__(self) -> None:
        self.archives: dict[str, dict[str, object]] = {}
        self.installs: set[str] = set()
        self.commands: list[dict[str, object]] = []

    def audit(self, event: str, args: tuple[Any, ...]) -> None:
        # Observe only packaging argv/cwd, never child environments or DUT argv.
        if event != "subprocess.Popen":
            return
        executable, argv, cwd, _env = args
        if (isinstance(executable, (str, bytes))
                and Path(os.fsdecode(executable)).name == "uv"
                and isinstance(argv, (list, tuple)) and len(argv) > 1
                and argv[1] in {"build", "venv", "pip"}):
            self.commands.append({"argv": list(argv), "cwd": str(cwd)})

    @pytest.hookimpl(wrapper=True)
    def pytest_fixture_setup(
        self, fixturedef: pytest.FixtureDef[Any], request: pytest.FixtureRequest,
    ) -> Generator[None, Any, Any]:
        result = yield
        if fixturedef.argname == "stack_artifacts":
            artifacts, _pins = result
            for package, pair in artifacts.items():
                for source in pair:
                    checksum = digest(source)
                    destination = OUTPUT / "packages" / source.name
                    previous = self.archives.get(source.name)
                    if previous is not None and previous["sha256"] != checksum:
                        raise RuntimeError("installed builders produced differing archives")
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, destination)
                    self.archives[source.name] = {
                        "package": package, "sha256": checksum,
                        "bytes": source.stat().st_size,
                        "path": str(destination.relative_to(ROOT)),
                    }
        elif fixturedef.argname == "installed_stack":
            if result.python.resolve().is_relative_to(ROOT):
                raise RuntimeError("installed acceptance environment is inside checkout")
            self.installs.add(str(request.param))
        return result


def run_tests() -> int:
    collector = ArchiveEvidence()
    sys.addaudithook(collector.audit)
    command = ["-q", "-W", "error", "--tb=short",
               f"--junitxml={OUTPUT / 'pytest.xml'}"]
    code = int(pytest.main(command, plugins=[collector]))
    write_json("installed-artifacts.json", {
        "archives": collector.archives, "installed_formats": sorted(collector.installs),
        "packaging_commands": collector.commands,
        "pytest_arguments": command, "pytest_exit_code": code,
    })
    return code


def test_results(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"complete": False, "reason": "JUnit missing"}
    cases = list(ET.parse(path).getroot().iter("testcase"))

    def count(selected: list[ET.Element]) -> dict[str, int]:
        return {"tests": len(selected), **{
            tag: sum(case.find(tag) is not None for case in selected)
            for tag in ("failure", "error", "skipped")
        }}

    suites = {name: count([case for case in cases
                          if case.get("classname", "").split(".")[-1] == name])
              for name in PROCESS_SUITES}
    totals = count(cases)
    audits = sum(
        case.get("classname", "").split(".")[-1] == "test_cli_interact_process"
        and case.get("name", "").startswith("test_t027_") for case in cases
    )
    return {
        "totals": totals, "installed_and_subprocess_suites": suites,
        "artifact_source_metadata_record_and_installed_import_audits": audits,
        "complete": totals["tests"] > 0
        and all(totals[tag] == 0 for tag in ("failure", "error", "skipped"))
        and all(row["tests"] > 0 for row in suites.values()) and audits == 5,
    }


def report(job: str, checks: dict[str, str]) -> int:
    environment = OUTPUT / f"{job}-environment.json"
    identity = json.loads(environment.read_text()) if environment.exists() else {}
    hosted_linux = (identity.get("system") == "Linux"
                    and identity.get("github", {}).get("GITHUB_ACTIONS") == "true")
    expected = ({"environment", "ruff", "mypy", "imports", "diff"}
                if job == "static" else {"environment", "reporter", "pytest"})
    passed = (bool(identity) and set(checks) == expected
              and all(value == "success" for value in checks.values()))
    results: dict[str, Any] = {}
    if job == "tests":
        results = test_results(OUTPUT / "pytest.xml")
        manifest = OUTPUT / "installed-artifacts.json"
        artifacts = json.loads(manifest.read_text()) if manifest.exists() else {}
        archives = artifacts.get("archives", {})
        passed &= (results["complete"] and len(archives) == 6
                   and artifacts.get("installed_formats") == ["sdist", "wheel"]
                   and artifacts.get("pytest_exit_code") == 0)
        for row in archives.values():
            archive = ROOT / row["path"]
            passed &= archive.is_file() and digest(archive) == row["sha256"]
    state = ("checks_passed_review_required" if passed and hosted_linux else
             "local_checks_only" if passed else "incomplete_or_failed")
    write_json(f"{job}-report.json", {
        "reported_at_utc": datetime.now(UTC).isoformat(),
        "reporter_sha256": digest(Path(__file__)),
        "state": state, "job": job, "checks": checks, "test_results": results,
        "commands": {key: CHECK_COMMANDS[key].replace("JOB", job)
                     for key in sorted(expected)},
        "environment": identity, "limits": LIMITS,
        "evidence_sha256": {p.name: digest(p) for p in OUTPUT.iterdir()
                            if p.is_file() and not p.name.endswith("-report.json")},
        "review_required": "Review both job reports from the same SHA/run/attempt, "
        "logs, JUnit and archive hashes before recording native Linux acceptance.",
    })
    summary = f"{job}: {state}. Native Linux acceptance is not automatically declared.\n"
    print(summary, end="")
    if "GITHUB_STEP_SUMMARY" in os.environ:
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a") as stream:
            stream.write(summary)
    return 0 if passed else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("snapshot", "test", "report"))
    parser.add_argument("job", choices=("static", "tests"))
    parser.add_argument("checks", nargs="*", help="fixed CI step name=outcome pairs")
    args = parser.parse_args()
    if args.operation == "snapshot":
        snapshot(args.job)
        return 0
    if args.operation == "test":
        if args.job != "tests":
            parser.error("test requires the tests job")
        return run_tests()
    return report(args.job, dict(pair.split("=", 1) for pair in args.checks))


if __name__ == "__main__":
    raise SystemExit(main())
