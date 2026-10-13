# Tasks: Bounded Evidence Retrieval

**Input**: [spec](spec.md), [plan](plan.md), [research](research.md),
[data model](data-model.md), [contract](contracts/evidence-retrieval.md),
[quickstart](quickstart.md). Feature `008-evidence-retrieval`; Git remains `main`.
**Status**: T001–T035 completed; final software gate/diff/installability review passed.
Full3889 passed; Feature008 software-complete, final pre-commit review passed.
Implementation: `Implement evidence retrieval` (Git revision `:/^Implement evidence retrieval`).
Native Linux/Windows/active-DUT/physical acceptance remains unexecuted; Phase1 incomplete.
**Tests**: Required by FR-027–030; meaningful focused RED before new behavior/fixes,
then GREEN and regression gates. Existing passing003 semantics need no artificial RED.
**Organization**: Story increments share foundation and remain independently testable.

## Format and Path Conventions

`- [ ] Tnnn [P?] [USn?] description with exact paths`. [P] means independent file
work at the stated dependency checkpoint; no automatic delegation/authorization.
Paths are relative to repository root. New paths are created only by their tasks.
All tasks obey Core/AGENTS.md and preserve003/005–007/schema-v1/Profile-v1.
For each completed authorized group, run focused checks then required full gate,
review diff and update docs/development_status.md and docs/development_history.md
with actual evidence. Never claim unexecuted hardware/platform validation.

## Phase 1: Setup

**Purpose**: Establish accepted baseline, scope and safe test execution.

- [x] T001 Read docs/project_context_core.md §§14–18/22–23, docs/development_status.md, specs/008-evidence-retrieval/{spec.md,plan.md,contracts/evidence-retrieval.md} and completed003/005–007 contracts; inspect Git status/diff/HEAD and affected code/tests; capture protected schema/Profile/old-contract baseline, run existing full uv gate and verify default parent/child test guards do not access hardware or real credentials. Record baseline and touched invariants in docs/development_history.md; do not implement retrieval.

## Phase 2: Foundational — First Implementation Group T001–T005

**Purpose**: Correct exception transport and establish only the pure read boundary.
**Independent Test**: Sync/async exception transport and constrained pure values pass;
old003 constructor/categories and all completed baseline behavior remain intact.

- [x] T002 Demonstrate JournalFailure transport failure through synchronous and asynchronous generator context managers in new core/tests/unit/test_evidence_failures.py; assert constructor/category/message/fact compatibility, read-only operation/kind/detail, writable traceback/cause/context/notes and preservation of the original normalized failure. Record genuine RED before production changes.
- [x] T003 Correct only the demonstrated frozen/slotted JournalFailure transport defect in core/src/dutchmate_core/evidence.py with an ordinary sealed exception; preserve existing constructor(operation,kind,detail), validations/categories/message and read-only facts. Run T002 GREEN and existing003 failure/SQLite regressions; do not change codecs/schema/policy or other exception contracts.
- [x] T004 Add meaningful constrained read-boundary tests in new core/tests/unit/test_evidence_access_values.py for core/src/dutchmate_core/evidence_access.py: "Immutable session_id/policy; live_reader:EvidenceReadPort-or-null; terminal_opener:async callable-or-null. At least one usable read capability when supplied. No filesystem/SQLite/framework fields." Test RunEvidencePage identities/page, EvidenceReadRejected kinds "no_associated_session/session_not_associated/read_unavailable/source_changed/read_capacity", EvidenceSourceOpenFailure "primary:JournalFailure-or-EvidenceReadRejected and reader_close_confirmed:exact bool", sealed facts/ordinary exception transport and live-vs-owned-terminal port surfaces. Record RED; do not test fake runtime implementation.
- [x] T005 Implement only pure values/ports/failures in new core/src/dutchmate_core/evidence_access.py matching data-model.md/contract §1: live session_id/policy/resolve_record/retrieve without writes/close; OwnedEvidenceReadPort adds terminal close; optional capability tuple and immutable RunEvidencePage/normalized failures. Run T002/T004 GREEN, full uv gate and diff/architecture review; record results in docs/development_status.md and docs/development_history.md. Stop after T005; no runtime association/read methods, terminal adapter, service route or CLI retrieval behavior yet.

**Checkpoint**: First group is exactly T001–T005. Do not continue to T006 without
explicit authorization. Foundation alone does not deliver user-visible retrieval.

## Phase 3: US1 — Inspect a Known Active Session (P1; MVP)

**Goal**: Authenticated individual/page retrieval while the existing capture continues.
**Independent Test**: Known explicit session, temporary SQLite, actual authentication,
all256 UART bytes and identical Basic/Enhanced-shaped fixture assertions; one RX/gate.

