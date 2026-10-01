# Feature Specification: Durable Evidence Journal

**Feature Branch**: `main`

**Created**: 2026-09-30

**Status**: Complete for software-only scope; physical hardware and arbitrary
power-loss acceptance remain deferred

**Input**: Add the Phase 1 durable evidence journal and bounded
retention/retrieval foundation without introducing delivery APIs or broader
session orchestration.

**Governing authority**: `docs/project_context_core.md`, especially §§11,
14.1–14.6, 16.1, 17.2–17.4, 18, 22.2, and 23;
`specs/001-rx-continuous-evidence/contracts/normalized-backend.md`; and the
opaque connection-provenance extension in
`specs/002-basic-serial-adapter/contracts/basic-serial-adapter.md`. The Core
document wins if a conflict is found. This specification replaces feature
001's in-process-only sequence scope only when the durable journal is used; it
does not change acquisition, backend, timestamp, loss, or exact-byte semantics.

## User Scenarios & Testing

### User Story 1 - Preserve authoritative evidence across restart (Priority: P1)

As Device Core, I need accepted evidence to remain an exact, ordered session
history after the journal is closed or the process terminates, so ambient UART
evidence and its provenance do not exist only in memory.

**Why this priority**: Durable evidence is the foundation for every later
session, Monitor, Interact, service, and CLI result. Retention and retrieval are
not meaningful until accepted records can be reopened reliably.

**Independent Test**: Create a journal session with a small explicit retention
policy, append every feature-001 evidence variant including arbitrary binary RX
and normalized connection provenance, acknowledge the appends, terminate and
reopen the journal, and verify the same session identity, sequence values,
record contents, provenance, and next append sequence.

**Acceptance Scenarios**:

1. **Given** a newly created journal, **When** its first evidence draft is
   accepted, **Then** it receives sequence `0` in that session and is
   acknowledged only after its durable transaction commits.
2. **Given** acknowledged records, **When** the journal is closed and reopened
   or the owning process terminates after acknowledgment, **Then** all committed
   records reopen intact in authoritative sequence order and appends continue
   without reusing a sequence.
3. **Given** process termination during an uncommitted append, **When** the
   journal recovers, **Then** it contains either the whole committed append
   transaction or the prior committed state, never a partial record or partial
   retention update.
4. **Given** a commit that may have completed before the process died but whose
   success was not returned to the caller, **When** the journal reopens,
   **Then** the committed record may be present and is identified by its
   durable sequence; this slice does not claim exactly-once caller retry.

---

### User Story 2 - Keep continuous evidence bounded and honest (Priority: P2)

As a developer, I need a rolling journal that retains recent evidence within
explicit quotas and records what it discarded, so continuous acquisition can
continue without silent loss or unbounded storage growth.

**Why this priority**: Continuous acquisition will eventually exhaust any
finite store. Rolling retention preserves the recent failure context while an
explicit marker keeps discarded history distinguishable from history that
never existed.

**Independent Test**: Create a session with deterministic small record-count
and byte quotas, append records past both limits, and verify that only the
oldest prefix is removed, sequences are never renumbered, one bounded coalesced
retention marker describes the full expired prefix, and a record that cannot
fit is rejected without changing the prior committed state.

**Acceptance Scenarios**:

1. **Given** an append that would exceed a session quota, **When** the record
   can fit after rolling retention, **Then** the oldest evidence prefix is
   discarded atomically with accepting the new record.
2. **Given** one or more retention passes, **When** session retention metadata
   is inspected, **Then** a bounded coalesced marker reports the discarded
   sequence range, observation-time endpoints with provenance where present,
   discarded record count, exact count of discarded RX payload bytes, and
   discarded quota-accounted byte count.
3. **Given** a stable reference to discarded evidence, **When** it is resolved,
   **Then** the outcome is `expired`; evidence that has never existed is
   `not_found`, and a range crossing the retained boundary is explicitly
   `partial`.
4. **Given** a single record that cannot fit the session's per-record or total
   byte limit, **When** append is attempted, **Then** append fails explicitly,
   no existing evidence is evicted, and no partial record is acknowledged.

---

### User Story 3 - Retrieve evidence in stable bounded pages (Priority: P3)

As a Device Core consumer, I need bounded raw evidence pages and stable
continuation positions, so later service and CLI clients can inspect a session
without loading an unbounded stream or confusing new appends with the query.

**Why this priority**: A chatty DUT can overwhelm a client or agent. Retrieval
must expose exact limits and expiry while remaining independent of delivery
transport or text decoding.

