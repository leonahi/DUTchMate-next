# Implementation Plan: Receive-Only Live Follow

**Feature**: `011-live-follow` | **Date**: 2026-10-16 | **Git branch**: `main`
**Input**: [spec.md](spec.md). T001–T024 complete; Feature011 software-complete; implementation commit recorded in development_status.md.
Completed evidence/progress/limits reconciled; existing architecture explanation accurate.
T0213444 focused/625 installed passes remain recorded evidence; no T022 test/full gate.
T022 import contracts/docs checks remain recorded; T023 tooling/docs/diff checks pass.
T023 trigger met; one incremental update completed with recorded health/zero-node limits.
T024 fresh 8182 full passes, including625 guarded Follow/007–010 process cases; static/import/diff/artifact/privacy review pass without correction.
Final separately authorized pre-commit/full/staged/installability/privacy review passed without correction.
Implementation committed; plan unchanged; Phase1 incomplete; nothing pushed or automatically started.
Spec Kit resolves011-live-follow as the logical feature name via its ignored local
pointer; no branch hook is configured and no Git branch was created.

## Summary

Add one receive-only live subscriber over the existing authoritative coordinator/
journal through authenticated NDJSON and the thin CLI. Atomically capture live
tail/provenance, wake on all append paths, read bounded pages on the same journal,
report retention gaps and explicit terminal delivery facts. No schema/evidence
variant, reader, transport owner, migration, Profile revision or dependency.

## Technical Context

**Language/Version**: Existing Python>=3.14,<3.15; committed software evidence3.14.3.
**Primary Dependencies**: Existing asyncio/dataclasses/json; FastAPI/Uvicorn,
Typer/HTTPX; SQLite/pyserial remain behind existing adapters. No new dependency.
**Storage**: Existing explicitv3 production journal, same worker/connection and003
retrieval; strictv1/v2 entry paths/readers untouched. Follow itself is ephemeral.
**Testing**: pytest/pytest-asyncio; deterministic gates/clocks/cancellation; both
backend shapes, real temporary journals, guarded loopback/Uvicorn and non-editable
wheel/sdist outside-cwd processes. No default hardware/account access.
**Target Platform**: Existing Linux/macOS POSIX delivery contract; actual Windows
commands remain unsupported. No native/physical acceptance automatically selected.
**Project Type**: Existing modular monolith/Ports-and-Adapters; inward Core,
authenticated local HTTP service and thin CLI.
**Performance Goals**: Notification-driven live reads, no idle storage polling,
one bounded page/frame, no network waits holding capture gate or pinning retention.
**Constraints**: One subscriber/job; min(policy,32 records/1MiB charged bytes);
1MiB JSON+LF/frame;16KiB body;1s heartbeat/5s send/receive frame budget;10s
handshake, no whole-session deadline. Existing eight read/eight mutation/one
Monitor slots and all durable I/O/cleanup guarantees remain.
**Scale/Scope**: Current ACTIVE associated session only, no resume/history/fanout;
all seven evidence variants, no new persistent values or backend capability.

## Constitution Check

The repository constitution is an unpopulated scaffold; it adds no rule/approval.
Core/AGENTS govern. The following gates were evaluated before research and
rechecked against the completed design artifacts.

| Gate | Design evidence | Result |
|---|---|---|
|Core receive-only semantics|Live view only, Ctrl-C closes subscriber, no DUT action|Pass|
|Single ownership|Same coordinator/live journal/read leases; no extra RX/store|Pass|
|Honest evidence|Atomic actual tail, exact bytes/sequences, explicit retention/tail/unknown facts|Pass|
|Bounds|One slot/page/signal, fixed frame/body budgets, explicit oversized terminal|Pass|
|Lifetime|Strong captured-generation queries, synchronous seals before HTTP drain, join before close|Pass|
|Compatibility|003/005–010 preserved; optional prepare transfer; no schema/Profile/clock/backend revision|Pass|
|Architecture/security|Core has no delivery imports; existing authentication/browser/no-store; thin CLI|Pass|
|Backend neutrality|Identical fixture workflows, capability-dependent loss preserved|Pass|
|Safety/installability|Guarded fake processes/uv/packages, native/hardware explicitly deferred|Pass|
|Scope/status at planning review|Artifacts only,0/24 tasks then; current foundation progress in tasks/status; Phase1 incomplete|Pass|

No unresolved clarification or unjustified violation. Alternatives/source
findings are in [research.md](research.md); exact behavior is in
[contract](contracts/follow.md), state/bounds in [model](data-model.md).

## Project Structure

### Documentation (this feature)

Eight Markdown artifacts under `specs/011-live-follow/`: spec.md, plan.md,
research.md, data-model.md, contracts/follow.md, quickstart.md, tasks.md and
checklists/requirements.md. Current progress stays in docs/development_status.md;
completed evidence is appended newest-first to docs/development_history.md.

### Planned implementation impact

- New `core/src/dutchmate_core/follow.py`: pure request/start/gap/batch/end/
  rejection/state/page-consumption values. Depend only on existing inward evidence/
  model values; no coordinator/runtime/adapter/delivery import.
