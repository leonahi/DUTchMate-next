# Tasks: Observation-Only Device Core Runtime

**Input**: `specs/005-observation-runtime/` spec, plan, research, data model,
internal contract, and quickstart.

**Status**: T001–T028 complete; software-complete. At T028, ready for final human
review/commit; current commit/progress status is in `docs/development_status.md`.
Fresh T028 gate: Ruff clean, mypy 40 files clean, three import
contracts kept (31 files/77 dependencies), pytest 924 passed with zero failures/
errors/skips, and diff/whitespace checks clean. No commit/human acceptance,
physical-hardware acceptance or Phase 1 completion is claimed.

Earlier implementation checkpoints: foundations, T006/T008 normal lifecycle,
T007/T009 Basic composition, and T010's six readback cases are GREEN.
T011 US1 regression review remains GREEN. T015 makes all 35 unchanged T012
request/cancellation cases GREEN (initially 20 RED/15 GREEN); earlier feature-005
cases remain GREEN. T016 makes all 22 unchanged T013 preparation cases GREEN;
T017 makes all 32 unchanged T014 cases GREEN after 29 RED/three GREEN, and all
27 T013 cases now pass. Combined focus passes 277; full suite passes 842.
T018 reviews US2 with 94 cases GREEN, targeted static/architecture checks, and
fresh full gate (842 passes). No defect/correction; production/tests unchanged.
T019 adds only shared fixture gates/counters and ten backend-fixture RED/GREEN
checks; at T019 full pytest passed 852. T020 adds 34 termination contracts:
33 expected RED failures and one GREEN unobserved-event case. Earlier feature
focus remains 277 GREEN. T021 adds 24 identical fixture lifecycle/readback cases:
initially 16 GREEN/eight expected RED. T022 implements autonomous termination/
terminal-before-active handling and disconnect precedence in runtime.py only.
All unchanged T020/T021 cases pass 58 after a fresh 41 RED/17 GREEN baseline;
whole feature focus passes 335, full pytest passes 910 with no failures/errors/
skips. Tests/fixtures and all other production remain unchanged.
T023 reviews US3/current/completed-feature regressions and architecture: 58 US3,
335 feature, 565 completed-feature and full 910 cases pass. No prohibited branch/
clock assumption, stale mutation or future behavior found; no code/test correction.
T024 reviews FR-001–030/full diff and corrects PreparationFailure exception
transport with 14 focused regressions (six RED/eight GREEN -> all GREEN).
Focus passes 349/full 924; contracts/schema/exports/deferrals remain unchanged.
T025 runs all 21 quickstart-focused test commands/five architecture-scope commands:
all pass, with no code/test correction. Final full-gate block stays deferred to T028.
T026 reconciliation was completed in development status/history; its marker is
now reconciled by T028 against that evidence, without rerunning the work.
T027's structural
trigger is met and one code-only incremental Graphify update completed:
2,435 nodes/6,370 edges/117 communities, no LLM extraction, output ignored.
T028's final fresh gate and diff review pass. Stop after T028; no further work
or hardware action was started in T028. Feature 005 was then uncommitted pending final human review.

**Tests**: Explicitly required by FR-028–030. Write meaningful deterministic
regressions before the related implementation; confirm RED, then GREEN.
Existing tests remain authoritative for completed-feature compatibility.

## Phase 1: Setup

**Purpose**: Reconcile actual starting state before future implementation.

- [x] T001 Review `docs/development_status.md`, `specs/005-observation-runtime/contracts/observation-runtime.md`, affected callers in `core/tests/`, and current git status/diff; verify the accepted `6d10cf7` code baseline or explain newer commits, then run focused existing Acquisition/Basic/Profile/SQLite tests using uv without hardware. Do not install dependencies or initialize new apps.

## Phase 2: Foundational contracts

**Purpose**: Establish truthful Acquisition lifecycle facts and immutable runtime
values before run orchestration. This is the first implementation task group.

