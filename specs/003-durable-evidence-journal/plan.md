# Implementation Plan: Durable Evidence Journal

**Branch**: `main` | **Date**: 2026-09-30 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from
`/specs/003-durable-evidence-journal/spec.md`

## Summary

Add one concrete SQLite-backed evidence journal to `dutchmate-core`. Each
journal database contains exactly one durable session, assigns authoritative
per-session sequences, atomically commits append plus rolling retention, and
supports stable references and bounded sequence-key pages. SQLite is used
directly through Python 3.14's standard-library `sqlite3`; no generalized
repository or storage-provider abstraction is added. The existing
`EvidenceRecorder` remains the acquisition append boundary, and the concrete
journal owns the new retrieval behavior.

## Technical Context

**Language/Version**: Python `>=3.14,<3.15`

**Primary Dependencies**: Python standard library (`sqlite3`, `json`,
`asyncio`, `concurrent.futures`, `pathlib`, `uuid`); existing project
dependencies unchanged

**Storage**: One SQLite schema-version-1 database per evidence session,
rollback-journal `DELETE` mode, `synchronous=FULL`, 4096-byte pages, immutable
session-policy `max_database_pages` reapplied/verified as `max_page_count` on
every writable connection, canonical JSON metadata BLOBs, and exact RX BLOBs

**Testing**: pytest 9.1 with pytest-asyncio; temporary paths; subprocess crash
harness using the repository Python; deterministic blocking-worker/cancellation
fakes; existing Ruff, mypy, Import Linter, and hardware fail-closed guards

**Target Platform**: Local Linux, macOS, and Windows filesystems supported by
Python 3.14 SQLite; no network filesystem durability claim

**Project Type**: Existing uv Python workspace and `dutchmate-core` library

**Performance Goals**: Sequential append remains the sole evidence order;
bounded retrieval never holds a cursor transaction between calls; 1,000
retention passes leave one coalesced marker; no unbounded in-memory materialize
or offset scan

**Constraints**: One session per file; no unbounded retention; no partial
record retrieval; no SQLite or Basic-specific type above the adapter boundary;
one journal-private worker thread and serialization gate; signed 64-bit durable
integers; no raw `sqlite3` exception in the Core-facing contract; no hardware
access

**Scale/Scope**: Current four feature-001 evidence variants, one writer journal
instance, concurrent callers serialized over short storage transactions, raw
session/sequence retrieval only, independent finite retrieval page ceilings,
schema version 1 and generic provenance-envelope version 1 only

## Constitution Check

The repository constitution template is not populated, so the governing gates
come from `AGENTS.md`, the Core document, and the active specification.

- **Authority**: Pass. The plan implements Core §§14.2, 14.5, and 14.6 and
  preserves feature-001/002 contracts.
- **Dependency direction**: Pass. Domain request/result values remain in shared
  Core; `dutchmate_core.adapters.sqlite_evidence` depends inward on them.
  Shared acquisition never imports the SQLite adapter.
- **Concrete boundary only**: Pass. The existing `EvidenceRecorder` is reused;
  retrieval is a concrete journal API, not a speculative repository/provider
  hierarchy.
- **Backend neutrality**: Pass. Persistence uses a normalized versioned
  provenance snapshot and never imports or branches on Basic identity.
- **Evidence integrity**: Pass. Sequences, exact bytes, timestamp provenance,
  and existing records are never reordered or rewritten to satisfy retention.
- **Boundedness**: Pass. Session creation requires finite retention, per-record,
  main-database-page, and independent retrieval-page bounds. A large retention
  quota cannot become a large in-memory retrieval page.
- **Durability honesty**: Pass. Acknowledgment follows commit; clean reopen and
  process-crash recovery are in contract. Arbitrary power loss, broken flushes,
  media faults, backups, and exactly-once retry are not claimed.
- **Hardware safety**: Pass. Tests use temporary files and fake backends only.
- **Phase discipline**: Pass. No Profile, service, CLI, Monitor/Interact,
  Control, reconnect, Enhanced, or MCP behavior is introduced.

Re-check after design: the data model and concrete contract satisfy each gate;
no exception or complexity waiver is required.

## Project Structure

### Documentation (this feature)

```text
specs/003-durable-evidence-journal/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── durable-evidence-journal.md
├── checklists/
│   └── requirements.md
└── tasks.md
```

### Source Code (repository root)

```text
core/
├── src/dutchmate_core/
│   ├── model.py                         # session/reference/provenance values
│   ├── evidence.py                      # recorder and retrieval value contract
│   └── adapters/
│       ├── basic_serial.py              # Basic provenance snapshot producer
│       └── sqlite_evidence.py            # concrete schema/codec/journal
└── tests/
    ├── unit/
    │   ├── test_evidence_journal_model.py
    │   └── test_sqlite_evidence_codec.py
    ├── contract/
    │   └── test_sqlite_evidence_journal.py
    └── integration/
        ├── test_durable_acquisition.py
        ├── test_sqlite_recovery.py
        └── fixtures/
            └── sqlite_recovery_worker.py
```

**Structure Decision**: Keep durable domain values beside the existing evidence
model and implement SQLite only in the infrastructure adapter package. Do not
split schema, codecs, repositories, migrations, or session managers into
separate abstractions until a demonstrated independent reason to change exists.

## Implementation Steps

1. **Establish durable values and normalized provenance snapshots.** Add
   validated session IDs, signed-64-bit sequence/counter bounds, finite session
   policy with independent retrieval ceilings, stable record/range references,
   retention marker, retrieval values, and normalized failures. Extend backend
   provenance with generic envelope version 1 around opaque backend kind/schema
   version and scalar fields; no backend registry.
