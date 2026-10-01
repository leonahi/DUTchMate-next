# Tasks: Durable Evidence Journal

**Input**: Design documents from `/specs/003-durable-evidence-journal/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`,
`contracts/durable-evidence-journal.md`, `quickstart.md`

**Tests**: This feature changes durability, ordering, retention, recovery, and
schema behavior. Every behavioral group follows RED/GREEN TDD; confirm each RED
failure is caused by the intentionally missing contract before production code.

**Organization**: T001–T005 establish the concrete boundary. User-story phases
then deliver durable append, honest retention, and bounded retrieval in
dependency order. No task authorizes physical hardware access.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel because it changes different files and has no
  dependency on another incomplete task in the same group
- **[US1]**, **[US2]**, **[US3]**: Maps the task to the specification user story
- Every task names its expected files

## Phase 1: Concrete Journal Foundation

**Purpose**: Establish validated durable values, normalized provenance storage,
and the schema-version-1 SQLite boundary before append behavior.

- [x] T001 Create `core/src/dutchmate_core/adapters/sqlite_evidence.py`,
  `core/tests/unit/test_evidence_journal_model.py`,
  `core/tests/unit/test_sqlite_evidence_codec.py`,
  `core/tests/contract/test_sqlite_evidence_journal.py`, and
  `core/tests/integration/fixtures/sqlite_recovery_worker.py` skeletons; add or
  extend `pyproject.toml` architecture/import guards only if the new adapter is
  not already covered, and add no runtime dependency.
- [x] T002 Add RED model tests in
  `core/tests/unit/test_evidence_journal_model.py` for `SessionId`, finite
  `SessionPolicy` with independent retrieval ceilings, signed-64-bit sequence
  and counter bounds, normalized scalar-only
  `ConnectionProvenanceSnapshot` envelope versus opaque backend kind/version,
  stable record/range references, empty ranges, retention marker endpoints,
  retrieval values, and normalized journal failures; confirm failures are the
  missing feature-003 values.
- [x] T003 Implement only the T002 immutable values and validation in
  `core/src/dutchmate_core/model.py` and `core/src/dutchmate_core/evidence.py`,
  preserving feature-001 evidence types and in-memory recorder behavior.
- [x] T004 Add RED codec/create/open tests in
  `core/tests/unit/test_sqlite_evidence_codec.py` and
  `core/tests/contract/test_sqlite_evidence_journal.py` for every current
  evidence variant, all 256 RX byte values, canonical strict metadata,
  deterministic charge, exact payload BLOBs, one-session schema metadata,
  stored `max_database_pages` with per-writable-connection
  `max_page_count` reapply/verify and over-bound rejection, supported generic
  envelope version, known/unknown opaque backend provenance snapshots, and
  instrumented proof that create/open/use/close stay on one journal worker
  thread; confirm the failures are the absent concrete journal and codecs.
- [x] T005 Implement only schema-version-1 create/open and strict codecs in
  `core/src/dutchmate_core/adapters/sqlite_evidence.py`, the generic provenance
  snapshot producer contract in `core/src/dutchmate_core/model.py`, and the
  Basic snapshot mapping in
  `core/src/dutchmate_core/adapters/basic_serial.py`; establish the
  journal-private single-thread executor/async gate and create/use/close the
  connection only on its worker thread; make T001–T004 GREEN and run focused
  Ruff, mypy, Import Linter, pytest, and `git diff --check` without implementing
  append, retention, or retrieval.

**Checkpoint**: The repository has one concrete versioned storage boundary and
round-trip codec, but no production durable append yet.

---

## Phase 2: User Story 1 - Durable authoritative append (Priority: P1) 🎯 MVP

**Goal**: Commit exact evidence with durable session sequence and recover it
after reopen or process termination.

**Independent Test**: Append every current record variant, reopen, and continue
sequence; run subprocess recovery cases and acquisition against the journal.

### RED tests for User Story 1

