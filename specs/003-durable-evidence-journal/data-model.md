# Data Model: Durable Evidence Journal

## SessionId

Opaque non-empty Core-generated identity for the one session contained in a
journal. It is immutable across path moves and reopen. The path is not identity.

## EvidenceSequence

Non-negative integer scoped to `SessionId`. The first accepted record is `0`;
`next_sequence` advances in the same transaction as append. Retention never
renumbers and never decreases `next_sequence`. SQLite's signed 64-bit
representation sets `SQLITE_INTEGER_MAX = 2^63 - 1`: stored record sequences
are `0..SQLITE_INTEGER_MAX - 1`, while `next_sequence` may reach
`SQLITE_INTEGER_MAX`. Append at that terminal value fails before insertion as
`capacity/sequence_exhausted`.

## SessionPolicy

Immutable required creation values:

- `max_retained_records: int > 0`
- `max_retained_charged_bytes: int > 0`
- `max_record_charged_bytes: int > 0`, no greater than either the retained-byte
  limit or independent retrieval page-byte ceiling
- `max_database_pages: int > 0`, with fixed 4096-byte pages and sufficient
  capacity for the version-1 schema
- `max_retrieval_page_records: int > 0`
- `max_retrieval_page_charged_bytes: int > 0`, independent of total retained
  bytes

Every value is at most `SQLITE_INTEGER_MAX`. Only rolling oldest-prefix
retention exists in version 1. The policy is stored inside the session and must
match on reopen; it is not silently replaced. `max_database_pages`, not the
connection's `PRAGMA max_page_count`, is persisted DUTchMate state. Every
writable connection reapplies it and verifies both
`page_count <= max_database_pages` and
`max_page_count == max_database_pages` before enabling writes.

## ConnectionProvenanceSnapshot

Normalized durable envelope supplied by any backend provenance object:

- `envelope_version = 1`, owned by the generic persistence contract
- `backend_kind: str`, non-empty opaque backend-provided discriminator
- `backend_schema_version: int > 0`, opaque to SQLite/shared Core
- `fields: tuple[ProvenanceField, ...]`, sorted by unique non-empty field name

`ProvenanceField.value` is exactly one of `None`, `bool`, `int`, or `str`.
Float, bytes, nested objects, exceptions, handles, Python type names, and
adapter objects are rejected. A `PersistedConnectionProvenance` wraps the
snapshot when reconstructing a durable segment-start record; shared Core treats
it opaquely just like the live Basic provenance subtype. Supported envelope
structure is validated without a registry of backend kinds/versions. Unknown
conforming backend values round-trip unchanged; unsupported envelope versions
fail explicitly.

## DurableEvidenceSession

Exactly one singleton row per journal:

- `session_id`
- `schema_version = 1`
- immutable `SessionPolicy`
- `next_sequence`
- `low_water_sequence`
- `retained_record_count`
- `retained_charged_bytes`

Invariants:

- `0 <= low_water_sequence <= next_sequence <= SQLITE_INTEGER_MAX`
- retained sequences are exactly the existing rows within
  `[low_water_sequence, next_sequence)`; sequence holes are corruption
- aggregate count/charge equals retained rows
- if no evidence expired, `low_water_sequence == 0` and no marker exists
- the session is appendable after close/reopen; no sealed/run state exists

## StoredEvidenceRecordV1

Relational row keyed by `sequence`:

- `record_kind`: one of `segment_started`, `rx_bytes`, `observer_loss`,
  `segment_ended`
- `record_version = 1`
- `metadata_json`: canonical strict UTF-8 JSON stored as BLOB
- `payload`: exact BLOB only for `rx_bytes`, otherwise null
- `charged_bytes`: deterministic encoded component charge
- `rx_payload_bytes`: payload length for RX, otherwise zero
- optional extracted timestamp endpoint fields used only to update retention
  metadata without comparing domains

The metadata contains the existing feature-001 normalized fields. Record order
is `sequence`; timestamp values are never a sort key.

## RetentionMarker

At most one singleton row, representing the coalesced expired prefix:

- `expired_start_sequence = 0`
- `expired_end_sequence = low_water_sequence` (exclusive)
- `first_discarded_timestamp` plus its full domain descriptor, or absent
- `last_discarded_timestamp` plus its full domain descriptor, or absent
- `discarded_record_count`
- `discarded_rx_payload_byte_count`
- `discarded_charged_bytes`

