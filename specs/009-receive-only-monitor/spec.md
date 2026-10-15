# Feature Specification: Bounded Receive-Only Monitor

**Feature Identifier**: `009-receive-only-monitor` (sequential repository workflow; work remains on `main`)
**Created**: 2026-10-14
**Status**: T001–T037 complete (37/37); T036 structural reconciliation and T037 final software verification are complete. Bounded receive-only Monitor is implemented through Core/service/CLI. Recorded T037 software gate: 5783 passed; Feature 009 is software-complete; Phase 1 and native/physical acceptance remain incomplete. See [tasks](tasks.md), [current status](../../docs/development_status.md) and [history](../../docs/development_history.md).
**Input**: Accepted bounded, receive-only Monitor through the authenticated service and thin CLI. The original `specify → plan → tasks` workflow defined scope; implementation and safe software acceptance followed in separately authorized tasks. No physical hardware acceptance is claimed.

## Authority and Scope

[Core](../../docs/project_context_core.md), especially §§5–7.1, 11–18, 22.2 C/H/I/J and 23, governs. Completed Features001–008 are dependencies, not permission to weaken ownership, evidence, lifecycle, security or delivery. [Current status](../../docs/development_status.md) governs progress. Concrete decisions below are detailed in [contract](contracts/monitor.md) and [data model](data-model.md).

This adds one finite literal-byte Monitor to an already active, explicitly associated session. It creates no reader, opens no DUT, transmits no UART bytes and performs no control action. Its start is a position in Core's committed observation order, never DUT emission time or a causal barrier.

Core §14.1 requires operation start/end evidence. This feature therefore introduces **explicit journal schema-v2 and operation-record-v2**, solely for these markers. Legacy schema-v1 creation/opening, old four record encodings, Feature003 retention/retrieval and Profile-v1 remain intact. New service-composed runs explicitly use v2; there is no migration or historical browsing. This is a persistence contract revision, not a Core semantic change.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Wait for an Exact Byte Condition (Priority: P1)

A caller with an active session requests a finite wait for one literal byte sequence, then inspects the result and referenced evidence through the authenticated CLI.

**Why this priority**: The smallest useful deterministic Monitor needs neither TX, text interpretation nor client timing loops.

**Independent Test**: In a guarded fake-DUT service/CLI stack, request a binary condition, inject unrelated/matching chunks, and retrieve markers and unchanged raw bytes. Run identical assertions against Basic-shaped and Enhanced-shaped fixtures.

**Acceptance Scenarios**:

1. **Given** an active known session and RX capability, **When** the condition arrives after the committed start marker across chunks, **Then** the first match has exact sequence/byte endpoints, provenance, finite timing and positive start/end references.
2. **Given** matching bytes committed before the start, **When** no later match arrives, **Then** old bytes cannot satisfy it and timeout is reported.
3. **Given** NUL/invalid-UTF-8 RX, **When** it matches, **Then** exact bytes stay retrievable as padded base64 without decoding/removing asynchronous or trailing output.
4. **Given** unknown/different/terminal session, missing Monitor support or another Monitor, **When** requested, **Then** an exact rejection creates no transport or operation evidence.

### User Story 2 - Understand Bounds and Evidence Quality (Priority: P2)

A caller distinguishes match, deadline, examined-byte limit and connection termination, including loss, retention and observation-boundary limits.

**Why this priority**: The terminal result must explain which bound/event won and what the evidence can establish.

**Independent Test**: Inject a host clock over a temporary journal to test equality, chunk spans, loss, segment ends and eviction independently of CLI latency.

**Acceptance Scenarios**:

1. **Given** RX publication at the deadline, **When** it contains a match, **Then** timeout wins; an eligible chunk just before it is processed atomically. A match on the last allowed byte wins over byte exhaustion.
2. **Given** observed loss between prefix/suffix, **When** later bytes arrive, **Then** matching restarts and loss/count remains explicit; no continuity is invented.
3. **Given** origin/segment change, disconnect, detach or recording/transport failure, **When** it terminates Monitor, **Then** the corresponding outcome does not rewrite capture facts.
4. **Given** rolling eviction of referenced markers/RX, **When** retrieved, **Then** Feature003 expired/partial/not-found rules apply; a completed match is neither revoked nor pinned.

### User Story 3 - Settle Owned Work and Evidence Honestly (Priority: P3)

Client loss, detach and shutdown leave no unowned wait, premature recorder closure or invented durable evidence.

**Why this priority**: Finite observation must preserve capture ownership and truthful cleanup.

**Independent Test**: Cancel waiters and gate marker writes/close; prove settlement and preservation of the existing permanent reader-cleanup uncertainty latch.

**Acceptance Scenarios**:

1. **Given** owned Monitor, **When** delivery disappears, **Then** the finite operation settles its outcome and submitted marker work while capture continues.
2. **Given** stop racing with start submission, **When** start positively commits, **Then** pending stop decides Monitor and end work joins before recorder close; rejection before submission creates no marker.
3. **Given** failed start acknowledgement, **Then** no reference/result is invented. **Given** failed end acknowledgement after a decision, **Then** preserve the observation outcome alongside `end_unconfirmed`, null end reference and normalized failure.
4. **Given** uncertain terminal-reader cleanup, **When** Monitor/shutdown settle, **Then** they cannot restore the false latch or authorize a clean marker.

### Edge Cases

