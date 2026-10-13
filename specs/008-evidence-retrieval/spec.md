# Feature Specification: Bounded Evidence Retrieval

**Feature Directory**: `008-evidence-retrieval`
**Feature Branch**: `main` (sequential feature identifiers do not create branches)
**Created**: 2026-10-10
**Status**: T001–T035 complete; final software gate/diff/installability review passed.
Full3889 passed; Feature008 software-complete, final pre-commit review passed.
Implementation: `Implement evidence retrieval` (Git revision `:/^Implement evidence retrieval`).
Native Linux/Windows/active-DUT/physical acceptance remains unexecuted; Phase1 incomplete.
**Input**: Accepted bounded, binary-safe evidence retrieval through the authenticated
service and thin CLI; preserve003 retrieval and005–007 ownership/security.

Core governs, especially §§5.2,13–19,22.2 A/H/I/J. Feature003 owns retained evidence,
references, fixed snapshots, pagination and expiration. Features005–007 retain
capture/lifecycle/security/client semantics. Concrete new application/HTTP/CLI
contracts belong in [contracts/evidence-retrieval.md](contracts/evidence-retrieval.md).
Schema-v1, Profile-v1 and the normalized physical backend contract stay unchanged.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Inspect a known active session (Priority: P1)

A developer supplies the session identity reported by status and inspects an exact
record or a bounded page while continuous capture remains owned by the service.

**Why this priority**: Make already-recorded UART evidence useful without stopping
capture or adding a client reader.
**Independent Test**: Guarded authenticated service, temporary journal and both
existing backend fixtures; retrieve exact binary/metadata while ambient RX continues.

**Acceptance Scenarios**:
1. **Given** a current associated session, **When** a stable reference is requested,
   **Then** its exact retained record or003 expiration/not-found report is delivered.
2. **Given** a page request, **When** recording continues, **Then** records retain
   sequence order, original bytes and provenance under the existing journal gate.
3. **Given** invalid caller security or an unrelated session, **When** requested,
   **Then** the caller is rejected before journal access with fixed private errors.
4. **Given** client return/loss, **When** later UART arrives, **Then** the same
   authoritative capture path records it without retry, detach or service signal.

### User Story 2 - Inspect the last terminal run (Priority: P2)

A developer reads the last associated session after detach or autonomous termination,
including a failed run whose journal was successfully created and safely closed.

**Why this priority**: Evidence outlives capture resources without becoming a catalogue.
**Independent Test**: Close the authoritative recorder, then retrieve through a
short-lived read-only reader; prove no writer recovery, capture reopen or file mutation.

**Acceptance Scenarios**:
1. **Given** terminal recorder closure confirmed, **When** evidence is requested,
   **Then** a per-request read-only reader validates the associated journal and closes.
2. **Given** recorder closure pending/unconfirmed or no usable source, **When** read,
   **Then** availability fails explicitly without speculative reopen or cleanup claims.
3. **Given** a new attach is admitted, **When** an old session is requested afterward,
   **Then** it is no longer selectable; previously admitted reads remain pinned.
4. **Given** service restart, **When** an old identity is supplied, **Then** there is
   no remembered association and no historical-path search.

### User Story 3 - Traverse a fixed snapshot honestly (Priority: P3)

A developer manually follows bounded continuation pages and sees exactly what
retention discarded or which requested sequences never existed.

**Why this priority**: Preserve003 evidence meaning across acquisition and eviction.
**Independent Test**: Append/evict between pages on both fixture shapes; verify all
four outcomes, frozen upper bound, empty ranges and insufficient-budget continuation.

**Acceptance Scenarios**:
1. **Given** an initial traversal, **When** later records append, **Then** continuation
   never extends its original snapshot end.
2. **Given** eviction crosses the next cursor position, **When** continued, **Then**
   the expired interval/marker is explicit and retained records resume as003 defines.
3. **Given** too small a caller byte budget, **When** read, **Then**003 returns its
   zero-record truncated page, unchanged next position and required record charge.
4. **Given** an encoded report cannot fit delivery bounds, **When** delivered,
   **Then** a fixed delivery-too-large rejection replaces the entire report; no
   records are split/omitted, cursor rewritten or automatic refetch performed.

### User Story 4 - Receive finite private delivery (Priority: P3)

A developer uses resource-free help or one authenticated bounded query, with honest
receipt/error/interrupt behavior and no credential, path or raw diagnostic leakage.

**Why this priority**: Extend the established client boundary without weaker guarantees.
**Independent Test**: Real grammar/installed entry, actual authentication, guarded
IPv4/IPv6, malformed/oversized responses and query-loss/close/shutdown races.

