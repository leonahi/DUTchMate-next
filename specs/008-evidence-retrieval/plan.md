# Implementation Plan: Bounded Evidence Retrieval

**Feature**: `008-evidence-retrieval` | **Date**: 2026-10-10 | **Git branch**: `main`
**Spec**: [spec.md](spec.md). Planning snapshot2026-10-10; execution progress is in
[tasks](tasks.md) and [current status](../../docs/development_status.md).

## Summary

Expose Feature003's individual references and bounded fixed-snapshot pages through
two authenticated service routes and two thin Typer commands. Retain one current/
last run/session association in the current service incarnation. Active reads use
the capture journal's existing gate; terminal reads use a private, short-lived
read-only connection after positive recorder closure. Preserve exact evidence and
all003 outcomes, with standard padded base64 for RX and independent finite delivery
limits. Extend005–007 resource ownership without public paths, historical browsing,
new persistence/Profile versions, additional acquisition or automatic pagination.

Decisions: [research](research.md), [data model](data-model.md),
[normative additive contract](contracts/evidence-retrieval.md),
[validation walkthrough](quickstart.md). Core remains authoritative.

## Technical Context

**Language/Version**: Repository Python3.14, managed exclusively through uv.
**Primary Dependencies**: Existing standard-library asyncio/sqlite3/base64/json,
FastAPI/Uvicorn service and Typer/HTTPX CLI; no dependency or lockfile change planned.
**Storage**: Existing003 SQLite schema-v1, SessionPolicy and retention metadata;
existing004 Profile-v1 unchanged. No cursor/session catalogue or new persisted data.
**Testing**: pytest, existing deterministic Basic/Enhanced-shaped fixtures, guarded
ASGI/native-loopback/process tests, Ruff, mypy and import-linter.
**Target Platform**: Existing Linux/macOS POSIX entry support; planning validated
on macOS. Native Linux/Windows and physical acceptance remain unexecuted.
**Project Type**: Existing uv workspace: Core library, local service, thin CLI.
**Performance Goals**: Finite bounded delivery and retained work, continuous single
RX ownership; no new throughput, hard-time, database-memory or socket-buffer claim.
**Constraints**: Request16384 bytes; token1024 ASCII bytes; session256 UTF-8 bytes;
page request4096 records/1048576 charged bytes also subject to003 policy; service
JSON and CLI JSON each1048576 bytes, CLI LF excluded. Eight Core leases/eight service
read tasks, separately from006's eight mutations. Existing10s/5s CLI HTTP budgets.
**Scale/Scope**: One runtime/current-or-last association per incarnation, two read
routes/two CLI subcommands, no queue/catalogue/background streaming.

## Constitution Check

The `.specify/memory/constitution.md` is an unpopulated scaffold, not a competing
authority. Gates derive from Core, AGENTS.md, current status and003/005–007.
Pre-research and post-design checks have no required exception:

- Core §§14–18/22–23: exact bytes, explicit retention/provenance, bounded retrieval,
  one service physical owner and normalized backend neutrality remain intact.
- Shared application imports no filesystem/SQLite/HTTP/client/framework detail.
  New ports represent the demonstrated persistence/lifetime boundary only.
- Active reads serialize with existing append/close; terminal access never calls
  writable003 open/recovery. Positive read-cleanup facts protect006's final marker.
- 006 caller/auth/browser gates and007 private finite delivery remain mandatory;
  old requests, replies, exits, lifecycle facts and mutation capacity unchanged.
- No schema-v1/Profile-v1 or physical backend contract revision; no Enhanced
  production mechanics, deferred feature, hardware action, dependency or exemption.
- Required architecture contracts remain strong; extend only if existing scopes
  do not cover actual new modules. Never name a nonexistent module in configuration.
- Acceptance requires meaningful RED/green coverage, fresh full gate/installability
  and honest platform/hardware limits. Planning does not claim feature completion.

## Project Structure

### Documentation (this feature)

```text
specs/008-evidence-retrieval/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/evidence-retrieval.md
├── checklists/requirements.md
└── tasks.md
```

### Source Code (repository root; planned changes)