- [x] T002 Add RED regressions in `core/tests/contract/test_acquisition_lifecycle.py` for returned descriptor versus committed provenance, origin-reset publication, observed disconnect before failed final append, actual `primary_failure_kind: AcquisitionFailureKind | None` separately from `close_failed`, clean None/false, close-only None/true with unchanged legacy TRANSPORT_FAILURE, combined primary/close failure, failed-open release uncertainty, and `join_terminated()` awaiting actual consumer/close completion. Prove legacy method return/failure behavior unchanged, generation-captured join results, and no future appends after the barrier.
- [x] T003 Implement only additive `AcquisitionSnapshot`, `snapshot()`, and `join_terminated()` in `core/src/dutchmate_core/acquisition.py`; preserve existing method return values and legacy failure behavior, while tracking first actual non-close `primary_failure_kind` separately at occurrence without decoding legacy failure/trigger/close combinations. Keep independent `close_failed`, committed provenance, trigger, and `physical_release_confirmed` (true only before open attempt or after successful returned-connection close); run T002 plus existing acquisition/Basic/durable acquisition regressions.
- [x] T004 Add RED immutable-value/status/preparation-contract tests in `core/tests/unit/test_runtime_model.py`: RunId is a fresh non-empty opaque string; run/profile are both absent initially and present after admission; unknown IDs remain absent; recorder policy must equal Profile policy by value; cleanup issues are an immutable tuple of at most two; raw exceptions/contexts are not status values; terminal provenance is historical. Cover the full state/owner_settled/cleanup matrix and impossible-status rejection, including settled owner with starting/acquiring/stopping Acquisition and runtime/snapshot release-certainty mismatch; `attach_admissible` is exactly `(state in {inactive, terminated, failed}) and owner_settled and physical_release_confirmed and recorder_close_confirmed`, never a supplied/stored override; initial settlement/cleanup facts make it true.
- [x] T005 Implement only planned values and minimal lifecycle contracts in `core/src/dutchmate_core/runtime.py` (RunId, state/intent/reason, RuntimeIssue, RuntimeStatus, RuntimeRejectedError including wrong_execution_context, PreparationFailure, PreparedObservationRun, ObservationRecorder, prepare callable). Make admissibility a derived read-only property using the exact predicate and validate authoritative owner_settled/state invariants. Extend existing contracts in `pyproject.toml` to forbid runtime-to-adapter imports and place runtime above Acquisition after the module exists. Run T004, focused static checks and Import Linter without adding exemptions or runtime attach/detach behavior.

**Checkpoint / exact first group**: T001–T005. Acquisition facts/join and runtime
values are verified; no orchestration/delivery/hardware behavior is built yet.

## Phase 3: User Story 1 - Own one durable observation run (P1)

**Goal**: Happy-path admitted prepare/start, capture, status, and ordered detach.
**Independent test**: Fake Basic + temporary Profile/journal; binary ambient
capture, detach, reopen, bounded evidence readback.

