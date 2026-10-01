# Contract: Durable Evidence Journal

## 1. Boundary

`SqliteEvidenceJournal` is the only production persistence implementation in
this slice. It implements the existing asynchronous `EvidenceRecorder.append`
contract and adds concrete create/open/close, reference resolution, and bounded
retrieval methods. No `Repository`, provider registry, migration service, or
second acquisition path is introduced.

Public Core-facing values and normalized errors live outside the adapter.
SQLite connections, cursors, rows, exceptions, PRAGMAs, and files remain inside
`dutchmate_core.adapters.sqlite_evidence`.

## 2. Lifecycle

### Create

`create(path, session_policy)`:

1. requires a path that does not already contain a journal;
2. validates all finite retention, retrieval, record, and physical policy
   values before opening a write transaction;
3. creates a SQLite connection with 4096-byte pages, applies the supplied
   `max_database_pages` as `max_page_count`, and verifies the effective ceiling
   before allocating the schema;
4. writes application ID `DUTM`, schema/user version `1`, the fixed schema, one
   generated `SessionId`, and one immutable session-policy row including
   `max_database_pages`;
5. commits schema and metadata;
6. rereads persisted policy and current `page_count`, reapplies the stored
   ceiling, and verifies it again before returning the writable journal.

Create never chooses a directory, rotates another journal, or creates a second
session in the file.

### Open

`open(path, expected_session_id=None)`:

1. opens an existing file without creating a missing one;
2. allows SQLite rollback recovery;
3. validates application ID, exact schema version 1, objects, integrity,
   evidence-record and generic provenance-envelope versions, aggregates,
   finite-integer bounds, and sequence/retention invariants;
4. optionally checks the expected session identity;
5. reads persisted `max_database_pages`, rejects `page_count` above it, reapplies
   it to `PRAGMA max_page_count`, and verifies SQLite reports that exact
   effective ceiling;
6. enables append only after all checks pass.

Failure is read-only/fail-closed and preserves the source. Version 1 performs
no migration or repair. SQLite rollback recovery in step 2 is the sole allowed
pre-validation mutation and may restore the last committed state before a
later validation error is discovered.

### Close and reopen

`close()` is idempotent and awaits completion of any operation already admitted
by that journal instance. New operations after close begins fail explicitly.
Close executes on the journal's SQLite worker thread, does not add evidence or
change session state, and shuts down that journal's private executor only after
the connection closes. Reopen continues at the persisted `next_sequence`.

## 3. Append and durability

Each journal owns one `ThreadPoolExecutor(max_workers=1)` and one asyncio
serialization gate. The SQLite connection is created, used, and closed only on
that executor's sole thread with `sqlite3` same-thread checking enabled. All
blocking create/open validation, append, retrieval, and close operations pass
through this one gate and executor. This is private journal machinery, not a
general worker framework.

Cancellation while waiting for the gate submits no work. Once work is
submitted, the async wrapper keeps the gate held and waits cancellation-
resistantly for the worker to finish before propagating cancellation. It never
closes or reuses the connection concurrently with still-running work.

`append(draft)` then performs:

1. encode and validate the entire record candidate;
2. reject an individually oversized record and detect sequence/counter
   exhaustion before beginning retention;
3. verify the effective physical ceiling, then `BEGIN IMMEDIATE`;
4. read the durable next sequence and current quota aggregates;
5. select the minimum oldest prefix needed for both retained quotas;
6. update the coalesced marker and delete that prefix if needed;
7. insert the exact record at the durable next sequence;
8. update next sequence, low water, and aggregates;
9. validate postconditions and commit;
10. reconstruct and return the accepted immutable record.

The acknowledgment point is successful return from SQLite commit. On any error
before that point, rollback is attempted and no accepted record is returned.
Acquisition maps the normalized journal error through its existing recording
failure behavior.

