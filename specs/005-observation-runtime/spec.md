# Feature Specification: Observation-Only Device Core Runtime

**Feature Directory**: `005-observation-runtime`

**Feature Branch**: `main` (directory numbering is independent of Git branch)

**Created**: 2026-10-03

**Status**: Software implementation and T001–T028 are complete. T028's fresh
full gate passes: Ruff clean, mypy 40 files clean, all three Import Linter
contracts kept (31 files/77 dependencies), 924 hardware-free pytest cases passed
with zero failures/errors/skips, and diff/whitespace checks clean. The suite
includes 349 feature-005 cases, 565 completed-feature regressions and ten fixture
checks. T026 documentation reconciliation and T027's one code-only incremental
Graphify update are complete; generated output remains ignored.

The accepted observation-only scope, contracts/schema-v1 and deferrals remain
unchanged. At the T028 checkpoint, feature 005 was software-complete and ready
for final human review and commit, not yet committed or claimed accepted.
Current commit/progress status is in `docs/development_status.md`. The separate pre-existing
feature-003 JournalFailure context-manager limitation remains documented and
outside this feature. No physical-hardware acceptance or Phase 1 completion is
claimed. Detailed implementation/RED–GREEN evidence is in
[development history](../../docs/development_history.md).

**Input**: Observation-only Device Core runtime for Profile activation,
durable-session association, and attach/status/detach using completed features
001–004. Define concurrency, cancellation, startup, and teardown while
preserving the accepted scope and deferrals.

**Governing authority**: `docs/project_context_core.md`, especially §§5.2,
9.4, 13, 14.2–14.6, 15.1, 15.4, 16.1–16.2, 17.2–17.4, 18, and 22.2.
Completed feature contracts remain authoritative for their existing behavior.
This specification defines an internal application contract, not delivery APIs.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Own one durable observation run (Priority: P1)

As a later service composition caller, I need one resolved human-owned Profile
to activate one observation run, so continuous capture and durable evidence
share a defined lifetime without client-owned readers.

**Why this priority**: Later delivery and workflows need an application owner.
This slice supplies the observation-run composition over existing Profile,
journal and Acquisition contracts.

**Independent Test**: Attach using a resolved Profile, temporary journal, and
fake Basic serial device. Feed binary/ambient output, inspect status, detach,
reopen, and retrieve exact bytes and the final segment boundary with existing
bounded retrieval.

**Acceptance Scenarios**:

1. **Given** an inactive runtime and explicit resolved Profile, **When** attach
   succeeds, **Then** one new durable session is associated with that immutable
   Profile in memory and one authoritative acquisition path runs.
2. **Given** an active run, **When** no request/subscriber is present, **Then**
   ambient bytes continue entering the same ordered durable stream.
3. **Given** an active run, **When** detach completes, **Then** acquisition and
   physical close finish before journal close, preserving final evidence the
   existing Acquisition contract can record.
4. **Given** a source Profile edit after resolution, **When** the run continues,
   **Then** resolved values, session policy, and historical effective
   configuration remain unchanged.
5. **Given** an existing journal destination or invalid Profile source, **When**
   composition is requested, **Then** no backend opens, no journal is overwritten,
   and the respective existing failure is explicit.

### User Story 2 - Serialize requests and clean up failures (Priority: P2)

As an application caller, I need attach/detach/cancellation to leave ownership
honest after failures, so retries cannot overlap runs or destroy diagnostics.

**Why this priority**: Resource lifetimes must survive competing requests and
caller cancellation before delivery layers expose them.

**Independent Test**: Gate preparation, open, first append, read, physical close,
and journal close. Race/cancel requests and inject failures; assert ordering,
one reader, kept journals, explicit outcomes, and blocking after uncertain cleanup.

**Acceptance Scenarios**:

1. **Given** attaching/active/detaching, **When** ObservationRuntime.attach
   receives another already resolved Profile, **Then** it rejects immediately
   without queuing, Profile I/O, or preparation. A Basic convenience-edge call
   may first read/resolve its bounded explicit Profile, but creates/opens no
   journal, constructs/opens no backend, and enumerates no hardware when rejected.
2. **Given** attach is in progress, **When** detach arrives, **Then** it requests
   that generation's stop and joins cleanup without a second owner or waiting
   behind a lock held throughout startup.
3. **Given** detach is in progress, **When** more detach calls arrive, **Then**
   they join the same cleanup and receive the same settled status.
4. **Given** an admitted attach waiter is cancelled, **When** submitted work
   finishes, **Then** startup stops at the next safe checkpoint, resources are
   cleaned up, and cancellation propagates only after settlement.
5. **Given** an admitted detach waiter is cancelled, **When** cleanup runs,
   **Then** cleanup continues independently; cancellation propagates only after
   settlement and other waiters remain unaffected.
