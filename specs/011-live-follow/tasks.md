# Tasks: Receive-Only Live Follow

**Input**: [spec](spec.md), [plan](plan.md), [research](research.md),
[model](data-model.md), [contract](contracts/follow.md), [quickstart](quickstart.md).
**Status**: **24/24 tasks complete** (T001–T024); Feature011 software-complete; implementation commit recorded in development_status.md.
Completed evidence/progress/limits reconciled; architecture explanation remains accurate.
Recorded T0213444 focused/625 process passes and26 archives/10 installations audited.
T022 seven import contracts/docs/link/scope/diff checks pass; no new test/full gate.
T023 trigger met; one update:6095 nodes/20503 edges/254 communities, zero tokens.
Graph-health/zero-node limits remain recorded; no rerun at T024.
Fresh T024 8182 full passes, including625 guarded Follow/007–010 process cases; Ruff/mypy/import/diff and artifact/privacy review pass.
Final separately authorized pre-commit review/full/staged/installability/privacy verification passed without correction.
Feature011 committed; nothing pushed. Phase1 incomplete; no next slice or hardware authorized.
**Tests**: Explicitly required by FR-022. RED tasks author tests only; record real
failures and unexpected passes. GREEN tasks implement only the paired contracts.
**Authority**: Core, active011 artifacts, completed001–010 and current status.
No production code, new tests, native/physical acceptance or Graphify run is
authorized by this planning workflow.

## Format and validation rules

`- [ ] TNNN [P?] [USn?] Description with exact paths`.
[P] means disjoint test work may overlap after prerequisites, not automatic agent
delegation. Setup/foundation/final tasks have no story label. Each RED/GREEN pair
is a focused task; coherent **full-gate checkpoints areT005/T013/T019/T024**.
Use RTK and the uv environment, run changed tests and directly affected regressions,
and report skipped/unexecuted hardware checks honestly. A genuine cross-cutting
change can require a broader gate under AGENTS8.3; never weaken an explicit gate.

After each authorized task/group, record only actually observed results in
`docs/development_history.md`, reconcile current progress in
`docs/development_status.md` and this file, and stop at the user's boundary.
No automatic commit/push, next task group, Graphify or hardware access.

## Phase 1: Setup

- [x] T001 Inspect the committed001–010 baseline, relevant diffs/tests, Core§§5/8/14–18/22.2/23 and current status; record the011 protected-input/consumer inventory in `docs/development_history.md` and progress in `docs/development_status.md`. Inventory `core/src/dutchmate_core/monitor.py`'s four append paths, `runtime.py`'s prepare/read/teardown owners, `adapters/observation_runtime.py`, `apps/service/src/dutchmate_service/app.py`, `http.py`, `server.py`, `evidence_http.py`, `apps/cli/src/dutchmate_cli/client.py`, `main.py`, `evidence.py` and `pyproject.toml`; protect old codecs/charges/Profile/backend/acquisition/bootstrap/credential/finite-client behavior. Confirm the first checkpoint isT001–T005 and make no behavior change.

## Phase 2: Foundation — first implementation group ends here

- [x] T002 Author RED pure-value tests in `core/tests/unit/test_follow_values.py` for request/start/gap/batch/end/rejection values: exact session/counter validation including bool/MAX, closed reasons, immutable captured provenance, missed-range containment and known/unknown cutoff semantics per contract§§1–3. Core end facts contain no network-delivery position. No coordinator/runtime/composition/service/CLI changes.
- [x] T003 Implement only the pure values in new `core/src/dutchmate_core/follow.py` to makeT002 GREEN; reuse existing model/evidence values and preserve the evidence union/codecs. Add the actual module to the inward layer below monitor and adapter-forbidden set in `pyproject.toml`; no ignored imports, weakened contracts or speculative ports. Run focused tests/static/import checks.
- [x] T004 Author RED pure bounded-state/page-consumption tests in `core/tests/unit/test_follow_state.py`: one pending page, exact ordered record progression/all seven variants, expired gap before records, unchanged whole-prefix marker, read-position progression without a network-delivery claim, zero-record charged shortage, no-progress rejection, seal/discard/cutoff and idempotent close. Use existing EvidencePage fixtures; no live I/O/async coordinator/composition behavior.
- [x] T005 Implement only the bounded pure state/page logic in `core/src/dutchmate_core/follow.py` needed forT004 GREEN. RunT002/T004 and directly affected `core/tests/unit/test_evidence.py`, `test_evidence_access_values.py`, `test_monitor_values.py`, `test_annotation_values.py`; review diff/import boundaries and run the full foundation gate. Record evidence/progress and stop beforeT006; no live registration/runtime/service/CLI behavior.