**Independent Test**: Retrieve a retained session range using small record and
byte page limits while appends continue and retention advances. Verify that the
first request fixes an upper sequence boundary, every response respects both
limits, continuation advances by sequence rather than offset, new appends are
excluded, and any evidence expired between pages is reported rather than
silently skipped.

**Acceptance Scenarios**:

1. **Given** a session or sequence-range request with positive record and byte
   limits, **When** more retained evidence exists than fits, **Then** the page
   is explicitly truncated and carries a continuation cursor.
2. **Given** a continuation cursor, **When** later records are appended,
   **Then** continuation returns only evidence below the upper boundary fixed by
   the first page.
3. **Given** retention removes evidence before a continuation is consumed,
   **When** retrieval resumes, **Then** the result reports the newly expired
   interval and may return remaining retained records without implying a
   complete page history.
4. **Given** the next record alone exceeds a request's byte limit, **When** a
   page is requested, **Then** no partial record is returned; the result reports
   the required record size and leaves continuation at that record.

### Edge Cases

- Session identity in the file disagrees with the caller's expected session.
- The journal is empty, or a requested range is empty, wholly before the
  retention boundary, wholly after the next sequence, or spans both.
- A retention range contains no timestamped observations or crosses timestamp
  domains/origins that cannot be compared.
- Equal observation timestamps remain valid and sequence order remains
  authoritative; persistence never sorts by timestamp.
- Process termination occurs before commit, after commit but before return, or
  during the atomic retention-and-append transaction.
- Storage is full, read-only, locked by another writer, or otherwise unable to
  commit.
- A journal has the wrong application identity, an unsupported store, record,
  or generic provenance-envelope version, malformed fields, or failed integrity
  checks; an unknown conforming backend provenance kind/version is not an
  incompatibility.
- Retention metadata itself must not grow with the number of retention passes.
- A cursor belongs to another session, range, or snapshot boundary.

## Requirements

### Functional Requirements

#### Session, identity, sequence, and append

- **FR-001**: One durable journal MUST contain exactly one durable evidence
  session. The journal path identifies the storage location; the immutable
  `SessionId` stored inside identifies the session independently of the path.
- **FR-002**: This slice MUST support only creating a new session journal,
  opening an existing journal, closing a journal handle, appending to the same
  session after reopen, and retrieving that session. Closing a handle MUST NOT
  semantically end, seal, rename, or classify a development run.
- **FR-003**: `SessionId` MUST be a non-empty opaque identity generated when the
  journal is created and preserved unchanged on every reopen. An optional
  expected session identity mismatch MUST fail before append or retrieval.
- **FR-004**: Evidence sequence MUST be scoped to one durable session. The first
  accepted record is `0`; every later accepted record receives the next
  integer; sequences MUST never be reused, rewritten, compacted, or renumbered
  after retention. The durable representation is a non-negative signed SQLite
  64-bit integer: record sequences range from `0` through `2^63 - 2`, and
  `next_sequence` ranges through `2^63 - 1`. Append MUST reject
  `next_sequence == 2^63 - 1` as explicit `capacity/sequence_exhausted` before
  insertion.
- **FR-005**: Append MUST accept the feature-001 pending evidence variants and
  return the accepted immutable feature-001 evidence record with its durable
  session sequence. Exact RX bytes, timestamp domain/origin, loss scope,
  connection/segment identity, terminal reason, capabilities, and connection
  provenance MUST retain their existing meaning.
- **FR-006**: The durable implementation MUST remain behind the existing
  evidence-recording boundary. Acquisition and shared Core MUST NOT branch on
  Basic backend identity or on whether a record is in memory or durable.
- **FR-007**: The persistence boundary MUST define a normalized storage snapshot
  envelope for opaque backend connection provenance. Envelope version, opaque
  backend-provided kind, and opaque backend provenance schema version MUST be
  distinct fields. Shared Core and SQLite MAY validate supported envelope
  structure and scalar field types, but MUST NOT maintain a registry of Basic,
  Enhanced-shaped, or other backend provenance kinds/versions. Unknown backend
  kind/version values in supported envelopes MUST round-trip unchanged;
  unsupported envelope versions MUST fail explicitly. Python pickle,
  module-qualified class names, pySerial objects, exceptions, and OS handles
  MUST NOT form part of the durable format.

#### Durability and recovery contract

- **FR-008**: An append MUST be acknowledged only after the transaction that
  assigns its sequence, writes the complete record, advances session metadata,
  and applies any required retention has committed successfully.
- **FR-009**: After an acknowledged append, the supported guarantee is recovery
  after clean reopen and abrupt process termination under the storage engine's
  committed-transaction semantics. Recovery MUST yield the whole committed
  transaction or the previously committed state; no partially encoded record,
  sequence advance, or retention marker is valid.