6. **Given** a created journal but failed backend construction/open/start,
   **When** cleanup completes, **Then** the journal is closed and kept with its
   actual session identity and whatever evidence committed.
7. **Given** failed/unconfirmed close, **When** another attach arrives, **Then**
   it rejects for that runtime instance's remaining lifetime; detach neither
   clears uncertainty nor retries physical close.
8. **Given** a runtime constructed on one running loop/thread, **When**
   attach/detach/status executes on another loop/thread or without a running
   loop, **Then** it fails before mutation, lock acquisition, or preparation;
   Basic-edge context failure also precedes its Profile read.

### User Story 3 - Report termination without backend assumptions (Priority: P3)

As an application caller, I need status and disconnect termination that
distinguish capture from ended/uncertain ownership without serial assumptions.

**Why this priority**: Clients need one state model rather than reconstructing
lifecycle from evidence or inventing reconnect behavior.

**Independent Test**: Run identical lifecycle assertions on fake Basic and the
Enhanced-shaped fixture with device timestamps, scoped loss, origin reset,
normalized disconnect, and failure. No protocol/hardware simulation is needed.

**Acceptance Scenarios**:

1. **Given** gated startup/teardown, **When** status is inspected, **Then** it
   reports attaching/detaching with established identities/capabilities only,
   distinguishing historical provenance from an active connection.
2. **Given** unexpected disconnect, **When** acquisition terminates, **Then**
   runtime closes its journal after acquisition cleanup, reports disconnect,
   and never automatically opens or scans for a device.
3. **Given** acquisition/recorder failure, **When** cleanup settles, **Then**
   status reports failure and cleanup certainty separately, preserving the
   first failure and distinguishable cleanup failures.
4. **Given** clean termination and a new explicit attach at a fresh destination,
   **When** accepted, **Then** a new run/session starts and old tasks cannot
   change the new generation's status.
5. **Given** both backend shapes, **When** identical lifecycle behavior runs,
   **Then** timestamp/loss provenance remains explicit without shared
   backend-identity branches.

### Edge Cases

- Cancellation before admission creates no run/resource.
- Cancellation during create/open/append/close does not abandon outstanding
  workers or cancel Acquisition's owner task.
- Attach-waiter cancellation after internal success publication but before
  result delivery still stops that run.
- Immediate startup disconnect can return terminal rather than active status.
- Final append failure does not prevent cleanup or fabricate a successful boundary.
- Journal close failure independently blocks reuse even after physical release.
- Rejected attach preserves the current/last summary.
- Runtime busy rejection performs no Profile I/O; Basic-edge busy calls may
  read/resolve the bounded explicit Profile before admission, without creating
  run resources. Invalid Profile may fail resolution instead of reporting busy.
- Close-only snapshot failure is primary_failure_kind None with close_failed
  true; runtime must not decode legacy transport failure to identify cleanup.
- Impossible state/owner-settlement/cleanup combinations cannot supply an
  independent attach_admissible flag or bypass its derived predicate.
- Racing detach/cancellation/acquisition termination coalesce into one teardown.
- Idle Acquisition is not an uncertain physical owner.
- Failed journal creation never authorizes removing a file it left behind.
- A failed backend open has no positive cleanup attestation in the existing
  normalized contract, so physical release remains unconfirmed even for a
  not-found failure. Most failed journal creations similarly leave recorder
  cleanup unconfirmed; exact conservative exceptions belong in the contract.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Runtime MUST own at most one accepted run, including startup and
  cleanup; each accepted attach MUST receive a fresh run identity.
- **FR-002**: Runtime MUST consume one already resolved immutable Profile.
  File resolution and explicit journal destination selection MUST stay outside
  shared lifecycle; no discovery, fallback, or Profile mutation is allowed.
- **FR-003**: RX/evidence MUST stay enabled and TX/Control/automatic reconnect
  disabled. Reported backend capability MUST still permit UART RX.
- **FR-004**: States MUST be inactive, attaching, active, detaching, terminated,
  or failed, with exact transition/status semantics in the internal contract.
- **FR-005**: ObservationRuntime.attach with an already resolved Profile MUST
  reject immediately during attaching/active/detaching, without Profile I/O,
  queuing, or preparation. The Basic edge MUST intentionally resolve its bounded
  explicit Profile before admission; a busy edge call MAY perform that read but
  MUST NOT create/open journals, construct/open backends, enumerate hardware,
  or otherwise prepare run resources. Later admitted attach MUST create a new session.