- [x] T006 [US1] Add RED contract tests in
  `core/tests/contract/test_sqlite_evidence_journal.py` for first/continued
  sequence, every evidence variant, exact binary bytes, commit-before-return,
  signed-64-bit sequence/counter exhaustion before mutation, cancellation after
  blocking append begins, serialization gate retention until the worker
  finishes, close waiting for admitted work, close/reopen continuation,
  idempotent close, post-close rejection, and normalized failures.
- [x] T007 [US1] Add RED subprocess tests in
  `core/tests/integration/test_sqlite_recovery.py` and commands in
  `core/tests/integration/fixtures/sqlite_recovery_worker.py` for abrupt exit
  after acknowledgment, interruption before commit, and commit-before-return
  ambiguity; assert only previous or complete committed state is recovered.

### Implementation for User Story 1

- [x] T008 [US1] Implement serialized off-event-loop atomic append and
  commit-before-acknowledgment in
  `core/src/dutchmate_core/adapters/sqlite_evidence.py` using the one-thread
  executor and cancellation-safe held gate, including checked durable
  sequence/counter updates, cancellation-after-commit ambiguity, rollback,
  close coordination, and normalized failures required by T006.
- [x] T009 [US1] Implement reopen/recovery and post-recovery invariant
  validation required by T007 in
  `core/src/dutchmate_core/adapters/sqlite_evidence.py`; do not add repair,
  migration, retry deduplication, or a power-loss claim.
- [x] T010 [US1] Add RED adapter-through-acquisition tests in
  `core/tests/integration/test_durable_acquisition.py` for ambient exact RX,
  segment/provenance round trip, journal sequence authority, recording-failure
  termination, and restart append into the same session using Basic and the
  Enhanced-shaped fixture.
- [x] T011 [US1] Make T010 GREEN with only narrowly required integration changes
  in `core/src/dutchmate_core/evidence.py` or
  `core/src/dutchmate_core/adapters/sqlite_evidence.py`; shared acquisition in
  `core/src/dutchmate_core/acquisition.py` must continue to depend only on
  `EvidenceRecorder` and must not branch on storage/backend identity.
- [x] T012 [US1] Run the quickstart durable-append/recovery selections, full
  feature-001/002 regressions affected by recorder/provenance changes, targeted
  Ruff/mypy/Import Linter, and `git diff --check`; record exact results before
  starting retention.

**Checkpoint**: A one-session journal durably appends and reopens authoritative
evidence; retention has not yet been enabled.

---

## Phase 3: User Story 2 - Bounded rolling retention and stable expiry (Priority: P2)

**Goal**: Keep the retained journal bounded while preserving explicit discard
provenance and stable expired/partial/not-found reference outcomes.

**Independent Test**: Exceed deterministic count/byte quotas repeatedly and
resolve references on both sides of the low-water boundary.

### RED tests for User Story 2

- [x] T013 [US2] Add RED retention tests in
  `core/tests/contract/test_sqlite_evidence_journal.py` for count and charged
  byte limits, minimum-oldest-prefix selection, sequence non-reuse, atomic
  append-plus-retention, persisted-versus-effective physical ceiling,
  `page_count` already over policy, and inability to establish the requested
  effective `max_page_count`, with the two normalized capacity reasons kept
  distinct.
- [x] T014 [US2] Add RED marker tests in
  `core/tests/contract/test_sqlite_evidence_journal.py` for one coalesced row
  across 1,000 passes, discarded record count, exact discarded RX payload-byte
  count, discarded charged-byte count, absence of redundant discard high-water
  state, no-timestamp ranges, and first/last timestamp endpoints retaining
  incomparable domain/origin provenance without duration claims.
- [x] T015 [US2] Add RED failure tests in
  `core/tests/contract/test_sqlite_evidence_journal.py` for individually
  oversized records, cumulative retention-counter exhaustion, page/full
  capacity failure, and transaction rollback; prove no prior evidence is
  evicted or marker/counter changed on failure.

### Implementation for User Story 2

