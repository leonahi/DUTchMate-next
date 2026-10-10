# Tasks: Observation CLI

**Input**: [spec.md](spec.md), [plan.md](plan.md), [research.md](research.md),
[data-model.md](data-model.md), [contract](contracts/observation-cli.md).
**Status**: T001–T025 and separately authorized final pre-commit review complete.
Fresh2261 tests passed, zero failures/errors/skips; Ruff/mypy61 files/7 import
contracts/diff checks clean. Complete24-file staged/installability review passed;
no new defect or source/test/config/dependency/contract change. This snapshot belongs
to `Implement observation CLI` (Git revision `:/^Implement observation CLI`).
Native evidence remains macOS only; Linux/Windows/native active-DUT/hardware unrun.
**Tests**: Required by FR-026–029; meaningful contract RED → GREEN before new behavior.
**Baseline**: main c2c9ce3;006 implementation b4c5730; preserve001–006 semantics.

Checklist format: sequential IDs; [P] identifies independent test files, not
automatic delegation authorization; [USn] identifies story work. A separate user
instruction controls which group executes. Stop first group after T005.

## Phase 1: Setup

- [X] T001 Read docs/development_status.md, Core and active007/006 contracts; inspect git status/HEAD/diff and apps/service/ with core/src/dutchmate_core/runtime.py; verify c2c9ce3 or explain newer baseline. Run existing006 selection in specs/007-observation-cli/quickstart.md with actual parent/child hardware/account guards. No resources/dependencies yet.
- [X] T002 Create minimal apps/cli/pyproject.toml, ruff.toml and src/dutchmate_cli/__init__.py; add workspace member and Typer>=0.27.3,<0.28/HTTPX>=0.28.1,<0.29 via uv --package dutchmate-cli, verifying public TyperException/Abort API, HTTPcore>=1.0.9,<2 and all35 old locked versions unchanged. Extend root pyproject.toml test/mypy/import contracts after package exists; add isolated apps/cli/tests/conftest.py hardware/real-account guards. No console entry until main.py exists, no commands/HTTP/core/service dependencies or blanket product lint exemptions.

## Phase 2: Foundational context and credential boundary

- [X] T003 Add RED apps/cli/tests/test_cli_context.py: host exactly127.0.0.1/default or::1; actual port exact integer1..65535; attach paths absolute POSIX1..4096 UTF-8 bytes/no NUL/no file checks; fixed passwd/effective-UID credential path ignoring HOME/XDG/overrides; no-follow descriptor traversal; regular effective-UID0600/nlink1;65 expected bytes plus one detection byte; exact64 lowercase hex+LF; readonly cleanup and fixed failures. Prohibit lock/marker/write/repair/Profile/journal I/O.
- [X] T004 Implement only typed invocation/context, read-only credential helper and fixed ordinary CliFailure categories in apps/cli/src/dutchmate_cli/context.py to make T003 GREEN. No auth-policy/bootstrap ownership replica, service/Core imports, frozen exception transport, Typer callback, network or user-input diagnostics.
- [X] T005 Verify T003 RED/GREEN, installed package/SDK imports, unchanged001–006 contracts and full appropriate uv Ruff/mypy/Import Linter/hardware-free pytest/diff gate; record actual foundation results in docs/development_status.md and newest-first docs/development_history.md. Stop T001–T005 before T006.

**Exact first implementation group: T001–T005.** Package/tooling and endpoint/
credential primitives only. HTTP, console entry and Typer commands remain later.

## Phase 3: US1 - Help and authenticated status (P1)

**Goal**: Safe help/usage and one authenticated existing status exchange.
**Independent test**: Actual credentials/006 gate with Typer help and wrapper privacy,
closed reported facts, one HTTP request, no run-resource preparation.