- **FR-006**: Mutations/terminal callbacks MUST serialize by generation. Status
  MUST remain inspectable during external I/O; lifecycle locks MUST NOT span
  preparation, open, capture, or close awaits.
  Runtime construction MUST bind immediately to a running event loop and its
  executing thread, without lazy binding/rebinding. All lifecycle mutation APIs
  MUST validate that context before locks/mutation/preparation; wrong-loop/thread
  or no-running-loop calls MUST reject as wrong_execution_context. Synchronous
  status MUST support only that same running context and MUST NOT mutate,
  schedule, marshal between threads, or bind the runtime. The Basic edge MUST
  check context nonmutatingly before Profile resolution. No process lock is added.
- **FR-007**: Detach during attach MUST request stop and join that generation.
  Concurrent detach MUST join one cleanup; inactive/settled detach MUST be
  idempotent and MUST NOT reopen or retry cleanup.
- **FR-008**: Startup MUST order resolved Profile validation/admission, fresh
  journal creation with exact Profile session policy, edge backend construction,
  and Acquisition start. No open may precede a usable durable recorder.
- **FR-009**: Acquisition MUST remain the sole backend opener/event consumer;
  segment start MUST commit before RX evidence under its existing contract.
  Runtime MUST add no staging reader or RX buffer.
- **FR-010**: Teardown MUST finish Acquisition/backend close and join its sole
  consumer before recorder close. Final appends MUST retain a usable recorder
  until completed, except when that recorder has itself failed.
- **FR-011**: Cleanup MUST be attempted for each acquired resource after earlier
  failures. No successful capture/boundary may be fabricated. First primary
  failure and cleanup failures MUST remain separate bounded normalized facts.
- **FR-012**: Runtime pre-admission cancellation MUST create no lifecycle
  mutation or run-resource preparation; the Basic edge MAY already have read
  its bounded explicit Profile before reaching admission. Admitted
  attach cancellation MUST request stop, drain work and cleanup, then propagate
  cancellation; it MUST NOT leave an active owner.
- **FR-013**: Detach cancellation MUST not cancel cleanup/other waiters; the
  cancelled waiter MUST await settlement. Repeated cancellation MUST not
  abandon teardown.
- **FR-014**: Failed preparation MUST close its created recorder before
  resource transfer and MUST report cleanup certainty and created session
  identity when available.
- **FR-015**: Created journals MUST remain after cancelled/failed attach.
  Runtime/composition MUST NOT delete journals, automatically retry creation/open,
  or remove artifacts after failed creation.
- **FR-016**: Each attach MUST use a fresh journal/session at an explicit
  destination. Append-resume is excluded; kept journals remain retrievable via
  existing bounded reopen/retrieval.
- **FR-017**: Profile/session association MUST be an in-memory mapping of the
  run's resolved Profile to its created session identity. Only one current/last
  summary may be retained; no Profile path or raw source is stored.
- **FR-018**: Feature-003 schema-v1 MUST stay unchanged. Persisted policy and
  effective segment provenance remain durable; full-Profile snapshot and
  historical DUT/Profile identity MUST NOT be claimed to survive restart.
  Durable association requires a future explicit versioned contract decision.
- **FR-019**: Status MUST be an immutable finite snapshot exposing state,
  current/last run and Profile, known session/connection/segment provenance,
  capture state, cleanup certainty, attach admissibility, terminal reason, and
  normalized failures. Unknown values MUST remain absent.
  owner_settled MUST reflect no initial owner or fully joined/quiescent generation
  work. attach_admissible MUST be computed, never independently supplied/stored:
  `(state in {inactive, terminated, failed}) and owner_settled and
  physical_release_confirmed and recorder_close_confirmed`. State/settlement
  invariants MUST reject impossible combinations; admission MUST use this same
  predicate after execution-context validation. Settled ownership MUST NOT
  coexist with a starting/acquiring/stopping acquisition; runtime physical
  release certainty MUST match its AcquisitionSnapshot when present.
- **FR-020**: Attaching MUST not claim a connection before Acquisition
  establishes it. Detaching MAY report live acquisition while draining;
  terminated/failed MUST not describe historical provenance as live.
- **FR-021**: Unexpected disconnect MUST terminate and clean up without
  reconnect; clean disconnect MUST differ from explicit detach, cancellation,
  transport failure, and recording failure.
- **FR-022**: Unconfirmed physical/recorder release MUST block further attach
  for that runtime's lifetime; reset/detach MUST NOT bypass this. Process restart
  MUST NOT be advertised as proof of physical release.
- **FR-023**: Runtime MUST use normalized Acquisition termination/provenance,
  never private fields, exception-message parsing, device queries, or lifecycle
  reconstruction from possibly expired evidence.
