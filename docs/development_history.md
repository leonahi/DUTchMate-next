# DUTchMate Development History

Completed slice records are kept newest first. Current status and next work live
only in `docs/development_status.md`.

## 2026-10-03 — Feature 004 Observation-Only DUT Profile Complete (T001–T021)

Completed the feature-004 production implementation and completion
documentation through T021. The software resolves one explicit caller-supplied
path containing strict, human-authored UTF-8 TOML with
`profile_version = 1`. The closed format is bounded to 65,536 serialized bytes;
resolution reads at most 65,537 bytes and enforces that ceiling on the captured
bytes before decoding or parsing. It returns immutable backend-neutral values
for DUT identity/name, explicit Basic selection and exact expected device, UART
configuration, DTR/RTS open intent, observation policy, and the existing
feature-003 `SessionPolicy` constructed directly from all six explicit finite
limits.

Profile v1 requires RX and evidence recording to remain enabled as mandatory
observation invariants. Its current permissions remain fail closed: UART TX,
semantic Control, and automatic reconnect are disabled. Opposite values and
recognized TX, Interact/console, Control, reconnect, or reacquire configuration
fail explicitly as `unsupported_behavior`; they are never silently ignored.
The deterministic failure matrix also distinguishes filesystem failures,
oversized input, invalid syntax, incompatible version, missing/unknown fields,
invalid values, and unsupported backends without exposing a parser tree,
partial result, or raw exception cause/context.

The generic Profile module contains no Basic or pySerial implementation type.
A TOML adapter owns filesystem/format resolution, and a separate pure Basic
adapter-side translator maps the resolved snapshot field-for-field into the
existing feature-002 `BasicSerialOpenRequest`. Resolution and translation do
not enumerate or open a device, construct a backend, start acquisition, create
a journal/session, or own lifecycle. No registry or generalized Profile manager
was introduced.

T018's final implementation review found and corrected four bounded defects.
Recognized Interact/console configuration had been classified as an unknown
field rather than unsupported behavior; invalid path values could leak a raw
`ValueError`; normalized failures retained raw exceptions through
`__context__`; and the quickstart import-search exclusion did not match the
nested Basic adapter path. Focused RED/GREEN regressions cover the behavioral
corrections, and the search was corrected and rerun.

Post-correction software validation passed 217 focused feature-004 tests and
565 full-repository tests with no failures or skips. Ruff passed, mypy reported
no issues in 33 source files, all 3 Import Linter contracts were kept after
analyzing 28 files and 56 dependencies, and `git diff --check` passed.

T020 confirmed that the shared Profile module and two adapter modules satisfy
Graphify's structural-change criteria, then ran the one required code-only
incremental update with Graphify 0.9.48. The ignored graph now contains 1,928
nodes, 4,471 edges, and 96 communities. Graphify reported one non-fatal
zero-node source (`pyproject.toml`) and refreshed 23 community names from their
hubs after the community set changed. No semantic/LLM extraction ran and no
generated Graphify output entered version control.

T021's fresh final gate passed: Ruff reported no violations; mypy reported no
issues in 33 source files; Import Linter kept all 3 contracts after analyzing 28
files and 56 dependencies; pytest passed 565 tests with 0 skipped and 0 failed;
and `git diff --check` passed. Feature 004 is software-complete and ready for
commit. The final pre-commit review corrected stale spec/status completion
metadata and found no production-contract defect.

Lifecycle and ownership, session orchestration, service/HTTP and authentication,
CLI, Monitor/follow, TX/Interact/console execution, semantic Control execution,
reconnect, release/reacquire/handoff, Enhanced, MCP, Profile discovery/default
paths, Profile writing/migration/overlay/reload, and numerical product defaults
remain deferred. No physical hardware was enumerated, opened, accessed,
modified, or validated, and no electrical or platform acceptance is claimed.

## 2026-10-01 — Feature 003 Durable Evidence Journal Complete (T001–T030)

Completed the feature-003 implementation and completion documentation for one
SQLite-backed durable session journal. The delivered software provides
immutable finite session policy, generic opaque provenance envelopes, canonical
exact-byte evidence storage, serialized durable append and reopen, rolling
bounded retention with a coalesced marker, stable reference resolution, bounded
fixed-snapshot raw pages, and fail-closed compatibility/corruption handling.
SQLite connections remain confined to their journal-owned single worker and
shared acquisition depends only on the backend-neutral recorder contract.

