# DUTchMate Development Status

This is the single authority for current progress, active phase, blockers,
milestone, and next work. It is subordinate to
`docs/project_context_core.md` and active focused implementation
specifications.

## Resume Here

- **Active phase**: Phase 1 — Basic backend through CLI.
- **Completed milestone**: `001-rx-continuous-evidence`; its task list and the
  final timestamp-regression and lifecycle conformance corrections are complete
  and validated.
- **Completed specification**:
  `specs/001-rx-continuous-evidence/spec.md`.
- **Next action**: Create a focused specification for the first real Basic
  backend adapter slice. Define user-selected serial-device opening,
  configuration provenance, host-observation timestamps, normalized
  disconnect/failure behavior, and safe DTR/RTS behavior on open before writing
  adapter code or touching hardware.
- **Scope guard**: Do not start service/HTTP, CLI, persistence, Monitor/Interact,
  Enhanced protocol/firmware, or MCP as part of that adapter specification.
- **Hardware**: No physical hardware has been accessed or validated. Hardware
  work remains separately authorized and opt-in.
- **Blockers**: None. Python 3.14 is the declared initial baseline.

## Repository Baseline

- The accepted baseline is organized as a reproducible agent-tooling commit
  followed by the feature-001 project and implementation commit.
- The Python 3.14 uv workspace contains the `dutchmate-core` package and the
  hardware-free test/static-analysis harness.
- Core now provides normalized backend/connection protocols, immutable
  capability and provenance values, exact-byte RX and observer-loss evidence,
  an in-memory append-only journal, and exclusive continuous acquisition with
  explicit segment transitions, teardown ordering, and failures.
- Basic-shaped and Enhanced-shaped backends exist only as test fixtures. The
  Enhanced-shaped fixture uses device-domain timestamps and observer-reported
  overflow solely to prove neutrality; it contains no Enhanced hardware,
  firmware, USB, framing, or helper-protocol behavior.
- Import Linter enforces inward dependencies from acquisition to backend and
  evidence boundaries to the domain model, plus the no-test-framework rule for
  production Core.

## Completed Feature: Continuous RX Evidence Foundation

The completed software-only slice establishes:

- one normalized, capability-driven backend boundary;
- one exclusive authoritative event consumer per owned connection;
- continuous ambient RX recording independent of workflows;
- exact binary UART-byte preservation and journal-assigned sequence order;
- explicit connection, segment, timestamp-domain/origin, and loss provenance;
- guarded same-domain timestamp comparison and explicit origin-reset segments;
- observer-scoped loss evidence with positive or explicitly unknown amounts;
- non-restartable teardown through physical close completion, generation-local
  termination signaling, and explicit open/stream/close failure handling;
- shared backend-independent behavior tests against both fixture shapes.

`specs/001-rx-continuous-evidence/` is complete according to its focused
specification and tasks. Decreasing timestamps within the current domain and
origin now terminate explicitly without recording the offending observation or
altering prior journal order. Acquisition remains `stopping` until connection
close completes, open failure creates no connection/segment evidence, and
unexpected stream completion explicitly ends the segment as a transport
failure. This is software-contract evidence only, not hardware acceptance or a
complete Phase 1 product.

## Current Limitations and Deferred Work

- No real Basic serial discovery/opening, serial configuration, DTR/RTS open
  handling, platform reconnect behavior, or physical-hardware validation.
- No durable persistence, bounded retention, retrieval, sessions, cursors,
  annotations, or crash-recovery guarantee; the in-memory recorder is test
  infrastructure for this foundation.
- No TX, Control, Monitor, Interact, follow, console, release/reacquire, or
  reconnect workflow.
- No service/HTTP, authentication, browser-origin rejection, CLI, MCP, or AI
  integration.
- No real Enhanced backend, protocol, firmware, USB framing, realistic timing,
  GPIO/event behavior, or Enhanced hardware-support claim.

## Planning Artifacts

- `specs/001-rx-continuous-evidence/spec.md`
- `specs/001-rx-continuous-evidence/checklists/requirements.md`
- `specs/001-rx-continuous-evidence/plan.md`
- `specs/001-rx-continuous-evidence/research.md`
- `specs/001-rx-continuous-evidence/data-model.md`
- `specs/001-rx-continuous-evidence/contracts/normalized-backend.md`
- `specs/001-rx-continuous-evidence/quickstart.md`
- `specs/001-rx-continuous-evidence/tasks.md`

## Blockers and Open Decisions

- No product decision blocks the next specification slice.
- Concrete Basic serial library/platform behavior, device selection, serial
  settings, DTR/RTS-open mitigation, normalized adapter failures, and hardware
  acceptance cases must be defined by the next focused specification; they are
  not contracts established by feature 001.
- Persistence/retention and later workflow/service contracts remain separate
  future specification decisions.

## Validation Status

- Specification checklist: 16/16 complete; no clarification markers remain.
- Python environment: Python 3.14.3; `uv sync --all-packages --dev` resolved 20
  packages and audited 19 packages.
- Focused acquisition validation: 29 passed. Focused quickstart validation now
  comprises 31 model/backend contract tests and 35 evidence/acquisition tests.
- Full gate: Ruff passed; mypy reported no issues in 15 source files; Import
  Linter kept 2 contracts with 0 broken; pytest passed 66 tests with 0 skipped
  and 0 failed; `git diff --check` passed.
- TDD evidence for the final correction: the two focused regression tests first
  failed because acquisition ended `stopped` instead of `failed`; after the
  correction, decreasing RX after either recorded RX or recorded loss produces
  an explicit transport failure. Equal timestamps remain valid, and origin
  reset clears the per-segment comparison baseline.
- TDD evidence for the lifecycle correction: 5 focused tests first failed for
  premature terminal state exposure, open failure stuck in `starting`, missing
  stream-end evidence, premature primary-failure exposure, and duplicate
  segment-end evidence after close failure. All now pass, with primary failures
  preserved and failed close conservatively preventing reacquisition.
- Neutrality/scope inspection found no backend-identity branch, serial/framework
  dependency, Enhanced implementation, or later-phase product code in Core.
  The only production `serial` match is the normalized
  `serial_line_control` capability name.
- Graphify's initial code-only structural index was generated because the slice
  introduced shared interfaces across multiple Core modules. Documentation
  semantic extraction was not included because its optional backend package is
  unavailable; this does not affect the code graph or software validation.
- No physical device was enumerated, opened, reset, flashed, or otherwise
  accessed.
