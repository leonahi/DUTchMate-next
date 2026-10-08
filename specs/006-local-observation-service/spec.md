# Feature Specification: Local Observation Service

**Feature Directory**: `006-local-observation-service`
**Feature Branch**: `main` (sequential directories do not create branches)
**Created**: 2026-10-07
**Status**: T001–T030 delivered. Bootstrap, HTTP/lifecycle/owned mutations,
controlled listener/signals and joined shutdown/confirmed bootstrap teardown
implemented. T027's14 focused commands GREEN, zero failures/errors/skips; union
coverage1485 distinct cases. Targeted Ruff/mypy51 files/five import contracts/diff clean.
T028 reconciles current status/history, baseline and limits with documentation-only
checks. T029 structural trigger met; one code-only incremental Graphify update
succeeded, outputs ignored. T030 fresh full gate:1485 passes, zero failures/errors/
skips; Ruff/mypy51 files/five import contracts/diff checks clean. Final intended
diff review found no new defect; no source/test/config correction.
Feature006 is software-complete, uncommitted and ready for separately authorized
final review and commit. Human acceptance and hardware/platform acceptance remain
separate. Unused test HTTP client dependencies removed.
**Input**: Minimal authenticated local Device Core Service for observation-only attach/status/detach.

Core governs, especially §§5.2, 13, 14, 15.1, 16.1–16.4, 17.2–17.4, 18, 19 and
22.2 A/H/J. Feature-005 lifecycle/cleanup, feature-004 Profile-v1 and feature-003
schema-v1 remain authoritative. Exact HTTP/bootstrap rules are in
[the contract](contracts/local-observation-service.md).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Reject unintended local access (Priority: P1)

A local developer obtains an owner-private credential; other local callers and
browser-originated requests reject before any Profile read or resource preparation.

**Why this priority**: Access control must exist on the first usable delivery surface.
**Independent Test**: Real isolated bootstrap plus fake-only app, raw security headers,
body faults and Profile/resource tripwires.

**Acceptance Scenarios**:
1. **Given** correct Host, absent Origin and current credential, **When** status
   is requested, **Then** immutable inactive facts return.
2. **Given** invalid/duplicate Host, any Origin or invalid credentials, **When**
   any HTTP path is requested, **Then** the first applicable gate rejects before body/Profile reads.
3. **Given** a prior clean incarnation, **When** restart succeeds, **Then** a fresh
   private credential replaces the previous token before requests run.
4. **Given** a URL secret or malformed input, **When** rejected, **Then** supported
   responses/logging never echo credentials or supplied input.

### User Story 2 - Own observation across requests (Priority: P2)

A permitted caller attaches using explicit Profile/journal paths, inspects status,
and detaches. Observation persists across idle clients and lost response delivery.

**Why this priority**: Existing lifecycle needs one persistent process owner.
**Independent Test**: HTTP attach with fake Basic and real temporary SQLite;
ambient binary evidence between calls; detach and existing bounded readback.

**Acceptance Scenarios**:
1. **Given** inactive service, **When** attach succeeds, **Then** one persistent runtime
   owns one run/session/reader and returns truthful immutable facts.
2. **Given** busy/uncertain cleanup, **When** another attach arrives, **Then**
   feature-005 rejection persists. Busy Basic edge may resolve the bounded Profile,
   but never creates a journal or constructs/opens a backend.
3. **Given** registered attach/detach, **When** HTTP delivery is cancelled/lost,
   **Then** the service operation settles independently without attach_cancelled intent.
4. **Given** disconnect/startup/acquisition/cleanup failure, **When** status returns,
   **Then** cause, primary, cleanup and certainty stay independent; no reconnect occurs.

### User Story 3 - Start and stop one honest owner (Priority: P3)

A developer starts one service for the local account and shuts down without
abandoning accepted work or silently taking over uncertain resources.