2. **Build and test schema-version-1 creation/opening and codecs.** Add the
   concrete SQLite module, application/schema identity, immutable one-session
   metadata, strict canonical JSON metadata codec, exact payload BLOB handling,
   deterministic storage charge, persisted `max_database_pages`, per-writable-
   connection ceiling reapplication/verification, and error normalization.
3. **Implement serialized atomic append and recovery.** Create/use/close the
   SQLite connection on one journal-private executor thread under a
   cancellation-safe async gate. Assign checked sequence/counters inside
   `BEGIN IMMEDIATE`, commit before acknowledgment, continue after reopen, and
   validate crash, cancellation, and ambiguous-return cases.
4. **Add atomic rolling retention.** Evict the minimum oldest prefix required
   by record/byte quotas in the same append transaction, update one coalesced
   marker, preserve timestamp endpoint provenance, reject oversized records
   before eviction, and enforce the database page ceiling.
5. **Add stable reference resolution.** Distinguish retained, expired,
   partially expired, and never-existent records/ranges from the durable
   low-water and next-sequence metadata without fabricating missing data.
6. **Add bounded snapshot pagination.** Implement sequence-key pages with both
   caller record/byte limits capped by independent session-policy ceilings, a
   fixed first-page upper bound, typed immutable continuation,
   oversized-next-record reporting, consistent empty ranges, and explicit
   expiry that occurs between pages.
7. **Integrate acquisition with the concrete journal.** Run the existing
   acquisition coordinator unchanged against SQLite, prove ambient exact-byte
   recording and normalized recording failure, and keep Basic/Enhanced-shaped
   behavior identical above the backend boundary.
8. **Harden compatibility and corruption behavior.** Test wrong application
   identity, unsupported store/record/generic-envelope versions, opaque unknown
   backend provenance, invariant breaks, malformed encodings, integrity
   failure, lock/full/read-only failures, and fail-closed preservation of source
   files.
9. **Validate and reconcile documentation.** Run focused quickstart matrices,
   all feature-001/002 regressions, static/architecture checks, the full
   repository gate, diff review, and update development status/history only
   after implementation is actually complete. Update Graphify only if the
   structural criteria require it.

## Architectural Invariants

- `EvidenceSequence`, never timestamp or SQLite row order, is authoritative.
- Append, retention, marker, counters, and sequence advance are one transaction.
- Durable sequences/counters use checked signed-64-bit arithmetic and fail
  before mutation on exhaustion.
- An accepted RX payload is stored and reconstructed exactly; it is never
  decoded or split by retention/retrieval.
- Retention only removes an oldest prefix and never renumbers or rewrites
  surviving evidence.
- A journal file contains one immutable session; handle close has no semantic
  session meaning.
- Shared acquisition sees only `EvidenceRecorder`; it contains no SQLite or
  Basic branch.
- Provenance storage is generic-envelope-version plus opaque backend
  kind/version/scalar-data, not pickle, Python class import, adapter registry,
  or raw pySerial object.
- `max_database_pages` is persisted policy; SQLite `max_page_count` is reapplied
  and verified connection configuration, not the policy source of truth.
- A journal-private one-thread executor owns the SQLite connection. Caller
  cancellation never releases serialization while submitted work still runs.
- Cursor state is a sequence snapshot position, not a long-lived database
  transaction and not an external token contract.
- All errors are explicit; corruption is never repaired or skipped silently.

## Critical Tests and Validation

- Model validation and immutability for every new value and boundary case.
- Physical-ceiling reapplication failures, current page count above policy, and
  bounded rollback-journal overhead distinction.
- Strict round-trip fixtures for every current evidence variant, all byte
  values, both timestamp observers, both loss-observability forms, known and
  unknown opaque backend provenance, and unsupported envelope versions.
- RED/GREEN atomic append, close/reopen, subprocess exit after acknowledgment,
  interrupted uncommitted transaction, cancellation while blocking work runs,
  gate/close ordering, and commit-before-cancellation ambiguity.
- Record-count and charged-byte retention, minimum-prefix eviction, oversized
  record no-op, 1,000-pass marker coalescing, and cross-domain timestamp
  endpoints.
- Stable single/range reference outcomes and cursor continuation while append
  and retention advance, including explicit empty ranges and independent page
  byte/record ceilings.
- Sequence, counter, quota, charge, and range/cursor boundary/exhaustion tests
  at `2^63 - 1`.
- Corruption/version/lock/capacity failure matrix with original-file hashes
  unchanged after validation failure, accounting explicitly for any permitted
  preceding SQLite rollback recovery.
- Adapter-through-acquisition exact bytes, provenance, sequence, restart, and
  recording-failure behavior without changing one-RX-consumer semantics.
- `uv run --frozen ruff check .`, `uv run --frozen mypy .`,
  `uv run --frozen lint-imports`, `uv run --frozen pytest`, and
  `git diff --check`.

## Platform-Specific Risks

- SQLite durability ultimately depends on OS/filesystem flush behavior; tests
  prove software process-crash recovery, not arbitrary power-loss survival.
- Network filesystems and copying a live journal are outside the guarantee.
- Rollback journals are temporary companion files; deployment storage must
  allow the documented bounded transaction overhead in addition to the main
  database page cap.
- Python `sqlite3` connections are thread-affine by default; all connection
  operations must remain on the journal's sole executor thread.
- Windows file locking and POSIX permission/read-only errors differ internally;
  tests assert normalized outcomes rather than OS error text.

## Complexity Tracking

No constitution violation or speculative abstraction is introduced. SQLite is
the only storage mechanism, and the existing recorder port is the only append
abstraction.
