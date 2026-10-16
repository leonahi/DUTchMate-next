# Implementation Plan: Bounded Attributed Client Annotations

**Feature**: `010-client-annotations` | **Date**: 2026-10-15 | **Git branch**: `main`
**Input**: [spec.md](spec.md). T001–T024 complete (24/24); documentation/status/history/artifact progress is reconciled with completed evidence and Core16 architecture remains conformant. T023's final code-only incremental Graphify update/tooling limits remain recorded and outputs/backups/tooling ignored. T024 fresh final gate6951 passed with installed/artifact/privacy/Core/contract review clean; no corrective change or full-gate/Graphify rerun. Feature010 is software-complete; implementation commit is recorded in development_status.md; Phase1 remains incomplete. The separately authorized final pre-commit review/commit is recorded in development_status.md. Spec Kit's feature resolver reports010-client-annotations as its logical feature name; no branch-creation hook exists and Git remains main.

## Summary

Add short attributed client assertions to the existing active session through Core, authenticated HTTP and thin CLI. Use the sole committed coordinator/journal, explicit schema3/annotation-v3, unchanged v1/v2 entry points and old encodings, bounded rate/size/ownership, ordinary retention/retrieval and existing cleanup/security. No hardware action or unrelated Phase1 feature.

## Technical Context

**Language/Version**: Repository Python>=3.14,<3.15; committed evidence uses3.14.3.
**Primary Dependencies**: Existing asyncio/collections/json/sqlite3/UTF-8/UUID, FastAPI/Uvicorn, Typer/HTTPX; Basic pyserial stays behind its boundary. No new package/dependency/lock change.
**Storage**: Existing SQLite three-table journal, explicit schema3. Original four record-v1/two operation-v2 byte encodings unchanged; one new annotation-v3 variant. No migration or separate store.
**Testing**: Existing pytest/pytest-asyncio, injected clocks/append gates, real temporary v1/v2/v3 journals, identical backend-shaped fixtures and guarded outside-cwd non-editable wheel/sdist processes.
**Target Platform**: Existing Linux/macOS POSIX delivery contract. Native macOS software evidence may be collected; Linux/Windows/active-DUT/physical/electrical acceptance is not automatically selected. Actual Windows commands remain unsupported.
**Project Type**: Existing modular monolith with inward application/domain, infrastructure adapters, authenticated local service and thin CLI.
**Performance Goals**: Annotation validation bounded by1024 UTF-8 bytes; rate state at most ten samples, one owner; no RX payload copy/window retained for annotations and no extra physical reader.
**Constraints**: Text1..1024 UTF-8 bytes/no NUL/surrogates; ten admissions/rolling1,000,000,000ns/incarnation; one pending annotation/run; existing16384 request,1048576 JSON(+CLI LF),1024 cursor and5s/10s client transport limits. Existing eight mutation/eight read/one Monitor service slots. Durable I/O/cleanup not time-bounded.
**Scale/Scope**: One current associated session per incarnation; active insertion and existing active/terminal reads only. No catalogue, restart/history, editing or schema auto-selection.

## Constitution Check

The constitution file is an unpopulated scaffold. It adds no rule or new approval process. Core/AGENTS govern; checks below passed at initial context review and were re-evaluated after research/contracts.

| Gate | Design evidence | Result |
|---|---|---|
|Core/client assertions|Fixed class/basis, declared surface, no verified-action claim/TX permission|Pass|
|Ownership/order|One coordinator/journal/RX; insertion sample under gate, admitted owner joins before close|Pass|
|Bounds/retention|1024-byte text, ten-rate/one-owner, normal codec charge/expiry, bounded read pages|Pass|
|Compatibility|Explicitv3, strict old factories/codecs/Profile-v1, old constructors optional, no migration|Pass|
|Lifecycle/security|005 facts/008 cleanup/009 Monitor preserved;006 security-before-body;007 thin transport|Pass|
|Architecture|New inward annotation value module; existing concrete coordinator/clock, no adapter imports in Core|Pass|
|Backend neutrality|No new backend method or Basic type test; identical shared fixtures|Pass|
|Safety/installability|Guarded software-only fixtures, existing uv/dependencies/packages, no physical action|Pass|
|Scope/status|T001–T024 complete24/24; fresh final software/installed/artifact/privacy/Core/contract gates pass; completed evidence/progress/limits reconciled; Feature010 software-complete; implementation commit recorded in development_status.md, Features001–010 committed baseline and Phase1-incomplete status preserved; separately authorized pre-commit review/commit recorded in development_status.md|Pass|

No unresolved clarification or unjustified violation. Product-level rules do not change. Research decisions and rejected alternatives are in [research.md](research.md), exact public/persistence behavior in [contract](contracts/annotations.md).

## Project Structure

### Documentation (this feature)

spec.md, plan.md, research.md, data-model.md, contracts/annotations.md, quickstart.md, checklists/requirements.md and tasks.md under specs/010-client-annotations/. Current progress in docs/development_status.md; completed evidence newest-first in docs/development_history.md. No competing design document or new constitution.

### Implementation impact (Core/runtime/service/CLI, hardening, final tooling and fresh software verification complete)

