# DUTchMate Development Status

This is the single authority for current progress, active phase, blockers,
milestone, and next work. It is subordinate to
`docs/project_context_core.md` and active focused implementation
specifications.

## Resume Here

- **Active phase**: Phase 1 — Basic backend through CLI.
- **Completed milestones**: `001-rx-continuous-evidence`,
  `002-basic-serial-adapter`, `003-durable-evidence-journal`, and
  `004-dut-profile-policy` are software-complete against their focused
  specifications. Features 001–003 are committed through `15890e59`; feature
  004 is included in the current `HEAD`.
- **Most recently completed specification**: `004-dut-profile-policy`; all
  defined tasks T001–T021 are complete.
- **Next action**: Await explicit selection and specification of the next
  coherent Phase 1 slice. Do not infer or start it automatically.
- **Scope guard**: Feature 004 resolves one explicit, bounded TOML Profile v1
  into immutable Core values and translates those values into an existing Basic
  open request without opening hardware. Do not add lifecycle/session
  orchestration, service/HTTP, CLI, Monitor/Interact, TX/Control, reconnect,
  release/reacquire, Enhanced behavior, MCP, or hardware work.
- **Hardware**: No physical hardware has been accessed or validated. The
  platform/electrical acceptance cases remain opt-in and separately authorized.
- **Blockers**: The next Phase 1 slice has not been selected; this is an
  intentional stopping point rather than a feature-004 blocker. Python 3.14
  remains the declared initial baseline.

## Repository Baseline

- The accepted committed baseline contains the reproducible agent tooling and
  completed features 001, 002, 003, and 004 through the current `HEAD`; feature
  003 and its predecessors are anchored by commit `15890e59`.
- Feature 004 adds the observation-only Profile domain, strict TOML-v1
  resolver, and pure Basic request translator.
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

## Completed Feature: DUT Profile and Policy

`specs/004-dut-profile-policy/` is software-complete through T021. The delivered
software-only scope is:

- one explicit caller-supplied path containing strict, human-authored UTF-8
  TOML with `profile_version = 1`, a closed schema, and a 65,536-byte serialized
  input ceiling enforced against at most 65,537 bytes actually read before
  decoding or parsing;
- immutable backend-neutral resolved values for explicit DUT identity/name,
  explicit `basic_serial` selection and exact expected device, complete UART
  configuration, and DTR/RTS open intent;
- mandatory version-1 observation invariants of RX enabled and evidence
  recording enabled, plus fail-closed permissions of TX disabled, semantic
  Control disabled, and automatic reconnect disabled;
- direct construction of the existing immutable feature-003 `SessionPolicy`
  from all six explicit finite persistence, retention, and retrieval limits,
  without Profile-specific quota types or numerical defaults;
- deterministic normalized Profile failures, including `input_too_large`, with
  no parser tree, partial resolved value, or retained raw exception cause or
  context; and
- separate adapter-side TOML resolution and pure Basic request translation.
  Shared Profile values contain no Basic or pySerial implementation type, and
  neither path enumerates or opens devices, starts acquisition, creates a
  journal/session, or owns lifecycle.

T018's complete diff/search review corrected four genuine defects: recognized
Interact/console configuration now fails as `unsupported_behavior`; invalid
path values no longer leak `ValueError`; normalized failures no longer retain a
raw exception through `__context__`; and the quickstart serial-import search now
correctly excludes the nested Basic adapter path. Focused regressions cover each
behavior. T020 found the structural-change criteria satisfied by the new shared
Profile module and two adapter modules, then performed the single prescribed
code-only incremental Graphify update. T021's fresh full validation gate passed.

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
- No TX, semantic Control, Monitor, Interact, follow, console, Profile delivery,
  lifecycle selection, or runtime policy enforcement behavior. Feature 004
  provides only immutable Profile resolution and pure Basic request translation.
- No service/HTTP, authentication, browser-origin rejection, CLI, MCP, or AI
  integration.
- No real Enhanced backend, protocol, firmware, USB framing, GPIO/event
  behavior, or Enhanced hardware-support claim.

## Planning Artifacts

Completed feature 004:

- `specs/004-dut-profile-policy/spec.md`
- `specs/004-dut-profile-policy/checklists/requirements.md`
- `specs/004-dut-profile-policy/plan.md`
- `specs/004-dut-profile-policy/research.md`
- `specs/004-dut-profile-policy/data-model.md`
- `specs/004-dut-profile-policy/contracts/dut-profile-v1.md`
- `specs/004-dut-profile-policy/quickstart.md`
- `specs/004-dut-profile-policy/tasks.md`

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

- There is no blocker to the feature-004 software completion work. Product
  defaults for the six persistence limits, service/Profile path selection,
  Profile discovery/default paths, writing, migration, overlay, reload, and
  lifecycle activation remain intentionally deferred.
- Actual glitch behavior, electrical DTR/RTS state, disconnect classification,
  non-standard baud support, RX load behavior, and cancellation/close behavior
  remain OS/driver/adapter-specific hardware acceptance questions. Their cases
  are documented but intentionally unexecuted.
- SQLite rollback-journal process-crash recovery is software-tested. Arbitrary
  power-loss behavior, storage-device flush honesty, media recovery, and
  live-file copying are not accepted claims and do not block this slice.

## Validation Status

- T018 post-correction validation passed all 217 focused feature-004 tests and
  the full repository regression of 565 tests, with no failures or skips. Ruff
  passed, mypy reported no issues in 33 source files, all 3 Import Linter
  contracts were kept after analyzing 28 files and 56 dependencies, and
  `git diff --check` passed.
- T018 added RED/GREEN regressions for the Interact/console classification,
  invalid-path normalization, and raw exception-context isolation defects. It
  also corrected and reran the feature quickstart's serial-import scope search.
- The default pytest harness replaces `serial.Serial` with a fail-closed
  sentinel; all normal adapter tests inject fakes. No test enumerated or opened
  a physical serial device.
- No physical-hardware or electrical validation was performed. Feature 004 has
  no hardware acceptance case, and its software results make no hardware claim.
- Feature 004's one code-only Graphify incremental update completed at 1,928
  nodes, 4,471 edges, and 96 communities. Graphify reported one non-fatal
  zero-node source (`pyproject.toml`) and automatically refreshed 23 community
  names from their hubs after the community set changed. Generated Graphify
  output remains ignored.
- T021's final gate passed: Ruff reported no violations; mypy reported no issues
  in 33 source files; Import Linter kept all 3 contracts after analyzing 28 files
  and 56 dependencies; pytest passed 565 tests with 0 skipped and 0 failed; and
  `git diff --check` passed. No physical hardware was accessed or validated.
