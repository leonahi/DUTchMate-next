# DUTchMate Development Status

This is the single authority for current progress, active phase, blockers,
milestone, and next work. It is subordinate to
`docs/project_context_core.md` and active focused implementation
specifications.

## Resume Here

- **Active phase**: Phase 1 — Basic backend through CLI.
- **Completed milestones**: `001-rx-continuous-evidence`,
  `002-basic-serial-adapter`, and `003-durable-evidence-journal` are
  software-complete against their focused specifications. Features 001 and 002
  are committed through `e2cd2cf`; feature 003 completed T001–T030 and its
  pre-commit review.
- **Most recently completed specification**:
  `003-durable-evidence-journal`; all defined tasks T001–T030 are complete.
- **Next action**: Await explicit selection and specification of the next
  Phase 1 slice. Do not infer or start it from feature 003.
- **Scope guard**: Feature 003 is one SQLite-backed durable session journal with
  bounded rolling retention and raw sequence retrieval. Do not add Profile or
  run orchestration, service/HTTP, CLI, Monitor/Interact, TX/Control, reconnect,
  release/reacquire, Enhanced behavior, MCP, or hardware work.
- **Hardware**: No physical hardware has been accessed or validated. The
  platform/electrical acceptance cases remain opt-in and separately authorized.
- **Blockers**: The next Phase 1 slice has not been selected; this is an
  intentional stopping point rather than a feature-003 blocker. Python 3.14
  remains the declared initial baseline.

## Repository Baseline

- The accepted committed baseline contains the reproducible agent tooling,
  completed feature-001 continuous-RX evidence foundation, and completed
  feature-002 Basic serial adapter through commit `e2cd2cf`.
- The Python 3.14 uv workspace contains the `dutchmate-core` package and a
  hardware-free test/static-analysis harness.
- Shared Core provides normalized backend/connection protocols, immutable
  capability and provenance values, exact-byte RX and observer-loss evidence,
  an in-memory append-only journal, and exclusive continuous acquisition with
  explicit segment transitions, teardown ordering, and normalized failures.
- Feature 003 T001–T030 add immutable durable session/policy/reference values,
  generic opaque provenance envelope version 1, strict evidence codecs,
  serialized durable append/reopen, rolling retention and its coalesced marker,
  stable reference resolution, and bounded fixed-snapshot sequence-key raw
  retrieval with explicit between-page expiry reporting.
- Feature 002 adds the first production Basic serial adapter behind that
  normalized boundary. It requires an exact device name, configures a closed
  pySerial handle before one open, reports receive-only capability and opaque
  immutable provenance, emits sequential exact-byte RX with host-observation
  timestamps, and coordinates cancellation, read completion, and one physical
  close.
- pySerial 3.5 and types-pyserial 3.5.0.20260712 are locked. pySerial objects,
  exceptions, handles, and Basic-specific configuration stay inside
  `dutchmate_core.adapters.basic_serial`.
- Import Linter and Ruff rules enforce inward Core dependencies, keep test
  frameworks out of production Core, prevent shared Core from importing
  adapters, and confine pySerial to the Basic adapter boundary.
- The Enhanced-shaped backend remains a minimal test-only neutrality fixture;
  it contains no Enhanced hardware, firmware, USB framing, timing, or helper
  protocol behavior.

## Completed Feature: Durable Evidence Journal

`specs/003-durable-evidence-journal/` is software-complete through T030.
It provides the model, codec, SQLite bootstrap, durable append/recovery,
retention, references, bounded fixed-snapshot pagination, fail-closed
compatibility/corruption handling, quickstart validation, final scope review,
and completion documentation. Its accepted boundary is:

- one SQLite database per durable session, using Python 3.14's standard-library
  `sqlite3`, rollback-journal `DELETE` mode, `synchronous=FULL`, strict schema
  version 1, exact RX BLOBs, and no added runtime dependency;
- commit-before-acknowledgment with clean-reopen and tested process-crash
  recovery. Exactly-once retry after commit-before-return ambiguity, arbitrary
  power-loss or lying flush hardware, and filesystem, media, directory, backup,
  or live-copy survival are explicitly not guaranteed;