**Acceptance Scenarios**:
1. **Given** help or invalid syntax, **When** invoked, **Then** no account/network/
   journal work occurs and input-bearing errors are never echoed.
2. **Given** any valid evidence report, **When** delivered, **Then** one complete
   bounded JSON record exits0, including partial/expired/not-found outcomes.
3. **Given** timeout/interrupt/loss, **When** client delivery ends, **Then** admitted
   reads/SQLite work settle under their owners; capture and mutation ownership remain.

### Edge Cases

- No run, unallocated session, missing optional read source, failed preparation with
  known session, unconfirmed recorder close or physical release with confirmed recorder close.
- Read admission before/after new attach, read seal, detach, worker submission or shutdown.
- Session/range/cursor mismatch; counter maximum, empty intervals, expiration and never-existent suffix.
- Canonical cursor tampering, invalid UTF-8/duplicates/nonfinite JSON and unsupported media.
- Exact/all256 UART bytes, NUL/non-UTF8/CRLF, empty payload, device domains and unknown opaque provenance.
- Page count/charged-byte/wire limits differ; base64 expansion or metadata alone exceeds delivery cap.
- Terminal source missing/replaced/corrupt/incompatible/dirty and read-only open needing recovery.
- Single record irreducibly exceeds delivery cap; repeated Ctrl-C or closed stdout/stderr.
- Frozen JournalFailure masks the underlying category during context-manager exception transport.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Expose individual stable-reference and bounded session/range page reads through the authenticated service and thin Typer CLI; no client database access.
- **FR-002**: Select only the current or last associated run of this service incarnation by explicit session identity; no journal-path input, catalogue, discovery or restart recovery.
- **FR-003**: Retain at most one current public association of run/session/policy and opaque read access; newly admitted attach replaces it, rejected attach preserves it.
- **FR-004**: Atomically pin a read at Core admission on the owning loop; later association replacement cannot retarget an admitted read, while later old-session requests reject.
- **FR-005**: Active/draining reads use the existing capture journal serialization gate/worker; create no independent active SQLite connection, RX reader or hardware owner.
- **FR-006**: Seal live-read admission and join admitted reads after acquisition joins and before recorder close; do not hold the short lifecycle lock while joining.
- **FR-007**: Terminal access requires confirmed recorder closure/settlement and uses one short-lived genuinely read-only reader per admitted request; never retain the capture recorder open or resume capture.
- **FR-008**: Missing/changed/corrupt terminal sources and unconfirmed close fail explicitly; no write, recovery, repair, permission changes or writable fallback.
- **FR-009**: Preserve known created sessions on failed preparation through an optional opaque terminal source handed off after cleanup; unknown session/source remains unavailable without path reconstruction.
- **FR-010**: Add the smallest normalized read-only application/composition boundary; filesystem/SQLite/HTTP/Typer details stay outside application/domain and backend identity never chooses read behavior.
- **FR-011**: Preserve003 stable references, range selection, counter domain, snapshot end, continuation, ordering, independent page budgets and all complete/partial/expired/not-found semantics.
- **FR-012**: Snapshot continuations are bounded value tokens with no connection/lock/history; later append is excluded, later eviction is reported, session/range/snapshot checks remain authoritative in003.
- **FR-013**: Preserve003 zero-record byte-shortage/truncated/required-charge behavior; outcome and truncation remain independent facts.
- **FR-014**: Deliver exact RX bytes through canonical padded standard base64 and retain all current record variants, original timestamp domains, connection/segment identities and opaque provenance/retention markers.
- **FR-015**: Never decode UART text/lines, synthesize missing provenance, compare different timestamp origins or reinterpret losses/cleanup/cause.
- **FR-016**: Strict closed wire schemas/UTF-8/primitive types, duplicate/nonfinite rejection and finite request/cursor bounds must precede read admission.
- **FR-017**: Additional delivery request ceilings are4096 records and1048576 charged bytes; existing immutable SessionPolicy still independently governs admitted003 reads and is never tightened/defaulted.
- **FR-018**: Service response UTF-8 bytes and CLI re-encoded JSON bytes each independently cap at1048576, with CLI LF excluded; retain at most bound+1 while detecting overflow.
- **FR-019**: If canonical encoding cannot fit, reject the entire report with fixed delivery_too_large; no silent trimming, record splitting, payload omission, replacement continuation or automatic retry.
- **FR-020**: A caller may explicitly lower page budgets; reuse of a valid continuation preserves its snapshot, while a fresh initial request creates a new traversal. Oversized single records remain explicitly undeliverable here without changing003 policy/schema.
- **FR-021**: Preserve006 selected-loopback Host/Origin/Sec-Fetch/Bearer/query/route/media/body gate, no-store and input-free diagnostics; exact new routes/errors are defined in the contract.
- **FR-022**: Own at most8 registered service read tasks separately from006's8 mutation tasks, with at most8 Core read leases; no unbounded queue/public jobs/replay cache.
- **FR-023**: Client loss cannot cancel capture, attach/detach or submitted SQLite work; read tasks/reader close settle under their owners and service shutdown seals/joins them.
- **FR-024**: Extend007 pure grammar and fixed private exits/receipt phases; one read/HTTP request, no auto-status, auto-pagination, credential refresh or file/raw-output mode.
- **FR-025**: Every valid HTTP200 EvidenceEnvelope exits0 as report delivery only; recognized HTTP rejections exit4; existing local argument/credential/platform/transport/interrupt/output mappings remain.
- **FR-026**: Preserve007 absolute10s HTTP budget/5s phases and raw uncompressed bounded consumption; no Core lifecycle timeout or forced worker abandonment.
- **FR-027**: Correct the demonstrated003 JournalFailure context-manager transport defect minimally, preserving constructor/category/fact fields and private diagnostic handling; no schema/codec semantics change.
- **FR-028**: Require focused regression tests before implementation, including actual auth/lifecycle, native guarded installed delivery and identical backend-neutral assertions across Basic/Enhanced-shaped fixtures.
- **FR-029**: Keep schema-v1/Profile-v1 and005–007 ownership/security semantics; explicitly document additive read/delivery contracts without weakening architecture constraints.
- **FR-030**: Pass the full uv/static/import/hardware-free test/diff gate and installability checks; software simulation is not physical or other-platform acceptance.
- **FR-031**: Implement none of the explicit deferrals; planning creates artifacts only and accesses no physical hardware.
- **FR-032**: Unconfirmed terminal-reader/partial-open cleanup must latch read admission closed and prevent a falsely clean service marker; preserve primary error and existing capture/ownership facts, with no automatic cleanup retry.

