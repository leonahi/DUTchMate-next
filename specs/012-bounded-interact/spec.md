# Feature Specification: Bounded Interact

**Feature Directory**: `012-bounded-interact`
**Feature Branch**: `main` (sequential directory numbering; no branch hook)
**Created**: 2026-10-18
**Status**: T001–T030 complete (30/30). Feature 012 is software-complete within
the observed macOS/arm64 scope; Phase 1 remains incomplete. The separately
authorized final pre-commit review and implementation commit are complete.

Core, authenticated service/API-v2 and thin CLI Interact are implemented. T030's
fresh final full gate passes 11,393 tests with zero failures/errors/skips and
warnings as errors; final guarded installed/artifact/privacy/Core review passes
without a new defect or production/test correction. [Development status](../../docs/development_status.md)
is authoritative for current progress; [history](../../docs/development_history.md)
records the initial cache setup failure, final GREEN evidence, earlier RED/GREEN
results, corrections and authorizations. The initial planning-only and first
T001–T005 restrictions are historical; separate task authorizations cover the
completed work. No hardware, Graphify rerun, commit, push or next slice at T030. Subsequently,
pre-commit review corrects one unpaired-v4-end timestamp invariant with six
RED→GREEN cases; the fresh11,399-test full gate and staged artifact/privacy review
pass. Implementation commit: `:/^Implement bounded interact`. Nothing pushed.

Core governs, especially §§5, 7, 9.4, 11–14, 15.1, 16–19, 22.2 D/H/I/J and23.
Completed Features001–011 remain authoritative except the explicit additive
versions here. Exact contracts are in [contracts/interact.md](contracts/interact.md).
No native serial/driver, electrical/DUT or Enhanced hardware acceptance is claimed.

## User Scenarios & Testing

### User Story 1 - Send exact bytes and observe a bounded result (Priority: P1)

A developer supplies binary bytes, one or more literal byte completion conditions,
an observation deadline and byte bound. DUTchMate sends at most once through its
owned connection and observes its existing evidence stream without client loops.

**Why this priority**: This is the smallest useful Interact transaction.
**Independent Test**: Both backend shapes, real temporary journal, authenticated
service and CLI; inject a response while write acknowledgement is held. Verify
exact payload, eligible RX, selected condition, honest TX facts and one RX path.

**Acceptance Scenarios**:

1. **Given** an active TX-authorized Profile and send-capable backend, **When** an
   exact payload is requested, **Then** durable intent precedes one bounded write,
   early RX remains eligible and a complete bounded report references evidence.
2. **Given** several conditions, **When** eligible bytes satisfy one, **Then**
   the first ending match wins, with request order breaking a same-byte tie.
3. **Given** no match, **When** the deadline or RX byte limit is reached, **Then**
   timeout or byte_limit is explicit; unrelated output remains in the journal.
4. **Given** TX disabled, absent capability, stale session or an occupied Interact
   slot, **When** requested, **Then** rejection performs no backend write.

### User Story 2 - Inspect honest TX and compatibility facts (Priority: P2)

A developer can distinguish requested bytes, backend acknowledgement, uncertain
partial progress and evidence durability, and keep using existing observation
Profiles, journals and clients under their original contracts.

**Why this priority**: An unsafe acknowledgement claim would invalidate evidence.
**Independent Test**: Full/short/zero returns, exception after possible progress,
lost journal acknowledgement and eviction; round-trip old formats and exercise
API-v1 unchanged plus explicitly selected API-v2 readback/Follow.

**Acceptance Scenarios**:

1. **Given** a full backend acknowledgement, **When** reported, **Then** it means
   backend acceptance only, with wire transmission and DUT receipt unverified.
2. **Given** timeout/failure without a returned count, **When** reported,
   **Then** the accepted prefix is unknown, never fabricated as zero or complete;
   no retry, remainder write, drain or buffer reset occurs.
3. **Given** a Profile-v1 or journal-v1/v2/v3, **When** used through its existing
   entry points, **Then** its validation, bytes, charges and delivery stay defined
   by001–011. New shapes require explicit new versions.
4. **Given** a concurrent Monitor, annotation, Follow or retrieval, **When** TX
   waits, **Then** continuous RX and ordinary evidence ordering/retention continue.

### User Story 3 - Cancel and stop without orphaning writes (Priority: P3)

A developer can cancel Interact or stop/detach the service with explicit outcome
and ownership facts, even if a write or evidence append has already started.