The accepted durability guarantee is intentionally limited to clean reopen and
tested software process-crash recovery under committed SQLite transactions.
Exactly-once retry after commit-before-return ambiguity, arbitrary power-loss or
lying flush hardware, and filesystem, media, directory, backup, or live-copy
survival are explicitly not guaranteed.

T028's final review found one lifecycle defect: cancellation of create/open
after worker submission could discard a successful bootstrap result without
closing its SQLite connection. A parametrized RED regression reproduced both
paths. The correction waits for the bootstrap worker, recovers a successful
result, closes the connection on that same owning worker, and then propagates
cancellation. The focused regression passed 2 tests, journal contract/recovery
passed 78 tests, the complete feature-003 group passed 137 tests, and the full
repository passed 347 tests with no failures. Ruff, mypy, all three Import
Linter contracts, and `git diff --check` passed in the T030 software validation.

Final pre-commit review found one further boundedness defect: corrupt persisted
sequence metadata could make open validation materialize an enormous expected
range before reporting corruption. A focused RED regression intercepted the
attempt at the signed-64-bit terminal value. Validation now compares row count
and contiguous sequence values without allocating from the persisted span; the
regression is GREEN. This is a fail-closed corruption correction only and adds
no persistence framework, migration, repair, or delivery behavior. The
corrected final candidate passed 348 tests with no failures or skips; Ruff,
mypy, all three Import Linter contracts, and `git diff --check` passed.

Graphify's structural-change criteria were evaluated. The one earlier
feature-003 incremental update already captured the new SQLite adapter and
shared provenance interface (1,426 nodes, 3,039 edges, 78 communities); T028's
localized private helper and regression test did not require another update.
No physical hardware was enumerated, opened, accessed, modified, or validated,
and no power-loss acceptance was performed.

## 2026-10-01 — Feature 003 Fail-Closed Open Validation (T026)

Made the T025 compatibility/corruption matrix GREEN with a bounded SQLite
adapter correction. Open now forces rollback-journal processing before
application validation, classifies stored decode failures as open failures,
maps malformed persisted invariants to corrupt-journal outcomes, and proves a
validated connection writable with a rolled-back no-op update before applying
the physical page ceiling. Supported generic envelopes still round-trip unknown
backend provenance kind/schema values opaquely, while SQLite operational errors
retain their normalized operational classifications. No migration, repair,
salvage, delivery behavior, or physical hardware work was added. The complete
feature-003 group passed 135 tests and the full repository passed 345 tests.

## 2026-10-01 — Feature 003 Compatibility/Corruption RED Matrix (T025)

Added 15 software-only contract cases for incompatible application, store,
record, and generic provenance-envelope versions; opaque unknown backend
provenance; missing schema objects; malformed metadata/payload invariants;
aggregate/sequence corruption; failed integrity checks; locked/read-only opens;
source preservation; and the rollback-recovery-before-validation exception.
The focused selection produced the intended 8 failures and 7 passing controls.
All 120 earlier feature-003 tests remain GREEN. No production code or physical
hardware was touched.

## 2026-10-01 — Feature 003 Pagination Validation Gate (T024)

Completed the software-only validation checkpoint before compatibility and
corruption work. The exact quickstart retention/reference/retrieval selection
passed 40 tests; the complete durable-journal model, codec, contract, recovery,
and acquisition-integration group passed 120 tests; and feature-001 evidence
ordering and timestamp regressions passed 64 tests. The full repository passed
330 tests. Ruff, mypy, all three Import Linter contracts, and
`git diff --check` passed. No defect was found and no production or test code
changed. No physical hardware was accessed.

## 2026-10-01 — Feature 003 Stable Pagination Continuation (T023)

Completed fixed-snapshot continuation and explicit between-page expiry for the
bounded raw evidence journal. Continuations now preserve the first page's
exclusive snapshot boundary, exclude later appends, report a newly expired
cursor-to-low-water interval with the current coalesced retention marker, and
resume retained sequence-key retrieval without changing T022's page bounds or
whole-record behavior. Both remaining T021 RED cases pass. No external cursor
encoding, delivery schema, or physical hardware behavior was added.