- **FR-010**: This feature MUST NOT claim survival of arbitrary power loss,
  storage-device failure, a filesystem or device that violates flush requests,
  media corruption, or loss of the journal files. The selected storage mode and
  flush behavior, plus the software recovery cases actually tested, MUST be
  documented in the implementation contract and quickstart.
- **FR-011**: If the process terminates after commit but before the append call
  returns, the record MAY be present on recovery. Reopen MUST expose its
  committed sequence honestly; transparent retry deduplication is deferred.
- **FR-012**: Commit, I/O, capacity, locking, and recovery failures MUST be
  normalized at the journal boundary. Failed append MUST not return an accepted
  record. Existing acquisition semantics then treat the exception as recording
  failure; this slice MUST NOT invent a parallel acquisition failure model.

#### Explicit bounded rolling retention

- **FR-013**: Session creation MUST require a finite positive session policy;
  there is no unbounded or implicit default. This slice supports rolling
  oldest-prefix retention only.
- **FR-014**: The policy MUST include a maximum retained record count, maximum
  retained quota-accounted bytes, and maximum single-record quota-accounted
  bytes. The storage contract MUST define deterministic byte accounting for
  every versioned record, not only RX payload bytes.
- **FR-015**: Immutable session policy metadata MUST persist
  `max_database_pages`; SQLite `PRAGMA max_page_count` itself MUST NOT be treated
  as persisted DUTchMate policy state. Every writable create/open/connection
  MUST reapply the stored limit and verify the effective ceiling. Open MUST fail
  explicitly if current `page_count` already exceeds the stored bound or SQLite
  cannot establish that effective ceiling, using normalized
  `capacity/database_over_ceiling` or
  `capacity/physical_ceiling_unavailable` respectively. The bounded main
  database MUST remain distinct from the additional finite rollback-journal
  transaction and recovery overhead. Deleting rows need not shrink the main
  file immediately if pages are reused within the verified ceiling.
- **FR-016**: When accepting a record would exceed a retained quota, the journal
  MUST discard only the minimum oldest evidence prefix needed to satisfy every
  quota. The discard, retention-marker update, record insert, and sequence
  advance MUST be one atomic transaction.
- **FR-017**: A record that cannot fit by itself MUST fail before any retained
  evidence is discarded. Payloads and metadata MUST NOT be truncated, split,
  decoded, or rewritten to make a record fit.
- **FR-018**: Retention MUST preserve one bounded coalesced prefix marker per
  session rather than an ever-growing tombstone list. It MUST distinguish the
  continuous expired sequence interval from sequences that never existed.
- **FR-019**: The coalesced marker MUST retain: expired half-open sequence range;
  first and last discarded timestamped observation with full timestamp
  provenance when either exists; explicit absence when none exists; discarded
  record count; exact count of discarded RX payload bytes; and discarded
  quota-accounted byte count.
- **FR-020**: Timestamp endpoints in a retention marker MUST remain separate
  provenance-bearing observations. A marker crossing domains or origins MUST
  NOT compare, subtract, or present them as one continuous clock duration.

#### Stable references and bounded retrieval

- **FR-021**: A stable single-record evidence reference MUST contain
  `SessionId` and `EvidenceSequence`. A stable range reference MUST additionally
  use a half-open sequence interval. Retention MUST NOT change reference
  identity.
- **FR-022**: Resolving a record below the session's retained low-water sequence
  MUST return `expired`; resolving at or above the session's next sequence MUST
  return `not_found`; and resolving a retained sequence MUST return the exact
  record. A reference carrying another session identity MUST fail explicitly as
  `session_mismatch`, not be searched or silently treated as this session.
- **FR-023**: An empty range `[x,x)` with `x <= next_sequence` MUST return a
  complete empty result because it requests no evidence; retention low-water
  MUST NOT make it expired. An empty range with `x > next_sequence` MUST be
  `not_found`. For non-empty ranges, one wholly below low-water MUST be
  `expired`; one containing expired and retained sequences MUST be `partial`
  with the expired interval and marker; one wholly at or above `next_sequence`
  MUST be `not_found`; and one extending beyond `next_sequence` after existing
  evidence MUST be `partial` with an explicit never-existent suffix. No result
  MAY silently omit expired or never-existent evidence while claiming
  completeness.