**Why this priority**: Physical side effects cannot be undone by cancelling a waiter.
**Independent Test**: Gate intent append, write submission/result, natural
termination and final evidence; race cancellation/detach/stop and verify every
admitted worker joins before handle/journal close and no stale generation writes.

**Acceptance Scenarios**:

1. **Given** cancellation before write submission, including pending intent ACK,
   **When** settled, **Then** no write occurs; acknowledged intent gets explicit
   not_submitted/cancelled settlement, otherwise no reference is invented.
2. **Given** a submitted write, **When** cancelled, detached or stopped, **Then**
   its result is joined and audited without retry; cancellation cannot revoke bytes.
3. **Given** disconnect, RX recording failure or explicit stop during a write,
   **When** acquisition closes, **Then** it seals and joins the write before
   backend close, and runtime joins audit settlement before recorder close.
4. **Given** delivery timeout or Ctrl-C, **When** the CLI exits, **Then** no
   success/zero-transmission claim is synthesized and no detach/retry follows.

### Edge Cases

- RX matching while a write is pending; already emitted buffered RX after boundary.
- Literal overlaps/chunk spans/ties, observer loss, origin resets, final-byte match.
- Full, zero, short, malformed or unknown write counts; exception after partial progress.
- Stop/cancel at every await, including submitted but unacknowledged journal work.
- TX result/end append failure independently of actual write and observation facts.
- Evicted intent/result/end, insufficient policy, counter/clock overflow, large provenance.
- Monitor markers and annotations interleaved with TX; Follow gaps and delivery overflow.
- API-v1 client against a v2-only run; no silent projection downgrade or negotiation.

## Requirements

### Functional Requirements

- **FR-001**: Core MUST accept an explicit session, exact payload of1..4096 bytes,
  one to four ordered nonempty literal byte conditions of1..256 bytes each,
  timeout1..4000 ms and max_rx_bytes1..1048576; reject coercion/bool/unknown inputs.
- **FR-002**: Admission MUST require the current active immutable Profile-v2 with
  explicit uart_tx_enabled=true, reported uart_receive and uart_send, a usable
  normalized writer and compatible evidence policy. No client selects permission.
- **FR-003**: The optional normalized writer MUST use the existing owned connection,
  one bounded write, fixed1000 ms backend wait and explicit full/partial/timeout/
  disconnect/failure facts. No backend names/library handles escape the boundary.
- **FR-004**: Basic MUST configure its positive write timeout before open, use one
  joined pyserial write, preserve read/open line behavior and never retry, flush,
  reset buffers or mutate open serial settings for Interact.
- **FR-005**: Profile-v2 MUST be additive and fail closed, with TX false by default.
  Profile-v1 parsing/value constructors/rejections and observation defaults MUST
  remain unchanged. Control/reconnect remain denied in both versions.
- **FR-006**: One Interact slot MUST span admission through final settlement;
  competing transactions fail busy, with no queue or separate public TX endpoint.
- **FR-007**: Exact durable intent MUST be acknowledged before backend submission.
  Observation starts at intent sequence+1 before TX, capturing fast responses;
  it is an observation-order boundary with explicit no-causation limitations.
- **FR-008**: Matching MUST be bounded and binary safe, handle chunk spans and
  multiple ordered conditions, reset on observed loss, and never cross provenance
  boundaries. Deadline equality yields timeout; matched last byte beats byte_limit.
- **FR-009**: TX settlement and observation MUST remain independent facts. Overall
  matched success requires full backend acknowledgement and an eligible match;
  write failure/partial/uncertain progress cannot be relabeled successful.
- **FR-010**: Outcomes MUST explicitly distinguish match, timeout, byte limit,
  disconnection, detach, origin reset, transport/recording failure, write timeout,
  partial write, cancellation and service stop as applicable. Rejections remain
  separate before admission. Exact precedence is settled in the contract.
- **FR-011**: Evidence MUST record exact requested payload, conditions, captured
  authorization/provenance, write submission/result and operation end. ACK of a
  write MUST NOT claim wire completion, exact wire bytes or DUT receipt.
- **FR-012**: Evidence MUST separate positive durable ACKs from unconfirmed appends;
  preserve actual write/observation facts if later audit append fails, invent no
  references, and never retry ambiguous writes or audit appends.
