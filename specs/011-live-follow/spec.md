# Feature Specification: Receive-Only Live Follow

**Feature identifier**: `011-live-follow` (sequential after010; Git remains `main`, no branch hook configured).

**Created**: 2026-10-16

**Status**: T001–T024 complete (24/24 tasks); Feature011 software-complete; implementation commit recorded in development_status.md.
Completed evidence/progress/limits reconciled; architecture explanation remains accurate.
Recorded T0213444 focused/625 process passes and26 archives/10 installations audited.
T022 seven import contracts/docs/link/scope/diff checks pass; no new test/full gate.
T023 trigger met; one update completed with recorded graph-health/zero-node limits.
Fresh T024 8182 full passes, including625 guarded Follow/007–010 process cases; static/import/diff/artifact/privacy review pass.
Final separately authorized pre-commit review passed without correction; Feature011 committed, nothing pushed. Phase1 remains incomplete.

**Input**: Accepted Phase1 slice: receive-only live Follow through Core, the authenticated service and the thin CLI, using the existing authoritative RX/evidence path.

Authority: [Core](../../docs/project_context_core.md), especially §§5,8,14–18,22.2,23; [current status](../../docs/development_status.md); completed001–010. Exact implementation contracts are in [Follow contract](contracts/follow.md), [model](data-model.md) and [plan](plan.md).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Observe new evidence live (Priority: P1)

A local user selects an already-active observation session and follows new evidence without interrupting capture or becoming a transport owner.

**Why this priority**: This supplies Phase1's live read-only view using the established capture, storage and authenticated client path.

**Independent Test**: Against each shared backend fixture and a real temporary journal, start Follow after existing evidence, publish binary RX, loss, Monitor markers and annotations, and verify the live output and ordinary retrieval agree.

**Acceptance Scenarios**:

1. **Given** committed evidence before admission, **When** Follow starts, **Then** its atomic start position is the first not-yet-committed journal sequence at admission; no prior record is replayed and current provenance is reported.
2. **Given** an idle admitted subscriber, **When** a record commits, **Then** it becomes available in exact sequence order, including all seven existing evidence variants, without a second DUT reader or new evidence records for Follow.
3. **Given** Monitor, annotations and evidence retrieval are active, **When** Follow runs or exits, **Then** their established admission, timing, ordering, retention and cleanup contracts remain intact.
4. **Given** a valid active subscriber, **When** another Follow is requested, **Then** the independent single Follow slot rejects the second request explicitly.

### User Story 2 - Recognize missed or undeliverable evidence (Priority: P2)

A user can distinguish exact received evidence, upstream observation loss, journal retention expiry and incomplete delivery.

**Why this priority**: A live display that silently skips records would misrepresent the authoritative stream.

**Independent Test**: Pause a subscriber while rolling retention advances, resume, and verify precise missed intervals, unchanged retention facts and later ordered bytes. Exercise oversized records and fragmented/malformed frames separately.

**Acceptance Scenarios**:

1. **Given** unread records expire, **When** the next bounded read occurs, **Then** an explicit retention gap covers exactly the subscriber's missed interval before later records; whole-prefix retention counters are not misattributed to that interval.
2. **Given** a record was materialized before subsequent eviction, **When** it is delivered, **Then** it remains valid evidence; Follow does not promise it is still retrievable.
3. **Given** a record cannot fit a Follow page or delivery frame, **When** encountered, **Then** Follow terminates explicitly rather than trimming, splitting, spinning or changing journal policy.
4. **Given** unexpected EOF or malformed streaming data, **When** the client detects it, **Then** it reports incomplete/invalid delivery, preserves its already-printed valid prefix and never reconnects automatically.

### User Story 3 - End a subscriber without ending acquisition (Priority: P3)

A user may interrupt Follow, lose the client connection, detach the run or stop the service without leaking subscriber work or changing physical ownership.

**Why this priority**: Subscriber lifetime must remain separate from acquisition lifetime and joined resource cleanup.

**Independent Test**: Deterministically race cancellation, detach, source termination, shutdown, stalled output and admitted reads; verify no orphan, stale-generation read, extra recorder/connection or shutdown dependency on an idle socket.

**Acceptance Scenarios**:

