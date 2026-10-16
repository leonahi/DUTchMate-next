# Feature Specification: Bounded Attributed Client Annotations

**Feature**: `010-client-annotations` | **Git branch**: `main` (no branch hook configured)
**Created**: 2026-10-15
**Status**: T001–T024 complete (24/24); fresh final gate6951 passed, installed/artifact/privacy/Core/contract review clean, no corrective change; T023 tooling/health limits remain recorded and outputs/backups/tooling ignored; Feature010 software-complete; implementation commit is recorded in development_status.md, Phase1 incomplete
**Input**: Accepted Phase 1 slice: bounded attributed client annotations through Core, the authenticated service and thin CLI; specify → plan → tasks only.

## Authority and scope

[Core](../../docs/project_context_core.md) §§8, 14.1–14.7, 15.1, 16–18, 22.2 I/J and 23 govern. [Current status](../../docs/development_status.md) identifies completed Features 001–009. Their contracts remain authoritative except the explicit additive annotation persistence and delivery revision in [contracts/annotations.md](contracts/annotations.md). No Core rule changes.

This slice adds one short client assertion to the already associated active session, then exposes it through existing evidence retrieval. It changes no DUT state, requires no TX permission, and creates no physical reader or separate evidence store. It does not annotate arbitrary historical sessions or backdate an external action.

## User Scenarios & Testing

### User Story 1 - Record and retrieve an attributed assertion (Priority: P1)

A developer records a build identifier or test-step description while observation continues, receives an acknowledged evidence reference, and retrieves the same assertion beside ordinary evidence.

**Why this priority**: This is the complete minimal annotation workflow and the MVP. It provides context without claiming DUT observations or enabling hardware actions.

**Independent Test**: With either backend-shaped fixture and a real temporary journal, annotate through the authenticated service/thin CLI, retrieve by reference and bounded page while active and after confirmed detach, and compare exact text and attribution. No physical device is used.

**Acceptance Scenarios**:

1. **Given** an active associated session, **when** text of 1..1024 UTF-8 bytes is recorded, **then** one acknowledged record identifies session, declared client surface, assertion classification, host timestamp origin and position in evidence order.
2. **Given** TX-disabled Profile-v1 and ambient RX, **when** an annotation is accepted, **then** acquisition continues without open/close/TX/control calls and exact RX remains unchanged.
3. **Given** an acknowledged annotation, **when** it is retrieved before or after confirmed writer close, **then** identical text and attribution/timing facts return using bounded retrieval.
4. **Given** the shared local credential, **when** an HTTP caller declares `cli`, **then** attribution is explicitly client-asserted, never verified executable, user or process identity.

### User Story 2 - Keep annotations bounded and retention honest (Priority: P2)

A developer gets explicit rejection for invalid or excessive attempts and an explicit expired result after normal rolling retention discards an annotation.

**Why this priority**: Client context must not bypass quotas, flood the writer or silently become incomplete evidence.

**Independent Test**: Deterministic clock and tiny-policy tests exercise exact text/rate/charge limits, mixed-record retention and v1/v2/v3 compatibility without CLI or hardware.

**Acceptance Scenarios**:

1. **Given** valid Unicode text, **when** encoded size is 1024 bytes, **then** it is accepted if policy permits; empty, 1025-byte, NUL-containing or surrogate-containing text rejects without insertion. Accepted whitespace, newlines and Unicode are not normalized.
2. **Given** one runtime incarnation shared by clients and attaches, **when** ten attempts were admitted within the preceding second, **then** the next is rate-limited without queuing/sleeping/appending. An attempt exactly one second after the oldest can proceed when otherwise eligible.
3. **Given** incompatible evidence charge limits, **when** insertion is requested, **then** it rejects before append without policy inflation or retention reservation.
4. **Given** rolling eviction, **when** an annotation is discarded, **then** its reference reports expired and pages retain ordinary explicit retention facts. Annotation text contributes no UART RX bytes.
5. **Given** old journals or preparation callers, **when** supported observation/Monitor/retrieval is used, **then** existing behavior remains intact. Annotation support is explicit; no artifact is silently migrated.

### User Story 3 - Preserve lifetime and security under failure (Priority: P3)

A developer can interrupt delivery or stop observation without abandoning an admitted write or confusing acknowledgement with verification of an external action.

**Why this priority**: Annotation shares the authoritative writer and must obey established cleanup/security.

**Independent Test**: Controlled append gates and cancellation/disconnect/shutdown races prove owner settlement before writer close, private errors and security-before-body behavior. Both backend shapes run shared assertions.

**Acceptance Scenarios**:

1. **Given** an admitted pending insertion, **when** its waiter disappears or detach/shutdown begins, **then** owned work settles before writer close; new admission rejects after sealing.
2. **Given** unconfirmed append or lost response, **when** delivery fails, **then** no reference is fabricated, no automatic retry occurs and no exactly-once claim is made. A record may exist despite missing acknowledgement.
3. **Given** missing credentials, browser-origin access or invalid route, **when** a body is offered, **then** security rejects before body/Core/journal work and returns no-store private diagnostics.
4. **Given** Monitor and evidence reads, **when** an annotation is inserted, **then** it occupies normal evidence order but cannot match literal RX, consume examined RX bytes or change capture/lifecycle facts.

### Edge Cases

Mixed-width Unicode/combining characters; preserved whitespace/newlines; escaped controls and malformed encodings; rate boundary/backward clock/overflow; concurrent clients and slot exhaustion; tiny policies; unknown/mismatched session; attaching/terminal/sealed states; missing optional support; retention during reply delivery; ambiguously acknowledged writes; segment-end racing with an already admitted session-level assertion; Monitor deadlines during delayed journal writes; whole-response/cursor overflow; wrong execution context; unconfirmed reader/writer cleanup; unknown schema/kind/version and malformed private stored data.