```text
core/src/dutchmate_core/
├── evidence.py                   # minimal JournalFailure transport correction
├── evidence_access.py            # new pure read ports/values/failures
├── runtime.py                    # association, pinned reads, close seal/cleanup latch
└── adapters/
    ├── sqlite_evidence.py        # reuse pure003 validation/selection, no codec revision
    ├── terminal_evidence.py      # new private identity and per-query read-only adapter
    └── observation_runtime.py    # optional live/terminal read-capability handoff
apps/service/src/dutchmate_service/
├── evidence_http.py              # new strict wire/cursor/projection/error handling
├── http.py                       # additive literal route gate; reuse006 projection
├── app.py                        # bounded registered reads/routes/shutdown conjunction
└── server.py                     # adjust final cleanup plumbing only if needed
apps/cli/src/dutchmate_cli/
├── evidence.py                   # new pure inputs and closed evidence-wire validation
├── main.py                       # evidence group/commands, existing entry/output seams
└── client.py                     # finite exchange reuse, separate new response validator
core/tests/{unit,contract,integration}/
apps/service/tests/
apps/cli/tests/                   # grammar/transport + installed guarded processes
```

**Structure Decision**: Extend the existing three packages. A terminal reader is
a distinct adapter because writable reopen/recovery and read-only lifetime change
independently. Reuse003 pure validators/selection, not its mutable open lifecycle.
Live access may expose a narrowed existing journal port without adding another
connection. Share private finite HTTP mechanics without adding a generalized
client/DTO framework or changing the old007 request/response/error seam. No new
package, persistence catalogue, backend-name policy, recorder facade with writes
or speculative extension layer.

Foundation boundary note (T005): runtime and evidence_access share the existing
application layer because RunEvidencePage reuses005's RunId. A deferred value-only
RunId import prevents initialization cycles for later consumers. Import contracts
now cover the new module at that layer and forbid adapter dependencies; every
constraint among previously existing modules is preserved, with no exemption.

## Implementation Sequence and Acceptance

1. Capture baseline and invariants. Demonstrate/fix only JournalFailure exception
   transport, then add pure read ports/values with focused validation (T001–T005).
2. RED live association/admission/cancellation/close races with identical Basic and
   Enhanced-shaped assertions. Add optional prepared access, pinned owner tasks,
   same-journal reads and seal/join before recorder close (T006–T009).
3. RED strict authenticated routes and current-session CLI requests. Add bounded
   service registry, schema/cursor/projection/error handling and thin CLI delivery.
   Complete active end-to-end gate as US1's independently testable MVP (T010–T014).
4. RED terminal native identity/read-only transaction/no-recovery/full-v1 validation
   and cleanup tests. Implement per-query reader and known failed-preparation handoff;
   preserve physical-release uncertainty and latch read cleanup before slot release
   (T015–T019). Optional terminal capability lets US1 work without a fake opener.
5. Verify003 snapshot/reference/retention semantics, exact records, full canonical
   cursor/binary projection and distinct policy/wire/output bounds. Correct only
   demonstrated gaps; existing passing003 behavior needs no manufactured change
   (T020–T025).
6. Exercise simultaneous eight-read/eight-mutation capacity, pending admission,
   append/eviction/detach/close/new-attach, cancellation/open/close and shutdown.
   Complete service clean-marker conjunction without changing capture facts
   (T026–T027).
7. Run actual guarded installed wheel/sdist CLI/service flows with known fake DUT
   fixtures, private temporary credentials, IPv4/IPv6, SIGINT/closed pipes/oversize/
   malformed responses. Correct only demonstrated delivery defects (T028–T030).
8. Review complete contracts/scope/installability, reconcile status/history, perform
   at most one justified code-only Graphify update after structural changes, and
   run fresh required full gate. Stop without automatic commit/push/next slice or
   physical acceptance (T031–T035).

Every stage runs focused tests first and the applicable full repository gate before
declaring its slice complete. Registry/lease admission has no queue. Core admission,
not HTTP registration, pins source identity. Terminal association holds no writer,
connection or FD. New attach removes old public selection while already admitted
reads finish their pinned source. Schema/policy/identity validation is inside one
read transaction; append/eviction on active readers use the existing worker gate.
Uncertain read cleanup seals later admission before release and keeps service dirty.
Primary failure wins over secondary close failure; close-only failure discards report.

## Complexity Tracking

No authority/architecture violation or exemption required. The new read port,
terminal adapter and bounded owner tasks solve current persistence, concurrency and
cleanup requirements; no speculative infrastructure is justified.