**First implementation group: T001–T005 only.**
It establishes pure values/state and import coverage, ending before any live
Follow behavior. T006 is RED coordinator/real-journal integration authoring only.

## Phase 3: User Story 1 — Observe new evidence live (P1; MVP)

**Goal**: One live-tail subscriber through Core/service/CLI over the existing journal.
**Independent test**: Both backend shapes and a real temporaryv3 journal; compare
new RX/loss/Monitor/annotation frames with ordinary retrieval, exclude old records,
interrupt Follow and verify capture continues.

- [x] T006 [US1] Author RED coordinator/real-journal tests in `core/tests/contract/test_follow_recording.py` and `core/tests/integration/test_follow.py`: atomic actual-tail/current-provenance registration under the append gate, metadata-only empty[MAX,MAX) probe, append/start/cancel races, all four append ACK paths, ambiguous-ACK wake hints, no lost idle wakeup, bounded fresh-head pulls and exact all256 byte values/seven variants. Run identically against both backend fixture shapes with real temporaryv3 journals and concurrent Monitor/annotations; change `core/tests/fakes.py` only if indispensable. No production changes.
- [x] T007 [US1] Implement only the narrow coordinator registration/coalesced wake/pull integration needed forT006 GREEN in `core/src/dutchmate_core/monitor.py` and existing pure `follow.py`. Reuse the existing live reader/empty-range probe and gate order; no SQLite/schema/evidence/clock/backend change. Preserve ordinary publication, Monitor start/end direct paths and post-ACK timing; no network wait under the gate. RunT006 plus existing `core/tests/contract/test_monitor_recording.py`, `test_annotation_recording.py`, `test_sqlite_evidence_journal.py`, `core/tests/integration/test_monitor.py` and `test_annotations.py`. Runtime admission/composition remains out of scope.
- [x] T008 [US1] Author RED runtime/composition tests in `core/tests/contract/test_follow_runtime.py` and `core/tests/contract/test_observation_composition.py`: optional capability defaultNone/valid/malformed transfer, current ACTIVE session checks/rejection precedence, captured-generation revalidation, independent single subscriber, one pull, eight shared submitted-read leases/no idle lease, cancelled start/result cleanup, synchronous seal/wakeup, final cutoff and join-before-close, unchangedv1/v2 and explicitv3 preparation. No production changes.
- [x] T009 [US1] Implement only the runtime/optional transfer/composition behavior needed forT008 GREEN in `core/src/dutchmate_core/runtime.py` and `core/src/dutchmate_core/adapters/observation_runtime.py`, usingT007's coordinator. Strongly own submitted query/cleanup work, preserve008 uncertainty and release facts, and expose synchronous Follow sealing for detach/service stop before drain. No service/CLI behavior. RunT008/T006 plus `core/tests/contract/test_observation_runtime.py`, `test_evidence_access.py`, `test_monitor_runtime.py`, `test_annotation_runtime.py`, `core/tests/integration/test_observation_runtime.py`, `test_live_evidence_composition.py`.
- [x] T010 [US1] Author RED service tests in `apps/service/tests/test_follow_http.py` for the literal route/readiness selection, closed16KiB request/session bounds, all rejection/error mappings including20 JournalFailure kinds, strict five frame/seven record variants/provenance/gap projection, no-store/security-before-body, independent one Follow job vs eight mutation/eight read/one Monitor slots, pre-header oversize vs post-header terminal/EOF,1s heartbeat and5s send bound. Include actual guarded loopback streaming where ASGI transport buffers; no production edits.
- [x] T011 [US1] Implement onlyT010's service behavior in new `apps/service/src/dutchmate_service/follow_http.py` and existing `app.py`, `http.py`, with minimal `server.py` stop-latch wiring if necessary. Register strongly before admission; synchronously seal/wake Follow at request_stop before HTTP drain, independently of recorder lifetime. Reuse existing `evidence_http.py` projection helpers without changing old routes. RunT010 plus `apps/service/tests/test_service_http.py`, `test_service_runtime.py`, `test_service_process.py`, `test_evidence_http.py`, `test_evidence_reads.py`, `test_monitor_http.py`, `test_annotation_http.py`. No CLI behavior.
- [x] T012 [US1] Author RED thin-CLI tests in `apps/cli/tests/test_cli_follow.py`: exact command/required session/resource-free help and validation-before-credential; one credential/request; closed NDJSON/identity media, five frames/seven variants, exact sequence/gap validation,1MiB+LF framing under arbitrary chunk splits/multiple frames,10s handshake/5s complete-frame trickle deadline/no whole-session limit, incremental flush/no transcript, terminal exit0 vs malformed/EOF5, Ctrl-C130 and broken pipe. Preserve old finite transport/tests; no production edits.
- [x] T013 [US1] Implement onlyT012's narrow streaming command/validation in new `apps/cli/src/dutchmate_cli/follow.py` and existing `main.py`, `client.py`; reuse existing `evidence.py`/Monitor/annotation validators, no Core/service import, decoding/retry/reconnect or relaxed finite exchange. Verify the US1 end-to-end scenario through actual guarded loopback with both backends/real journal and concurrent Monitor/annotation/active retrieval. RunT012 plus existing CLI transport/command/evidence/Monitor/annotation suites and full US1 gate. Record evidence and stop at this coherent MVP checkpoint.

