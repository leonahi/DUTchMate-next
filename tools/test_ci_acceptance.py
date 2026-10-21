"""Fail-closed reporting checks; no product behavior or external resources."""

import json
from pathlib import Path
from typing import Any

import pytest
from tools import ci_acceptance as ci


@pytest.fixture
def evidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(ci, "ROOT", tmp_path)
    monkeypatch.setattr(ci, "OUTPUT", tmp_path)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    ci.write_json("tests-environment.json", {
        "system": "Linux", "github": {"GITHUB_ACTIONS": "true"},
    })
    cases = [f'<testcase classname="{name}" name="guarded"/>'
             for name in ci.PROCESS_SUITES]
    cases += [f'<testcase classname="test_cli_interact_process" '
              f'name="test_t027_audit[{n}]"/>' for n in range(5)]
    (tmp_path / "pytest.xml").write_text(
        "<testsuites><testsuite>" + "".join(cases) + "</testsuite></testsuites>"
    )
    archives = {}
    for n in range(6):
        path = tmp_path / f"package-{n}.whl"
        path.write_bytes(bytes([n]))
        archives[path.name] = {"path": path.name, "sha256": ci.digest(path)}
    ci.write_json("installed-artifacts.json", {
        "archives": archives, "installed_formats": ["sdist", "wheel"],
        "pytest_exit_code": 0,
    })
    return tmp_path


def run_report() -> int:
    return ci.report("tests", {
        "environment": "success", "reporter": "success", "pytest": "success",
    })


def read_report(path: Path) -> dict[str, Any]:
    return dict(json.loads((path / "tests-report.json").read_text()))


def test_success_still_requires_review(evidence: Path) -> None:
    assert run_report() == 0
    assert read_report(evidence)["state"] == "checks_passed_review_required"


def test_other_features_t027_names_do_not_replace_012_audits(evidence: Path) -> None:
    junit = evidence / "pytest.xml"
    junit.write_text(junit.read_text().replace(
        "</testsuite>", '<testcase classname="test_legacy" name="test_t027_other"/>'
        "</testsuite>",
    ))
    assert run_report() == 0
    result = read_report(evidence)["test_results"]
    assert result["artifact_source_metadata_record_and_installed_import_audits"] == 5
    junit.write_text(junit.read_text().replace(
        'classname="test_cli_interact_process" name="test_t027_audit[0]"',
        'classname="test_legacy" name="test_t027_audit[0]"',
    ))
    assert run_report() == 1


@pytest.mark.parametrize("system,hosted", [("Darwin", "true"), ("Linux", "false")])
def test_local_run_cannot_claim_hosted_acceptance(
    evidence: Path, system: str, hosted: str,
) -> None:
    ci.write_json("tests-environment.json", {
        "system": system, "github": {"GITHUB_ACTIONS": hosted},
    })
    assert run_report() == 0
    assert read_report(evidence)["state"] == "local_checks_only"


@pytest.mark.parametrize("problem", [
    "failure", "error", "skipped", "missing-suite", "missing-audit", "missing-junit",
    "missing-environment", "missing-manifest", "missing-archive", "changed-archive",
    "missing-format", "nonzero-exit",
])
def test_incomplete_evidence_fails(evidence: Path, problem: str) -> None:
    junit = evidence / "pytest.xml"
    manifest = evidence / "installed-artifacts.json"
    if problem in {"failure", "error", "skipped"}:
        junit.write_text(junit.read_text().replace(
            'name="guarded"/>', f'name="guarded"><{problem}/></testcase>', 1,
        ))
    elif problem == "missing-suite":
        junit.write_text(junit.read_text().replace(ci.PROCESS_SUITES[0], "other"))
    elif problem == "missing-audit":
        junit.write_text(junit.read_text().replace("test_t027_audit[0]", "other"))
    elif problem.startswith("missing-") and problem.split("-", 1)[1] in {
        "junit", "environment", "manifest", "archive",
    }:
        {"missing-junit": junit, "missing-environment": evidence / "tests-environment.json",
         "missing-manifest": manifest, "missing-archive": evidence / "package-0.whl"}[
             problem].unlink()
    elif problem == "changed-archive":
        (evidence / "package-0.whl").write_bytes(b"changed")
    else:
        value = json.loads(manifest.read_text())
        if problem == "missing-format":
            value["installed_formats"] = ["wheel"]
        else:
            value["pytest_exit_code"] = 1
        ci.write_json("installed-artifacts.json", value)
    assert run_report() == 1
    assert read_report(evidence)["state"] == "incomplete_or_failed"


def test_missing_or_failed_checks_cannot_pass(evidence: Path) -> None:
    assert ci.report("tests", {}) == 1
    assert ci.report("tests", {"environment": "success", "pytest": "failure"}) == 1


def test_packaging_audit_ignores_child_credentials_and_non_uv_commands() -> None:
    collector = ci.ArchiveEvidence()
    collector.audit("subprocess.Popen", (
        "python", ["python", "child"], "/tmp", {"credential": "private"},
    ))
    collector.audit("subprocess.Popen", (
        "uv", ["uv", "build", "--offline"], "/tmp", {"credential": "private"},
    ))
    assert collector.commands == [{"argv": ["uv", "build", "--offline"], "cwd": "/tmp"}]
