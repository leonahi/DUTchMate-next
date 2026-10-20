# Implementation Plan: Bounded Interact

**Branch**: `main` | **Feature**: `012-bounded-interact` | **Date**: 2026-10-18
**Spec**: [spec.md](spec.md) | **Contract**: [interact.md](contracts/interact.md)
**Status**: T001–T030 complete (30/30); Feature 012 is software-complete within
the observed macOS/arm64 scope. Phase 1 remains incomplete. Subsequent separately
authorized pre-commit review/implementation commit are complete.
Current progress belongs to [development status](../../docs/development_status.md);
observed task evidence belongs to [history](../../docs/development_history.md).
Latest executed full gate: final pre-commit11,399 passes after one narrow v4
invariant correction; staged artifact/installability/privacy checks also pass.

## Summary

One exact-byte transaction through the existing connection/recorder/runtime,
authenticated service and thin CLI. Commit intent before submitting one write;
observe existing RX from intent+1, including during write. Separate backend
acceptance, observation, overall outcome and audit ACKs. One fail-fast slot spans
the whole transaction. Explicit Profile2/journal4/API2 preserve legacy behavior.
Reuse the concrete coordinator and Acquisition ownership; no generic framework.
Decisions/alternatives: [research.md](research.md). No unresolved design decisions.

## Technical Context

**Language/Version**: Python >=3.14,<3.15; repository3.14 and existing uv lock.
**Dependencies**: Existing pyserial3.5, SQLite stdlib, asyncio, FastAPI/Starlette,
Uvicorn, Typer; pytest/mypy/Ruff/import-linter. No dependency/lock change made.
**Storage**: Existing single-worker three-table SQLite; explicit4 only for
Profile2 composition; old1/2/3 factories/codecs unchanged.
**Testing**: Hardware-free unit/contract/integration tests, real temporary journals,
Basic library fakes and minimal Enhanced-shaped fixture; guarded actual loopback
and non-editable wheel/sdist outside-cwd acceptance.
**Target Platform**: Existing POSIX service/CLI; native macOS baseline. Actual
Windows CLI unsupported; no new OS/driver/hardware support claim.
**Project Type**: Modular monolith; Core plus thin service/CLI packages.
**Performance Goals**: <=4096 TX bytes, <=1024 condition bytes, <=1MiB examined RX,
<=4s observation, configured1s write wait, one transaction.
**Constraints**: One continuous RX path; no gate across write/network wait;
bounded owners and honest ACKs, no hard OS/journal/join deadline.
**Scale/Scope**: One owned connection, concurrent existing read-only workflows;
no TX-only command, catalogue, Console or streaming input.

## Constitution Check

The constitution is an unfilled scaffold, adding no authority; do not edit it.
The table records planning-time checks, not current implementation progress.

| Gate | Before research | After design |
|---|---|---|
|Core/Phase1 scope|Pass|No product rule change or deferred mechanics|
|Owner/inward dependencies|Pass|Acquisition owns writer; CLI HTTP-only|
|Policy/capability|Pass|Human Profile2 opt-in, physical capability separate|
|Evidence/compatibility|Pass|Explicit4/2 dispatch; protected old codecs/surfaces|
|Bounds/joins|Pass|One slot, natural/explicit close join writes|
|Lean structure|Pass|Concrete integration, no generic operation framework|
|Validation/safety|Pass|Defined gates; design-only work at that checkpoint|

No exemption/contract weakening needed. API2 exists because old validators are
closed; use literal allowlists/shared handlers, not a parallel implementation.

## Project Structure

Feature artifacts: spec, plan, research, data-model, one contract, quickstart,
quality checklist and tasks. No separate design/architecture document.

Implemented consumer inventory reconciled at T028:

| Area | Paths under existing package source directories |
|---|---|
|Pure values|`core/src/dutchmate_core/{backend.py,model.py,profile.py}`, new `interact.py`|
|Connection owner|`core/src/dutchmate_core/acquisition.py`, `adapters/basic_serial.py`|
|Commit/operation ownership|`core/src/dutchmate_core/{monitor.py,runtime.py}`|
|Profile/composition|`core/src/dutchmate_core/adapters/{toml_profile.py,basic_profile.py,observation_runtime.py}`|
|Persistence/terminal|`core/src/dutchmate_core/adapters/sqlite_evidence.py`, `evidence.py` and model union; existing `terminal_evidence.py` selected-version dispatch reused unchanged|
|Service|`apps/service/src/dutchmate_service/{app.py,http.py,evidence_http.py,follow_http.py}`, new `interact_http.py`; existing `server.py` stop/drain wiring reused unchanged|
|CLI|`apps/cli/src/dutchmate_cli/{main.py,client.py,evidence.py,follow.py}`, new `interact.py`|
|Import coverage|Root `pyproject.toml` covers `interact` and `profile` in existing inward contracts; no exemptions or dependency/lock change|
|Follow record union|`core/src/dutchmate_core/follow.py`: separately authorized three-type v4 union extension; existing Follow workflow reused|
|Tests/docs|Existing package test directories; status/history and 012 artifacts; existing architecture explanation remains accurate and unchanged|

