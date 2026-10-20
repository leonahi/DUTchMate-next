# Tasks: Bounded Interact

**Input**: [spec](spec.md), [plan](plan.md), [research](research.md),
[model](data-model.md), [contract](contracts/interact.md), [guide](quickstart.md).
**Status**: T001–T030 complete (30/30). T030's fresh full gate, guarded installed
flows and final artifact/compatibility/privacy/Core review pass; no new defect or
production/test correction. Feature 012 is software-complete within the observed
macOS/arm64 scope; Phase 1 remains incomplete. Actual results, the initial cache
setup failure and remaining native/physical/Enhanced limits are in development
status/history. T030 stopped before commit. The subsequent separately authorized
final pre-commit review corrects one v4 timestamp invariant with six RED→GREEN
cases; final11,399-test gate and staged artifact/privacy checks pass. Implementation
committed as `Implement bounded interact`. No Graphify rerun, hardware/account
access, push or next slice. All task instructions below retain their original scope.
**Tests**: Explicitly required by FR-022. RED authors tests and records genuine
missing-feature failures, not collection errors; GREEN implements the paired scope.
Existing already-passing assertions remain evidence, never forced RED by weakening.
**Authority**: Core, completed001–011 and current status. No automatic execution,
commit/push, next group or hardware action is authorized by this task list.

## Format and Validation

`- [ ] TNNN [P?] [USn?] Description with file paths`. [P] means disjoint work
can overlap after prerequisites, not automatic agent delegation. All new module
boundaries receive root `pyproject.toml` import coverage when created, without
weakening rules. Per task run focused new/direct regressions/static checks.
Full coherent checkpoints: **T005/T019/T025/T030**; additional cross-cutting fixes
may trigger AGENTS8.3. Record observed results/current progress in
`docs/development_history.md` and `docs/development_status.md` after authorized
groups; never mark a task complete from planning alone.

## Phase 1: Setup

- [x] T001 Inspect Core and completed001–011/current status/git diff; verify the consumer/protected-input inventory in `specs/012-bounded-interact/plan.md` against `core/src/dutchmate_core/backend.py`, `acquisition.py`, `monitor.py`, `runtime.py`, Profile/persistence/Basic adapters and existing service/CLI validators. Record baseline, invariants and first-group boundary in `docs/development_history.md` and `docs/development_status.md`; no behavior change. Protect old codecs/charges/Profile values/constructors/API1/Monitor clocks/security/cleanup; confirm T001–T005 only.

## Phase 2: Foundation — First Implementation Group Ends Here

- [x] T002 Author RED pure-value tests in `core/tests/unit/test_interact_values.py` for `payload: bytes length1..4096`, `conditions: tuple count1..4, each bytes length1..256`, `timeout_ms: exact int1..4000`, `max_rx_bytes: exact int1..1048576`; bool/type/MAX/UUID/ref/clock validation, normalized write result known/unknown prefixes, not_submitted consistency, separate observation/overall facts and bounded audit failure list. Use contract§§1/2/4/5. No actual connection/write/Profile/schema behavior.
- [x] T003 Implement only T002 pure values in new `core/src/dutchmate_core/interact.py`, normalized optional writer/result declarations in `core/src/dutchmate_core/backend.py` and required pure record values in `core/src/dutchmate_core/model.py`. Preserve existing BackendConnection/BackendEvent/Profile constructors; no journal-union/codec integration yet. Add actual new module to inward layers/adapter-forbidden coverage in `pyproject.toml`; run focused values/model/static/import checks. No live writer or prepared access.
- [x] T004 Author RED pure bounded matcher/decision tests in `core/tests/unit/test_interact_state.py`: multiple literal overlap/chunk spans, first ending byte/request-index tie, loss resets, last-byte match, deadline equality/whole-chunk eligibility, empty initial window, provenance boundary, early-match-before-ACK, timeout-before-ACK, write-failure/stop precedence and final-decision immutability. Prefix state<=1024 bytes; `condition_index: exact int0..conditions.count-1`. No I/O/async coordinator tests.
- [x] T005 Implement only T004 pure matcher/state in `core/src/dutchmate_core/interact.py`; keep bounded prefixes/counters/positions and one frozen observation, no RX transcript/general matcher framework. Run T002/T004, `core/tests/unit/test_model.py`, `test_evidence.py`, `test_monitor_values.py`, `test_annotation_values.py`, `test_follow_values.py`, directly affected backend regressions/static/import checks, then full foundation gate. Review diff, record evidence/progress and stop beforeT006.

