# DUTchMate Development History

Completed slice records are kept newest first. Current status and next work live
only in `docs/development_status.md`.

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