### Core tests and implementation

- [x] T006 [P] [US1] Add RED live contract/race tests in new core/tests/contract/test_evidence_access.py: optional prepared-access compatibility/matching session-policy, no-run/pending/unavailable/mismatch, correct owner loop, atomic Core admission, new-attach replacement vs rejected attach, pinned reads, eight-lease capacity, waiter cancellation and seal/join-before-recorder-close without holding lifecycle lock. Verify no second RX/active database connection and unchanged RuntimeStatus/attach predicates.
- [x] T007 [P] [US1] Add RED real-journal integration scenarios in new core/tests/integration/test_evidence_access.py using existing Basic and Enhanced-shaped fixtures identically: idle/between-operation RX, empty pre-segment read, ordered reference/page selection and exact all256 bytes/NUL/non-UTF8/CRLF with reported provenance. Guards reject hardware access; fixtures exercise capability differences without emulation.
- [x] T008 [US1] Implement optional PreparedObservationRun.evidence_access and runtime association/read methods in core/src/dutchmate_core/runtime.py; match session/policy, publish one pending/live slot, pin private owned read tasks before first await, reject unsupported/mismatched/over-capacity reads and shield/join cancellation. Add seal/join after acquisition settlement and before recorder close, retaining existing lifecycle facts; terminal remains unavailable without an opener. Run T006/T007 GREEN.
- [x] T009 [US1] Supply narrowed live read access from the existing journal in core/src/dutchmate_core/adapters/observation_runtime.py; use existing003 gate/worker without another active SQLite connection or recorder ownership. Keep optional terminal_opener null until US2; old preparation callers stay valid. Verify actual composition live-read integration, append/retention/close serialization and unchanged005 suites.

### Service tests and implementation

- [x] T010 [US1] Add RED route/wire/security tests in new apps/service/tests/test_evidence_http.py for contract §§4–7: exact POST bodies/literal routes, existing006 auth/browser gates before body/source work, actual body16384+1 detection, "1..256 UTF-8 bytes, no NUL; exact string, no normalization", "exact integer0..9223372036854775807, not bool", "both null or both exact integers0..9223372036854775807 with start<=end", "exact integer1..4096, not bool; also no greater than SessionPolicy ceiling", "exact integer1..1048576, not bool; also no greater than SessionPolicy ceiling", "null or1..1024 ASCII bytes, canonical unpadded base64url token". Cover exact source/code/status pairs, closed schemas, cursor encoding, all record variants/base64/provenance/markers and complete bounded output; no terminal open needed.
- [x] T011 [US1] Implement apps/service/src/dutchmate_service/evidence_http.py and additive apps/service/src/dutchmate_service/{app.py,http.py} routes/projections/cursor/error mapping and eight separately registered owned read jobs. Reuse006 public provenance projection and literal security/media gates; canonical whole-envelope1048576-byte encoder with bound+1 detection/base64 preflight; authenticate before admission, no path/DB input, no page trimming/retry, no schema or mutation-registry changes. Run T010 GREEN and existing006 regressions.

### CLI tests and implementation

- [x] T012 [US1] Add RED grammar/input/transport/wire/output tests in new apps/cli/tests/test_cli_evidence.py: exact evidence record/page flags, required session/sequence/budgets, paired range/nulls, bounded lexical cursor, resource-free help/no-command, repeated valued options and fixed private local/remote exits. Apply the exact T010 input constraints with lexical-only input token check; assert one fixed authenticated request/no Core imports/auto-status/pages. Validate canonical standard base64, closed evidence wire and "Service UTF-8 JSON <=1048576 bytes; CLI JSON <=1048576 bytes plus one LF" without recomputing003 facts; preserve old007 behavior.
- [x] T013 [US1] Implement new apps/cli/src/dutchmate_cli/evidence.py and additive apps/cli/src/dutchmate_cli/{main.py,client.py} group/commands/closed-wire validation. Reuse private finite007 HTTP/credential/output mechanics with separate new reply/error validator; preserve original007 exchange seam/error pairs,10s total/5s phases, canonical JSON+LF, valid200 exit0/recognized rejection exit4 and private local receipt behavior. Run T012 GREEN and old007 regressions.
- [x] T014 [US1] Validate active Core→actual-auth service→thin CLI flows in core/tests/integration/test_evidence_access.py, apps/service/tests/test_evidence_http.py and apps/cli/tests/test_cli_evidence.py; review all US1 races/privacy/backend-neutral checks and full gate. Record active MVP results/remaining terminal scope in docs/development_status.md and docs/development_history.md; no terminal fallback or later story by implication.