`interact.py` holds pure values/matching/state, depending inward on model/backend/
evidence. Existing `monitor.py` holds narrow commit/publication integration;
runtime holds optional prepared access/generation lifetime. Preserve Monitor
implementation/clocks; no broad coordinator extraction/rename. No extra clock,
store or port beyond the actual optional UART write boundary.

## Implementation Groups and Acceptance

1. **T001–T005, pure foundation**: Inventory/protect001–011. RED/GREEN normalized
   write/Interact values and bounded multi-literal state; import coverage. Full
   foundation gate. Stop before Profile/schema/adapter/live integration changes.
2. **T006–T019, US1 transaction**: Paired RED/GREEN Profile2, journal4, Basic writer,
   Acquisition admission/close, coordinator/runtime, API2 and CLI. Verify exact
   intent-before-write, early RX, independent ACKs and one reader. Focused checks
   per pair, full MVP gate atT019.
3. **T020–T022, US2 evidence/compatibility**: Adversarial ACK/retention/charge/version
   tests; correct demonstrated defects only with consumer inventory. Full gate
   atT025 unless a corrective cross-cutting change independently triggers AGENTS8.3.
4. **T023–T025, US3 lifetime**: Cancellation at every await, natural failures,
   detach/HTTP drain and join ordering. Full combined hardening gate atT025.
5. **T026–T027, installed acceptance/review**: Guarded real authenticated loopback,
   both backend shapes/IPv4+IPv6, non-editable wheel/sdist outside checkout; old
   installed command regressions and artifact/metadata/private-file review.
6. **T028–T030, closure**: Docs from observed results, one code-only Graphify update
   if structural trigger met, fresh final full gate/artifact review. Stop before
   commit/push/next slice/hardware.

Critical invariants: no backend call before positive intent ACK; exactly one
registered write even after cancellation; no write await under append gate;
natural and explicit Acquisition close join writers before physical close;
runtime audit joins before recorder close; unknown counts stay null; frozen
observation unchanged; no unversioned legacy projection change.

### Protected Compatibility

- Profile-v1 values/parser/defaults/error precedence and old Basic constructor,
  descriptor/provenance/open/read behavior.
- v1/v2/v3 bytes/charges/factories, selected-version/terminal validation.
- API-v1 old routes/shapes, finite transport limits and no-flag CLI; seven old
  evidence projections; Monitor clock/ACK behavior, annotations and Follow gaps.
-005 terminal facts,008 permanent uncertainty,006 security/bootstrap, one reader,
  dependencies/locks, package boundaries and hardware exclusion.

### Validation Checkpoints

AtT005/T019/T025/T030 run through RTK: `uv run ruff check .`, `uv run mypy .`,
`uv run lint-imports`, `uv run pytest`, `git diff --check`. Within pairs use new
tests/direct regressions and targeted static checks. Never weaken gates/contracts.
Actual guarded installed-process paths are required; infrastructure failure is
not passing acceptance. New source boundaries get import coverage immediately.

### Observed Implementation and Software Closure

T001–T027 implement and verify the bounded transaction described above. T023's
two backend-shape failures were one pre-registration cancellation gap, corrected
at T025 in runtime.py. T027's four new regressions expose and verify correction
of one v4 fact-validation gap in interact.py. T020/T021/T024 assertions already
GREEN are recorded as such; T022 required no production correction.

T026 executes 192 installed Interact scenarios plus 625 legacy CLI process cases.
T027 adds five artifact audits and four Core regressions; its final full gate
passes 11,393 tests, including all 197 installed Interact/artifact cases and the
625 legacy process cases. The intermediate standalone T027 installed run is not
final acceptance evidence. See history for actual commands and diagnostics.

T028 reconciles those observed records and reviews the existing architecture
explanation against implemented dependencies/ownership. The explanation remains
accurate: the optional writer and private operation owners stay within the
established Core/service/CLI roles and inward dependency boundaries. No architecture
explanation, Core rule, contract, production, test or dependency change is made
at T028. The consumer inventory above records actual edits and reused consumers.

T029's actual tooling result/limits remain in status/history; T030 does not rerun
Graphify. T030's fresh full gate passes 11,393 tests with zero failures/errors/skips,
including all 197 Interact/artifact and 625 legacy process cases. Five fresh artifact
audits also pass separately. Complete diff/Core/contract/compatibility/privacy review
finds no new defect; production/tests/dependencies and the existing architecture
explanation remain unchanged. The initial incomplete-cache setup failure and final
populated-offline-cache run are distinguished in history. At T030, Feature 012 was
software-complete and uncommitted. Phase 1 remains incomplete; native Linux/Windows,
physical UART/DUT, safe-open/electrical and Enhanced acceptance remain outstanding.
T030 stopped before commit. The subsequent separately authorized pre-commit review
finds a self-contained v4-end timestamp check incorrectly conditional on a retained
start. Remove that condition in sqlite_evidence.py only; six journal regressions
cover append rollback, writer reopen and read-only terminal open on both shapes.
All780 focused checks and a fresh11,399-test full gate pass. Refreshed independent
287-blob index export/five artifact audits pass. No legacy codec/charge/Profile/API1,
clock, ownership, dependency or architecture change. Implementation committed as
`Implement bounded interact`; nothing pushed, no Graphify/hardware/accounts or next slice.