## 2026-10-01 — Feature 003 Bounded Raw Retrieval (T022)

Implemented policy-capped, whole-record raw evidence pages ordered by durable
sequence, with charged-byte accounting, oversized-next-record reporting, and
typed keyset continuation cursors. Retrieval values now live in the planned
backend-neutral `evidence.py` contract; SQLite remains confined to its adapter
and journal worker. T020's nine pagination cases pass. Five T021 cursor,
lock-release, and cancellation cases pass; fixed-snapshot continuation and
between-page expiry remain intentionally RED for T023. No physical hardware
was accessed.

## 2026-09-30 — Feature 003 Durable Journal Foundation (T001–T005)

Completed the software-only durable value, codec, and SQLite bootstrap
foundation. No physical device was enumerated, opened, modified, or validated.

### Delivered

- Added immutable session identity, finite session policy with independent
  retrieval ceilings, signed-64-bit persisted counter/sequence validation,
  stable references, retention endpoints, retrieval values, and normalized
  journal failures.
- Added generic provenance envelope version 1 with opaque backend kind/schema
  version and scalar-only sorted fields. Basic serial owns its flattened
  mapping; unknown conforming backend values remain opaque and round-trip.
- Added strict canonical JSON metadata codecs for all four current evidence
  variants, exact RX BLOB handling, and deterministic logical byte charge.
- Added one-session SQLite schema-version-1 create/open/close with `DUTM`
  application identity, 4096-byte pages, rollback `DELETE`, `synchronous=FULL`,
  persisted immutable policy, and no added runtime dependency.
- Persisted `max_database_pages` as policy while reapplying and verifying
  `max_page_count` on every writable create/open. Oversized databases and an
  unavailable requested ceiling have distinct normalized failures.
- Confined each connection's creation, use, and close to one journal-owned
  `ThreadPoolExecutor(max_workers=1)` worker with one asyncio serialization
  gate. Shared Core still does not import adapters; no architecture exemption
  was added.
- Stopped before durable append, retention, retrieval, recovery subprocesses,
  cancellation/commit ambiguity, delivery surfaces, or hardware behavior.

### Validation Evidence

- RED: the initial model suite failed 45 tests for missing feature-003 values;
  the codec/bootstrap suite failed 14 tests for absent codecs/journal behavior;
  two follow-up invariant tests failed before their minimal validations were
  added.
- `uv run --frozen pytest core/tests/unit/test_evidence_journal_model.py
  core/tests/unit/test_sqlite_evidence_codec.py
  core/tests/contract/test_sqlite_evidence_journal.py -q`: 62 passed.
- `uv run --frozen ruff check .`: passed.
- `uv run --frozen mypy .`: no issues in 25 source files.
- `uv run --frozen lint-imports`: 3 contracts kept, 0 broken.
- `uv run --frozen pytest`: 272 passed, 0 skipped, 0 failed.
- `git diff --check`: passed.
- No physical hardware was touched.

## 2026-09-30 — Feature 002 Basic Serial Backend Adapter (T001–T020)

Completed the first production Basic serial adapter behind feature 001's
normalized backend contract. This is a software-only completion record; no
physical serial device was accessed or validated.

### Delivered

- Added and locked pySerial 3.5 plus types-pyserial 3.5.0.20260712, confined
  pySerial imports and implementation types to
  `dutchmate_core.adapters.basic_serial`, and extended shared Core only with
  opaque immutable connection provenance and normalized failure values.
- Required an exact explicit platform device name. The adapter performs no
  enumeration, discovery, URL handling, automatic choice, implicit default, or
  fallback selection.
- Constructed `serial.Serial(port=None)`, configured the complete supported
  UART, flow-control, exclusivity, and line-state intent while closed, and
  called `open()` exactly once after configuration. Successful provenance
  preserves selected/opened names and requested/effective configuration.
- Applied DTR and applicable static RTS intent before open; under RTS/CTS, RTS
  remains driver-managed. Provenance records the preconfigured-while-closed
  strategy and honestly marks glitch-free transition as not guaranteed and
  physical electrical state as not verified. This is serial-open handling, not
  semantic Control.