### Key Entities

- Associated run: one current run identity, known session/policy and opaque read source; no public path or catalogue.
- Admitted read: a finitely retained query bound to one association until result/failure and cleanup settle.
- Evidence request/page/reference/cursor:003 values and their established semantics, projected through bounded delivery.
- Terminal source: private composition identity capable of opening a read-only reader after positive capture-recorder closure.
- Delivered envelope: actual evidence/page facts or fixed normalized error, never a hardware or cleanup attestation.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Every accepted binary fixture round-trips all256 byte values/NUL/non-UTF8/CRLF unchanged through HTTP and installed CLI.
- **SC-002**: Shared active/terminal/page/race assertions pass identically for both existing fixture shapes with one capture owner/consumer.
- **SC-003**: Every continuation preserves snapshot identity/end across append and explicitly reports eviction; no expired evidence is silently partial.
- **SC-004**: Every report is whole and within its delivery limit or explicitly rejected; never silently split/trim/auto-refetch.
- **SC-005**: Every read-close/client-loss/shutdown test settles owned work without capture cancellation or speculative terminal reopen.
- **SC-006**: Every help/security/usage-rejection scenario performs zero credential/read preparation as applicable, with no private sentinel leaks.
- **SC-007**: Completed001–007 regressions and architecture/installability gates pass without physical hardware or scope expansion.

## Assumptions

- Accepted baseline is feature007 implementation a14d1727f5a9a2dd1cab59ac2b662f47919bbe9d on main; no branch/commit/push implied by planning.
- Users supply an already-running listener and explicit known session; an explicit status invocation can obtain that identity, never an automatic preflight.
- Initial service/CLI support remains Linux/macOS POSIX. Native Linux/Windows and active-DUT/physical acceptance remain unexecuted.
- Read-only terminal validation is allowed to fail if SQLite would need recovery; same-UID malicious replacement/live copying and arbitrary power-loss/media recovery are not new guarantees.
- Delivery bounds do not claim an exact cap on003 policy-sized record materialization, OS/SQLite buffering or hard-real-time filesystem/decoding/cleanup.
- Deferred: streaming/follow, text/line decoding, regex/patterns, Monitor, annotations, catalogue/discovery, restart/arbitrary historical browsing, TX/Interact/console, Control, reconnect/handoff, service management, Enhanced production, MCP/AI and physical-hardware acceptance.