- [x] T016 [US2] Implement minimum-prefix rolling retention, coalesced marker,
  deterministic aggregates, and physical page-cap handling atomically with
  append in `core/src/dutchmate_core/adapters/sqlite_evidence.py`; make
  T013–T015 GREEN without changing evidence sequence/timestamp semantics.
- [x] T017 [US2] Add RED stable-reference tests in
  `core/tests/contract/test_sqlite_evidence_journal.py` for retained record,
  wholly expired range, partially expired range, `[x,x)` complete for every
  `x <= next_sequence` regardless of low water, empty range not-found only for
  `x > next_sequence`, never-existent sequence/range, partially never-existent
  range suffix, and session mismatch.
- [x] T018 [US2] Implement single/range reference resolution and explicit
  retained/expired/partial/not-found outcomes in
  `core/src/dutchmate_core/adapters/sqlite_evidence.py`; return current marker
  metadata without silently partial success.
- [x] T019 [US2] Run the quickstart retention/reference selection, acquisition
  recording-failure tests, marker boundedness check, targeted static and
  architecture checks, and `git diff --check`; record exact results before
  pagination.

**Checkpoint**: Durable evidence is rolling-bounded and every discarded prefix
remains explicit through one constant-size marker and stable references.

---

## Phase 4: User Story 3 - Bounded stable retrieval (Priority: P3)

**Goal**: Retrieve raw evidence in bounded fixed-snapshot sequence pages.

**Independent Test**: Page with small limits while appends and retention
advance; verify no duplicates, new append leakage, silent expiry, or partial
records.

### RED tests for User Story 3

- [x] T020 [US3] Add RED page tests in
  `core/tests/contract/test_sqlite_evidence_journal.py` for required positive
  caller limits capped by independent finite retrieval record/byte ceilings,
  proof that a large retained-byte quota does not enlarge pages, policy
  rejection when a record cannot fit the page-byte ceiling, exact boundary
  fits, complete/truncated pages, oversized-next-record reporting, and cursor
  progression by sequence rather than offset/timestamp.
- [x] T021 [US3] Add RED snapshot/concurrency tests in
  `core/tests/contract/test_sqlite_evidence_journal.py` for exclusion of later
  appends, expiry between pages, cursor/session/range mismatch, and proof that a
  returned cursor holds no live SQLite transaction or lock; cancellation of a
  blocking retrieval must retain the gate until its worker finishes and delay
  close or the next operation.

### Implementation for User Story 3

- [x] T022 [US3] Implement bounded raw page retrieval and typed keyset cursor
  validation in `core/src/dutchmate_core/adapters/sqlite_evidence.py`, with
  page/outcome values in `core/src/dutchmate_core/evidence.py`; never split a
  record or order by timestamp.
- [x] T023 [US3] Implement fixed snapshot upper bounds and explicit
  between-page expiry handling in
  `core/src/dutchmate_core/adapters/sqlite_evidence.py`; make T020–T021 GREEN
  without adding external cursor encoding or delivery schemas.
- [x] T024 [US3] Run the quickstart retrieval selection plus all durable journal
  model/codec/contract/integration tests, feature-001 evidence ordering and
  timestamp regressions, targeted static/architecture checks, and
  `git diff --check`.

**Checkpoint**: The three user stories are independently testable and together
provide durable append, bounded honest retention, and bounded retrieval.

---

## Phase 5: Compatibility, Corruption, and Completion

**Purpose**: Close failure/recovery coverage, verify no scope or boundary leak,
and reconcile project status.

- [x] T025 Add RED compatibility/corruption tests in
  `core/tests/contract/test_sqlite_evidence_journal.py` and
  `core/tests/integration/test_sqlite_recovery.py` for wrong application ID,
  unsupported store/record/generic provenance-envelope versions, opaque
  round-trip of unknown backend provenance kind/schema versions, missing schema
  objects,
  malformed metadata/payload invariants, aggregate/sequence corruption,
  `quick_check` failure, locked/read-only paths, and no writes after validation
  failure apart from explicitly permitted preceding rollback recovery.