- [X] T006 [P] [US1] Add RED apps/cli/tests/test_cli_commands.py for pure root callback, global --host/--port ordering, no-command/root/status help0 with no account/credential/network/platform I/O; missing/invalid target and unknown/input-bearing arguments fixed invalid_arguments2; no completion/version/URL/token/env/output-mode additions. Test CliRunner grammar plus direct console wrapper, public Typer interrupt/error handling without exception.show/text/locals.
- [X] T007 [P] [US1] Add RED apps/cli/tests/test_cli_transport.py for one status request with exact Host including port80/IPv6 brackets and one Bearer, no Origin/proxy/env/redirect/retry/DNS/fallback;10s absolute/5s phase limits; raw uncompressed accumulation<=1048577/accepted<=1048576; strict UTF-8/media/duplicate/nonfinite/closed006 wire/output bounds; all six states and fixed HTTP/local exit/envelope mappings. No duplicated domain predicates or raw diagnostics.
- [X] T008 [US1] Implement one concrete async HTTPX exchange and wire-shape validation in apps/cli/src/dutchmate_cli/client.py; explicit client/transport settings, outer monotonic deadline, raw streaming cap and normalized local categories/delivery phase. Make T007 GREEN; no global HTTP owner, generic client/DTO framework, service/Core imports or mutation timing.
- [X] T009 [US1] Implement pure Typer root/status command and console main wrapper in apps/cli/src/dutchmate_cli/main.py; register dutchmate script in apps/cli/pyproject.toml only now. Use public pinned Typer APIs/standalone_mode=False, help0, fixed diagnostics, no pretty locals/logs; valid200 report stdout/exit0 including failed, remote error stderr/exit4. Make T006 GREEN; no attach/detach behavior yet.
- [X] T010 [US1] Run US1 commands from specs/007-observation-cli/quickstart.md, targeted/static/import checks and actual006 authenticated status integration in apps/cli/tests/test_cli_transport.py; inspect HTTPX/httpcore/Typer logging/error paths and fix only demonstrated007 security/transport/projection defects. US1 is not complete lifecycle/console-process acceptance.

## Phase 4: US2 - Existing attach/detach delivery (P2)

**Goal**: Expose accepted service lifecycle while keeping capture/service ownership intact.
**Independent test**: Fake Basic plus temporary SQLite through actual006 authentication;
client exits while ambient evidence remains and explicit detach follows005.

- [X] T011 [US2] Add RED apps/cli/tests/test_cli_lifecycle.py and attach/detach grammar in test_cli_commands.py: explicit --profile/--journal bounded absolute strings mapped to exact006 fields, no CLI file checks; bodyless detach, missing/extra/unsupported options, no service/autostart/defaults; existing busy/Profile/runtime/HTTP categories; every valid200 report including failed exits0. Use real guarded006 composition and zero CLI resource imports/calls.
- [X] T012 [US2] Add only Typer attach/detach wiring in apps/cli/src/dutchmate_cli/main.py and necessary fixed request mapping in client.py to make T011 GREEN; lexical context before credential/network, at most one request, no retry/preflight/status follow-up/implicit detach or duplicated Profile/journal/lifecycle logic.
- [X] T013 [US2] Add reported-fact/privacy/failure/idle-binary regressions in apps/cli/tests/test_cli_lifecycle.py: primary versus cleanup/trigger/certainty separation, nullable committed IDs, immutable reported Profile and no recomputed admissibility. Run identical report assertions against existing Basic/Enhanced-shaped fixtures; real temporary journal readback stays in tests only. Record genuine RED only if new gaps appear.
- [X] T014 [US2] Correct only demonstrated T013 new-client presentation/integration defects in apps/cli/src/dutchmate_cli/main.py and client.py with focused regression evidence. If none, record no defect without production change; never revise001–006 policy/schema/runtime/security or implement evidence delivery.
- [X] T015 [US2] Run US2/006/completed-core selections from specs/007-observation-cli/quickstart.md plus static/import/scope checks; record results in docs/development_history.md, confirming one service owner/RX and client exit never detaches. Real installed SIGINT/process acceptance remains US3.

## Phase 5: US3 - Client deadlines, interruption and privacy (P3)

**Goal**: Finite client delivery with honest unknown outcomes and safe installed console.
**Independent test**: Gated service mutations/slow responses, installed-process SIGINT,
empty/closed output and private diagnostic sentinels; hardware-free only.

- [X] T016 [P] [US3] Add deadline/loss/phase regressions in apps/cli/tests/test_cli_transport.py: slow headers/empty waits/continual trickling10s total,5s phases, overflow chunks sliced not exact socket cap, invalid/partial responses, no automatic requests, and request_outcome not_submitted→unknown→report_received independent of service admission. Actual006 admitted attach/detach must settle after client loss; record genuine RED if any.
- [X] T017 [US3] Correct only T016-demonstrated client waiting/cancellation/bounds issues in apps/cli/src/dutchmate_cli/client.py and context.py; no sync HTTP worker, retry, service signal/detach or Core timeout. If already GREEN, record no defect without code changes.
- [X] T018 [P] [US3] Add installed console-process tests in apps/cli/tests/test_cli_process.py with parent/child hardware/real-account guards: main(args) privacy/exits distinct from CliRunner, first/repeated SIGINT130/public Typer returned interrupt, private argv/credential/exception sentinels, closed stdout/stderr, actual IPv4/IPv6 auth and outside-cwd imports. Verify wheel/sdist/entry through uv into temporary locations; no product external-program launcher.
- [X] T019 [US3] Correct only T018-demonstrated entry-wrapper/log/interrupt/output defects in apps/cli/src/dutchmate_cli/main.py and client.py; suppress default value echo/tracebacks, preserve local delivery phase and never change006 admitted ownership. If no defect, record that without production changes.
- [X] T020 [US3] Execute all US3 and completed001–006 regressions in specs/007-observation-cli/quickstart.md plus static/import/installability checks; report mocked/native/platform/IPv6 evidence honestly, inspect privacy/guard preservation and record actual results in docs/development_history.md. No hardware/Windows/Linux acceptance claim from macOS.