- Exact limits, bool/coercion/duplicate/extra/query fields, malformed or noncanonical base64, terminal/attaching/draining state and absent optional support.
- Overlap, chunk prefixes/trailing bytes, empty RX, loss/unobservable loss, origin changes, counter overflow and policy too small for either marker.
- Append/retention/point-read races, registration before Core admission, stop around start submission, deadline equality and late/ambiguous end writes.
- Encoded provenance/markers/report overflow rejects wholly; references can expire after success.
- Client cancellation, SIGINT/closed pipes, bad remote reports, all journal failures and blocked durable I/O at shutdown.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Require an explicit session of the current active run in this service incarnation; never attach/select DUT/browse history/read client paths or monitor terminal runs.
- **FR-002**: Require one exact literal condition of1..256 bytes, timeout1..4000 ms and examined-RX bound1..1048576 bytes; all mandatory, no defaults/text/regex/unbounded mode.
- **FR-003**: Core owns admission/timing/matching/outcomes/evidence. One Core Monitor and one registered service Monitor; no queue, second reader, retention pin, unbounded byte buffer or client timing loop.
- **FR-004**: Reuse the authoritative journal gate/worker. A minimal serialized recording coordinator publishes only positively acknowledged records on the owner loop, commits the start marker and installs matching/deadline before releasing that boundary.
- **FR-005**: Match only post-start RX within captured connection/segment. Span chunks/support overlap with bounded state; reset on observed loss and terminate at boundaries. Host publication timing controls deadline; backend clocks/provenance remain separate.
- **FR-006**: First decision freezes half-open window, byte endpoints/counts, observed-loss count and timing. Timeout wins equality; match on last allowed byte wins byte exhaustion. End latency/later RX cannot extend the window.
- **FR-007**: Outcomes are `matched`, `timeout`, `byte_limit`, `disconnected`, `detached`, `timestamp_origin_reset`, `recording_failure`, `transport_failure`, `service_stopping`; exact races follow contract and preserve capture facts.
- **FR-008**: Markers share total sequence, durable acknowledgement, ordinary charge/retention/retrieval with RX. Start retains condition/provenance; end retains outcome/window/match/timing. Condition bytes are not UART RX/TX.
- **FR-009**: Explicit schema-v2/operation-record-v2 preserves legacy schema-v1, four record-v1 codecs, Profile-v1 and all003 snapshot/outcome/zero-page/counter/retention rules without migration. Terminal v2 reads remain short-lived and genuinely read-only after confirmed writer close.
- **FR-010**: Preflight both marker ceilings against captured policy without reservation/pinning/policy change. Failed start returns normalized error without fabricated refs/retry; failed end preserves observation facts with explicit incomplete durability.
- **FR-011**: Own finite work across cancelled delivery. Detach seals admission and settles marker work before recorder close. Shutdown seals registration/Core admission, decides active Monitor, joins it and preserves old mutation/read cleanup and permanent uncertainty.
- **FR-012**: Add only authenticated literal POST `/v1/observation/monitor` under unchanged006 peer/Host/browser/Bearer/media/query/privacy gates; closed request/result/errors. Body cap16384 bytes, canonical response cap1048576 bytes independently of policy; whole413 on overflow.
- **FR-013**: Add only thin CLI `monitor` with mandatory inputs/closed-wire validation. Independent canonical output cap1048576 bytes plus LF; retain007 credentials, receipts, timeout/transport/output/interrupt/exits.
- **FR-014**: Add exactly two marker projections to evidence HTTP/CLI; preserve four old shapes, binary encoding, cursor caps, snapshots, errors and whole413. All declared `JournalFailure` categories retain exact mappings/standard exception transport.
- **FR-015**: Require focused RED/GREEN Core/journal/runtime/service/CLI/lifetime/installed tests and identical Basic/Enhanced-shaped assertions; retain full uv/import/installability/privacy gate. Default and planning validation remain hardware-free.

### Key Entities

- **Monitor request/operation**: explicit session/condition/bounds; private finite owner and committed start boundary.
- **Monitor result**: frozen outcome/window/byte endpoints/provenance/timing and independent evidence durability.
- **Operation evidence**: ordered/charged start/end; stable references can expire.
- **Prepared Monitor access**: optional application capability over the same journal/coordinator; absent support preserves legacy attach behavior and rejects Monitor explicitly.
- **Host clock**: incarnation-local monotonic timing distinct from backend observation clocks.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Identical backend scenarios prove binary chunk-spanning matches and zero pre-boundary matches, with one RX path.
- **SC-002**: Injected-clock tests prove observation deadline/bounds, all ties/outcomes and no causation claim; durable I/O/cleanup time is separately described, never falsely bounded.
- **SC-003**: Strict active/terminal marker/window/provenance/retention projections and legacy v1/Profile compatibility pass.
- **SC-004**: At-limit/one-over request, condition, counter, cursor, HTTP/output tests reject whole overflow without private leakage.
- **SC-005**: Ownership/shutdown tests show no unowned Monitor, premature writer close or false clean marker.
- **SC-006**: Full software gate/guarded installed flows pass before implementation completion; native/physical acceptance is separately unexecuted unless authorized.

## Assumptions and Deferrals

Observation-only Profile-v1 suffices. Legacy injected runs may omit Monitor support; production composition explicitly supplies it. The4000 ms ceiling preserves007's5 s phase/10 s overall HTTP budget, not a guarantee for blocked journal/OS I/O. Literal binary matching is the sole completion condition, a concrete Core-permitted model.

Deferred: capture-only/time-only modes, multiple conditions, regex/text/lines, Follow/streaming, TX/Interact/console, Control, handoff/reconnect, annotations, catalogue/discovery, restart recovery/arbitrary history, service management, Enhanced production, MCP/AI and native/physical/electrical acceptance. No operation catalogue/status/replay/cancellation API, retained result history or new backend method/capability.

**Unresolved decisions**: None. Research/contract artifacts settle the concrete choices. Implementation progress is recorded in [tasks](tasks.md); all 37 implementation tasks are complete; current status governs readiness and remaining acceptance.
