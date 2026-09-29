---

description: "Implementation tasks for the continuous RX evidence foundation"
---

# Tasks: Continuous RX Evidence Foundation

**Input**: Design documents from `specs/001-rx-continuous-evidence/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, and
`contracts/normalized-backend.md`

**Tests**: Required. Write each listed test first, confirm it fails for the
intended missing behavior, then implement the smallest passing behavior.

**Organization**: Tasks follow the three prioritized user stories and preserve
one independently testable checkpoint per story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Safe to execute in parallel after its prerequisites because it
  touches different files
- **[Story]**: Maps to a user story in `spec.md`

## Phase 1: Setup

**Purpose**: Establish the smallest reproducible Python/core workspace.

- [x] T001 Create the Python 3.14 uv workspace with `requires-python = ">=3.14,<3.15"`, shared dev dependencies, pytest/ruff/mypy configuration, and `3.14` in `.python-version` using `pyproject.toml` and `.python-version`, then generate `uv.lock` with uv
- [x] T002 Create the `dutchmate-core` package metadata and intentionally minimal import surface in `core/pyproject.toml` and `core/src/dutchmate_core/__init__.py`
- [x] T003 Add enforceable import-linter layering and ruff banned-API rules for the existing `dutchmate_core` modules in `pyproject.toml` without exemptions or references to nonexistent packages

**Checkpoint**: `uv sync --all-packages --dev` succeeds, the empty core package
imports, and no service, CLI, adapter, or MCP package exists.

---

## Phase 2: Foundational Test Harness

**Purpose**: Prepare shared test collection without implementing product
behavior.

- [x] T004 Create hardware-free pytest package markers and shared fixture factories in `core/tests/__init__.py`, `core/tests/conftest.py`, `core/tests/contract/__init__.py`, `core/tests/unit/__init__.py`, and `core/tests/integration/__init__.py`; fixtures must never discover or open host serial devices

**Checkpoint**: pytest collects the core test tree with no physical hardware
access.

---

## Phase 3: User Story 1 - Preserve Continuous Authoritative UART Evidence (Priority: P1) 🎯 MVP

**Goal**: One owned receive-capable connection has one continuously running RX
consumer, and arbitrary binary observations become ordered authoritative
evidence even when no workflow exists.

**Independent Test**: Feed arbitrary binary chunks around an idle period through
the Basic-shaped fixture; verify one consumer and exact ordered reconstruction.

### Tests for User Story 1

- [x] T005 [P] [US1] Write failing capability, ID, non-empty RX, and all-256-byte exact-payload tests in `core/tests/unit/test_model.py`
- [x] T006 [P] [US1] Write failing atomic consecutive-sequence, immutable snapshot, exact-byte, and append-failure tests in `core/tests/unit/test_evidence.py`
- [x] T007 [P] [US1] Create the minimal Basic-shaped connection fixture and failing single-consumer/disconnect contract tests in `core/tests/fakes.py` and `core/tests/contract/test_backend.py`, plus failing idle-period, second-start rejection, arbitrary-chunking, and explicit-recorder-failure tests in `core/tests/integration/test_acquisition.py`

### Implementation for User Story 1

- [x] T008 [US1] Implement immutable capabilities, opaque connection/segment IDs, base event validation, and evidence record types required by the failing US1 model tests in `core/src/dutchmate_core/model.py`
- [x] T009 [US1] Implement the normalized backend and single-consumer owned-connection protocols required by the US1 contract tests in `core/src/dutchmate_core/backend.py`
- [x] T010 [US1] Implement the recorder protocol and in-memory atomic append-only recorder required by US1 in `core/src/dutchmate_core/evidence.py`
- [x] T011 [US1] Implement exclusive start/stop, continuous event consumption, ambient RX recording, disconnect handling, and explicit failure behavior in `core/src/dutchmate_core/acquisition.py`

**Checkpoint**: US1 tests pass independently; reconstructing RX evidence returns
exact bytes, acquisition survives an idle/no-workflow interval, and a second RX
path is rejected.

---

## Phase 4: User Story 2 - Preserve Timing and Connection Provenance (Priority: P2)

**Goal**: Every observation has honest domain/origin and segment provenance,
while Core sequence—not timestamp—defines order.

**Independent Test**: Feed repeated timestamps, an origin reset, a stale prior-
connection event, and a disconnect; verify sequence order and segment isolation.

### Tests for User Story 2

- [x] T012 [P] [US2] Extend `core/tests/unit/test_model.py` with failing validation/comparison tests for host/device observer, observation meaning, units, opaque origins, non-negative values, and rejection of cross-domain or cross-origin comparison
- [x] T013 [P] [US2] Extend `core/tests/integration/test_acquisition.py` with failing tests for equal-timestamp sequence ordering, segment start/end records, backend-observation origin-reset transition, stale prior-connection rejection, and current backend-observation domain validation

### Implementation for User Story 2

- [x] T014 [US2] Implement backend-observation timestamp domains, observation timestamps, segment provenance, and guarded same-domain comparison in `core/src/dutchmate_core/model.py`
- [x] T015 [US2] Implement initial segment snapshots, origin-reset close/open ordering, stale-connection isolation, and segment terminal reasons in `core/src/dutchmate_core/acquisition.py`

**Checkpoint**: US2 tests pass independently on the Basic-shaped fixture;
identical timestamps remain distinctly ordered, origin reset creates a new
segment, and no host timestamp is presented as DUT time or universal time.

---

## Phase 5: User Story 3 - Prove Backend Neutrality (Priority: P3)

**Goal**: The same shared behavior passes against Basic-shaped host/no-telemetry
and Enhanced-shaped device/overflow fixtures without backend identity branches.

**Independent Test**: Parameterize the backend contract and acquisition suite
over both fixtures and record Enhanced-shaped counted overflow with explicit
observer scope and device timestamp.

### Tests for User Story 3

- [x] T016 [US3] Add the test-only Enhanced-shaped fixture with device-domain timestamps, observer-scoped counted overflow, and non-serial disconnect semantics in `core/tests/fakes.py`; extend `core/tests/unit/test_model.py` with failing unknown-vs-zero loss validation tests
- [x] T017 [US3] Parameterize identical backend and acquisition behavior assertions over both fixtures and add explicit capability rejection/no-lossless-claim checks in `core/tests/contract/test_backend.py` and `core/tests/integration/test_acquisition.py`

### Implementation for User Story 3

- [x] T018 [US3] Implement loss-observability variants, observer-loss event/evidence validation, and normalized recording in `core/src/dutchmate_core/model.py` and `core/src/dutchmate_core/acquisition.py` without inspecting backend identity

**Checkpoint**: US3 shared tests pass unchanged for both shapes; counted overflow
is correctly positioned evidence, missing Basic telemetry remains explicitly
unobservable, and the fixture contains no Enhanced protocol or hardware model.

---

## Phase 6: Validation and Documentation

**Purpose**: Prove the completed slice remains within its architecture and
document its actual status without claiming hardware support.

- [x] T019 Add or update import-linter contracts for the now-existing core modules in `pyproject.toml`, run the neutrality/scope scan from `specs/001-rx-continuous-evidence/quickstart.md`, inspect every match, and remove any backend-identity branch, serial/framework dependency, later-phase behavior, or stale reference from `core/src/` and `core/tests/`
- [x] T020 Run `uv run ruff check .`, `uv run mypy .`, `uv run lint-imports`, `uv run pytest`, and `git diff --check`; record exact results and do not claim completion while any required command fails
- [x] T021 Update `docs/development_status.md` and prepend the completed software-only slice record to `docs/development_history.md`, including validation evidence, deferred real Basic adapter work, no hardware action, and no Enhanced hardware-support claim

**Checkpoint**: The required software gate passes, documentation matches the
implemented baseline, and no physical device has been accessed.

**Final review finding**: T019–T021 are complete, but the specification's Edge
Cases require an undeclared decreasing timestamp in the current domain/origin
to fail explicitly. The implemented acquisition path validates the current
domain and now detects that regression using the last successfully recorded
timestamp in the active segment. The conformance gap is closed.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: starts immediately in T001 order because T003 revisits
  root configuration created by T001.
- **Test Harness (Phase 2)**: depends on Setup.
- **US1 (Phase 3)**: depends on the test harness and is the MVP.
- **US2 (Phase 4)**: depends on US1 evidence/acquisition behavior.
- **US3 (Phase 5)**: depends on US1 and US2 normalized provenance behavior.
- **Validation (Phase 6)**: depends on all selected user stories.

### User Story Dependencies

- **US1**: no story dependency; delivers exact continuous RX evidence.
- **US2**: depends on US1 recorder/acquisition types but has an independent
  provenance test checkpoint.
- **US3**: depends on US1/US2 shared semantics and independently proves
  neutrality by parameterization.

### Within Each User Story

- Execute listed test tasks first and confirm intended failures.
- Implement only behavior required to make those tests pass.
- Run the story's focused tests before moving to the next story.
- Do not introduce deferred APIs while satisfying a test.

### Parallel Opportunities

- After T004, T005, T006, and T007 may be written in parallel because they
  target separate test files/support files.
- Other implementation tasks are intentionally sequential because they build
  the same small contract and later tasks modify shared files.
- T019 and documentation preparation for T021 may begin after US3, but T021 must
  record the final T020 results.

## Parallel Example: User Story 1

```text
Task T005: Write model/value tests in core/tests/unit/test_model.py
Task T006: Write recorder tests in core/tests/unit/test_evidence.py
Task T007: Write fake/contract/acquisition tests in core/tests/fakes.py,
           core/tests/contract/test_backend.py, and
           core/tests/integration/test_acquisition.py