- `core/src/dutchmate_core/model.py`, `evidence.py`: normalized immutable annotation/pending variants, union/materialization, unchanged old behavior.
- New `core/src/dutchmate_core/annotation.py`: request/receipt/rejection/prepared-access values and bounded admission helpers as needed; reuse existing MonitorClock/coordinator types, no new infrastructure abstraction.
- `core/src/dutchmate_core/adapters/sqlite_evidence.py`: pure v3 codec/charge, explicit v3 factories/dispatch, selected-codec retained Monitor pair checks and annotation-aware timestamp scans.
- `core/src/dutchmate_core/adapters/terminal_evidence.py`: strict expected1/2/3 read-only dispatch; `adapters/observation_runtime.py`: explicit v3/optional annotation access with existing per-runtime clock.
- `core/src/dutchmate_core/monitor.py`: narrow gated annotation append, old post-ACK Monitor publication preserved; `runtime.py`: optional transfer capability, synchronous admission, one owned insertion, rate history and seals/joins.
- New `apps/service/src/dutchmate_service/annotation_http.py`; existing app.py/http.py/evidence_http.py: exact route/readiness/strict body/projection/error and shared mutation ownership, no generic registry rewrite. Existing server/bootstrap need no new public contract.
- New `apps/cli/src/dutchmate_cli/annotation.py`; existing main.py/client.py/evidence.py: required annotate command, one request, closed receipt and single new evidence variant. No Core import/authoritative limiter in CLI.
- `pyproject.toml`: include actual annotation module in inward layer/adapters prohibition when created. Place application annotation values below runtime and above monitor; do not weaken existing contracts or add exemptions.
- New focused tests under existing core/tests/unit, core/tests/contract, core/tests/integration, apps/service/tests and apps/cli/tests, exact paths in tasks.md. Extend shared fakes only if indispensable; no production Enhanced behavior.
- Existing strict-union consumers/tests may need minimal exhaustive narrowing proven necessary by the new union. Inventory/report each such file; preserve runtime behavior until its explicitly scheduled new variant is implemented. No casts, Any broadening, weakened contracts or unrelated refactor.

**Structure Decision**: Extend existing concrete coordinator and ordinary journal. Keep normalized persisted values in model/evidence; annotation request/access values can depend on monitor capability types without a reverse import. A small private append-publication helper may be extracted only to preserve the same gate/post-ACK logic, not as a framework. Profile/normalized backend/acquisition contracts need no new capability or policy. Architecture is preserved; update architecture documentation only if an actual implemented relationship changes.

## Implementation Sequence and Validation Checkpoints

1. **Foundation group T001–T005**: record baseline/invariants/consumer inventory; RED/GREEN annotation pure values and v3 codecs; RED/GREEN explicit v3 journal/terminal compatibility. No live annotation composition/runtime/HTTP/CLI behavior. Focused checks during tasks, full gate at T005 because the shared evidence/persistence change is cross-cutting.
2. **US1 coordinator/runtime T006–T009**: RED/GREEN real-journal/backend-neutral insertion/timestamp/Monitor publication; RED/GREEN optional runtime admission/strong owner/limiter and old preparation compatibility. Production composition choosesv3 only here. Focused005/008/009 regressions.
3. **US1 service/CLI T010–T013**: RED/GREEN security-before-body/readiness/route/shared eight jobs, closed receipt/evidence variant and one thin command. End-to-end MVP includes active and confirmed-close terminal retrieval. Full gate at T013.
4. **US2 bounds/retention T014–T016**: additional deterministic byte/rate/charge/format/cursor/retention cross-product tests and minimal corrections only for demonstrated defects. Directly affected003/008/009 regressions; no separate full gate yet—this is part of the combined hardening checkpoint.
5. **US3 lifetime/security T017–T019**: cancellation/delivery loss/detach/autonomous stop/service sealing, post-segment assertion, cleanup uncertainty and private errors. Correct demonstrated defects only, preserve capture facts; full combined hardening gate at T019.
6. **Installed software evidence T020**: guarded outside-cwd wheel/sdist end-to-end annotate/retrieve/expiry/loss/error fixtures and existing007/008/009 installed regressions. No native/hardware acceptance selected.
7. **Final conformance/status T021–T023**: complete diff/Core/contracts/compatibility/artifact/privacy review, safe quickstart tests, mark only actually completed tasks, status/history reconciliation. At T023 evaluate actual Graphify trigger and, if needed, run one final code-only incremental update per tooling/skill rules; planning never triggers it. No premature updates during earlier groups.
8. **Fresh final T024**: full uv/import/diff gate, final installability/artifact review and marker reconciliation; rerun full gate after any corrective executable/contract change. Merely recording already-observed results follows AGENTS8.3 documentation consistency checks. Stop for separate commit authorization.

The **first implementation group is exactly T001–T005**. RED tasks authorize tests only and report actual failures without placeholder tests. Full gates are T005/T013/T019/T024, not every RED/GREEN task. Each includes `uv run ruff check .`, `uv run mypy .`, `uv run lint-imports`, `uv run pytest`, `git diff --check`; use RTK and uv with hardware/account guards. All required full gates must be GREEN before claiming their checkpoint. Focused regressions may already pass; do not invent defects or force artificial RED.

## Complexity Tracking

No violation. Explicit schema3 is required by the new closed evidence variant; bounded owner/rate state protects a genuine shared persistence boundary. Existing host clock/coordinator/worker/security/jobs suffice. No new dependency, backend method, Profile revision, port hierarchy, registry, persistent queue or extra reader/store.