**Exact first group: T001–T005.** Pure values and matching/decision state only;
no Profile-v2 parsing, journal-v4 codecs, Basic write, Acquisition admission,
coordinator/runtime wiring, service/CLI or hardware behavior. T006 is RED only.

## Phase 3: US1 — One Exact Bounded Transaction (P1; MVP)

**Independent test**: Both backend shapes, real temporary journal and authenticated
service/CLI; inject eligible RX during pending ACK, verify exact payload/selected
condition/report/readback, one writer invocation and unchanged sole RX.

- [x] T006 [US1] Author RED Profile-v2 tests in new `core/tests/contract/test_interact_profile.py` and directly affected `core/tests/unit/test_profile_model.py`: distinct v2 values, exact004 closed TOML/error/size rules, TX defaultfalse/explicittrue, RX/recording true and Control/reconnect false, v1 constructors/rejections unchanged, immutable edits, Basic translation and zero resource access on resolution/version rejection. No production edits.
- [x] T007 [US1] Implement only T006 in `core/src/dutchmate_core/profile.py`, `adapters/toml_profile.py`, `adapters/basic_profile.py` and necessary profile-union annotations in `runtime.py`; retain old value constructors exactly and introduce distinct v2 types. Run new and existing004 Profile/005 attach composition regressions; no write/runtime Interact wiring yet.
- [x] T008 [US1] Author RED real-journal/schema/codec tests in new `core/tests/contract/test_interact_journal.py` and existing `core/tests/contract/test_sqlite_evidence_journal.py`: all three contract§5 kinds/metadata/BLOBs, exact legacy seven bytes/charges/factories, explicit4/terminal dispatch, host-only timestamps/zero RX charge, valid max-shape callback, retained-pair validation, corruption/mismatch categories and ambiguous ACK. Use temporary files only.
- [x] T009 [US1] Implement only T008 codecs/factories/union/retained-pair/terminal support and pure charge callback in `core/src/dutchmate_core/adapters/sqlite_evidence.py`, `adapters/terminal_evidence.py`, `evidence.py` and required model union points. Preserve default1/explicit2/3 and all20 failure kinds. Cover schema4 timestamp context and host-only endpoint skips. Run003/008–010 journal/terminal/retention/Monitor-pair/annotation regressions; composition still selects legacy3 untilT015.
- [x] T010 [US1] Author RED Basic write tests in new `core/tests/contract/test_basic_serial_write.py`: explicit opt-in/default RX-only, closed-handle1000 ms timeout configuration/effective provenance2, one write/all256 bytes, full/short/zero/malformed count, timeout after possible progress, positively classified disappearance, unknown failure, simultaneous read/write progress and defensive joined close. Assert no retry/flush/reset/cancel_write/settings mutation/discovery. Use serial-library fakes, no physical target.
- [x] T011 [US1] Implement only T010 optional writer in `core/src/dutchmate_core/adapters/basic_serial.py` and necessary write opt-in construction values in `adapters/basic_profile.py`. One strong writer worker; `status: acknowledged/partial/timeout/disconnected/failure`, null count on exception, no wire receipt claim. Preserve old constructor defaults/descriptors/provenance/open/read/close. Run new and existing002 adapter/normalized-backend regressions/static checks.
- [x] T012 [US1] Author RED connection-owner tests in new `core/tests/contract/test_acquisition_write.py`: synchronous one-slot submission/revalidation, capability vs policy-independent writer mechanics, zero second reader/open, cancellation-resistant strong write join, seal before close on explicit stop/natural disconnect/recording and transport failure, no audit dependency/deadlock and generation isolation. Exercise both fixtures identically, changing `core/tests/fakes.py` only for indispensable optional write behavior; defaults remain unchanged.
- [x] T013 [US1] Implement only T012 narrow `submit_uart_write` and every-path seal/join in `core/src/dutchmate_core/acquisition.py`. Retain physical owner/private connection; no public TX workflow or generic job abstraction. Join writer before connection close independently of audit; run new plus existing001/002/005 acquisition/termination/cancellation regressions.
- [x] T014 [US1] Author RED coordinator/runtime/composition tests in new `core/tests/contract/test_interact_recording.py`, `test_interact_runtime.py`, `core/tests/integration/test_interact.py` and existing `core/tests/contract/test_observation_composition.py`: intent ACK before synchronous write registration, early RX eligibility, busy lifetime, exact admission/preflight, ordering of every append path/Monitor clocks, independent observation/TX/audits, optional access defaults, Profile1→3/Profile2→4 and joined teardown. Both backend shapes/real journals; no production edits.
- [x] T015 [US1] Implement only T014 in `core/src/dutchmate_core/monitor.py`, `runtime.py`, `adapters/observation_runtime.py` and pure `interact.py` as needed. Prepared access optional; gate never held over write wait; share post-ACK publication without altering009 clocks/order; notify Follow on new attempts; capture generation/policy and register strong owners. Add actual dependency coverage in `pyproject.toml`. Run new plus005/008–011 recording/runtime/lifetime/composition regressions; no service/CLI behavior yet.
- [x] T016 [US1] Author RED authenticated/API2 tests in new `apps/service/tests/test_interact_http.py`, `test_api_versions.py` and directly affected evidence/Follow service tests: literal v2 allowlist/shared handlers, v1 unchanged/version rejection before action/query, Profile2 and ten evidence variants, security-before-body/no-store/private errors, request<=16384/detect16385, report<=1048576, one independent Interact job, cancelled delivery and stop seals. Verify existing slot capacities and real guarded loopback where ASGI buffering hides disconnects.
- [x] T017 [US1] Implement only T016 in new `apps/service/src/dutchmate_service/interact_http.py` and existing `app.py`, `http.py`, `evidence_http.py`, `follow_http.py`, with `server.py` stop wiring only if necessary. Explicit literal paths/version validators, no generic router/command framework. Preserve006 security/bootstrap and old shapes; strongly own/join Interact at request_stop before drain. Run new and006/008–011 security/HTTP/runtime/process regressions.
- [x] T018 [US1] Author RED thin CLI/version tests in new `apps/cli/tests/test_cli_interact.py`, `test_cli_api_versions.py` and affected evidence/Follow tests: resource-free help/default1, explicit2 paths/closed validators, local base64/bounds before credentials, one credential/request, required options, identity/refs/outcome/TX/observation/audit consistency, fixed private errors/413/10s deadline/interrupt, no polling/retry/detach. Preserve007–011 no-flag request/output behavior.
- [x] T019 [US1] Implement only T018 in new `apps/cli/src/dutchmate_cli/interact.py` and existing `main.py`, `client.py`, `evidence.py`, `follow.py`; version2 dispatch stays literal, default1 paths/validators unchanged. Validate/print one<=1048576-byte report plus LF, delivered-report exit0 even for failed outcome, no wire-success inference. Run US1 across actual authenticated fake-only service/both shapes/real journals with concurrent Monitor/Follow/annotation/readback, all directly affected CLI suites, then full MVP gate. Record and stop atT019.