## Phase 6: Final review and completion

- [X] T021 Review full intended tracked/untracked diff against specs/007-observation-cli/spec.md FR-001–030, contracts/observation-cli.md, Core and001–006; inspect apps/cli/, pyproject.toml/uv.lock for bootstrap/domain copies, secret logging, unsafe help/transport, unnecessary dependencies, generated/runtime files or accidental deferrals. Fix genuine007 defects minimally with regression evidence only; do not weaken imports or revise Core.
- [X] T022 Execute all focused quickstart scenarios and exact scope searches in specs/007-observation-cli/quickstart.md; correct only demonstrated007 failures. Do not run the final full-gate block assigned to T025 automatically.
- [X] T023 Reconcile docs/development_status.md and newest-first docs/development_history.md with actual CLI scope, progress, committed baseline, limits and unexecuted OS/hardware cases; Resume Here about40 lines maximum, no unmade commit/acceptance claim.
- [X] T024 Read docs/agent_tooling.md and assess actual CLI/package/dependency-interface structural changes; if triggered, run exactly one code-only incremental Graphify update, record evidence in docs/development_history.md and keep output ignored. No update for planning only.
- [X] T025 Use verification-before-completion; run fresh full uv Ruff/mypy/Import Linter/hardware-free pytest/git diff --check gate and inspect final intended diff/installability/task markers. Record actual counts in docs/development_status.md and docs/development_history.md; rerun diff checks after docs. Stop without automatic commit/push/next slice or physical hardware.

## Dependencies and execution order

T001 → T002 → T003 RED → T004 GREEN → T005 → US1(T006–T010)
→ US2(T011–T015) → US3(T016–T020) → final(T021–T025).

Tests precede required new behavior: T006/T007→T008/T009; T011→T012.
Additional regressions precede corrections: T013→T014; T016→T017; T018→T019.
T016/T018 can be authored independently after US2; corrections remain sequential.
No status-only MVP bypasses lifecycle/installed-process acceptance.

## Parallel opportunities

- T006 grammar and T007 transport tests are independent files after foundation.
- T016 transport lifetime and T018 process tests are independent after US2.
- These describe scheduling only; no automatic sub-agent authorization or competing
  production edits. The planning research agents wrote no files.

## Requirement coverage

| Requirements | Tasks |
|---|---|
| FR-001–004 command/framework/target/help | T002,T003–004,T006,T009,T011–012 |
| FR-005–009 credential/security/HTTP targeting | T003–004,T007–010,T018–020 |
| FR-010–012 lexical inputs/exact requests | T003–004,T011–012,T015 |
| FR-013–015 deadlines/raw bounds/wire validation | T007–008,T016–017 |
| FR-016–019 reports/error/envelopes/exits | T006–009,T011–014,T018–019 |
| FR-020–022 loss/phase/privacy | T007–010,T013–014,T016–020 |
| FR-023–025 architecture/no resource/platform | T002–005,T011–015,T018–021 |
| FR-026–028 meaningful console/auth/fixture proof | T006–020 |
| FR-029–030 gates/deferrals | T005,T010,T015,T020–025 |

## Implementation strategy and counts

Setup/foundation5; US1 five; US2 five; US3 five; final five; total25.
Four [P] test tasks in two pairs. T001–T025 delivered;no task remains unchecked.
First group is exactly T001–T005, with no Typer commands/HTTP/console/service changes.
Use contract-driven RED/GREEN for new behavior and only genuine regression failures
for corrections; do not manufacture failures when earlier behavior already satisfies
the contract. Update current status and completed evidence at the stated checkpoints.
No Spec Kit rerun, commit, push, Graphify refresh or hardware action is implied.