- **FR-024**: Acquisition MAY gain minimum read-only snapshot and termination/join
  guarantees needed here. Reader, ordering, generation, clock, failure, and
  close contracts MUST remain intact; additions MUST be explicitly documented.
  Failed open MUST NOT be equated with confirmed release merely because no
  connection was returned. Cleanup failure MUST remain visible alongside an
  earlier primary failure.
  The additive snapshot MUST expose primary_failure_kind:
  AcquisitionFailureKind | None for the first actual non-close acquisition
  failure, separately from close_failed. Close-only failure MUST leave that
  field None even when legacy Acquisition.failure remains TRANSPORT_FAILURE.
  Runtime MUST project these explicit facts directly, without reinterpreting
  legacy failure kinds or trigger/close combinations. Terminal trigger,
  committed provenance, and physical-release certainty MUST remain independent.
- **FR-025**: Backend/journal construction MUST stay at the composition edge.
  Shared runtime MUST use Core contracts and MUST NOT import adapters,
  filesystem, serial, HTTP, CLI, or MCP implementations.
- **FR-026**: Preparation substitution MUST solve resource-lifecycle testing;
  no registry/plugin/session catalogue, second persistence implementation, or
  competing acquisition architecture may be introduced.
- **FR-027**: Existing sequence, acknowledgment, retention, expiry, fixed-snapshot
  pagination, and provenance-envelope semantics MUST remain unchanged. Runtime
  MUST add no evidence kind.
- **FR-028**: Identical shared tests MUST run on fake Basic and the existing
  Enhanced-shaped fixture, including explicit RX capability rejection. No helper
  wire/firmware/GPIO/USB/timing or production Enhanced behavior may be added.
- **FR-029**: Tests MUST use temporary journals, fakes, and deterministic gates;
  default tests MUST retain fail-closed hardware guards and MUST NOT enumerate
  or open physical devices.
- **FR-030**: Tests MUST cover ordering, races, repeated cancellation, partial
  failure, uncertain close, immediate/active disconnect, stale generations,
  direct primary/close snapshot projection, derived admissibility/impossible
  statuses, construction-time loop/thread ownership, runtime-versus-Basic-edge
  busy I/O guarantees, journal compatibility/readback, and architecture.
  Implementation MUST pass the full repository validation gate.

### Key Entities

- **Observation Run**: Fresh accepted identity, immutable resolved Profile,
  session when created, and generation-scoped ownership.
- **Runtime Status**: One immutable current/last summary, never a growing history.
- **Prepared Run Resources**: Backend and usable recorder transferred from edge
  preparation to the accepted run.
- **Termination Summary**: Reason, first failure, cleanup failures, and independent
  cleanup certainty.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Successfully prepared runs have exactly one session; successful
  active runs have one backend open and one authoritative consumer. Cancelled
  pre-preparation runs and rejected attaches create zero run resources; a busy
  Basic edge may still perform the bounded explicit Profile read.
- **SC-002**: Binary/ambient bytes and successfully recorded final boundaries
  survive detach/reopen, subject only to explicit existing retention/expiry.
- **SC-003**: Every listed lifecycle race/failure has a deterministic regression;
  no cleanup runs twice and no stale generation changes a newer run.
- **SC-004**: Cancelled callers observe settled cleanup or explicit unconfirmed
  failure, never an abandoned owner or false success.
- **SC-005**: Both shapes pass identical shared assertions without identity
  branches, preserving timestamp and scoped-loss provenance.
- **SC-006**: Previously valid journals remain readable unchanged; historical
  full-Profile recovery is neither implemented nor claimed.
- **SC-007**: Default tests make no physical serial access; required software,
  static, and architecture checks pass before implementation is declared complete.

## Assumptions

- Accepted baseline: `6d10cf7`; features 001–004 are software-complete.
- Runtime construction requires and permanently binds to its current running
  loop/thread. Lifecycle APIs and synchronous status require that same running
  context; returned immutable snapshots may be inspected elsewhere. Process-wide
  locks/service exclusivity remain a later service responsibility.
- Existing adapter calls must eventually settle. No new numeric lifecycle
  deadline or forced worker abandonment is introduced. Pending status stays
  inspectable; no autonomous DUT-completion wait is introduced.
- In-memory association suffices here: Core requires effective historical
  configuration, already persisted per segment, not a complete source Profile.
- Attaching begins only after resolved Profile admission; parser failure is
  outside runtime mutation.

## Explicit Exclusions and Deferred Behavior

- Service/HTTP/authentication/browser rejection, CLI, process locks/deployment.
- Monitor/follow, derived views/patterns, annotations, operations, expanded
  retrieval filters, live subscriptions.
- TX/Interact/console, line endings/arbitration, semantic Control, intentional
  DTR/RTS actions, safe-state execution.
- Reconnect/native-USB topology, release/reacquire/handoff, ownership-gap records,
  external-program execution.
- Durable Profile/DUT identity association, schema changes, session catalogue,
  naming/sealing/resumption/rotation/deletion, cleanup retries, Profile discovery,
  reload/default paths, numerical defaults.
- Enhanced production behavior, MCP, AI, and physical hardware/electrical
  acceptance. Existing serial-open limitations remain explicit.