## Phase 4: User Story 2 — Recognize missed/undeliverable evidence (P2)

**Goal**: Bounded, honest live output under retention pressure and slow/malformed delivery.
**Independent test**: Pause a reader, evict unread records, resume with explicit gap;
compare coalesced retention facts and exact later bytes; oversized data never spins.

- [x] T014 [P] [US2] Add Core boundary/retention tests only in `core/tests/contract/test_follow_retention.py`: real journal/both shapes, minimum policies and fixed caps, eviction before/during/after materialization, repeated adjacent gaps, unchanged whole-prefix counts/timestamp domains, exact missed-range intersection, MAX head and no-progress/oversized-first-record termination, annotation/Monitor interleaving and no retention pinning. Run new tests plus directly affected003/008–010 Core tests; report already-GREEN cases and defer genuine fixes toT016.
- [x] T015 [P] [US2] Add delivery edge tests only in `apps/service/tests/test_follow_http.py` and `apps/cli/tests/test_cli_follow.py`: exact encoded cap/overflow, escaped Unicode/LF/CR/base64, all variants, oversized provenance/marker/record, duplicate/unknown/NaN/bool/wrong-order fields, split delimiters, partial EOF/extra terminal/trailing frames, identity-only encoding, heartbeat while query pending, trickle and send expiry, bounded accumulators/private diagnostics. Run new and affected006/007/008–010 delivery regressions; do not correct production yet.
- [x] T016 [US2] Correct only genuineT014/T015 defects in the affected `core/src/dutchmate_core/follow.py`, `monitor.py`, `runtime.py`, `apps/service/src/dutchmate_service/follow_http.py` or `apps/cli/src/dutchmate_cli/follow.py`/narrow existing consumers. Inventory every consumer actually affected, preserve old behavior and add focused evidence where needed. If no defect, record no-change. Run both edge suites and required003/008–010 journal/read/Monitor/annotation/service/CLI regressions. No schema/Profile/backend/refactor expansion; broader cross-cutting fixes require governing validation.

## Phase 5: User Story 3 — Independent subscriber lifetime (P3)

**Goal**: Cancellation and shutdown cannot orphan work, alter acquisition or deadlock drain.
**Independent test**: Race stop/cancel at each await while holding query/send gates;
observe exactly-once cleanup, no stale generation and continuing RX after client exit.

