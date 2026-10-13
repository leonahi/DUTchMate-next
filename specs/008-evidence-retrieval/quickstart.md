# Validation Walkthrough: Bounded Evidence Retrieval

This walkthrough defines acceptance; executed software evidence and unexecuted
platform/hardware limits are recorded in [current status](../../docs/development_status.md)
and [history](../../docs/development_history.md). It is not hardware evidence.
Commands assume the repository root, uv and repository Python3.14. RTK is an output
wrapper only. Test paths were created by the matching completed tasks.

## First implementation group: T001–T005 only

Read Core §§14–18/22–23,008 spec/plan/contract and current status; inspect git status
and capture the unchanged001–007/schema/Profile baseline. Run existing validation
before creating tests. Use a failing sync/async context-manager regression for003
JournalFailure, then minimally correct exception transport. Add only pure read
port/value/failure definitions and meaningful focused validation. No runtime reads,
terminal adapter, service route or CLI command is implemented in this group.

```bash
rtk proxy git status --short
rtk proxy uv run pytest core/tests/unit/test_evidence_failures.py core/tests/unit/test_evidence_access_values.py
rtk proxy uv run ruff check .
rtk proxy uv run mypy .
rtk proxy uv run lint-imports
rtk proxy uv run pytest
rtk proxy git diff --check
```

Before files exist, baseline uses the full gate, not a command naming missing tests.
Record genuine RED, exact GREEN and stage gate results in status/history. Stop at
T005 unless subsequent work is explicitly authorized.

## Story acceptance after implementation

| Story | Focused files/scenarios | Required proof |
|---|---|---|
| US1 active | core/tests/contract/test_evidence_access.py; core/tests/integration/test_evidence_access.py; apps/service/tests/test_evidence_http.py; apps/cli/tests/test_cli_evidence.py | One existing RX/journal worker gate, both fixture shapes, all256 bytes, actual auth, known session only, pin/replace/seal/close, old007 regressions. |
| US2 terminal | core/tests/contract/test_terminal_evidence_reader.py plus runtime/service tests | Writer closed before terminal read; per-query URI mode=ro/query_only; unchanged database/no recovery writes; full-v1 identity/session/policy validation; failed preparation, unavailable source, primary/close failures and dirty cleanup latch. |
| US3 pages | shared Core retrieval tests plus HTTP/CLI evidence tests | Stable MAX reference, frozen snapshot across append/eviction, all four outcomes, markers/domains, complete+truncated, empty shortage page, exact required charge, token canonicality, independent wire/JSON caps and whole413 rejection. |
| US4 finite delivery | apps/service/tests/test_evidence_reads.py; apps/cli/tests/test_cli_evidence_process.py | Read/mutation capacity independence, pre-Core jobs, waiter/worker lifetime, shutdown join, false cleanup stays dirty, installed outside-cwd entries, real guarded loopback/auth, private errors, help/SIGINT/closed pipes. |

Tests create their own journals/credentials and use existing fake/Enhanced-shaped
fixtures. Patch forbidden serial/open/account/credential boundaries in the parent
and actual CLI/service child processes; a parent-only guard does not prove child
safety. Native service runs with an explicitly supplied fake composition; never run
an installed attach against physical serial or a real account/service credential.
No port discovery, arbitrary journal search or automatic cleanup retry.

Examples of the implemented grammar (do not run against an actual listener during
planning; explicit session must come from a separately requested status report):

```text
dutchmate evidence --help
dutchmate evidence record --help
dutchmate evidence page --help
dutchmate --port PORT evidence record --session SESSION --sequence 0
dutchmate --port PORT evidence page --session SESSION --max-records 32 --max-charged-bytes 65536
dutchmate --port PORT evidence page --session SESSION --max-records 32 --max-charged-bytes 65536 --start 0 --end 100 --cursor TOKEN
```

One explicit query returns one complete compact JSON envelope plus LF. RX is
canonical standard padded base64, never UART text. A valid200 complete/partial/
expired/not_found report exits0. Recognized remote rejection exits4. Bounds/malformed
replies/interrupt/closed pipes retain007 private local error/receipt behavior. No
automatic status, follow, second page, smaller retry, export, detach or service signal.

## Final software gate and review

Run the full uv/Ruff/mypy/import-linter/pytest/diff gate above fresh after all changes.
Rebuild/install wheel and sdist with locked dependencies in separate temporary
environments, run actual entry/help/imports outside cwd, and exercise guarded
process cases. Check no mandatory editable/local path, undeclared package data,
unrelated dependency upgrade, weak architecture contract or generated/private file.
Review all003/005–007 regressions and new requirements against the whole diff.

Keep schema-v1/Profile-v1/Core/old feature contracts unchanged. Update current status
and newest-first history with actual results; assess Graphify once after structural
implementation, not during this documentation-only planning. Native macOS evidence
does not imply native Linux/Windows or active-DUT/electrical acceptance. No hardware
action, commit, push or later slice is part of the final T035 authorization.