## Phase 4: US2 — Honest ACK, Durability and Compatibility (P2)

**Independent test**: Run adversarial write/audit/retention/version cases against
the US1 MVP. They must never fabricate progress, downgrade a version or hide RX.

- [x] T020 [P] [US2] Add adversarial Core/real-journal tests in new `core/tests/contract/test_interact_retention.py` and `test_interact_audit.py`: prefix/unknown acceptance, intent ACK ambiguity prevents TX, TX/end independent ACK failures with self-contained end facts, eviction/unpaired pairs, minimum policy/exact charges/MAX/clock overflow, host/device timestamp domains and concurrent Monitor/annotations. Both shapes; run new plus003/009/010 regressions, record already-GREEN assertions honestly.
- [x] T021 [P] [US2] Add delivery/version edge tests in `apps/service/tests/test_api_versions.py`, `test_interact_http.py`, `apps/cli/tests/test_cli_api_versions.py`, `test_cli_interact.py`: legacy golden shapes/no downgrade, all ten variants/Follow framing, canonical base64/all bytes, duplicate/NaN/bool/unknown inputs, escapes/large provenance, exact caps/whole413, unavailable v2 on old service without retry and fixed error privacy. Run affected007–011 delivery regressions; no production corrections yet.
- [x] T022 [US2] Correct only demonstrated T020/T021 defects in the inventoried affected files from `specs/012-bounded-interact/plan.md`; record actual changed-consumer inventory in `docs/development_history.md`. Preserve old codecs/Profile/API1/clock/charges; no speculative refactor. Run both suites and directly affected persistence/version/HTTP/CLI regressions/static/import checks. If no defect, record no-change. Apply AGENTS8.3 full gate if corrective scope demands it.