- [x] T017 [P] [US3] Author Core lifetime/race tests only in `core/tests/contract/test_follow_lifetime.py`: cancelled start before/after registration, pending/idle pull cancellation, reentrant pull, capacity exhaustion, detach vs append/Monitor/annotation/read, synchronous seal, final known/unknown cutoff, discarded prefetched tail vs offered position, source failure/stop precedence, close uncertainty, cleanup-latch preservation, old preparation and replacement-generation isolation. Prove joined submitted reads before close and no socket dependency; both backend shapes/real journals. Run new plus affected005/008–010 lifetime/read tests.
- [x] T018 [P] [US3] Author service lifetime/security tests only in `apps/service/tests/test_follow_lifetime.py`: client disappearance during admission/pull/send, stalled peer/frame deadline, slot ownership/release, stop before Uvicorn drain, pending-query heartbeats, terminal cutoff/EOF honesty, no-store on all paths and security-before-body after stop. Verify Monitor/annotations/ordinary reads remain independent; actual guarded loopback is required where buffering hides behavior. Run new plus006/008–010 shutdown/security regressions; no production edits.
- [x] T019 [US3] Correct only genuineT017/T018 ownership/lifetime defects in the demonstrated affected `core/src/dutchmate_core/runtime.py`, `monitor.py`, `follow.py`, `apps/service/src/dutchmate_service/app.py`, `http.py`, `server.py`, `follow_http.py` or narrow delivery consumers, with focused evidence/consumer inventory. Otherwise record no-change. RunT017/T018 and focused005/006/008/009/010 lifecycle/read-cleanup/security/Monitor/annotation regressions, then the full combined US2/US3 gate and final checkpoint diff review.

## Phase 6: Installed flows, final review and closure

- [x] T020 Add and execute guarded installed-process validation in `apps/cli/tests/test_cli_follow_process.py`: non-editable wheel/sdist outside checkout, both backend shapes and numeric IPv4/IPv6, actual incremental Follow/new exact bytes/Monitor/annotation/coexisting reads, retention gap, idle heartbeat, capacity/error/oversize, Ctrl-C/closed pipe/disconnect/stop. Reuse existing guarded builders; shared fixture changes only if indispensable and with inventory. Run existing `test_cli_process.py`, `test_cli_evidence_process.py`, `test_cli_monitor_process.py`, `test_cli_annotations_process.py`. No real account/serial/discovery/hardware access.
- [x] T021 Review the complete011 diff against Core, `specs/011-live-follow/spec.md`, `plan.md`, `data-model.md`, `contracts/follow.md`, this task list, completed003/005–010 contracts and `docs/development_status.md`. Inspect wheel/sdist module bytes/metadata/locked dependencies/private-artifact exclusions and finite transport/codec compatibility. Correct only genuine011 defects minimally with focused evidence and the required full-gate rerun. Reconcile `specs/011-live-follow/quickstart.md` only with actually executable guarded validation; no hardware or new scope.
- [x] T022 Reconcile only completed evidence/progress in `docs/development_status.md`, `docs/development_history.md` and011 artifacts; preserve committed001–010 and Phase1-incomplete status. Review Core§16 conformance and actual dependency/ownership relationships; update existing architecture explanation only if an implemented relationship changed, never alter Core rules or create a competing design document. Record native Linux/Windows, active-DUT, physical/electrical and Enhanced acceptance limits.
- [x] T023 Read `docs/agent_tooling.md` and `.codex/skills/graphify/SKILL.md`; evaluate final011 structural/shared-interface trigger against actual code. If triggered, perform **one code-only incremental Graphify update** now; previous feature runs do not satisfy this task. Keep generated output/backups/local tooling ignored/excluded, never read `graphify-out/graph.json` directly; if it stalls/fails stop/report without an unauthorized retry. Record actual outcome/limits in `docs/development_history.md` and current progress in `docs/development_status.md`. No earlier011 task runs Graphify.
- [x] T024 Run fresh final Ruff/mypy/import-linter/pytest/diff gate and non-editable wheel/sdist installability/compatibility/privacy review for the final011 tree, including guarded Follow and007–010 process suites. Review Core/contract/complete diff/artifact scope; correct genuine defects only with focused evidence and rerun full gate after any corrective executable/governing-contract change. Reconcile only completed markers in011 artifacts and `docs/development_status.md`/`docs/development_history.md`; documentation-only result recording uses consistency/diff checks. Report011 software readiness, Phase1 incompleteness, remaining native/physical/Enhanced limits and exact status next action. No commit/push/next slice/Graphify rerun/hardware; stop for separately authorized pre-commit review.