**Why this priority**: Duplicate ownership/shutdown races invalidate capture guarantees.
**Independent Test**: Isolated bootstrap, fake/gated runtime and hardware-free
subprocess tests of exclusion, stale markers and joined shutdown.

**Acceptance Scenarios**:
1. **Given** a live owner, **When** another service uses a different port,
   **Then** it rejects before credential replacement/runtime creation.
2. **Given** a registered attach not yet invoked, **When** shutdown starts,
   **Then** admission closes, all operations settle, then detach/join runs.
3. **Given** unclean/uncertain/malformed marker, **When** restart is attempted,
   **Then** no automatic takeover, journal probing or marker clearing occurs.
4. **Given** fully confirmed cleanup, **When** shutdown finishes,
   **Then** credentials invalidate, cleanup is durably confirmed and the lock releases.

### Edge Cases

- Import/configuration creates no runtime, listener, credential or DUT resources.
- IPv6 unavailable fails; no address fallback, DNS selection or dual listener.
- Origin absent differs from present-empty/null/duplicate; only absence is eligible.
- Bad Host precedes Origin/auth; authentication precedes body/route errors.
- Pre-registration observed cancellation/disconnect submits nothing; wire loss can race registration.
- HTTP 200 with failed runtime state means a completed exchange, not active capture.
- Lost attach response grants neither automatic retry nor exactly-once replay.
- Eight pending mutations fill the finite service registry; results do not form a history.
- Hung work keeps shutdown pending without timeout/abandonment.
- OS lock availability is not physical-release evidence; even idle crashes may block restart.
- Partial bootstrap cleanup and failed safe publication fail closed.
- Primary failure with confirmed physical/recorder cleanup can still permit clean service shutdown.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: FastAPI MUST compose exactly one persistent ObservationRuntime constructed in async lifespan on its running loop/thread.
- **FR-002**: All runtime APIs MUST execute on that owning loop/thread; HTTP/framework types remain outside shared Core.
- **FR-003**: Launcher MUST bind only default numeric 127.0.0.1 or explicitly selected ::1, explicit port, IPv6-only sockets and no fallback.
- **FR-004**: Service MUST use one process/worker; reload, multiple workers and post-lock forks are unsupported.
- **FR-005**: Nonblocking OS lock MUST reject cooperating duplicate processes for the same account regardless of port; PID/age is never authority.
- **FR-006**: Bootstrap MUST validate private account ownership, permissions, regular files and link safety before runtime/resources.
- **FR-007**: One cryptographically random process-lifetime credential MUST be safely published before admission, rotated on eligible restart and invalidated at shutdown.
- **FR-008**: Credential transport MUST use one Authorization Bearer header only; URL/query/cookie/argv/environment tokens and secret logging are forbidden.
- **FR-009**: Host MUST be exactly one configured numeric authority; missing/duplicate/malformed/unlisted values reject deterministically.
- **FR-010**: Every present Origin MUST reject; absent Origin still requires Host/auth. Browser provenance headers cannot bypass rejection.
- **FR-011**: Ordering MUST be Host → Origin/browser provenance → authentication → route/query/body validation → service admission, before Profile reads/preparation.
- **FR-012**: Bounded well-formed credentials MUST use constant-time comparison; tests/development use the same authentication path.
- **FR-013**: HTTP MUST expose only attach, status and detach with exact methods, fields, projection and mappings in the contract.
- **FR-014**: Attach MUST require bounded explicit absolute Profile and fresh journal destination paths; no defaults/discovery/overwrite/resume.
- **FR-015**: Basic/SQLite construction MUST remain at existing attach_basic_observation edge; runtime stays the normalized lifecycle owner.
- **FR-016**: Runtime/Profile failures MUST map to bounded categories without raw exception text, input echo, source paths, private tasks or resources.
- **FR-017**: Status MUST preserve truthful known/absent facts, trigger/primary/cleanup/certainty separation and backend neutrality.
- **FR-018**: Mutations MUST register strongly owned bounded operation tasks before yielding; cancelled/lost HTTP delivery MUST NOT cancel them.
- **FR-019**: Observed pre-registration cancellation/disconnect MUST submit nothing; exact wire-disconnect versus admission ordering is not promised.
- **FR-020**: Completed operation entries MUST be consumed/removed; no replay cache, public jobs, unowned work or growing history.
- **FR-021**: Shutdown MUST close mutation admission, join registered operations, then detach/join runtime before credential/ownership release.
- **FR-022**: Repeated cooperative shutdown/cancellation MUST preserve draining and a latched startup stop; admission MUST NOT reopen. No finite lifecycle timeout, forced cancellation or uncertainty reset.
- **FR-023**: Separate bounded service cleanup marker MUST be unconfirmed before runtime construction, confirmed only after joined physical/recorder cleanup.
- **FR-024**: Unclean/uncertain/malformed marker with released OS lock MUST block startup; no PID stealing, automatic clearing or journal repair.
- **FR-025**: Partial startup MUST unwind acquired resources in reverse order and preserve inability to confirm cleanup. Replacement followed by fsync failure MUST report publication failure without falsely claiming rollback; true marker is attempted only after actual cleanup confirmation.
- **FR-026**: Access logs/input-bearing diagnostics MUST be disabled; errors and supported logs expose bounded normalized categories only.
- **FR-027**: Schema-v1, Profile-v1, sequence/retention/retrieval and feature-005 lifecycle/cancellation/cleanup semantics MUST remain unchanged.
- **FR-028**: Hardware-free tests MUST cover security ordering, lifetime, busy, cancellation/shutdown, bootstrap/stale/duplicate and IPv4/IPv6 contracts.
- **FR-029**: Identical applicable shared lifecycle assertions MUST run on fake Basic and existing Enhanced-shaped fixture without Enhanced production behavior.
- **FR-030**: Implementation MUST pass full repository gates with strengthened service/Core boundaries and no exemptions or hardware access.