## Phase 5: US3 — Cancel and Stop Without Orphaning Writes (P3)

**Mandatory regressions within T014/T023**: After early match/timeout/byte_limit,
later disconnect/origin reset/fallback failure before TX ACK still latches overall
termination, preserving frozen observation. T016/T021 additionally race Profile
path edits and replacement generations: version guard/preparation share one
resolved value and actual captured admission, never stale service status.

T014 must assert exact Monitor/Interact clock sample count/order from contract§3,
including Monitor start sample reuse, conditional end sampling and unchanged
no-Interact behavior. Malformed backend returns stay normalized report failures;
invalid application report/clock construction instead takes the joined500 path.

**Independent test**: Gate every submission/ACK/close and cancel/stop on both sides
of it. Prove zero pre-submission writes, one joined post-submission write, no
physical close before settlement and no journal close before audit.

- [x] T023 [P] [US3] Add Core lifetime/race tests in new `core/tests/contract/test_interact_lifetime.py`: cancel pending intent/after ACK/before registration/after registration/during write/audit, stop vs match/deadline, natural disconnect/recording failure, physical-close-before-audit ordering, origin reset, stale generations, slot retention, independent Monitor/Follow/annotations/read leases and permanent cleanup uncertainty. Both shapes/real journals; run005/008–011 lifetime regressions.
- [x] T024 [P] [US3] Add service/client lifetime tests in new `apps/service/tests/test_interact_lifetime.py` and existing `apps/cli/tests/test_cli_interact.py`: peer loss/HTTP timeout/SIGINT/pipe failure, registered-before-stop jobs, synchronous seals before Uvicorn drain, blocked write/audit with shutdown, no slot reuse/orphan/false clean marker, no client result synthesis/detach/retry. Use actual guarded loopback for disconnect/drain behavior; preserve006/009–011 lifetimes.
- [x] T025 [US3] Correct only demonstrated T023/T024 lifetime defects in the affected `core/src/dutchmate_core/acquisition.py`, `monitor.py`, `runtime.py`, `adapters/basic_serial.py` or narrow service/CLI Interact consumers. Otherwise record no-change. Run all US2/US3/new/direct lifecycle/security/cleanup regressions and full combined hardening gate; review complete ownership/Core conformance and record current progress/limits in status/history. No worker abandonment or contract weakening.

## Phase 6: Installed Acceptance and Closure