- Reported only `uart_receive`. Successful connections receive fresh
  connection/segment identity and a fresh host-observation timestamp
  domain/origin; acquisition copies adapter provenance unchanged without a
  Basic identity branch.
- Implemented one sequential blocking `read()` at a time through
  `asyncio.to_thread`, capturing `monotonic_ns` immediately after read return
  in the same worker. Normalized RX preserves exact bytes and return order;
  empty reads emit nothing, and no adapter queue, prefetch path, or concurrent
  reader exists.
- Normalized open, read, and close failures without leaking pySerial/OS objects.
  Device loss is emitted only when stable exception attributes positively
  identify disappearance; ambiguous failures remain `read/io_failure`, and
  exception message text never controls classification.
- Implemented caller/lifecycle-thread `cancel_read()`, mandatory outstanding
  read completion before one physical close, and idempotent repeated/concurrent
  close. Acquisition remains non-restartable through physical teardown,
  preserves an established primary failure, blocks restart after unconfirmed
  release, and emits no duplicate terminal segment evidence.
- Added fake-driven adapter-through-acquisition coverage for immutable
  provenance, ambient exact-byte RX, host timestamp provenance, device loss,
  ambiguous read failure, explicit stop/close ordering, and second-owner
  rejection.
- Added fail-closed hardware-safety guards: the default test suite cannot invoke
  the physical serial factory, and static tests reject serial enumeration,
  pySerial URL handlers, URL-like selectors, or automatic device selection.

### T019 Correction

Final diff review found an FR-024 defect: a failing `cancel_read()` caused the
adapter to skip joining the outstanding blocking read and proceed to physical
close. A focused RED regression observed one physical close while the read was
still active. The corrected close path always awaits that read before its
single physical close while retaining the normalized cancellation failure;
the focused contract suite then passed 56 tests.

### Validation Evidence

- `uv run --frozen ruff check .`: passed.
- `uv run --frozen mypy .`: no issues in 20 source files.
- `uv run --frozen lint-imports`: 3 contracts kept, 0 broken.
- `uv run --frozen pytest`: 210 passed, 0 skipped, 0 failed.
- `git diff --check`: passed.
- Focused feature-002 model, adapter-contract, integration, and safety groups
  passed; all feature-001 regression groups remained GREEN.
- Focused diff/search review found no Basic identity branch or pySerial object
  outside the adapter boundary; no discovery/URL-handler path, raw exception
  leak, concurrent/duplicate RX path, timestamp-based evidence ordering,
  semantic Control, TX, reconnect, delivery surface, Enhanced implementation,
  firmware, or MCP was introduced.
- No physical serial hardware was enumerated, opened, modified, or validated.
  Platform/electrical acceptance remains explicitly deferred.

## 2026-09-29 — Feature 001 Lifecycle Correction

Closed the teardown and terminal-state gaps found in the final pre-commit
review.

### Delivered

- Acquisition now remains non-restartable in `stopping` until its one physical
  connection close finishes; successful teardown exposes `stopped` only after
  close completion.
- Each acquisition consumer captures its generation's termination event, so a
  prior task cannot signal a later generation.
- Backend-open failure now enters `failed`, signals termination, preserves and
  re-raises the original exception, creates no connection/segment evidence or
  consumer task, and permits a later valid start.
- Unexpected normal stream completion now records a transport-failure segment
  end before teardown.
- Close failure cannot strand acquisition in `stopping`. An existing primary
  recording/transport failure is preserved; otherwise close failure becomes the
  terminal transport failure. Because physical close is unconfirmed, a new
  owner remains rejected.
- Removed the deferred `ownership_lost` segment reason and ownership-loss
  lifecycle wording from the focused feature 001 documents.

### Validation Evidence

- RED: 5 focused lifecycle tests failed for the intended missing behavior:
  premature `stopped`, open failure left in `starting`, absent stream-end
  evidence, premature `failed` during close, and duplicate terminal evidence
  when close failed.
- GREEN: focused acquisition suite passed 29 tests; feature quickstart suites
  passed 31 model/backend tests and 35 evidence/acquisition tests.
- `uv run --frozen ruff check .`: passed.
- `uv run --frozen mypy .`: no issues in 15 source files.
- `uv run --frozen lint-imports`: 2 contracts kept, 0 broken.
- `uv run --frozen pytest`: 66 passed, 0 skipped, 0 failed.
- `git diff --check`: passed.
- No physical hardware was touched.