### Key Entities

- Service incarnation: one process/loop, credential and OS lock.
- Private bootstrap state: fixed per-user lock, token and one finite cleanup marker.
- Service operation: retained attach/detach task until settlement, never a public job.
- HTTP status view: readiness and immutable runtime facts, no live handle.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Every security rejection causes zero Profile reads/run-resource preparation.
- **SC-002**: Each accepted run uses one runtime/reader/session; ambient binary evidence survives detach/readback.
- **SC-003**: Cancelled/lost delivery never abandons a registered mutation or creates attach_cancelled intent.
- **SC-004**: Duplicate/stale-owner tests never produce a competing owner or false cleanup confirmation.
- **SC-005**: Shutdown joins accepted work before final detach and recorder/resource release.
- **SC-006**: Both backend shapes pass applicable identical tests; completed 001–005 regressions remain green.
- **SC-007**: Captured responses/logs and URL examples contain no credentials or supplied-input diagnostics.

## Assumptions and Explicit Deferrals

- Completed 001–005 baseline: feature-005 commit 2824c0dc3ecc63684f573b3b0a55c621e18e069f;
  HEAD ed11051 records its hash. Initial local service platform is Linux/macOS POSIX;
  Windows service support rejects before bootstrap and is deferred, without changing portable Core.
- Fixed per-account guard covers cooperating service instances, not arbitrary tools/other users.
  Transport exclusivity remains independently enforced where the existing adapter supports it.
- Idle crashes can conservatively leave unclean state. External operator resolution is
  required; no reset/recovery/daemon-manager API is introduced.
- Original planning introduced no code/dependencies. Separately authorized T001–T005
  now add only installable service tooling and private bootstrap helpers.
- Deferred: retrieval/streaming, CLI, Monitor/follow, TX/Interact/console, Control,
  reconnect, release/reacquire/handoff, session catalogue/naming/sealing,
  Profile discovery/defaults/reload, durable Profile association/schema changes,
  Enhanced production behavior, MCP/AI and physical-hardware acceptance.