- **FR-024**: This slice MUST retrieve complete raw evidence records by entire
  session or half-open sequence range only. Every request MUST supply positive
  `max_records` and `max_charged_bytes` no greater than independent finite
  session-policy ceilings `max_retrieval_page_records` and
  `max_retrieval_page_charged_bytes`. These retrieval ceilings MUST NOT be
  derived from the total retained-byte quota. Every accepted individual record
  MUST fit within the page-byte ceiling, so a large retention quota never
  authorizes an equivalently large in-memory page.
- **FR-025**: A response MUST never exceed either requested bound and MUST never
  return a partial evidence record. If the next whole record cannot fit the
  byte bound, the response MUST report its required size and leave the
  continuation position unchanged.
- **FR-026**: The first page MUST capture an exclusive sequence snapshot upper
  bound. A continuation cursor MUST remain bound to that session, original
  range, snapshot upper bound, and next sequence; later appends MUST not enter
  the same traversal.
- **FR-027**: Pagination MUST use sequence-key continuation, never row offset or
  timestamp order. Each response MUST state whether it is truncated and return
  a continuation cursor exactly when retained or possibly newly expired
  evidence remains below the snapshot upper bound.
- **FR-028**: If retention advances past a cursor between pages, retrieval MUST
  report the newly expired interval before advancing to any remaining retained
  records. Cursor mismatch, malformed position, and reuse with another query
  MUST fail explicitly.
- **FR-029**: The internal cursor in this slice MAY be a typed immutable Core
  value. HTTP/CLI encoding, signing, secrecy, transport compatibility, and
  external token lifetime are deferred to the delivery specification.

#### Schema compatibility, corruption, and validation

- **FR-030**: The journal format MUST have an application identity, store schema
  version, record kind/version, and generic persisted provenance-envelope
  version that do not depend on Python class names or import paths. Backend
  provenance kind/schema version remain opaque payload metadata, not journal
  compatibility versions.
- **FR-031**: Opening a journal MUST run storage-engine recovery first, then
  validate application identity, supported schema/record/envelope versions,
  immutable session policy, retention and finite-integer invariants, and an
  integrity check appropriate to the selected mechanism. Before permitting
  writes it MUST reapply and verify the policy's physical database ceiling as
  required by FR-015.
- **FR-032**: The initial implementation supports schema version `1` only.
  Unsupported older or newer versions MUST be rejected explicitly without
  writing. Future migrations MUST be deliberate, version-to-version, atomic,
  and separately tested; no migration framework is required in this slice.
- **FR-033**: Corruption or malformed stored evidence MUST fail closed. The
  journal MUST perform no write after validation fails, except that the storage
  engine's rollback recovery permitted by FR-031 may already have restored the
  last committed state. It MUST NOT silently repair, skip, reorder, reinterpret,
  or return a partial success, and MUST expose no raw storage-library exception
  as the public failure contract.
- **FR-034**: Software-only tests MUST cover exact binary round trips, every
  current evidence variant, provenance snapshots, reopen and process-crash
  recovery, interrupted transactions, sequence continuation, both retention
  quotas, coalescing, expired/partial/not-found outcomes, cursor stability under
  append and retention, independent retrieval ceilings, empty ranges,
  unsupported generic envelope versions, opaque unknown backend provenance,
  sequence/counter exhaustion, cancellation while blocking SQLite work runs,
  incompatible versions, corrupt rows/files, and storage-full/locked failures.
- **FR-035**: The full feature-001 and feature-002 suites MUST remain green.
  Tests MUST use temporary journal paths and fake backends only; no serial
  device may be enumerated, opened, or touched.

#### SQLite execution, cancellation, and finite counters

- **FR-036**: Each open journal MUST own one private single-thread executor and
  one async serialization gate. Its SQLite connection MUST be created, used,
  and closed only on that executor's sole worker thread with Python
  `sqlite3` thread checking left enabled. All create/open validation, append,
  retrieval, and close work for that journal MUST be strictly serialized; this
  is a journal-local implementation, not a general worker framework.
- **FR-037**: Cancellation while waiting to acquire the journal gate MUST submit
  no SQLite work. Once blocking work has been submitted, async cancellation
  MUST NOT release the gate, close the connection, or admit another operation
  until the worker finishes. The caller then observes cancellation. Close MUST
  likewise wait for admitted blocking work before closing on the worker thread.
- **FR-038**: If an append caller is cancelled after blocking work begins, the
  transaction MAY have committed before cancellation is observed. No accepted
  record is returned to that cancelled caller, no automatic retry occurs, and
  reopen/reference retrieval is the authoritative way to determine whether the
  sequence was committed. This is the existing commit-before-return ambiguity,
  not rollback or exactly-once behavior.