- [x] T006 [P] [US1] Add RED normal-run contract tests in `core/tests/contract/test_observation_runtime.py` for construction-time running-loop/thread binding (no-loop construction rejected), same-context attach/detach/nonmutating synchronous status, wrong-loop/thread/no-running-loop API rejection before locks/mutation/preparation, no rebinding after termination, direct resolved-Profile busy rejection with zero Profile I/O/preparation, fresh identity/session association, exact policy, gated status, idempotent detach, and final append/consumer/close completion before recorder close. Read-only returned snapshots may be inspected elsewhere without permitting runtime calls there.
- [x] T007 [P] [US1] Add RED edge tests in `core/tests/contract/test_observation_composition.py` for nonmutating context guard before bounded explicit Profile resolution, resolution before admission even when busy (invalid Profile can fail first), zero journal create/open/backend construct/open/hardware enumeration or other run preparation on busy rejection, exact journal policy/path, journal-before-backend startup, existing-file rejection without overwrite/open, immutable source snapshot, and fake-only serial access.
- [x] T008 [US1] Implement normal generation-owned lifecycle in `core/src/dutchmate_core/runtime.py`: constructor binds immediately to its running loop/thread, APIs guard context before locks/mutation/preparation, synchronous status projects without mutation/scheduling, and admission uses the exact derived predicate. Add admitted prepare/start, fresh Acquisition, short publication lock, active-result settlement, caller stop, joins before recorder close, and one immutable current/last summary; publish owner_settled only after generation work is joined/quiescent. Expose no resource/task handles, cross-thread dispatch, process lock, or new retrieval surface; run T006.
- [x] T009 [US1] Implement concrete `attach_basic_observation` and preparation closure in `core/src/dutchmate_core/adapters/observation_runtime.py`: nonmutating owning-context guard first, bounded explicit Profile resolution next without a busy precheck/reservation, authoritative runtime admission next, and existing SQLite/Basic preparation only if admitted. Busy may incur that Profile read but no run-resource preparation. Keep explicit paths/private fake seams at this edge; run T007 with hardware sentinel intact.
- [x] T010 [US1] Add and run end-to-end temp-journal/fake-Basic readback tests in `core/tests/integration/test_observation_runtime.py`, covering exact binary/ambient evidence, final segment boundaries, retention/expiry under small quotas, unchanged fixed-snapshot pages, and no recoverable full-Profile claim after reopen.
- [x] T011 [US1] Run focused US1 and completed-feature regressions from `specs/005-observation-runtime/quickstart.md` plus targeted Ruff/mypy/Import Linter checks; correct only defects within `core/src/dutchmate_core/runtime.py`, `core/src/dutchmate_core/adapters/observation_runtime.py`, and the explicitly allowed Acquisition additions.

**Checkpoint**: Happy-path development MVP. Not feature completion/release:
US2 cancellation/failure and US3 autonomous termination remain mandatory.

## Phase 4: User Story 2 - Serialize requests and clean up failures (P2)

**Goal**: Fail-fast competing attach, coalesced detach, cancellation-resistant
ownership, retained artifacts, and honest cleanup/reuse outcomes.
**Independent test**: Deterministic gates/races/failures at each external stage.

- [x] T012 [P] [US2] Add RED request/cancellation race tests in `core/tests/contract/test_observation_runtime.py` for concurrent already-resolved runtime attach rejection without Profile I/O/preparation, owning-context validation before mutation, detach during attach, simultaneous detach, first stop intent, cancellation before admission/at prepare/open/append/read/close, cancellation after internal active publication, repeated cancellation, and captured old-generation waiter results after a new attach.
- [x] T013 [P] [US2] Add RED failure/ownership-transfer tests in `core/tests/contract/test_observation_composition.py` for create-before/after-commit failure, allowed pre-open certainty exceptions, construction failure after known create, failed open, recorder policy mismatch, retained empty/partial files, no artifact identity probing/reopen/deletion, and normalized failure without raw cause/context leakage.
- [x] T014 [US2] Add RED failure/teardown tests in `core/tests/contract/test_observation_runtime.py` for direct snapshot `primary_failure_kind`/`close_failed` projection with no legacy inference, first primary plus at most two ordered cleanup issues, failed first/final append, failed connection/journal close, consumer join despite errors, derived admissibility throughout pending/terminal cleanup, permanent uncertainty blocking, idempotent terminal detach, and fresh-destination retry only after confirmed cleanup.
- [x] T015 [US2] Implement fail-fast already-resolved runtime admission using the exact derived predicate after owning-context validation, stop-intent arbitration, captured-generation results, shielded owner work, and cancellation-resistant attach/detach waiters in `core/src/dutchmate_core/runtime.py`; never hold a lifecycle lock during external I/O, cancel the owner, or submit another open. Run T012.
- [x] T016 [US2] Implement partial-preparation cleanup and normalized PreparationFailure in `core/src/dutchmate_core/adapters/observation_runtime.py`; keep created journal files and known IDs, affirm pre-open closure only for structural validation or CREATE invalid_input/journal_exists, and mark other create failures unconfirmed without probing. Run T013.
- [x] T017 [US2] Implement independent physical/recorder certainty, direct snapshot primary/close projection (no legacy Acquisition.failure decoding), first-primary preservation, ordered bounded cleanup facts, failed-open conservative blocking, and permanent uncertain-cleanup rejection via the exact derived predicate in `core/src/dutchmate_core/runtime.py`. Ensure recorder close follows Acquisition join even on failure; run T014 plus Acquisition regressions.
- [x] T018 [US2] Run all US2 regressions and targeted static/architecture checks from `specs/005-observation-runtime/quickstart.md`; retain deterministic race gates and eliminate no-op-close/reset paths that falsely clear uncertainty in `core/src/dutchmate_core/runtime.py` and its composition adapter.

