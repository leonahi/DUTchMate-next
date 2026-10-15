# Implementation Plan: Bounded Receive-Only Monitor

**Feature**: `009-receive-only-monitor` | **Date**: 2026-10-14 | **Git branch**: `main`
**Input**: [spec.md](spec.md). T001–T037 complete (37/37); all 37 implementation tasks are complete. Implementation and safe software acceptance are recorded in [current status](../../docs/development_status.md) and [history](../../docs/development_history.md); recorded T037 full gate: 5783 passed. Feature 009 is software-complete; Phase 1 and native/physical acceptance remain incomplete.

## Summary

Implemented one finite binary literal Monitor over the already owned active stream, Core-owned start boundary/matching/deadline/outcome and ordinary durable operation markers. The existing authenticated service, thin CLI and evidence projections include Monitor. The implementation preserves001–008 RX/lifecycle/security, explicit schema-v1 support/Profile-v1, and008 read-only terminal ownership. Explicit schema-v2 is required for operation evidence, with no migration or unrelated workflow.

## Technical Context

**Language/Version**: repository Python>=3.14,<3.15; observed baseline3.14.3.
**Primary Dependencies**: existing asyncio/sqlite3/base64/JSON, FastAPI/Uvicorn, Typer/HTTPX, pyserial behind Basic boundary. No new dependency or lockfile change was required.
**Storage**: existing SQLite journal; explicit v2 marker variants/new composition; unchanged default v1 factories/old record-v1 codecs and Profile-v1 TOML.
**Testing**: pytest/pytest-asyncio; injected clock/append gates; real temporary v1/v2 journal; identical Basic/Enhanced-shaped fixtures; guarded installed wheel/sdist processes.
**Target Platform**: established Linux/macOS POSIX software contract; native macOS evidence available. Windows actual commands remain unsupported; Linux/Windows/physical acceptance not automatically selected.
**Project Type**: modular monolith; inward Core and infrastructure, authenticated local HTTP service, thin Typer CLI.
**Performance Goals**: linear bounded literal matching, prefix state<=256 positions, one operation; observation1..4000ms and examined RX1..1048576; no retained RX window.
**Constraints**: condition1..256 bytes; request16384 bytes; service/CLI canonical JSON1048576 bytes independently, LF extra; old cursor1024,5s phase/10s HTTP and8 reads/8 mutations retained; one separate Monitor slot. No forced bound on submitted I/O/cleanup.
**Scale/Scope**: one current/last associated run per incarnation; Monitor active only. No catalogue, background result store, second RX/journal reader or framework abstraction.

## Constitution Check

The repository `.specify/memory/constitution.md` is an unpopulated scaffold, not a competing authority. Apply AGENTS/Core gates; assessed before research and rechecked after design:

| Gate | Design evidence | Result |
|---|---|---|
|Core/active scope|Finite receive-only literal Monitor, no TX/control/backend protocol|Pass|
|Ownership/order|Same journal gate/worker; atomic positive-ack boundary; owned settlement before close|Pass|
|Evidence/compatibility|Explicit v2 only; exact old codecs/policy/retrieval; normal retention and honest marker failures|Pass|
|Backend neutrality|Capability/provenance values, identical fixtures, no Basic assumption above adapter|Pass|
|Security/thin delivery|Same006 gate/007 transport; Core semantics, closed additive projections and exact bounds|Pass|
|Architecture|New monitor in existing inward application layer; actual modules covered by import contracts, no exemption|Pass|
|Installability/safety|Existing packages/uv/deps; guarded outside-cwd installs, no physical access|Pass|
|Scope/status|T001–T037 complete; native/physical acceptance pending, remaining Phase1 explicit, no Core rewrite|Pass|

No unjustified violation or unresolved decision. The original design check is retained here; implementation conformance was reviewed at T033 and safe software acceptance at T034. All 37 implementation tasks are complete; native/physical acceptance remains pending.

## Project Structure

### Documentation (this feature)

spec.md, plan.md, research.md, data-model.md, contracts/monitor.md, quickstart.md, checklists/requirements.md and tasks.md in `specs/009-receive-only-monitor/`.