- **FR-039**: Every persisted sequence, range endpoint, page/cursor position,
  quota, charge, page count, record count, and cumulative retention counter MUST
  be validated and updated with checked arithmetic in `0..2^63 - 1` before the
  write that would overflow. Sequence exhaustion MUST report
  `capacity/sequence_exhausted`; other persisted-counter overflow MUST report
  `capacity/counter_exhausted`. Either failure leaves the prior transaction
  state unchanged.

### Key Entities

- **Durable Evidence Session**: Exactly one bounded evidence container per
  journal, identified by immutable `SessionId`, next sequence, persisted
  session policy, and schema metadata.
- **Durable Evidence Record**: A versioned, binary-safe representation of one
  existing feature-001 evidence record and its session sequence.
- **Connection Provenance Snapshot**: Generic versioned envelope containing an
  opaque backend kind/version and scalar fields, persisted without a backend
  registry.
- **Session Policy**: Required independent limits for retention, individual
  records, physical main-database pages, and retrieval page bytes/records.
- **Retention Marker**: One coalesced bounded description of the discarded
  session prefix, including sequence, timestamp provenance, and amount.
- **Evidence Reference**: Stable session-plus-sequence identity for a record or
  half-open range, independent of current retention.
- **Retrieval Page**: Bounded raw records, expiry information, truncation state,
  and optional continuation cursor over a fixed snapshot upper bound.

## Success Criteria

### Measurable Outcomes

- **SC-001**: All acknowledged records in the recovery test matrix reopen with
  byte-for-byte payloads, equal normalized provenance, original sequence, and
  no duplicate or missing committed sequence after clean close and tested
  abrupt process termination.
- **SC-002**: Every interrupted transaction test produces exactly the previous
  committed state or the complete new transaction; zero partial rows, partial
  retention changes, or reused sequences are observed.
- **SC-003**: Under deterministic count and byte quotas, retained evidence
  never exceeds either configured limit, only the oldest required prefix is
  removed, and retention metadata remains constant-size across at least 1,000
  retention passes.
- **SC-004**: For all tested references, retained, expired, partially expired,
  and never-existent evidence are distinguished with no silently incomplete
  success response.
- **SC-005**: Every retrieval page respects both caller limits and the
  independent session-policy record/byte ceilings, traverses a fixed sequence
  upper bound without duplicates or timestamp ordering, and explicitly reports
  truncation or expiry caused between pages. Increasing retention capacity does
  not increase the permitted page size.
- **SC-006**: Every incompatible-version, corruption, locking, full-storage,
  physical-ceiling, sequence/counter-exhaustion, and malformed-record test fails
  closed without exposing a raw storage-engine exception or modifying the
  original committed evidence; cancellation tests retain serialization until
  blocking work finishes.
- **SC-007**: The full repository validation gate and all feature-001/002
  regressions pass without backend-identity branching, a second RX path, or
  physical hardware access.

## Assumptions

- Python 3.14 and the existing uv workspace remain the implementation baseline.
- The storage-mechanism choice, transaction mode, flush settings, physical
  quota enforcement, and canonical encoding are design decisions for this
  feature's plan and contract, not unstated assumptions.
- A caller later composed by the Device Core Service will choose a journal path
  and the explicit finite policy. Path selection, directory layout across
  sessions, and profile-to-policy mapping are not part of this slice.
- Sequence is authoritative order. Observation timestamps remain provenance and
  may be compared only under the existing feature-001 domain/origin rules.
- The existing in-memory recorder remains finite test infrastructure. It is not
  retroactively described as durable or retention-capable.

## Explicit Exclusions and Deferred Behavior

- DUT Profile schema, human-owned retention policy presentation, policy
  authorization, and numerical product defaults.
- Session listing, naming, tagging, sealing, run orchestration, automatic
  rotation into a new session, export/import, deletion, backup, replication,
  or multi-session directory management.
- Operation/Monitor/Interact/Control records and lookup, annotations, derived
  text/lines/patterns, time-range indexes, segment filters, live follow, and
  subscription APIs.
- Service/HTTP routes, authentication, browser-origin rejection, JSON schemas,
  cursor token encoding/signing, CLI commands, and user-facing formatting.
- UART TX, semantic DTR/RTS Control, reconnect, release/reacquire, handoff, or
  changes to Basic serial opening and RX behavior.
- A generalized repository, storage-provider plugin, migration framework, or
  support for storage mechanisms other than the one selected in this plan.
- Enhanced backend/protocol/firmware, MCP, AI analysis, and all physical
  hardware access or acceptance.
- Exactly-once caller retries, arbitrary power-loss certification, media-fault
  recovery, silent salvage, or a claim that backups exist.