If the async caller is cancelled after blocking append work begins, the worker
still runs to completion under the held gate and the caller then receives
cancellation rather than an accepted record. The transaction may already have
committed. Reopen/reference retrieval determines whether its sequence exists;
cancellation does not imply rollback and triggers no automatic retry.

Guaranteed and tested:

- close/reopen after acknowledgment retains the record;
- abrupt process exit after acknowledgment retains the committed transaction;
- interruption before commit yields the previous committed state;
- append plus retention is all-or-nothing.

Explicitly not guaranteed:

- exactly-once retry after commit-before-return ambiguity;
- arbitrary power-loss or lying flush hardware;
- filesystem, media, directory, backup, or live-copy survival.

## 4. Version-1 storage

The database contains only fixed schema-version-1 tables for singleton session
metadata, evidence rows, and an optional singleton retention marker. Evidence
metadata is strict canonical JSON stored as a UTF-8 BLOB. RX payload is stored
unchanged in a separate BLOB. No pickle or Python class name is accepted.

Quota charge is exactly:

```text
8 (sequence) + 8 (record version) + len(kind UTF-8)
+ len(metadata BLOB) + len(payload BLOB or empty)
```

The stored charge is checked against recomputation on open/read. The exact count
of RX payload bytes is also accumulated independently for retention reporting;
discarded payload content is not retained by the marker.

Writable connections use rollback `DELETE`, `synchronous=FULL`, foreign keys,
zero busy timeout, and fixed page size. Immutable session policy, not the
connection PRAGMA, persists `max_database_pages`. Every writable connection
rejects `page_count > max_database_pages`, reapplies the stored value to
`max_page_count`, and requires the reported effective ceiling to equal it. The
bounded main database therefore cannot exceed `max_database_pages * 4096`.
Separately, the finite transient rollback journal contains pre-image pages
touched by the transaction plus engine headers; deployment must reserve that
additional recovery space.

All durable integers use SQLite's signed 64-bit range. With
`SQLITE_INTEGER_MAX = 2^63 - 1`, record sequences are
`0..SQLITE_INTEGER_MAX - 1`, and `next_sequence` may equal the maximum. Append
at that value fails before insertion as `capacity/sequence_exhausted`. Every
quota, page count, charge, range/cursor position, record count, and cumulative
retention counter is constrained to `0..SQLITE_INTEGER_MAX`; checked arithmetic
fails before mutation as `capacity/counter_exhausted` when another persisted
value would overflow.

## 5. Provenance snapshot

`BackendConnectionProvenance` supplies a generic
`ConnectionProvenanceSnapshot(envelope_version, backend_kind,
backend_schema_version, fields)`. Version `1` of the generic envelope and its
scalar field structure are the only parts SQLite/shared Core interpret.

The Basic adapter owns the opaque kind, backend schema version, and field
mapping for its provenance. Shared Core and SQLite do not import
`BasicSerialConnectionProvenance`, switch on its kind, or keep a registry of
known backend versions. Any unknown backend kind/version conforming to envelope
version 1 round-trips unchanged. Unsupported generic envelope versions fail
explicitly. Retrieval reconstructs `PersistedConnectionProvenance(snapshot)`,
which remains opaque to shared Core. Equality for durable round-trip tests is
by snapshot value, not by the original adapter implementation class.

## 6. Rolling retention

Retention is evaluated on each append after full candidate encoding. Existing
records are ordered only by session sequence. The minimum oldest prefix is
chosen so the candidate plus survivors fit both count and charged-byte quotas.

One marker coalesces the complete expired prefix. Its first and last timestamp
endpoints are the first and last discarded timestamped records by sequence.
Each endpoint retains its own timestamp-domain/origin descriptor. They are
never subtracted, reordered, or described as one clock when provenance differs.
The marker also carries cumulative discarded record count, exact discarded RX
payload-byte count, and discarded charged-byte count; it stores no discarded RX
payload content. `expired_end_sequence` is the low-water boundary, so no second
latest-discard high-water field exists.