- authoritative sequence scoped to the immutable session identity and continued
  after reopen without reuse or retention renumbering;
- required finite record, byte, per-record, and database-page limits; rolling
  minimum-prefix eviction; and one bounded coalesced retention marker;
- stable session-plus-sequence references with explicit retained, expired,
  partial, and not-found outcomes;
- raw bounded sequence-key pages over a fixed snapshot upper bound, with typed
  internal cursors and explicit between-page expiry;
- normalized versioned backend provenance snapshots so persistence remains
  backend-neutral and never imports Basic types into shared Core.

Session naming/listing/sealing, numerical product defaults, Profile mapping,
delivery APIs, annotations, derived representations, operation lookup, repair,
migrations beyond rejecting non-v1 stores, and all later workflows remain
deferred.

## Completed Feature: Basic Serial Backend Adapter

`specs/002-basic-serial-adapter/` is complete for its software-only scope. It
delivers:

- explicit, exact user-selected device names with no enumeration, URL handler,
  automatic, first-device, or fallback selection;
- validated baud/data/parity/stop/flow settings and configure-before-open
  ordering on a closed `serial.Serial(port=None)` handle;
- DTR and applicable static RTS intent applied while closed, with RTS explicitly
  driver-managed under RTS/CTS and honest provenance that glitch-free
  transitions and physical electrical state are not guaranteed or verified;
- receive-only normalized capability reporting, fresh connection/segment and
  host-observation timestamp identities, and unchanged opaque provenance copied
  by acquisition;
- one sequential `asyncio.to_thread` read at a time, exact binary preservation,
  post-read host timestamps captured in the worker, empty-read suppression, and
  one event-stream consumer;
- normalized open/read/close failures, stable-attribute-only device-loss
  classification, and no raw pySerial or OS exception leakage;
- caller/lifecycle-thread `cancel_read()`, mandatory outstanding-read join,
  exactly one physical close, idempotent concurrent close, primary-failure
  preservation, and restart blocking while physical release is incomplete or
  unconfirmed;
- fake-driven adapter-through-acquisition coverage and fail-closed guards that
  prevent the default test suite from opening or enumerating physical serial
  devices.

T019 found one FR-024 lifecycle defect: if `cancel_read()` failed, physical
close could occur before the outstanding blocking read returned. A focused RED
regression test proved the ordering error. The adapter now always awaits that
read before its one physical close while retaining the normalized cancellation
failure as the primary close-path error. No other specification or boundary
defect remained after focused diff/search review.

## Completed Feature: Continuous RX Evidence Foundation

`specs/001-rx-continuous-evidence/` remains complete. Shared Core retains one
capability-driven backend boundary and one authoritative RX consumer; continuous
ambient exact-byte evidence; journal-assigned authoritative sequence order;
explicit connection, segment, timestamp-domain/origin, and loss provenance;
guarded same-domain timestamp comparison and origin-reset segments;
observer-scoped loss evidence; and generation-local, non-restartable teardown
through physical close completion.

## Current Limitations and Deferred Work

- No physical-hardware acceptance has occurred. Safe-open line behavior,
  electrical DTR/RTS state, platform/driver disconnect classification,
  non-standard baud behavior, RX under load, and cancellation/close behavior
  remain hardware acceptance cases rather than validated claims.
- No serial discovery, automatic device selection, reconnect, or
  release/reacquire workflow.
- Feature 003 has production schema-version-1 append/reopen, rolling retention,
  stable reference resolution, and bounded whole-record sequence pages with a
  fixed continuation snapshot and explicit between-page expiry. Compatibility
  and corruption validation is fail-closed; annotations and broader session/run
  lifecycle remain deferred.
- No TX, semantic Control, Monitor, Interact, follow, console, or DUT Profile
  delivery behavior.
- No service/HTTP, authentication, browser-origin rejection, CLI, MCP, or AI
  integration.
- No real Enhanced backend, protocol, firmware, USB framing, GPIO/event
  behavior, or Enhanced hardware-support claim.