1. **Given** active Follow, **When** Ctrl-C or client disconnect occurs, **Then** only the subscriber is cancelled/unregistered; acquisition, Monitor and annotation activity continue.
2. **Given** detach or service-stop intent, **When** it is admitted, **Then** new Follow starts/pulls are sealed synchronously, idle subscribers wake, already-submitted journal work is joined before recorder close, and socket lifetime does not own the recorder.
3. **Given** a connected client and source teardown, **When** a terminal frame can be delivered, **Then** it states the stop reason, delivered-prefix position and known source end or explicit unknown end; an undelivered tail is never called retention loss.
4. **Given** unauthorized/browser-originated/malformed requests, **When** submitted, **Then** existing security-before-body, private errors and no-store behavior remain effective, including streaming paths.

### Edge Cases

- Admission racing append, Monitor start/end, annotation insertion, stop or replacement generation.
- A commit whose acknowledgement fails; notifications are hints, journal snapshots remain authoritative.
- Wakeup during query/clear/wait, empty pages, exact integer MAX boundaries and no lost notification.
- Retention crossing both a read snapshot and a subscriber's next sequence; no fabricated loss counts.
- One oversized first record, exhausted read capacity, pending pull cancellation and uncertain cleanup.
- Chunked LF delimiters, escaped newlines, every byte value, noncanonical base64, duplicate keys, unknown fields, wrong session/order and partial EOF.
- Idle heartbeats, slow/trickling peers, blocked output, broken pipes and service stop before HTTP drain.
- Old preparations without Follow, explicitv1/v2 factories and unchanged productionv3 composition.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Follow MUST be a read-only subscriber to the existing authoritative evidence path; no additional physical reader, transport, journal writer or independent capture loop.
- **FR-002**: Admission MUST require the explicit currently associated ACTIVE session and a valid optional Follow capability bound to that run's coordinator/live journal. Old preparations without it remain valid but unavailable for Follow.
- **FR-003**: Start MUST atomically capture the actual committed journal tail and current segment provenance relative to appends. Records committed before this boundary are excluded; later records are eligible. No caller cursor, historical replay or causation claim.
- **FR-004**: Follow MUST preserve sequence order, exact RX bytes and all existing provenance, timestamp domains, loss facts, Monitor markers and attributed annotation assertions.
- **FR-005**: Follow MUST create no durable start/end records, schema version, retention exemption or storage migration.
- **FR-006**: One independent Follow subscriber per runtime and one independent service Follow job MUST be allowed; occupied capacity rejects immediately without a queue. Existing mutation/read/Monitor limits remain unchanged.
- **FR-007**: Buffering MUST be bounded to one page of at most32 records within the captured journal policy and Follow charged-byte cap, one coalesced change notification and bounded frame encoding. No unbounded transcript or per-record notification queue.
- **FR-008**: Slow consumers MUST NOT pin retention or block acquisition on network/stdout. Reads use the same active journal and bounded existing read ownership; idle waits consume no read lease.
- **FR-009**: Expired unread sequences MUST produce an explicit gap before subsequent records. Distinguish subscriber missed range, coalesced whole-prefix retention metadata and upstream observer loss.
- **FR-010**: Oversized/undeliverable records, read-capacity loss and source failure MUST produce explicit terminal outcomes where transport permits; never silently skip, trim or split an evidence record.
- **FR-011**: Committed changes from acquisition, annotations and both Monitor marker paths MUST wake Follow without changing Monitor matching, ordering or clock sampling. Notification state is not evidence.
- **FR-012**: Admission, submitted reads and cleanup MUST have strong captured-generation ownership; cancellation cannot orphan registrations or worker work, nor rebind to a later attach.
- **FR-013**: Client exit/disconnect MUST close only its subscriber, leaving acquisition, backend ownership, Monitor, annotations and existing retrieval intact.
- **FR-014**: Detach/service stop/source end MUST seal admissions and new pulls, wake idle subscribers and join submitted journal work before recorder close. Teardown MUST NOT wait for an idle subscriber or peer consumption.
- **FR-015**: A terminal report MUST identify its reason, next undelivered sequence and known source cutoff or explicit uncertainty; no claim that a send was consumed by a peer or that an unoffered tail is retention loss.
- **FR-016**: The authenticated service MUST expose a literal streaming route with closed bounded request and frame schemas, existing security-before-body/readiness rules, no-store and private errors.
- **FR-017**: Streaming MUST distinguish initial admission failures from post-header terminal frames and abnormal EOF. It MUST bound each frame and send, provide transport-only idle heartbeats, and avoid a whole-session deadline for human-controlled Follow.
- **FR-018**: The thin CLI MUST make one authenticated streaming request, validate and print one closed canonical frame at a time and never decode UART text, aggregate a transcript, poll, retry, reconnect or open a DUT.
- **FR-019**: CLI Ctrl-C MUST use existing interrupt exit130 and close only the HTTP subscriber. Broken pipe, invalid response, local timeout and remote errors MUST retain private diagnostics and distinguish unsuccessful delivery from a clean terminal.
- **FR-020**: Existing finite CLI requests MUST retain their 5s phase/10s absolute budgets. Only Follow receives the specified bounded-handshake/indefinite-session streaming transport.
- **FR-021**: Existing003 persistence/retrieval,005 lifecycle,006 security/shutdown,007 thin-client,008 active/terminal read cleanup,009 Monitor and010 annotation semantics MUST remain compatible.
- **FR-022**: Tests MUST cover RED/GREEN contracts, both shared backend shapes, real temporary journals, deterministic retention/lifetime races and actual guarded streaming/installability outside the checkout. No physical serial discovery or real-account credential access.
- **FR-023**: Native Linux/Windows, active-DUT, physical/electrical/safe-open and Enhanced hardware acceptance MUST remain explicitly unproven by software fixtures.
- **FR-024**: TX/Interact, console, Control, release/reacquire/handoff, reconnect, text/line decoding, regex, historical browsing, Enhanced production, MCP/AI and unrelated Phase1 work MUST remain deferred.