## Requirements

### Functional Requirements

- **FR-001**: Core MUST accept only the explicit current active session, with a committed segment and annotation-capable preparation. Old preparation constructors remain valid; missing support rejects annotation alone. Contract fixes admission precedence.
- **FR-002**: Text MUST be 1..1024 UTF-8 bytes, with no NUL or surrogate code point, preserved without stripping, normalization, UART interpretation or command execution.
- **FR-003**: Records MUST declare `client_assertion`, originating surface and `client_asserted` attribution basis. HTTP allows declared `cli`/`http`; direct Core additionally allows `core`. Authentication authorizes access, never verifies surface/user/process identity.
- **FR-004**: Core MUST use the sole recorder gate and ordinary sequence, sample host monotonic receipt time at insertion, and record its clock origin. This is neither client action time, DUT time, wall time nor commit time. No caller supplies time, origin or sequence.
- **FR-005**: Core MUST allow one pending owned annotation per run and ten admitted attempts in a rolling 1,000,000,000 ns window per incarnation, shared across surfaces/attaches. No wait queue, automatic delay or retry. Contract defines exact accounting.
- **FR-006**: Success MUST require positive durable append acknowledgement and return its reference and immutable record. Missing acknowledgement MUST NOT imply record absence or assertion truth.
- **FR-007**: Persistence MUST be explicitly versioned, preserve v1/v2 formats and old record bytes/charges, and reject unsupported combinations. New composition selects the new format; no migration, repair, format guessing or restart/history feature.
- **FR-008**: Annotations MUST use ordinary record/retained/page charge bounds, rolling retention, coalesced expiry metadata, database ceiling and references. Zero UART RX bytes; no backend-domain retention timestamp endpoints. Conservative codec-based policy preflight precedes submission.
- **FR-009**: Existing active/terminal record/page retrieval MUST include the closed annotation variant while preserving snapshots/cursors/truncation/413 and read-only terminal ownership. No new retrieval route/catalogue.
- **FR-010**: Existing authentication, peer/Host/Origin/browser rejection, strict media/body validation, no-store and privacy MUST precede annotation work. Content is intentional authenticated evidence, never diagnostics.
- **FR-011**: CLI MUST validate bounded inputs before credentials, make one request, validate/print the closed reply and preserve established errors/timeouts/cancellation. No attach/status/read loop, retry, local transport or duplicated Core policy.
- **FR-012**: Admitted insertions MUST remain strongly owned/joined despite waiter cancellation, detach and shutdown. Seal before teardown and join before writer close. Preserve Feature 005 facts, 008 cleanup uncertainty and 009 Monitor ownership/timing.
- **FR-013**: Verification MUST use focused RED/GREEN contract/persistence/runtime/service/CLI/retention/security/lifetime/installed regressions, identical shared workflows against both backend shapes, and the task-defined full gates. All validation remains hardware-free.
- **FR-014**: No Follow, TX/Interact/console, Control, handoff/reconnect, editing/deletion/backdating, arbitrary metadata/attachments, historical insertion/catalogue, restart recovery, Profile change, verified identity infrastructure, Enhanced production, MCP or AI.

### Key Entities

- **Annotation request**: Explicit session, exact bounded text and declared surface; no evidence position or time.
- **Client annotation evidence**: Immutable attributed client assertion, host receipt time/origin and ordinary sequence.
- **Annotation receipt**: Associated run/session, acknowledged reference and record; no action verification or retention guarantee.
- **Admission budget**: At most ten monotonic admission times per incarnation and one pending owner per run; transient bounded state, no durable catalogue.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Every successful acceptance insertion is retrievable with identical UTF-8 text/attribution/timing, subject only to explicit retention.
- **SC-002**: Tests accept 1/1024 bytes, reject 0/1025, and admit no eleventh attempt within a rolling second across clients/reattach.
- **SC-003**: Shared scenarios pass on both fixture shapes with zero annotation-caused open/TX/control calls and unchanged RX.
- **SC-004**: Retained/expired annotations remain distinguishable from DUT observations and correctly classified by bounded active/terminal retrieval.
- **SC-005**: Cancellation/shutdown schedules settle owners before close, reject sealed admission and preserve lifecycle/Monitor/read cleanup.
- **SC-006**: Legacy journal/Profile/delivery regressions and final installation/architecture/security gates pass without hardware/new dependency.

## Assumptions

- Existing single-session association, shared local Bearer authentication and Linux/macOS POSIX delivery remain. Actual Windows commands remain unsupported. Native Linux/Windows, active-DUT, physical/electrical and Enhanced hardware acceptance are separately authorized work.
- Text is small prose, not attachments or arbitrary metadata. The 1024-byte limit fits the existing request envelope even with worst-case JSON escapes. Fixed limits protect the writer without new configurable Profile policy.
- Surface attribution is a bounded unverified declaration, not a new authentication principal. No caller can relabel the record as a DUT observation or DUTchMate action.
- Acknowledgement proves recording, not assertion truth, exactly-once delivery, future retention or physical power-loss guarantees.
- Planning alone completed no implementation task. Concrete layouts and compatibility decisions live in the contract/data model; current progress is in development_status.md and task checkboxes. Core, authenticated HTTP and thin CLI annotation, bounds/lifetime hardening, installed flows, complete-diff/artifact review, documentation/conformance reconciliation, final code-only Graphify update and T024 fresh final verification are complete. Tooling/graph-health and native/physical acceptance limits remain recorded. Feature010 is software-complete; implementation commit is recorded in development_status.md; Phase1 remains incomplete. The separately authorized final pre-commit review/commit is recorded in development_status.md.
