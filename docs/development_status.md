# DUTchMate Development Status

This is the single authority for current progress, active phase, blockers,
milestone, and next work. It is subordinate to
`docs/project_context_core.md` and active focused implementation
specifications.

## Resume Here

- **Active phase**: Phase 1 — Basic backend through CLI.
- **Completed milestones**: `001-rx-continuous-evidence` and
  `002-basic-serial-adapter` are software-complete against their focused
  specifications.
- **Most recently completed specification**: `002-basic-serial-adapter`; all
  defined tasks T001–T020 are complete.
- **Next action**: Review and commit the accepted feature-002 baseline. The
  feature-002 task list defines no T021; after the commit, select and specify
  the next Phase 1 slice before implementing it.
- **Scope guard**: Do not infer the next product contract or add TX, semantic
  Control, discovery, reconnect, profile delivery, persistence, service/HTTP,
  CLI, Enhanced protocol/firmware, or MCP from feature 002.
- **Hardware**: No physical hardware has been accessed or validated. The
  platform/electrical acceptance cases remain opt-in and separately authorized.
- **Blockers**: None for committing the software-only feature-002 baseline.
  Python 3.14 remains the declared initial baseline.

## Repository Baseline

- The accepted committed baseline contains the reproducible agent tooling and
  completed feature-001 continuous-RX evidence foundation.
- The Python 3.14 uv workspace contains the `dutchmate-core` package and a
  hardware-free test/static-analysis harness.
- Shared Core provides normalized backend/connection protocols, immutable
  capability and provenance values, exact-byte RX and observer-loss evidence,
  an in-memory append-only journal, and exclusive continuous acquisition with
  explicit segment transitions, teardown ordering, and normalized failures.
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
- No durable persistence, bounded retention, retrieval, sessions, cursors,
  annotations, or crash-recovery guarantee; the in-memory journal remains
  foundation/test infrastructure.
- No TX, semantic Control, Monitor, Interact, follow, console, or DUT Profile
  delivery behavior.
- No service/HTTP, authentication, browser-origin rejection, CLI, MCP, or AI
  integration.
- No real Enhanced backend, protocol, firmware, USB framing, GPIO/event
  behavior, or Enhanced hardware-support claim.

## Planning Artifacts

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

- No product decision blocks committing feature 002.
- Actual glitch behavior, electrical DTR/RTS state, disconnect classification,
  non-standard baud support, RX load behavior, and cancellation/close behavior
  remain OS/driver/adapter-specific hardware acceptance questions. Their cases
  are documented but intentionally unexecuted.
- The next Phase 1 feature and its concrete contracts have not been selected in
  this document. Feature 002 defines no T021, so later behavior must begin with
  an explicitly selected focused slice rather than being inferred here.

## Validation Status

- Final feature-002 software validation passes 210 tests with 0 skipped and 0
  failed. The Basic adapter contract suite passes 56 tests, including the T019
  FR-024 cancellation-failure regression.
- `uv run --frozen ruff check .` passes; `uv run --frozen mypy .` reports no
  issues in 20 source files; `uv run --frozen lint-imports` keeps all 3
  contracts; and `git diff --check` is clean.
- Feature-002 model, adapter-contract, integration, safety, and feature-001
  regression selections are GREEN. Focused searches confine pySerial and
  Basic-specific types to the adapter boundary and find no enumeration, URL
  handlers, shared-Core Basic identity branch, second RX path, TX/Control,
  reconnect, delivery framework, Enhanced implementation, firmware, or MCP.
- The default pytest harness replaces `serial.Serial` with a fail-closed
  sentinel; all normal adapter tests inject fakes. No test enumerated or opened
  a physical serial device.
- Graphify 0.9.48 received one code-only incremental update because feature 002
  added an adapter module and changed shared provenance interfaces. It produced
  1,126 nodes, 2,445 edges, and 70 communities; targeted explanations resolve
  the Basic adapter and normalized provenance relationships, and the structural
  diagnostic reports no missing/dangling endpoints, self-loops, duplicate or
  collapsed edges. Generated output remains ignored local tooling state and is
  not software acceptance evidence.