- [x] T026 Implement only the fail-closed validation and stable error
  classification needed by T025 in
  `core/src/dutchmate_core/adapters/sqlite_evidence.py`; do not add migration,
  repair, salvage, or error-message-dependent behavior, and distinguish the
  permitted preceding SQLite rollback recovery from post-validation writes.
- [x] T027 Run every exact command in
  `specs/003-durable-evidence-journal/quickstart.md`, including full
  feature-001/002 regression groups, and confirm the default fail-closed serial
  guard prevents physical hardware access.
- [x] T028 Review the complete feature-003 diff and focused `rg` matches for
  SQLite/Basic leakage into shared Core, pickle/class-name persistence,
  unbounded retrieval/metadata, timestamp ordering, duplicate RX paths,
  accidental session orchestration, delivery APIs, later-phase behavior,
  temporary debugging code, and stale contracts; correct only genuine
  feature-003 defects with regression tests.
- [x] T029 Update `docs/development_status.md` and prepend
  `docs/development_history.md` only after implementation is complete, recording
  the exact durability limitation and software validation; evaluate the
  Graphify structural-change criteria in `docs/agent_tooling.md` and update it
  once only if required.
- [x] T030 Use `verification-before-completion` and run
  `uv run --frozen ruff check .`, `uv run --frozen mypy .`,
  `uv run --frozen lint-imports`, `uv run --frozen pytest`, and
  `git diff --check`; report exact pass/skip/fail counts, validation not run,
  deferred behavior, and that no physical hardware or power-loss acceptance
  occurred.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Foundation (T001–T005)**: Starts immediately; blocks every user story.
- **US1 (T006–T012)**: Depends on T005 and provides durable append/reopen.
- **US2 (T013–T019)**: Depends on US1 because retention is part of append.
- **US3 (T020–T024)**: Depends on US2 because pagination must report retention
  that advances between pages.
- **Completion (T025–T030)**: Depends on all user stories.

### Within Each Behavioral Group

- Add the specified RED tests and confirm the intended failure before production
  changes.
- Implement only the minimum active task behavior.
- Run the focused GREEN selection before broadening validation.
- Do not weaken feature-001/002 assertions or hardware fail-closed guards.

### Parallel Opportunities

- T002 model tests and T004 codec test design touch different files, but T004's
  executable RED suite waits for T003 model names.
- Documentation review and focused-search preparation can occur independently,
  but implementation user stories are intentionally sequential because append,
  retention, and pagination build on the same transaction/schema invariants.
- Test files may be developed independently where marked by distinct task IDs;
  production work in `sqlite_evidence.py` remains serialized to avoid competing
  schema/transaction edits.

## Implementation Strategy

### First implementation group: T001–T005

1. Add only the concrete module/test structure and applicable import guard.
2. RED-test and implement immutable session policy, finite-integer,
   reference/cursor, and opaque provenance-envelope values.
3. RED-test and implement schema-version-1 creation/opening, physical-ceiling
   reapply/verification, strict codecs, and the journal-private one-thread
   connection owner/gate.
4. Keep append, retention, retrieval, recovery, and acquisition integration
   absent until their later task groups.
5. Stop after focused GREEN/static validation and report readiness for T006.

### Incremental delivery

1. T001–T005: concrete foundation, no append.
2. T006–T012: durable authoritative append/reopen MVP.
3. T013–T019: rolling bounded retention and stable expiry.
4. T020–T024: bounded snapshot retrieval.
5. T025–T030: corruption/compatibility hardening and full completion gate.

## Notes

- SQLite is selected; do not add a provider interface, repository hierarchy, or
  alternate storage implementation.
- Tests use temporary paths and fake backends only. Never enumerate or open a
  physical serial device.
- Software process-crash recovery is not arbitrary power-loss or media-failure
  certification.
- Numerical product defaults, profile mapping, session orchestration, and
  external cursor encoding remain deferred.