### Implemented source changes (repository root)

- `core/src/dutchmate_core/model.py`, `evidence.py`: inward Monitor fact/operation record and pending values, additive unions.
- New `core/src/dutchmate_core/monitor.py`: request/report/rejections/clock capability, minimal matcher/committed coordinator.
- `core/src/dutchmate_core/runtime.py`: optional prepared capability, active admission, strong owners, seals/teardown.
- `core/src/dutchmate_core/adapters/sqlite_evidence.py`: additive pure v2 helpers/explicit factories/strict validation; same journal mechanics, preserve v1 entry points.
- `core/src/dutchmate_core/adapters/terminal_evidence.py`, `observation_runtime.py`: immutable expected format/read-only dispatch and live composition; new `adapters/monotonic_clock.py`.
- New `apps/service/src/dutchmate_service/monitor_http.py`; existing app/http/evidence_http provide route/projection/owned job/shutdown integration. The server implementation remains unchanged; existing stop hooks suffice.
- New `apps/cli/src/dutchmate_cli/monitor.py`; existing main/client/evidence additive command/wire projections only.
- `core/tests/unit`, `core/tests/contract`, `core/tests/integration`, `apps/service/tests`, `apps/cli/tests`: focused files named in tasks, preserve existing suites and physical/account guards.
- Root `pyproject.toml`: actual monitor module is included in the existing application layer/adapter prohibition; no boundary was weakened. No new package or dependency required.

**Structure Decision**: Existing packages and ownership boundaries suffice. Keep normalized marker values in model and v2 pure codec beside v1 to avoid model/application cycles or a speculative persistence framework. Acquisition remains unchanged; the recorder wrapper supplies the committed publication boundary without a broad refactor. Existing Ports-and-Adapters/package boundaries and Core architecture are unchanged, so no separate architecture-document rewrite is required.

## Implementation Sequence and Validation

The sequence below records the original task groups. T001–T037 are complete; the sequence below is historical. Detailed RED/GREEN counts and corrections belong in history.

1. Foundation T001–T005: capture governing/baseline evidence; RED/GREEN pure request/report/clock/rejection/matcher and operation marker/codec/charge values only. Stop before runtime/journal-v2 creation/routes.
2. RED/GREEN strict v2 journal/terminal compatibility and unchanged003 selectors; wire explicit version target without creating history/recovery behavior.
3. RED/GREEN committed coordinator/live composition and active runtime: positive start boundary, clock/matcher, single-owner admission, normal end markers and optional capability compatibility.
4. RED/GREEN authenticated service/result/error/bounded independent jobs and thin CLI; extend only two evidence wire variants. Validate US1 end-to-end MVP.
5. US2 boundary/quality regressions: deadline/byte ties, chunk/loss/segment edges, retention/cursors/binary/413; correct only demonstrated defects, full gate.
6. US3 ownership/failure regressions: submitted start/end races, cancelled waiters, detach/shutdown joins and permanent read-cleanup latch; preserve capture facts, full gate.
7. Guarded installed-process, privacy/security/backend-neutral acceptance and artifact metadata/import review; no real credential/hardware or unsupported native claim.
8. Complete feature diff/Core/spec/old-contract review; safe acceptance reconciliation, status/history, one Graphify code-only incremental update only if actual structural trigger, then fresh final uv/installability/diff gate. Separate authorization for any later commit.

Each RED checkpoint authorizes tests only. GREEN work is confined to the paired demonstrated requirements. Edge-case correction tasks make no production change if tests find no defect. Planning alone completed no implementation tasks; checkboxes now reflect only actually completed work. Required gate: `uv run ruff check .`, `uv run mypy .`, `uv run lint-imports`, `uv run pytest`, `git diff --check`; execute through RTK/uv with repository hardware guards. Focused checks precede broader gates. Final corrections require gate rerun.

## Complexity Tracking

No constitutional/Core/architecture violation. One host-clock external boundary and one committed recorder coordinator address concrete nondeterministic timing/order; explicit v2 is required by operation evidence. No extra package, registry framework, persistent pool or speculative future abstraction.