**Checkpoint**: US1 is independently usable for active capture; terminal reads explicitly
unavailable until US2. Existing status remains the only separately requested identity report.

## Phase 4: US2 — Inspect the Last Terminal Run (P2)

**Goal**: Read the last associated safely closed journal without retaining/reopening capture.
**Independent Test**: Closed writer, no FD/connection held in target, one query-only
read transaction per query, unchanged database, positive close and explicit uncertainty.

- [x] T015 [US2] Add RED read-only adapter tests in new core/tests/contract/test_terminal_evidence_reader.py: native identity before/after open, expected session/exact policy, schema/record/provenance/retention invariants, mode=ro/cache=private/query_only verified, one read transaction/full validation, forbidden003 writable open/recovery/create/chmod/repair, no writer/FD retained, missing/changed/corrupt/incompatible/dirty-source mapping and cancellation-resilient open/read/close including partial-open cleanup certainty. Capture identity failure alone must not fail otherwise valid capture.
- [x] T016 [US2] Implement new core/src/dutchmate_core/adapters/terminal_evidence.py with immutable private resolved-path/native-device-inode/session/policy target and per-request owned reader/worker. Reuse pure helpers in core/src/dutchmate_core/adapters/sqlite_evidence.py with minimal extraction only if needed, preserving003 behavior/codecs; normalize partial-open failure with real close certainty, primary precedence and close-only report rejection. Run T015 GREEN; no recovery/writable fallback/immutable/nolock/persistent pool.
- [x] T017 [US2] Add RED terminal association/cleanup tests in core/tests/contract/test_evidence_access.py and core/tests/integration/test_evidence_access.py: detach/autonomous terminal/known failed-preparation session, unallocated session, optional target absent, recorder-close unconfirmed, physical-release unconfirmed with recorder closed, source replacement and already pinned old reads. Assert cleanup latch seals before slot release, primary error preserved, unexpected opener resource uncertainty stays dirty and neither RuntimeStatus nor attach eligibility is rewritten.
- [x] T018 [US2] Wire captured terminal target/optional PreparationFailure.terminal_evidence_access in core/src/dutchmate_core/adapters/observation_runtime.py and core/src/dutchmate_core/runtime.py. Release all live association references at terminal publication, open only after owner_settled AND recorder_close_confirmed; retain live-only access when native target capture fails, no artifact discovery. Latch runtime.evidence_read_cleanup_confirmed false on unconfirmed terminal/partial-open cleanup before lease release; add positive read-cleanup conjunction to apps/service/src/dutchmate_service/{app.py,server.py} final marker plumbing without modifying capture/attach facts. Run T017 GREEN.
- [x] T019 [US2] Verify active+terminal authenticated service/CLI integration in core/tests/integration/test_evidence_access.py and apps/service/tests/test_evidence_http.py, both backend fixtures and existing003/005–007 regressions/full gate. Record terminal read-only/uncertainty evidence in docs/development_status.md and docs/development_history.md; no restart browsing/physical acceptance claim.

## Phase 5: US3 — Traverse a Fixed Snapshot Honestly (P3)

**Goal**: Preserve003 outcomes/cursors/retention exactly under finite binary delivery.
**Independent Test**: Append/evict between continuations; full outcome/marker/order
projection and explicit whole-report overflow, independent record/charged/wire limits.