## Dependencies & Execution Order

- T001 → T002 RED → T003 GREEN → T004 RED → T005 GREEN/full foundation.
- T006 RED → T007 GREEN → T008 RED → T009 GREEN → T010 RED → T011 GREEN →
  T012 RED → T013 GREEN/full MVP; each depends onT005 and prior paired integration.
- T014 andT015 may run independently afterT013; both precedeT016.
- T017 andT018 may run independently afterT016; both precedeT019/full hardening.
- T020 → T021 → T022 → T023 → T024; all depend onT019.
- US2/US3 are independently executable acceptance suites against the US1 MVP;
  they harden existing semantics, not alternative feature implementations.
  Required baseline gap/lifetime/security behavior is already part of US1.

## Parallel Examples

**US1:** Coordinator contract and real-journal integration cases withinT006 can
be authored in disjoint files afterT005. Keep shared fake edits serialized.
GREEN integration tasks remain ordered.

**US2:** T014 Core retention tests andT015 delivery framing tests use different
files and may overlap afterT013. Both must report actual outcomes beforeT016.

**US3:** T017 Core lifetime tests andT018 service lifetime tests may overlap
afterT016. Shared process builders and production corrections remain serialized.
No parallel work is automatically launched by these examples.

## Requirement Coverage

| Requirements | Primary tasks / acceptance |
|---|---|
|FR-001–005 live start/exact records/no new storage|T001–T009, T013, T021|
|FR-006–010 slots/bounds/retention/explicit failure|T002–T005, T008–T016, T019|
|FR-011 all append paths/no timing change|T006–T007, T013–T014, T017|
|FR-012–015 ownership/cancel/seal/cutoff|T008–T011, T017–T020|
|FR-016–017 authenticated bounded streaming|T010–T011, T015, T018–T020|
|FR-018–020 thin CLI/interrupt/finite compatibility|T012–T013, T015, T020–T021|
|FR-021 compatibility|All GREEN tasks, T016/T019–T024|
|FR-022–024 evidence/limits/deferrals|All test/checkpoint tasks, T020–T024|

## Implementation Strategy and Full Gates

MVP first: T001–T005 foundation, thenT006–T013 one coherent live workflow.
Add boundary and lifetime hardening throughT019, installed review throughT022,
final toolingT023 and fresh readinessT024. **Authorization for a group never
implies authorization for the next group.**

AtT005/T013/T019/T024 run all commands through RTK/uv:

```bash
uv run ruff check .
uv run mypy .
uv run lint-imports
uv run pytest
git diff --check
```

Focused regression anchors (select directly affected tests; broader at checkpoints):
003 `core/tests/contract/test_sqlite_evidence_journal.py`,
`test_terminal_evidence_reader.py`, `core/tests/integration/test_sqlite_recovery.py`;
005 `core/tests/contract/test_observation_runtime.py` and
`core/tests/integration/test_observation_runtime.py`;
006 `apps/service/tests/test_service_http.py`, `test_service_runtime.py`,
`test_service_bootstrap.py`, `test_service_process.py`;
008 `core/tests/contract/test_evidence_access.py`,
`core/tests/integration/test_live_evidence_composition.py`,
`apps/service/tests/test_evidence_reads.py` and corresponding evidence HTTP/CLI;
009 existing monitor recording/runtime/integration/service/CLI/lifetime files;
010 corresponding annotation recording/runtime/retention/lifetime/integration/
service/CLI files. Preserve twenty journal error mappings/seven import contracts.

Planning completed no implementation/test execution. No task is marked complete
by specification quality review, research, prior feature validation or Graphify.