- [x] T026 Add/execute guarded non-editable wheel/sdist outside-cwd acceptance in new `apps/cli/tests/test_cli_interact_process.py`: both backend shapes/real journals/numeric IPv4+IPv6, exact TX/early match/multiple conditions, failures/audit expiry, API2 readback/Follow, concurrent old workflows, cancellation/service stop and v1 compatibility. Reuse established007–011 builders/physical-discovery-account guards; shared fixture edits require inventory. Run existing CLI observation/evidence/Monitor/annotation/Follow process suites. No real serial/account access.
- [x] T027 Review full012 diff against Core/active artifacts/completed001–011 and `docs/development_status.md`; audit wheel/sdist source bytes/metadata/RECORD/installed imports/private exclusions using established harnesses in `apps/cli/tests/test_cli_interact_process.py`. Correct genuine defects minimally with focused evidence and required gate reruns. Reconcile `specs/012-bounded-interact/quickstart.md` only to executable guarded flows; preserve explicit native/physical limits.
- [x] T028 Reconcile actual completed evidence/progress/tasks in `docs/development_status.md`, `docs/development_history.md` and012 artifacts; Phase1 remains incomplete. Review dependency/ownership changes against existing architecture explanation and update it only if actually changed. No Core rule change, new competing status/design or documentation of unimplemented behavior as complete.
- [x] T029 Read `docs/agent_tooling.md` and `.codex/skills/graphify/SKILL.md`; evaluate actual structural/shared-interface changes, then perform one code-only incremental Graphify update if triggered. Keep generated output/backups/local tooling ignored; never read graph.json directly. If failed/stalled, stop/report without automatic retry. Record actual result/limits in `docs/development_history.md` and `docs/development_status.md`. No earlier012 task rebuilds Graphify.
- [x] T030 Run fresh final Ruff/mypy/import-linter/pytest/diff gate and installed artifact/compatibility/privacy review for the final012 tree, including `apps/cli/tests/test_cli_interact_process.py` and007–011 process regressions. Review complete diff/Core/contract conformance; correct genuine defects with focused evidence and rerun required gates. Reconcile only observed completion markers in012 artifacts/status/history. Report software scope, remaining native/physical/Enhanced limits, no hardware actions, and stop before commit/push/next slice or Graphify rerun.

## Dependencies and Execution Order

- T001 → T002 RED → T003 GREEN → T004 RED → T005 GREEN/full foundation.
- T006→T007→T008→T009→T010→T011→T012→T013→T014→T015→T016→T017→T018→T019.
  Every even task here is RED, its following odd task GREEN; full MVP atT019.
- T020/T021 depend onT019, can overlap; both → T022.
- T023/T024 depend onT022, can overlap; both → T025/full hardening.
- T026→T027→T028→T029→T030, afterT025.
- US2/US3 are independently runnable acceptance/hardening suites over US1;
  baseline durability/cancellation/security already belong to MVP, never optional.

## Parallel Examples

US1: WithinT014, recording and runtime test authoring can use its separate files
afterT013; shared fixture changes serialized. GREEN tasks remain ordered.
US2: T020 Core tests andT021 delivery tests are disjoint afterT019.
US3: T023 Core lifetime andT024 delivery lifetime are disjoint afterT022.
No automatic agent launch is implied; shared production corrections stay serialized.

## Requirement Coverage

| Requirements | Primary tasks |
|---|---|
|FR-001/006–010 request/slot/boundary/matching/outcomes|T002–T005, T014–T019, T023–T025|
|FR-002/005 Profile/capability authorization|T006–T007, T012–T015, T020–T021|
|FR-003/004 normalized/Basic write|T002–T003, T010–T013, T020/T023|
|FR-011–013 exact evidence/ACK/schema|T008–T009, T014–T015, T020/T022|
|FR-014/016 explicit delivery/legacy compatibility|T016–T021, T026–T027|
|FR-015 ordering/coexistence|T014–T015, T019–T020, T023/T026|
|FR-017/018 cancellation/close/joins|T010–T015, T017, T023–T026|
|FR-019–021 security/thin CLI/bounds|T016–T019, T021/T024/T026|
|FR-022/023 validation/scope|All checkpoints, T026–T030|

## Strategy and Full Gates

30 tasks: setup1, foundation4, US1 fourteen, US2 three, US3 three, closure5.
Smallest first implementation increment isT001–T005; the functional MVP endsT019.
At **T005/T019/T025/T030** run through RTK:

```bash
uv run ruff check .
uv run mypy .
uv run lint-imports
uv run pytest
git diff --check
```

Within tasks use focused new/direct regressions; record failures/limits precisely.
No test validates physical UART wire/electrical/DUT receipt. Planned verification
is not executed evidence, and group completion never authorizes the next group.