- [x] T020 [P] [US3] Extend shared tests in core/tests/contract/test_evidence_access.py and core/tests/integration/test_evidence_access.py against both fixtures: sequence MAX not_found, empty ranges, complete/partial/expired/not_found, never-existent suffix, marker domains, append beyond snapshot, eviction across continuation, changing page budgets, policy rejection and zero-record byte-shortage with unchanged next position/required charge. Use003 results as authority; record no defect if existing semantics pass, never manufacture a production change.
- [x] T021 [P] [US3] Extend apps/service/tests/test_evidence_http.py with canonical cursor key order/version/UTF-8/base64url/padding/duplicate/nonfinite/session/range/snapshot rejection and transport boundaries. Quote "Accumulate at most1048577 raw/encoded bytes for overflow detection"; test standard-base64 pad bits/all256 bytes, loss "overflow|other_observed_loss", segment reasons "explicit_stop|disconnected|timestamp_origin_reset|recording_failure|transport_failure", all provenance/retention fields, independent wire/policy limits and irreducible record/metadata whole413 rejection with no rewritten cursor/split/omission/refetch.
- [x] T022 [US3] Correct only demonstrated T020/T021 defects in core/src/dutchmate_core/{evidence_access.py,runtime.py}, core/src/dutchmate_core/adapters/{sqlite_evidence.py,terminal_evidence.py} and apps/service/src/dutchmate_service/evidence_http.py as applicable; preserve003 fixed snapshots/outcome/zero-page/schema/policy. If no defect, record that result in docs/development_history.md without changing production code; rerun affected regressions.
- [x] T023 [US3] Extend apps/cli/tests/test_cli_evidence.py for canonical cursor response validation versus lexical input check, binary/provenance/marker/order round trip, every valid outcome exit0, corruption/overflow private invalid_response5, remote413 exit4 and explicit smaller-budget continuation. Apply "Service UTF-8 JSON <=1048576 bytes; CLI JSON <=1048576 bytes plus one LF" and "Accumulate at most1048577 raw/encoded bytes for overflow detection"; no outcome/charge/domain recomputation or auto-pagination.
- [x] T024 [US3] Correct only demonstrated T023 defects in apps/cli/src/dutchmate_cli/{evidence.py,client.py,main.py}; preserve old007 validators/receipt/closed-pipe behavior and fixed bounds. If no defect, record in docs/development_history.md without production change; run focused CLI/old007 regressions.
- [x] T025 [US3] Run active/terminal snapshot/eviction/binary/bounds/error suites plus full gate; review exact003 projections, all declared JournalFailure mappings and no schema/Profile changes using specs/008-evidence-retrieval/contracts/evidence-retrieval.md. Record honest US3 results in docs/development_status.md and docs/development_history.md.

## Phase 6: US4 — Receive Finite Private Delivery (P3)

**Goal**: Bound independently owned reads, preserve privacy and verify installed delivery.
**Independent Test**: Actual guarded native loopback/entries plus deterministic
shutdown/cancellation/cleanup races without hardware, queues or falsely clean markers.

- [x] T026 [US4] Add RED read-ownership/shutdown tests in new apps/service/tests/test_evidence_reads.py and extend core/tests/contract/test_evidence_access.py: eight reads separately from eight mutations, no queued admission/public history, service-registered-before-Core replacement, waiter loss, worker/open/close/retention/detach/new-attach races and shutdown seal/join-before-final-detach. Assert "runtime.evidence_read_cleanup_confirmed starts true, is false permanently after unconfirmed terminal/partial-open cleanup" and admission closes before failed slot release; already pinned work settles, no retry/reset or falsely clean marker.
- [x] T027 [US4] Correct/complete demonstrated ownership/latch/shutdown gaps in core/src/dutchmate_core/runtime.py and apps/service/src/dutchmate_service/{app.py,server.py}; preserve lifecycle-lock scope, positive006 cleanup conjunction, no forced submitted-worker abandonment/new Core deadline. Run T026 GREEN and old005/006 shutdown tests; record no code change if coverage demonstrates no gap.
- [x] T028 [US4] Add guarded installed-process coverage in new apps/cli/tests/test_cli_evidence_process.py, reusing existing process fixtures with changes only where required: fresh wheel/sdist installs/outside-cwd entry/imports, actual IPv4/IPv6 auth, fake-DUT active/terminal all256-byte evidence, known-session queries, no-command/help without account I/O, SIGINT, closed stdout/stderr, malformed/oversized replies and fixed secret-sentinel privacy. Guard actual CLI/service children plus parent; use temporary credentials/journals and explicit fake composition, never actual serial/account access.
- [x] T029 [US4] Correct only demonstrated T028 delivery/installability defects in apps/cli/src/dutchmate_cli/{main.py,client.py,evidence.py}, apps/service/src/dutchmate_service/{app.py,http.py,evidence_http.py,server.py} and package configuration only if necessary. Preserve dependencies/uv.lock absent concrete need, no profile/Core-policy or writable fallback changes; record no defect/no production change when applicable, rerun focused regressions.
- [x] T030 [US4] Run all story/installed/privacy/security/backend-neutral/lifetime suites and full uv gate; inspect install artifacts/metadata and record actual native platform evidence and unexecuted Linux/Windows/active-DUT/physical acceptance in docs/development_status.md and docs/development_history.md. No service management, catalogue, hardware or later feature.

## Phase 7: Polish and Cross-Cutting Final Gate