The timestamp endpoints are ordered by evidence sequence, not compared as
clock values. Marker updates are allowed because Core explicitly permits
coalesced retention metadata; retained evidence records remain immutable.
`discarded_rx_payload_byte_count` is only the exact cumulative byte count;
discarded payload content is not retained. `expired_end_sequence` already
supplies the retention boundary, so no separate latest-discard high-water field
exists.

## EvidenceReference

Stable pair `(session_id, sequence)`. Resolution variants:

- `Found(record)` when retained
- `Expired(reference, marker)` when sequence is below low water
- `NotFound(reference)` when sequence is at or above next sequence
- `SessionMismatch(reference)` when the reference names another session

## EvidenceRangeReference

Stable half-open interval `(session_id, start_inclusive, end_exclusive)` with
`0 <= start <= end <= SQLITE_INTEGER_MAX`. An empty `[x,x)` with
`x <= next_sequence` is complete and empty regardless of low water; with
`x > next_sequence` it is not found. A non-empty range can be retained, expired,
partial, or not found.
`partial` identifies each expired prefix and/or never-existent suffix. Expiry,
nonexistence, and page truncation are independent states.

## EvidenceRetrievalRequest

- session or range reference
- `max_records: int > 0`
- `max_charged_bytes: int > 0`
- optional typed `EvidenceCursor`

Requests above implementation safety ceilings fail validation. Version 1 uses
the independent session-policy `max_retrieval_page_records` and
`max_retrieval_page_charged_bytes` ceilings and returns complete raw normalized
records only. Retained-byte capacity never determines an allowed page size.

## EvidenceCursor

Immutable internal value:

- `session_id`
- original `range_start_inclusive`
- original `range_end_exclusive` or session-range sentinel
- `snapshot_end_exclusive`
- `next_sequence`

It is validated as one coherent query snapshot. It has no public string/token
encoding in this feature.

## EvidencePage

- ordered tuple of complete records
- `snapshot_end_exclusive`
- optional expired interval and current `RetentionMarker`
- optional never-existent suffix interval
- outcome: `complete`, `partial`, `expired`, or `not_found`
- `truncated: bool`
- optional continuation cursor
- `charged_bytes`
- optional `next_record_required_bytes` when the next record cannot fit

`partial` describes retention loss, while `truncated` describes pagination;
both may be true.

## JournalExecutionState

One open journal owns one `ThreadPoolExecutor(max_workers=1)`, one asyncio
serialization gate, and one SQLite connection created/used/closed only on the
executor thread. An operation is either waiting for the gate, submitted to the
worker, or complete. Cancellation while waiting submits nothing. Cancellation
after submission records caller cancellation but keeps the gate held until the
worker completes; then cancellation is propagated. For append, completion may
include a committed transaction even though no accepted record is returned to
the cancelled caller. Close waits for every admitted operation and closes the
connection on the same worker before executor shutdown.

## JournalFailure

Normalized typed errors with stable operation and category, including:

- invalid policy/request/cursor/session identity
- journal already exists / journal missing
- incompatible application or schema/evidence-record/generic-envelope version
- corrupt journal or invariant violation
- busy/locked
- capacity/full
- `capacity/database_over_ceiling` or
  `capacity/physical_ceiling_unavailable`
- `capacity/sequence_exhausted` or `capacity/counter_exhausted`
- read-only/permission
- open/read/write/commit/close I/O failure

Raw `sqlite3` and OS exception objects do not cross the concrete adapter's
public boundary. A failed append returns no accepted record.

Every persisted integer counter, quota, size, page count, range/cursor position,
and checked sum remains in `0..SQLITE_INTEGER_MAX`. Overflow is detected before
mutation and leaves the prior transaction state unchanged.

## State Transitions

```text
missing path --create(policy)--> open appendable session
open --append/commit-----------> open with next_sequence advanced
open --append+retention--------> open with prefix expired atomically
open --close-------------------> same durable session, no open handle
closed --open------------------> open appendable same session
open/closed --corruption-------> fail closed; source preserved
```

There is no seal, run completion, rotation, delete, or multi-session transition.