```

## Parallel Example: User Story 2

```text
Task T012: Write backend-observation timestamp-domain model tests in
           core/tests/unit/test_model.py
Task T013: Write segment/acquisition tests in
           core/tests/integration/test_acquisition.py
```

## Parallel Example: User Story 3

US3 is intentionally sequential: T016 creates the Enhanced-shaped fixture,
T017 consumes it in shared contract/acquisition tests, and T018 implements only
the normalized behavior those tests require.

## Implementation Strategy

### MVP First

1. Complete T001–T004.
2. Complete T005–T011 with red-green-refactor discipline.
3. Run the US1 checkpoint and stop if exact-byte or single-RX-path behavior is
   not proven.

### Incremental Delivery

1. **US1**: exact continuous evidence and exclusive RX ownership.
2. **US2**: honest timestamp/segment provenance without changing US1 behavior.
3. **US3**: backend-neutral proof and explicit loss telemetry.
4. **Validation**: full gate and status/history update.

## Notes

- No task may open real hardware; any future hardware test must be separately
  specified, explicitly configured, marked, and excluded from the default run.
- The Enhanced-shaped fixture is test code only and must never be described as
  Enhanced backend implementation or acceptance.
- `snapshot()` on the in-memory recorder is test support, not a public evidence
  retrieval contract.
- Do not create HTTP, CLI, MCP, persistence-format, Monitor/Interact, TX,
  control, reconnect, release/reacquire, or firmware code while executing these
  tasks.