Feature `001-rx-continuous-evidence` is ready to commit against its focused
specification. Real adapters, durability, workflows, delivery surfaces, and
later phases remain deferred.

## 2026-09-29 — Feature 001 Timestamp-Regression Correction

Closed the final conformance gap found during T019–T021 review.

### Delivered

- Added acquisition regression coverage for decreasing timestamps and proved
  the original path incorrectly stopped normally while recording the offending
  observation.
- Added a per-segment baseline shared by timestamped RX/loss observations. The
  baseline advances only after successful evidence recording and resets after a
  successfully recorded timestamp-origin segment transition.
- A decreasing timestamp in the current domain/origin now ends the segment with
  an explicit transport failure. Earlier evidence and sequence values remain
  unchanged; the offending observation is not recorded.
- Strengthened origin-reset coverage to accept a lower timestamp in the new
  domain/origin, while preserving equal-timestamp behavior within a segment.

### Validation Evidence

- RED: 2 focused tests failed because acquisition returned `stopped` instead of
  `failed` for RX→RX and loss→RX timestamp regressions.
- GREEN: focused acquisition suite passed 24 tests.
- `uv run --frozen ruff check .`: passed.
- `uv run --frozen mypy .`: no issues in 15 source files.
- `uv run --frozen lint-imports`: 2 contracts kept, 0 broken.
- `uv run --frozen pytest`: 61 passed, 0 skipped, 0 failed.
- `git diff --check`: passed.
- No physical hardware was touched.

Feature `001-rx-continuous-evidence` now satisfies its focused specification.
Real adapters, durability, workflows, delivery surfaces, and later phases remain
deferred.

## 2026-09-29 — Feature 001 Validation and Documentation (T019–T021)

Completed the T019–T021 validation/documentation slice for the first Phase 1
software foundation. The feature remains open because final specification
review found one implementation gap not covered by the passing suite.

### Delivered

- Established the Python 3.14 uv workspace and `dutchmate-core` package.
- Added the normalized backend and single-consumer connection boundary.
- Added exact-byte RX evidence, Core-assigned journal sequence ordering,
  connection/segment provenance, timestamp-domain/origin validation, and
  observer-scoped loss evidence.
- Added exclusive continuous acquisition, explicit disconnect/stop/failure
  behavior, and timestamp-origin segment transitions.
- Proved backend-neutral shared behavior with hardware-free Basic-shaped and
  Enhanced-shaped test fixtures. The Enhanced-shaped fixture is not a real
  backend and simulates no helper protocol, firmware, USB framing, or hardware
  timing.
- Added import-linter contracts for inward Core module dependencies and the
  production/test-framework boundary.

### Validation Evidence

- `uv sync --all-packages --dev`: resolved 20 packages; audited 19 packages.
- Focused quickstart suites: 31 model/contract tests and 28
  evidence/acquisition tests passed.
- `uv run --frozen ruff check .`: passed.
- `uv run --frozen mypy .`: no issues in 15 source files.
- `uv run --frozen lint-imports`: 2 contracts kept, 0 broken.
- `uv run --frozen pytest`: 59 passed, 0 skipped, 0 failed.
- `git diff --check`: passed.
- Scope scan found no Basic identity branch, serial/framework dependency,
  Enhanced implementation, or later-phase product code above the normalized
  boundary.
- No physical hardware was touched.

### Limitations Retained

Real Basic serial transport and hardware acceptance, durable persistence and
retention, workflows, service/HTTP, CLI, Enhanced hardware/protocol/firmware,
and MCP remain deferred. The in-memory journal and both backend shapes are
software test infrastructure, not production adapters or durability claims.

Graphify's initial code-only structural index was generated for the new shared
interfaces. Its diagnostic reported 29 dangling endpoints and 62 same-endpoint
collapsed-edge candidates; documentation semantic indexing was unavailable
because Graphify's optional backend package is not installed.

Final specification review found that acquisition does not reject an undeclared
decreasing timestamp in the current domain/origin, contrary to the feature
specification's Edge Cases. No production behavior was added because this slice
was restricted to T019–T021. A focused red-green correction remains required
before feature `001` can be declared complete. That gap was closed by the newer
record above.