- `core/src/dutchmate_core/monitor.py`: gated live-head registration and
  coalesced wakeup on all four append paths. Update its no-journal-read docstring
  only for the new gated metadata probe. Do not change Monitor matching/clock.
- `core/src/dutchmate_core/runtime.py`: optional prepared Follow transfer near
  PreparedObservationRun, admission/one owner/pulls/seals/joins/final cutoff,
  using existing read lease/uncertainty machinery. Keep idle wait ownership
  separate from submitted resource-query ownership.
- `core/src/dutchmate_core/adapters/observation_runtime.py`: expose optional
  Follow access from the already-selectedv3 coordinator/live reader.
- `pyproject.toml`: when follow.py exists, include it below monitor and above
  acquisition in the inward layers and adapter-forbidden source set; no exemption,
  weakened contract, dependency or lock change.
- New `apps/service/src/dutchmate_service/follow_http.py`: guarded admission/
  streaming/strict projections, per-frame bound/send timeout/heartbeat. Existing
  app.py/http.py add the literal route and independent job owner; server.py may
  need minimal stop-latch wiring to seal before HTTP drain. Reuse existing record/
  provenance/retention projection helpers, no competing evidence codec.
- New `apps/cli/src/dutchmate_cli/follow.py`: bounded frame validator/cursor and
  narrow streaming exchange; existing client.py/main.py add command/error routing
  and narrowly accurate help. Reuse strict existing delivery validators; finite
  exchanges/context/credential behavior stay unchanged.
- Focused new tests in existing Core/service/CLI test trees; exact files/tasks
  below. Reuse guarded process builders. Shared fakes change only if indispensable.
- No planned edit to model.py/evidence.py, SQLite/terminal adapters, Profile,
  acquisition/backend, bootstrap/credentials, package metadata or uv.lock.
  A demonstrably required compatibility fix needs an affected-consumer inventory,
  focused evidence and minimal scope, never speculative rewrites.

**Structure Decision**: Extend concrete coordinator and runtime, not a message bus
or subscription framework. The pure follow module can sit below monitor because
prepared coordinator transfer lives at runtime. No dependency cycle or new port
hierarchy. Existing read boundary already provides a metadata-only live-head
probe and bounded selection. Architecture docs change only if an actual
implemented relationship changes; no new architecture document or Core rewrite.

## Implementation Sequence and Validation Checkpoints

1. **Foundation T001–T005**: baseline/invariant/consumer inventory; RED/GREEN pure
   Follow values, then RED/GREEN bounded page/gap/read-position state. No live
   coordinator/runtime/composition/HTTP/CLI behavior. Extend import coverage only
   when the new module exists. Full foundation gate atT005.
2. **US1 T006–T009**: RED/GREEN coordinator and actual-journal integration, both
   fixture shapes/all four append paths; RED/GREEN optional preparation/runtime
   admission/strong query ownership/seals/cutoff and productionv3 capability.
3. **US1 T010–T013**: RED/GREEN authenticated streaming/job/stop contract and thin
   incremental CLI. Real guarded streaming, Monitor/annotation/read coexistence
   and end-to-end MVP; full gate atT013.
4. **US2 T014–T016**: Core retention/byte/page/gap boundaries and service/CLI
   framing/slow-consumer/privacy edge tests; minimal corrections only for
   demonstrated defects. Focused003/008–010 regressions.
5. **US3 T017–T019**: deterministic Core and service lifetime/shutdown/security
   races, cancellation and stalled peers; correct genuine defects only, inventory
   consumers and run combined focused005/006/008–010 plus full gate atT019.
6. **Installed/review T020–T022**: guarded wheel/sdist streaming outside checkout
   and existing007–010 process regressions; complete Core/spec/contracts/artifact/
   privacy review; executable quickstart reconciliation; completed-evidence-only
   status/history and Core§16 conformance.
7. **Final tooling/readiness T023–T024**: evaluate actual final structural/shared
   interface Graphify trigger atT023, one code-only incremental update if triggered,
   no premature updates; fresh final full gate/installability/artifact review
   atT024. Stop for separate pre-commit authorization; no automatic commit/push.

First implementation group: **T001–T005 only**, ending beforeT006 coordinator/
journal live integration. Individual RED/GREEN tasks use focused validation, not
routine full-suite repeats. Required full gates areT005/T013/T019/T024:
`uv run ruff check .`, `uv run mypy .`, `uv run lint-imports`,
`uv run pytest`, `git diff --check`. Run through RTK/uv with hardware/account
guards. Rerun required full gate after a corrective executable/governing-contract
change. Documentation recording of observed results uses AGENTS8.3 consistency/
diff checks. No tests or new behavior have been executed during planning.

## Complexity Tracking

No violation. One ephemeral subscriber and bounded existing read boundary suffice.
The internal empty-range head probe avoids new persistence schema/API, while
explicit framing/stop ownership is necessary for a genuine streaming boundary.
No generic registry, copied broadcast queue, new dependency, second reader,
historical catalogue or future capability implementation.