## Planning Artifacts

Completed feature 003:

- `specs/003-durable-evidence-journal/spec.md`
- `specs/003-durable-evidence-journal/checklists/requirements.md`
- `specs/003-durable-evidence-journal/plan.md`
- `specs/003-durable-evidence-journal/research.md`
- `specs/003-durable-evidence-journal/data-model.md`
- `specs/003-durable-evidence-journal/contracts/durable-evidence-journal.md`
- `specs/003-durable-evidence-journal/quickstart.md`
- `specs/003-durable-evidence-journal/tasks.md`

Completed feature 002:

- `specs/002-basic-serial-adapter/spec.md`
- `specs/002-basic-serial-adapter/checklists/requirements.md`
- `specs/002-basic-serial-adapter/plan.md`
- `specs/002-basic-serial-adapter/research.md`
- `specs/002-basic-serial-adapter/data-model.md`
- `specs/002-basic-serial-adapter/contracts/basic-serial-adapter.md`
- `specs/002-basic-serial-adapter/quickstart.md`
- `specs/002-basic-serial-adapter/tasks.md`

Completed feature 001:

- `specs/001-rx-continuous-evidence/spec.md`
- `specs/001-rx-continuous-evidence/checklists/requirements.md`
- `specs/001-rx-continuous-evidence/plan.md`
- `specs/001-rx-continuous-evidence/research.md`
- `specs/001-rx-continuous-evidence/data-model.md`
- `specs/001-rx-continuous-evidence/contracts/normalized-backend.md`
- `specs/001-rx-continuous-evidence/quickstart.md`
- `specs/001-rx-continuous-evidence/tasks.md`

## Blockers and Open Decisions

- Numerical product defaults and service/profile path selection remain outside
  feature 003; journal creation requires explicit finite values. The next
  focused Phase 1 slice requires explicit selection and specification.
- Actual glitch behavior, electrical DTR/RTS state, disconnect classification,
  non-standard baud support, RX load behavior, and cancellation/close behavior
  remain OS/driver/adapter-specific hardware acceptance questions. Their cases
  are documented but intentionally unexecuted.
- SQLite rollback-journal process-crash recovery is software-tested. Arbitrary
  power-loss behavior, storage-device flush honesty, media recovery, and
  live-file copying are not accepted claims and do not block this slice.

## Validation Status

- T027 ran every quickstart command, including the full feature-001/002
  regression groups. T028's post-correction validation then passed the focused
  create/open cancellation regression (2 tests), journal contract and recovery
  group (78 tests), complete feature-003 group (137 tests), and full repository
  regression (347 tests, no failures).
- The corrected final commit candidate passes 348 tests with no failures or
  skips. Ruff passes, mypy reports no issues in 27 source files, Import Linter
  keeps all 3 contracts, and `git diff --check` is clean.
- T028 found that cancellation of create/open after worker submission could
  discard a successful bootstrap result without closing its SQLite connection.
  The cancellation-resistant bootstrap join now retrieves that result, closes
  the connection on its owning journal worker, and only then propagates
  cancellation; the parametrized create/open regression is GREEN.
- Final pre-commit review found that corrupt persisted sequence metadata could
  cause open validation to materialize an attacker-sized expected range before
  rejecting it. Validation now checks row count and contiguous sequence values
  without allocating from the persisted span; the focused RED/GREEN regression
  covers the signed-64-bit terminal value.
- The default pytest harness replaces `serial.Serial` with a fail-closed
  sentinel; all normal adapter tests inject fakes. No test enumerated or opened
  a physical serial device.
- Graphify 0.9.48 already received the one code-only incremental update required
  by feature 003's new SQLite adapter and shared provenance interface. It
  produced 1,426 nodes, 3,039 edges, and 78 communities. T029 did not repeat the
  update because T028's private helper and regression test were localized and
  did not add a module, change a shared interface or dependency direction, or
  perform a significant multi-module refactor. Generated output remains ignored
  local tooling state and is not software acceptance evidence.