Retention metadata is not assigned an evidence sequence and is not a growing
tombstone stream. Its expired sequence range is the stable proof of what was
discarded. This uses the Core §14.5 permission to coalesce marker metadata while
surviving evidence records remain immutable.

If a candidate cannot fit alone, append fails before deletion. If the database
page ceiling or filesystem prevents commit after logical retention, the entire
transaction rolls back and capacity failure is explicit.

## 7. References and retrieval

### Single reference

For `(session_id, sequence)`:

- wrong session: explicit `session_mismatch` without cross-session search;
- `sequence < low_water`: `expired` with marker;
- `low_water <= sequence < next_sequence`: exact retained record;
- `sequence >= next_sequence`: `not_found`.

### Range/page

An empty explicit range at a position no greater than the captured
`next_sequence` is complete with no records, even if the position is below the
retention low water; it requests no discarded evidence. An empty range beyond
`next_sequence` is `not_found`.

The first request validates its session/range and captures
`snapshot_end_exclusive = min(requested_end_or_next, next_sequence)`. It then
selects records using
`sequence >= page_start_sequence AND sequence < snapshot_end_exclusive`,
ordered ascending, until either required bound would be exceeded.

A page never splits a record. If the first next record exceeds the page byte
limit, the page returns its required charge, is truncated, and preserves the
same next position. Otherwise continuation advances to one past the last
returned sequence. Immutable session policy supplies independent finite
`max_retrieval_page_records` and `max_retrieval_page_charged_bytes` ceilings.
Caller values must be positive and no greater than those ceilings; the retained
byte quota does not enlarge either page ceiling. Policy validation guarantees
every accepted record fits within the page-byte ceiling.

The cursor is an immutable internal value bound to session, original range,
snapshot end, and next position. A later append is outside that traversal. If
retention advances over the next position, the next page reports that expired
interval and resumes at the new low water if retained evidence remains. Offset
pagination and timestamp ordering are forbidden.

The response distinguishes:

- outcome (`complete`, `partial`, `expired`, `not_found`);
- page truncation;
- expired interval and marker;
- never-existent suffix when an explicit range extends beyond the captured
  session `next_sequence`;
- continuation;
- returned charged bytes;
- optional next-record required bytes.

## 8. Failure behavior

Stable normalized journal categories cover invalid input, exists/missing,
session mismatch, incompatible version/application, corruption, busy, capacity,
database over ceiling, physical ceiling unavailable, sequence exhausted,
counter exhausted, read-only/permission, and open/read/write/commit/close I/O
failure. Behavior may use stable SQLite result attributes/codes internally;
exception message text is not a classification contract.

No raw SQLite/OS exception, connection, cursor, row, file handle, or SQL string
crosses the adapter boundary. Corrupt or incompatible journals are never
partially returned, silently migrated, automatically repaired, or modified.
The only exception to the last term is SQLite rollback recovery explicitly
allowed during open before application validation.

## 9. Concurrency and ownership

- One journal instance serializes every SQLite operation through its async gate
  and private one-thread executor; the connection never changes threads.
- Cancellation after work submission cannot release the gate before that work
  finishes; close also waits for admitted work.
- SQLite transaction rules preserve sequence if another process attempts a
  write; busy/lock failure is explicit and not retried indefinitely.
- Retrieval is callable concurrently with acquisition but uses short bounded
  transactions and owns no hardware or RX reader.
- A continuation cursor owns no SQLite cursor, connection, snapshot, or lock.
- This contract does not create service ownership, session orchestration, or a
  second evidence producer.

## 10. Explicitly absent

Profiles/default policy, multi-session management, annotations, operations,
derived representations, time/segment filters, external cursor encoding,
service/HTTP, CLI, live follow, TX/Control, reconnect, handoff, Enhanced, MCP,
backup/export, repair/salvage, and physical hardware behavior.