- [x] T031 Review the complete feature008 diff against docs/project_context_core.md, specs/008-evidence-retrieval/{spec.md,plan.md,data-model.md,contracts/evidence-retrieval.md,tasks.md}, completed003/005–007 and current status. Audit every FR-001–032/error/cursor/byte/provenance/association/cleanup/capacity invariant, no deferred code, schema-v1/Profile-v1 unchanged, inward imports/installability and no unrelated/generated/runtime/credential/Graphify files; correct only genuine defects with focused regressions.
- [x] T032 Execute applicable safe acceptance from specs/008-evidence-retrieval/quickstart.md; reconcile focused tests, installed wheel/sdist validation and all four independent story criteria. Review paths/options/help/response privacy and exact transport bounds; identify skipped/unexecuted hardware/platform work accurately in docs/development_history.md.
- [x] T033 Reconcile actual implemented contracts/counts/task progress/current scope in docs/development_status.md (Resume Here about40 lines or fewer) and append newest-first evidence to docs/development_history.md; retain prior committed baseline and do not claim final validation before T035 or Phase1 complete. Update architecture documentation only if architecture changed; do not rewrite Core/old feature contracts.
- [x] T034 Assess structural changes using docs/agent_tooling.md and .codex/skills/graphify/SKILL.md; if justified, run one code-only incremental Graphify update after implementation, otherwise record no update required in docs/development_history.md. Keep graphify-out/ and backups ignored, never read graph.json directly or include generated output in intended diff.
- [x] T035 Under verification-before-completion, run fresh rtk proxy uv run ruff check ., uv run mypy ., uv run lint-imports, uv run pytest and git diff --check; rerun full gate after any corrective change, confirm final diff/installability/unchanged schema/Profile and mark only actually completed tasks in specs/008-evidence-retrieval/tasks.md. Record final results in docs/development_status.md and docs/development_history.md and report feature008 software readiness and remaining native/physical limits. Stop; do not commit, push, start another slice or access physical hardware.

## Dependencies and Execution Order

T001 → T002 → T003 → T004 → T005 blocks all stories. US1 T006/T007 tests can be
prepared concurrently after T005; T008 → T009 → T010 → T011 → T012 → T013 → T014.
US2 depends on US1's admitted read/lifecycle and delivery seam: T015 → T016 → T017
→ T018 → T019. US3 depends on active and terminal availability; T020/T021 can run
concurrently after T019, then T022 → T023 → T024 → T025. US4 depends on all prior
stories: T026 → T027 → T028 → T029 → T030. Final T031 → T032 → T033 → T034 → T035.
T021/T023 also verify the data-model constraints "positive exact integer-or-null"
for lost_bytes and "nonnegative exact integer, never bool" for timestamp values;
003/006 supply the unchanged closed provenance descriptor constraints.
Tests precede the code they exercise; no premature adapter/runtime implementation
in the pure foundation. A sequential authorization may stop at any named task.

## Parallel Examples

- US1: T006 core contract and T007 integration tests touch separate new files after
  foundation; run identical fixture assertions without concurrent edits to runtime.
- US2: No parallel marker: adapter/association/cleanup steps deliberately depend on
  the preceding resource-lifetime implementation and shared test files.
- US3: T020 Core semantics and T021 service transport tests use separate files after
  US2, then integrate before the corrective task.
- US4: No parallel marker: shutdown fixes precede installed process tests; shared
  runtime/service/CLI files require sequential work.

## Implementation Strategy

First authorization group is **T001–T005 only**: baseline, JournalFailure RED/fix,
read-boundary RED/types, focused/full validation and checkpoint documentation.
US1 is the smallest user-visible MVP (T006–T014), with terminal reads unavailable.
US2 enables safely closed last-run reads; US3 proves pagination/delivery edge cases;
US4 completes installed lifetime/privacy proof. All35 tasks are needed for final008
software acceptance; completing one increment does not authorize the next.

Task counts: setup1/foundation4; US1 nine, US2 five, US3 six, US4 five; final five.
No automatic commit/push/deploy or physical acceptance at any checkpoint. Deferrals
are exactly spec/contract §9. The Feature003 exception correction is in scope only
because retrieval now needs honest exception transport through read resource scopes.

## Requirement Coverage

| Requirements | Primary tasks |
|---|---|
| FR-001–006,010 | T004–T014 (read ports, association, live gate and delivery) |
| FR-007–009,032 | T015–T019, T026–T027 (terminal identity/close and cleanup latch) |
| FR-011–015 | T007, T010–T013, T020–T025 (003 projection, snapshots and bytes) |
| FR-016–021 | T010–T013, T021–T025 (closed schema, auth, independent bounds/errors) |
| FR-022–023 | T006, T008, T011, T017–T018, T026–T030 (bounded owners and lifetime) |
| FR-024–026 | T012–T014, T023–T024, T028–T030 (thin finite private CLI) |
| FR-027 | T002–T003 (focused exception regression/correction) |
| FR-028–031 | T001, all RED/checkpoint tasks and T031–T035 (neutrality, gate, scope) |