## Phase 5: User Story 3 - Report termination without backend assumptions (P3)

**Goal**: Autonomous disconnect/failure cleanup, exact status/cause precedence,
and identical shared behavior on both normalized backend shapes.
**Independent test**: Parameterized lifecycle with real temp journals and fake
Basic/Enhanced-shaped events, without wire/hardware simulation.

- [x] T019 [US3] Extend only deterministic current-contract lifecycle gates in `core/tests/fakes.py`, reusing Enhanced-shaped device timestamps, observer loss, origin reset, normalized non-serial disconnect, and reported RX rejection. Do not add GPIO/helper/USB/firmware behavior or Enhanced Profile selection.
- [x] T020 [P] [US3] Add RED status/immediate-disconnect/active-disconnect/recording-failure/racing-stop tests in `core/tests/contract/test_observation_runtime.py`; assert actual Acquisition trigger beats stop intent, failures independently force failed state, terminal provenance is historical, no reopen occurs, and late tasks cannot publish to a new generation.
- [x] T021 [P] [US3] Parameterize shared lifecycle and durable readback assertions in `core/tests/integration/test_observation_runtime.py` identically over fake Basic and Enhanced-shaped preparation, including binary/ambient bytes, timestamp domains, scoped loss, origin resets, explicit missing-RX rejection, cleanup ordering, fresh explicit subsequent sessions, and unchanged journal schema/version.
- [x] T022 [US3] Implement autonomous Acquisition termination observation and direct primary_failure_kind/close_failed projection in `core/src/dutchmate_core/runtime.py`, keeping terminal cause independent and using only normalized snapshots, no legacy-failure decoding/private fields/evidence reconstruction. Keep all callbacks on the owning loop/thread and handle terminal-before-active publication and committed provenance distinctions; run T020/T021.
- [x] T023 [US3] Run all US3/current-feature tests with completed Acquisition/Basic/Profile/SQLite regressions and architecture checks from `specs/005-observation-runtime/quickstart.md`; remove any backend-identity branch, host-clock assumption, stale-generation mutation, or simulated future capability discovered in shared code/tests.

## Phase 6: Review, verification, and completion documentation