### Key Entities

- **Follow request**: Explicit session identity only.
- **Start boundary**: Captured run/session, next committed sequence and current segment provenance.
- **Subscriber**: One ephemeral generation-bound cursor, bounded pending page and coalesced change signal; no durable job/history.
- **Gap**: Exact unread interval expired by retention plus unchanged coalesced retention facts.
- **Terminal**: Explicit delivery/source reason, next sequence and known/unknown source end.
- **Stream frame**: Started, record, gap, heartbeat or terminal; a delivery representation, never a new evidence variant.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Against both backend fixture shapes, every eligible retained record is delivered once in sequence with byte-for-byte RX equality; no record before the atomic start boundary is emitted.
- **SC-002**: Every deliberately expired unread interval is reported exactly, with no silent skip or fabricated per-subscriber loss count; all over-budget cases terminate explicitly.
- **SC-003**: Idle and blocked subscribers remain within the specified bounded state and never create another DUT reader, pin retention or make recorder close depend on peer consumption.
- **SC-004**: Ctrl-C/disconnect leaves capture running; detach/shutdown joins submitted reads and closes resources once, including deterministic cancellation races.
- **SC-005**: Closed streaming/security/privacy and guarded wheel/sdist tests pass, together with required003/005–010 regressions and fresh final static/full-test/diff gates.

## Assumptions

- One Follow subscriber is the smallest useful Phase1 scope; Core permits but does not require concurrent subscribers. Future fanout is not implemented.
- Follow is human-controlled and may remain open indefinitely; per-I/O bounds do not impose a Core capture timeout or forced worker abandonment.
- All seven existing evidence variants are relevant live context. Filtering/decoded output is deferred.
- Fixed budgets, framing, rejections and cursor rules are settled in the contract, not new Profile settings.
- Planning authorizes artifacts only. The separately authorized T001–T024 work is tracked in tasks/current status. T016 corrected the six T015 CLI retention-marker coherence defects. All210 T017/T018 lifetime cases pass unchanged; T019 required no correction and passed6240 focused/8086 full cases with the combined US2/US3 gate and checkpoint diff review. T020 adds guarded installed-process tests. T021 found no production defect;3444 focused/625 installed cases pass. T022 reconciles completed evidence/progress/limits and verifies Core§16 conformance with no architecture rewrite or new test/full gate. T023 completed one code-only incremental Graphify update after the structural trigger was met; graph-health/zero-node limits are recorded. T024 passed the fresh final full gate (8182 cases, including625 guarded installed cases) and artifact/privacy/Core/contract review without correction. Final separately authorized pre-commit review passed without correction and repeated the full/staged/installability/privacy gate. Feature011 is software-complete and committed; implementation commit is recorded in development_status.md. Nothing pushed; Phase1 and native/physical/Enhanced acceptance remain incomplete.
