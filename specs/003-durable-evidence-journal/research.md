# Research: Durable Evidence Journal

## Decision: SQLite via Python 3.14 `sqlite3`

Use the standard-library SQLite binding and one database per durable evidence
session. No runtime dependency is added.

### Why it fits

- Transactions atomically cover the record row, session counters, rolling
  deletes, and coalesced retention marker.
- BLOB columns preserve exact UART bytes without a text encoding.
- An integer primary key supports durable session sequence and keyset paging.
- Recovery, locking, integrity checks, page limits, application identity, and
  schema versioning already exist in the engine.
- Freed pages are reusable, so rolling retention can keep the logical set
  bounded without requiring a `VACUUM` in the acquisition path.
- SQLite ships with Python 3.14, preserving uv packaging and offline install
  behavior without a native extension or new license notice.

Primary references: SQLite's
[atomic commit](https://www.sqlite.org/atomiccommit.html),
[locking and rollback journal](https://www.sqlite.org/lockingv3.html), and
[PRAGMA](https://www.sqlite.org/pragma.html) documentation, plus Python 3.14's
[`sqlite3` documentation](https://docs.python.org/3.14/library/sqlite3.html).

## Decision: Rollback journal, `DELETE`, `synchronous=FULL`

Use these fixed connection settings for writable journals:

- `PRAGMA journal_mode=DELETE`
- `PRAGMA synchronous=FULL`
- `PRAGMA page_size=4096` at creation
- `PRAGMA max_page_count=<stored session-policy value>` on every writable
  connection, followed by verification of the returned effective ceiling
- `PRAGMA foreign_keys=ON`
- `PRAGMA busy_timeout=0`
- `PRAGMA application_id=0x4455544D` (`DUTM`)
- `PRAGMA user_version=1`

Every write uses `BEGIN IMMEDIATE`, applies append and any retention in one
transaction, and acknowledges only after `commit()` returns. Bounded retrieval
fully materializes one bounded page and ends its read transaction before
returning; no cursor retains a SQLite snapshot or lock.

`max_page_count` is connection configuration, not DUTchMate's persisted source
of truth. Immutable session metadata stores `max_database_pages`. Create applies
the supplied limit before schema allocation, persists it, then rereads and
verifies it. Reopen reads the stored value. Each writable connection rejects
current `page_count` above the policy, applies the value to `max_page_count`,
and verifies SQLite reports the requested effective limit. Failure to establish
the ceiling is `capacity/physical_ceiling_unavailable`; an already oversized
main database is `capacity/database_over_ceiling`. Append remains unavailable.
The main database is bounded to
`max_database_pages * 4096`; the rollback journal remains separate finite
transaction/recovery overhead containing touched-page pre-images plus journal
headers.

Rollback-journal mode was selected over WAL for the first persistence slice
because the durable session has one writer, pages are bounded and short, and a
single main file at rest plus a transaction-local recovery journal is easier to
validate, move while closed, and reason about. WAL would improve read/write
overlap but introduces persistent `-wal`/`-shm` companions and checkpoint/WAL
growth rules that this slice does not need. Concurrent callers remain safe;
their short operations may serialize rather than opening a second evidence
ordering path.

`FULL` requests the engine's durable commit protocol, but the product guarantee
is deliberately narrower: committed transactions recover after clean reopen
and tested abrupt process termination. The feature does not certify arbitrary
power failure, device-cache honesty, filesystem failure, network filesystems,
media loss, or live-file copying.

If a process dies after SQLite commits but before Python returns, the record may
exist even though the caller did not observe success. The sequence exposes that
fact after reopen; exactly-once retry is not invented.

## Decision: One session per database

The journal file is the durable bounded container described by Core §14.2. Its
metadata row stores one generated immutable session ID, next sequence, low-water
sequence, session policy, aggregate counters, and schema version.

This is smaller and clearer than a database-level session manager. It avoids
premature contracts for listing, naming, rotation, deletion, directories, or
run lifecycle. Closing and reopening a connection does not seal the session.
Later service composition chooses paths and decides when a new session file is
created.

## Decision: Canonical typed rows, not pickle

Schema version 1 stores:

- fixed record kind and record schema version;
- canonical UTF-8 JSON metadata in a BLOB, with sorted keys, compact separators,
  strict known fields, and no non-finite numbers;
- exact RX payload in a separate BLOB for RX records;
- deterministic quota charge and exact RX payload length as indexed integers.

Canonical metadata uses product discriminators and enum values, never Python
class/module names. Decode validates all required/allowed keys and reconstructs
the normalized evidence value. Unknown kinds, versions, fields, enum values, or
invalid cross-field combinations are corruption/incompatibility failures.

The deterministic charge is:

`8 sequence bytes + 8 version bytes + UTF-8 kind bytes + metadata BLOB bytes + payload BLOB bytes`

This stable logical accounting covers every record and is independent of
SQLite planner/page overhead. The required database-page cap provides the hard
main-file bound. A rollback journal is additionally bounded by the pre-image
pages touched in the transaction plus SQLite journal headers; because the main
page set is capped and one transaction touches only that finite set, temporary
recovery storage is finite and documented separately from retained evidence.

## Decision: Versioned opaque provenance snapshot

Persisting feature-002 provenance must not import Basic types into shared Core
or use unsafe pickle. Extend the normalized base provenance contract with a
durable snapshot containing:

- generic `envelope_version = 1` owned by this persistence contract;
- non-empty opaque backend-provided `backend_kind`;
- positive opaque backend-provided `backend_schema_version`;
- sorted unique string fields whose values are only `None`, `bool`, `int`, or
  `str`.

The Basic adapter produces its own version-1 flattened snapshot of selected and
opened device name, requested/effective configuration, open-line intent and
reported state, exclusivity, and verification limitations. Shared acquisition
still copies the opaque runtime value unchanged. The SQLite codec asks only for
the generic snapshot and returns a generic persisted-provenance value on
reconstruction. SQLite validates the envelope version and scalar structure but
does not recognize or register backend kinds or backend schema versions.
Unknown conforming backend values round-trip unchanged; only an unsupported
generic envelope version fails compatibility validation. No backend registry or
identity branch is required.

## Decision: Rolling prefix and one coalesced marker

Creation requires all of:

- maximum retained record count;
- maximum retained charged bytes;
- maximum single-record charged bytes;
- maximum 4096-byte database pages;
- independent maximum retrieval-page record count;
- independent maximum retrieval-page charged bytes.

There is no unbounded or implicit default. On append, reject a record that
cannot fit by itself before changing the database. Otherwise select the minimum
oldest prefix whose removal makes both retained quotas true, then delete,
update one marker, insert, and advance sequence in one transaction.

The marker describes the continuous expired prefix `[0, low_water)` and stores
discarded record count, the exact count of discarded RX payload bytes,
discarded charged bytes, and the first/last timestamped observations
encountered. Timestamp endpoints retain full domain/origin descriptors
separately; no duration or cross-domain comparison is inferred. If no discarded
record carried a timestamp, the absence is explicit. One row is updated, so
marker storage is constant across arbitrarily many retention passes. No
additional latest-discard high-water field is needed: `expired_end_sequence`
already is the retention low-water boundary and session `next_sequence` is the
append high water.

## Decision: Stable references and snapshot keyset cursors

The stable record reference is `(session_id, sequence)` and the stable range is
`(session_id, start_inclusive, end_exclusive)`. The low-water and next-sequence
values distinguish retained, expired, partial, and never-existent references.

The first page fixes `snapshot_end_exclusive = min(requested_end,
next_sequence)`. Its typed cursor carries session ID, original range, snapshot
end, and next sequence. Pages query `sequence >= next` ordered by sequence, not
by timestamp and not by SQL offset. Appends above the snapshot end are excluded.
If retention passes the cursor, the next result reports the expired interval
before continuing with retained records.

Session policy persists finite `max_retrieval_page_records` and
`max_retrieval_page_charged_bytes` independently of total retained quotas.
Caller limits must be positive and at or below those ceilings. A record is
never split; if it alone exceeds the caller's byte bound, the page reports
required size and leaves the cursor at that sequence. Policy validation requires
the maximum single-record charge to fit under the independent page-byte ceiling,
so every accepted record can be retrieved without letting a large retention
quota authorize a large in-memory page.

For an empty `[x,x)` range, `x <= next_sequence` returns complete and empty even
when `x < low_water`; no evidence was requested. Only `x > next_sequence` is
`not_found`.

External cursor serialization, signing, and HTTP compatibility are deferred.

## Decision: Fail closed on compatibility and corruption

Open first lets SQLite perform rollback recovery, then checks application ID,
`user_version`, schema objects, the singleton session/marker invariants,
sequence/counter aggregates, known record and generic provenance-envelope
versions, and `PRAGMA quick_check` before enabling append.

Version 1 has no migrations. Older or newer store versions, wrong application
identity, unknown evidence-record versions, unsupported generic provenance
envelope versions, malformed canonical metadata, failed integrity, and
invariant mismatches return normalized incompatible or corrupt journal
failures. Unknown backend provenance kinds/schema versions inside a supported
envelope are opaque data and do not fail open. The adapter does not write,
salvage, skip rows, or repair automatically after validation fails. SQLite's
preceding rollback recovery may have restored the last committed state; the
resulting files remain available for later explicit diagnosis.

## Decision: One journal-private SQLite worker thread

Each open journal owns one `ThreadPoolExecutor(max_workers=1)` and one asyncio
serialization gate. The SQLite connection is created, used, and closed only on
that executor thread with the standard `sqlite3` same-thread check enabled.
Create/open validation, append, retrieval, and close all pass through the same
gate and executor; there is no general worker service and no second connection
or ordering path.

Cancellation while waiting for the gate submits no work. After work is
submitted, the async wrapper shields and waits for the worker to finish before
releasing the gate, even if its caller has been cancelled; it then propagates
cancellation. This prevents a cancelled caller from allowing a later operation
or close to overlap the still-running SQLite call.

Cancellation does not interrupt SQLite or imply rollback. An append may commit
before the cancelled caller observes cancellation, so the call returns no
accepted record and has an indeterminate caller-visible outcome. Reopen or
reference retrieval resolves whether the sequence committed. No automatic
retry or deduplication is added.

## Decision: Signed 64-bit durable integers

SQLite `INTEGER` is treated as signed 64-bit, with
`SQLITE_INTEGER_MAX = 2^63 - 1`. Evidence records use sequences
`0..SQLITE_INTEGER_MAX - 1`; `next_sequence` may equal
`SQLITE_INTEGER_MAX`. If it already equals that value, append fails before
insertion as `capacity/sequence_exhausted` because advancing it would overflow.

All persisted range/cursor positions, quotas, sizes, page counts, record counts,
and cumulative retention counters remain within `0..SQLITE_INTEGER_MAX`.
Checked addition occurs before mutation. Non-sequence overflow fails as
`capacity/counter_exhausted`; the transaction and prior evidence remain
unchanged. Python's larger integer range is never used to bypass the durable
representation.

## Alternatives Rejected

### Custom append-only binary log

Would require inventing framing, checksums, torn-write recovery, indexes,
retention compaction, atomic metadata replacement, locking, and migration.
Those are exactly the hard requirements SQLite already supplies.

### JSON Lines or CBOR stream

JSON Lines is awkward for arbitrary bytes and atomic retention compaction.
CBOR would add a dependency but still leave crash recovery, indexes, locking,
and prefix reclamation unsolved.

### One file per record

Atomic rename helps individual records but not atomic sequence/retention
metadata, and directory entry growth is unbounded and expensive to paginate.

### LMDB or another embedded database

Capable, but adds a native dependency, packaging/licensing surface, and a
second runtime component without a requirement SQLite cannot meet.

### General persistence port and provider registry

Rejected as speculative. The existing recorder port is the concrete append
boundary already used by acquisition. Only one storage mechanism is required;
the concrete journal exposes retrieval directly.

## Open Decisions

None block implementation. Numerical product defaults and profile/service path
selection are deliberately deferred; this slice requires explicit finite
values at journal creation.