- [x] T024 Review full diff against `specs/005-observation-runtime/spec.md` FR-001–030 and `contracts/observation-runtime.md`; inspect changed consumers/exports in `core/` and `pyproject.toml`, verify unchanged schema-v1/evidence/Backend contracts, no new dependency/exemption, no paths in status, no unbounded summary history, and preserved deferrals. Correct real scope/contract defects with focused regressions.
- [x] T025 Run the focused scenarios and scope searches in `specs/005-observation-runtime/quickstart.md` against `core/tests/`; fix only demonstrated failures. Defer its final full-gate block to T028 to avoid an unnecessary duplicate run.
- [x] T026 Update `docs/development_status.md` and append newest-first completed-slice evidence to `docs/development_history.md`; keep Resume Here within about 40 lines and distinguish software acceptance from unexecuted hardware cases. Reconcile baseline/commit references without claiming a commit that has not happened.
- [x] T027 Read Graphify guidance in `docs/agent_tooling.md`, assess the actual structural diff (`core/src/dutchmate_core/runtime.py`, composition module, and Acquisition interface additions), and run exactly one code-only incremental Graphify update if these planned changes satisfy its structural trigger; record actual result in `docs/development_history.md`, keeping generated output ignored.
- [x] T028 Use verification-before-completion and run the fresh full gate from `AGENTS.md`: uv Ruff, mypy, Import Linter, hardware-free pytest, and git diff --check. Record actual outputs/counts in `docs/development_status.md` and `docs/development_history.md`, review the final diff, rerun diff checking after documentation edits, and leave no failed required check or unsupported hardware claim.

## Dependencies and execution order

```text
T001 -> T002 -> T003 -> T004 -> T005
  -> US1 (T006–T011)
  -> US2 (T012–T018)
  -> US3 (T019–T023)
  -> review/completion (T024–T028)
```

Tests precede the code they validate: T006 -> T008; T007 -> T009;
T012 -> T015; T013 -> T016; T014 -> T017; T020/T021 -> T022.
T019 precedes T020/T021. US2/US3 depend on the same runtime established by
US1; do not assign competing implementation edits to that module.

Parallel opportunities are limited to separate test files with satisfied
prerequisites. Within US1, T006/T007 can be drafted together after T005;
within US2, T012/T013 after T011; within US3, T020/T021 after T019.
T014 shares a file with T012 and therefore follows it. Parallel markers describe
file independence, not authorization to spawn agents automatically.

## Requirement coverage

| Requirements | Tasks |
|---|---|
| FR-001–007 (state/admission/serialization) | T004–006, T008, T012, T015, T020, T022 |
| FR-008–010 (startup/teardown) | T002–003, T006–010, T013–017 |
| FR-011–016 (failure/cancellation/session creation) | T012–018 |
| FR-017–020 (association/status/schema) | T004–010, T020–022, T024 |
| FR-021–024 (termination/uncertainty/Acquisition) | T002–003, T014–017, T020–023 |
| FR-025–027 (composition/architecture/compatibility) | T005, T007–010, T016, T021, T024 |
| FR-028–030 (neutrality/software validation) | T019–025, T028 |

## Implementation strategy

The exact first implementation group is **T001–T005**, setup plus foundational
contracts. No runtime orchestration begins until that group is verified.
Then develop US1's happy path, add US2 safety semantics, and finish US3
autonomous termination/neutrality. All three are required for this slice's
completion; a happy-path demo is not accepted Phase 1/runtime completion.

Task counts: setup 1, foundation 4, US1 6, US2 7, US3 5, final review 5;
total 28. Six tasks are marked parallel: T006/T007, T012/T013, and T020/T021
form three pairs. T001–T025 have been delivered; US1 and all 35 T012 cases are
GREEN. T015 implements request/cancellation behavior after verified T012 RED.
T016 made all 22 T013 preparation cases GREEN; T017 makes all 27 T013 and 32
T014 cases GREEN. T018 review verifies all 94 US2 cases without code correction.
T019 fixture gates are verified GREEN. T020/T021 initially recorded 41 RED/
17 GREEN; T022 makes all 58 unchanged cases GREEN. T023 verifies regressions/
architecture without correction. T024 corrects preparation exception transport
after full review. T025's focused scenarios/scope checks pass without code changes;
T026 reconciliation, T027's structural update and T028's fresh final gate/diff
review are complete. T026's marker now reflects its existing completion record.
All 28 tasks are checked; at T028 the software-only feature was ready for final
human review and commit. That checkpoint implied no further work or accepted-baseline
advancement; current commit/progress status remains in development status.