- **FR-013**: Explicit journal-v4/new record-v4 codecs MUST preserve all seven old
  variants, old factories/codecs and charges. All new records use ordinary bounded
  retention/retrieval; TX contributes zero RX count/backend timestamp endpoints.
- **FR-014**: API-v2 MUST explicitly carry Profile-v2 and new evidence variants.
  API-v1 remains strict and never silently emits new shapes; old runs/clients
  retain001–011 behavior. No migration, automatic fallback or negotiation.
- **FR-015**: The existing append gate/worker MUST order RX, Monitor, annotations
  and Interact. It MUST NOT be held across UART write wait or network/stdout work.
  Existing Monitor clocks/outcomes and annotation limits/attribution stay intact.
- **FR-016**: Follow and retrieval MUST expose new records only in the explicit
  new delivery version, with existing pages/gaps/expiry/limits. No second journal,
  RX consumer, copied transcript, retention pin or operation catalogue.
- **FR-017**: Pre-submission cancellation MUST suppress TX. Post-submission
  cancellation MUST join and audit actual settlement; it cannot undo acceptance.
  Existing Monitor/annotation cancellation semantics MUST remain unchanged.
- **FR-018**: Acquisition and backend close MUST seal/join admitted writes before
  physical close on every teardown path. Runtime MUST join Interact audit before
  recorder/read-source closure; service MUST seal before HTTP drain.
- **FR-019**: Authenticated local delivery MUST preserve006 security-before-body,
  browser rejection, no-store and private bounded errors. One independent service
  Interact job MUST NOT consume/replace existing mutation/read/Monitor/Follow slots.
- **FR-020**: Thin CLI MUST validate explicit bytes/limits before credentials,
  make one authenticated finite request and print one validated bounded report;
  no policy resolution, local serial/file TX, polling, retry or implicit detach.
- **FR-021**: Request, payload, condition, observation, response, pending-worker
  and retained-state limits MUST be explicit. Observation/write timeout MUST NOT
  be advertised as a hard deadline for OS work, journal I/O or joined cleanup.
- **FR-022**: Hardware-free RED/GREEN contracts, real journals, shared tests against
  both backend shapes, legacy compatibility, races/security and guarded installed
  flows MUST verify the contract at the plan/task-defined full checkpoints.
- **FR-023**: No Console, arbitrary streaming TX, Control, handoff/reconnect,
  text/line/regex transforms, generic command framework, Enhanced implementation,
  MCP, AI, historical browsing or unsolicited hardware acceptance is in scope.

### Key Entities

- **Interact request/report**: One explicit byte transaction and independently
  bounded observation, write acknowledgement and durability facts.
- **Normalized write result**: Submitted write status, known prefix or unknown,
  backend acknowledgement only; not an RX event or physical receipt.
- **Interact evidence**: Versioned intent, TX settlement and operation end in
  ordinary journal order with stable references and honest uncertainty.
- **Profile-v2 policy**: Immutable human-owned opt-in, separate from capability.

## Success Criteria

### Measurable Outcomes

- **SC-001**: All256 byte values survive payload handling and evidence round-trip;
  each admitted transaction invokes the backend at most once and RX remains single.
- **SC-002**: Every declared terminal/ACK/cancellation case has deterministic
  expected facts; no test infers wire transmission or receipt from a backend ACK.
- **SC-003**: A response received during pending write ACK can match; pre-boundary
  bytes cannot. Concurrent attempts cannot interleave payloads.
- **SC-004**: All completed001–011 regressions remain passing at full checkpoints;
  old encoded records/charges, Profile-v1 and API-v1 shapes stay unchanged.
- **SC-005**: At each cancellation/stop/failure checkpoint, all submitted writes
  and audit work join before their resource closes, with bounded admitted state.
- **SC-006**: Guarded installed service/CLI flows exercise real authentication and
  exact binary reports/readback/Follow without physical discovery or device access.

## Assumptions

- The requested planning workflow authorizes settling focused concrete contracts,
  not changing Core. No Core/rationale rule change is needed.
- Fixed1000 ms write wait avoids reconfiguring an open serial handle; it bounds
  library waiting only. Observation has its own explicit finite bounds.
- New clients explicitly select API-v2; old clients remain supported for legacy
  runs and reject unsupported-version errors rather than receive invented v1 data.
- Native Linux/Windows, active-DUT, physical/electrical and Enhanced hardware
  acceptance remain separate. Software fixtures prove contracts only.
