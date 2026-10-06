# DUTchMate Development History

Completed slice records are kept newest first. Current status and next work live
only in `docs/development_status.md`.

## 2026-10-06 — Feature 005 Final Pre-Commit Review and Commit

Reviewed the complete feature-005 change set against Core, FR-001–030, the
internal runtime contract, plan, all completed T001–T028 definitions, completed
feature contracts and development status. No new scope/contract defect was found;
production code and tests needed no correction. Single generation/reader ownership,
direct Acquisition snapshot projection, loop/thread ownership, cancellation-resistant
cleanup, recorder-after-Acquisition joins and conservative reuse gating remain intact.
Basic/SQLite construction stays at the edge; Profile/session association remains
in memory, schema-v1 and evidence semantics remain unchanged, and all deferrals persist.

Used verification-before-completion and reran the complete gate through rtk proxy/uv
with UV_CACHE_DIR=/private/tmp/dutchmate-feature005-uv-cache:

- uv run ruff check .: all checks passed.
- uv run mypy .: no issues in 40 source files.
- uv run lint-imports: three contracts kept, zero broken; 31 files/77 dependencies.
- uv run pytest --tb=short --junitxml=/private/tmp/dutchmate-feature005-precommit.xml:
  924 passed, zero failures/errors/skips; existing fail-closed hardware guards active.
- git diff --check and git diff --cached --check: clean after completion metadata
  reconciliation; the complete intended 21-file staged diff/stat was inspected.

Reconciled current development status for the explicitly authorized commit, and
made pre-commit planning metadata explicitly refer to its T028 checkpoint rather
than retain stale current-status claims. Earlier history entries remain unchanged.
The commit is identified by subject `Implement observation runtime lifecycle`,
following parent 6d10cf72014c46d7eeb5481b26857222ee40b7fd on main; Git records its hash.
Generated Graphify output/backups, local tooling, temporary journals and gate
reports are excluded. No additional Graphify update or Spec Kit stage was run.

Feature 005 is software-complete; Phase 1 is incomplete. No physical device was
accessed or validated, no hardware acceptance is claimed, nothing was pushed,
and no subsequent development slice was selected or started.

## 2026-10-06 — Feature 005 T028 Fresh Final Software Gate GREEN

Executed only T028. Used verification-before-completion and ran the fresh full
repository gate through rtk proxy/uv with
UV_CACHE_DIR=/private/tmp/dutchmate-feature005-uv-cache:

- uv run ruff check .: all checks passed.
- uv run mypy .: no issues in 40 source files.
- uv run lint-imports: all three contracts kept, zero broken; 31 files and
  77 dependencies analyzed, with no new exemption or weakened rule.
- uv run pytest --tb=short --junitxml=/private/tmp/dutchmate-t028-full.xml:
  924 passed, zero failures/errors/skips. JUnit confirms 349 feature-005 cases,
  565 completed-feature regressions and ten T019 fixture checks. All US1/US2/US3
  and T024 correction regressions remain GREEN.
- git diff --check: clean before documentation edits, then rerun clean after
  completion records were reconciled; untracked-file whitespace also verified.

Reviewed the final tracked diff against accepted baseline 6d10cf7 and all
untracked feature additions, including runtime/Basic composition, additive
Acquisition snapshot/join behavior, tests/fixture gates, import-contract changes
and planning/completion metadata. No new feature-005 defect or failed required
check remained; no production/test correction or extra validation rerun was
needed. Schema-v1/evidence/Backend/Profile contracts, dependencies/lockfile,
exports, authority ordering and accepted scope/deferrals remain unchanged.
Runtime uses normalized facts only; one owner/reader and actual joins preserve
evidence and conservative cleanup certainty. Default hardware guards remain
active. Generated Graphify output/backups are ignored and not tracked.

Reconciled final spec/plan/tasks/quickstart and development status/history as
software-complete and ready for final human review/commit. All 28 task markers
are checked; T026's previously restricted marker now reflects its completed
two-file reconciliation record, without rerunning T026 or changing that record.
No further feature/task, Spec Kit stage or Graphify update is started. Only
completion documentation changes in T028; hashes preserve all production,
tests/fixtures/configuration and normative contracts. The pre-existing
feature-003 JournalFailure context-manager limitation remains separately
documented and outside feature 005; it does not fail this feature's required gate.

HEAD/accepted committed baseline remains
6d10cf72014c46d7eeb5481b26857222ee40b7fd on main, with features 001–004 accepted.
Feature 005 remains uncommitted working-tree content pending final human review
and an explicit commit instruction. No human acceptance, commit, release, Phase 1
completion or physical-hardware/electrical/Enhanced-hardware acceptance is claimed.
No physical device was enumerated, opened, modified or tested. Stopped after T028.

## 2026-10-06 — Feature 005 T027 Code-Only Incremental Graphify Update

Executed only T027. Read the repository Graphify guidance and local skill/update
reference. Assessed the actual accepted-baseline diff, including the two new
production modules runtime.py/adapters/observation_runtime.py, shared Acquisition
snapshot()/join_terminated()/snapshot values and runtime coverage in the existing
dependency contracts. These satisfy the module/shared-interface structural
trigger; earlier per-slice graph runs do not substitute for this final assessment.

Verified installed Graphify 0.9.48 and existing interpreter/output/manifest before
updating. Corpus preflight found 126 files/~172,144 words, with no skipped-sensitive
files, 38 changed code sources and no deletions. The installed CLI's plain update
path rescans the full corpus and Markdown AST headings; to honor code-only
incremental scope, exactly one invocation used the existing
graphify.watch._rebuild_code(Path('.'), changed_paths=changed_code,
force=False, block_on_lock=True) updater via Graphify's installed interpreter.
Only changed code paths were passed; existing graph/documentation content was
preserved. No semantic extraction, API/LLM calls, fresh full extraction, labeling
command, second update or runtime test execution.

Update succeeded (exit 0): 2,435 nodes, 6,370 edges and 117 communities, compared
with 2,240/5,241/116 before the run. The report records zero input/output LLM
tokens. Non-fatal diagnostics were one zero-node source (pyproject.toml) and
34 community labels refreshed deterministically from their hubs. No retry or
LLM relabeling followed. The updater backed up four curated output files and
refreshed graph JSON, HTML, report, manifest and labels under ignored graphify-out/.

Read-only graphify explain verifies ObservationRuntime, attach_basic_observation,
AcquisitionSnapshot and join_terminated at their actual source locations; report/
manifest checks confirm the indexed symbols and successful output. graph.json
was never read directly. Git check-ignore verifies graph/report/HTML/manifest/
labels/backups are covered by the existing graphify-out/ rule, and git ls-files
finds no tracked generated graph output. Source/test/configuration hashes remain
unchanged; generated output is not staged or committed.

Recorded T027 completion in development status/history and checked only T027
in tasks.md. T026's deliberately untouched marker remains as it was; completion
is recorded in the reconciled development status. No other planning artifact,
production/test/dependency/contract/schema change, Spec Kit, commit or physical
hardware action/acceptance claim. Documentation links/whitespace/scope verified.
Stopped after T027; T028 remains unchecked and its fresh full software gate was
not run. Prior software validation remains prior evidence, not a new T028 result.

## 2026-10-06 — Feature 005 T026 Development Status/History Reconciliation

Executed only T026 and changed only development_status.md and this history.
Reconciled the active Phase 1/feature-005 working-tree milestone, recorded
validation evidence, remaining acceptance work, limitations and deferrals.
Replaced the accumulated chronological status narrative with a current summary
and checkpoint tables; prior completed-slice records are retained unchanged below.
Removed stale claims that US3 termination and runtime/Profile activation remain
unimplemented. Detailed feature/task evidence stays in history, while current
status and the authorized stopping point remain solely in development status.

Read-only Git verification confirms branch main and HEAD
6d10cf72014c46d7eeb5481b26857222ee40b7fd. The accepted baseline remains 6d10cf7,
including feature 004; committed milestones 001/002/003 are respectively
a13522c/e2cd2cf/15890e59. Feature 005 remains modified/untracked working-tree
work. No feature-005 commit, baseline advancement or complete feature acceptance
is claimed. All implementation/review through T025 is delivered; T026's
documentation reconciliation is complete. Task/spec/plan/quickstart files and
their T026 progress markers are deliberately untouched under the user's explicit
two-file restriction; current completion is recorded in development status.

Validation is reconciled as prior software evidence: T024's latest full gate
passed 924 cases and its feature focus passed 349; T025's 21 focused test/five
architecture-scope commands passed, including 349 feature cases, 565 completed
regressions and ten fixture checks. T025 omitted its final-gate block. T026 reruns
no software tests, static suite or hardware cases and makes no fresh software-gate
claim. Documentation verification checks actual Git references, local links,
whitespace, bounded Resume Here and the two-file change scope.

No physical device has been accessed, modified or validated. Fake/temporary-
journal and Enhanced-shaped tests establish software contracts only; real
platform/electrical acceptance cases remain unexecuted, never reported as passed.
The feature-003 JournalFailure context-manager limitation remains separately
recorded, while feature-005 preparation-error transport is fixed. Scope/deferrals
and normative Core/contracts are unchanged. No code/test/dependency/configuration
change, commit, Spec Kit or Graphify operation. Earlier history entries retain
their original checkpoint claims. T027/T028 remain unexecuted; this reconciliation
does not perform their structural assessment/update or final software gate.

## 2026-10-06 — Feature 005 T025 Quickstart Focused Scenarios/Scope Checks GREEN

Executed only T025. Read quickstart and ran all 21 focused pytest commands and
five architecture/scope commands before its final implementation-gate block,
with the documented file selections/filters. All commands succeeded. No
unrestricted full pytest or final-gate block was run; T028 retains that step.
The three canonical focused runs pass 105 foundational/value, 214 runtime/
composition and 30 integration cases. Combined feature focus passes 349,
completed-feature regressions 565, and T019 fixture checks ten. US1 groups pass
91/65/21/six; T024 correction check 15; US3 58 (T020 34/T021 24); US2 94
(T012 35/T013 27/T014 32), T016 preparation subset 22, and Acquisition
regressions 64. All selected tests have zero failures/errors/skips.

Focused scenarios cover resolved-Profile startup, binary/ambient continuous RX,
actual consumer/physical-close joining before recorder close, bounded durable
readback/retention, repeated cancellation, partial preparation/start failures,
retained journals and uncertainty blocking, immediate/active disconnect with no
reopen, explicit fresh sessions, both normalized shapes, direct primary/close
snapshot facts, derived admissibility/impossible statuses, exact loop/thread
ownership and runtime-versus-Basic-edge busy semantics. No demonstrated code/
test defect, changed expectation, weakened gate, or fixture/capability emulation.

Quickstart architecture checks keep all three Import Linter contracts (31 files/
77 dependencies), Ruff clean and mypy 40 files clean. Schema search reports
version 1; the specified SQLite/model/Backend diff is empty. Shared-runtime
searches show only inward Core/standard-library imports, no backend/framework/
physical-device dependency or identity branch, no private/legacy Acquisition
access, automatic reconnect, lifecycle deadline or evidence reconstruction.
Concrete Basic/SQLite/Profile construction stays at the composition edge.

One documentation count was stale after T024: excluding T020/T021 selects 291,
comprising the original 277 earlier cases and 14 new T024 cases. The quickstart
description is clarified; selectors and tests are unchanged. Hashes confirm all
42 source/test/configuration files, dependencies/lockfile and normative contracts
unchanged. Only six progress/count-description artifacts change. Documentation
whitespace checks pass; no final-gate diff-check block is executed. Commands
used rtk proxy and the documented uv run/--no-sync variants with
UV_CACHE_DIR=/private/tmp/dutchmate-feature005-uv-cache.

T024's full 924-pass result remains prior evidence; no fresh full-suite/final-gate
claim is made for T025. Updated only T025 checkbox, spec/plan/quickstart progress,
development status and this record. Routine slice recording does not complete
T026's feature-level status/history reconciliation. No Spec Kit, Graphify, commit,
physical hardware action or acceptance claim; accepted baseline remains 6d10cf7.
Documentation-only work has no structural Graphify trigger; whole-feature
assessment remains T027. Stopped after T025; T026–T028 remain unchecked.
Complete feature acceptance is deferred, including the fresh final gate at T028.

## 2026-10-06 — Feature 005 T024 Full Contract/Scope Review and Correction GREEN

Executed only T024. Reviewed the full tracked/untracked feature-005 diff against
FR-001–030 and the internal contract: ownership/context/admission (001–007),
startup/cleanup/cancellation/retained journals (008–016), bounded in-memory
association/status/additive Acquisition facts and compatibility (017–024), and
composition/sequence/retention/neutrality/hardware-free scope (025–030).
Inventoried the new runtime/Basic composition modules, additive Acquisition API,
test consumers and package exports. Existing root exports and module import
surfaces are preserved; pyproject adds only runtime coverage to two existing
import contracts. No dependency/lockfile churn or new/relaxed exemption.
Schema-v1, evidence/Backend/Profile persistence contracts and all deferrals remain
unchanged. Status holds normalized current/last values with no Profile-source/
journal-destination path, raw diagnostics, live handle or unbounded summary history.

Reproduced one genuine feature-005 defect: frozen/slotted PreparationFailure
rejects standard contextlib __traceback__ restoration with TypeError. Runtime
then mistakes the normalized report for internal-contract failure and loses the
known session, original primary and actual cleanup certainty, blocking even
confirmed-cleanup reuse. Two direct sync/async and four real temporary-journal
runtime regressions went RED for this defect; eight fact reassignment/deletion
checks passed. After the bounded correction, all 14 new cases and the unchanged
normalization case pass. JUnit confirms identical new RED/GREEN case sets.

Only PreparationFailure changes in production: normal RuntimeError transport
attributes remain writable, while all four normalized fact fields remain read-
only and validated. Constructor/replacement/equality/hash behavior and fixed
message are preserved and verified. RuntimeStatus copies only normalized facts,
never exception transport metadata. No lifecycle, Acquisition, composition,
persistence/schema, policy or fixture behavior changes. All existing model tests/
helpers are unchanged; new regressions are appended. One stale composition-test
comment is corrected without executable changes. No other scope/contract defect
was found. The existing feature-003 JournalFailure interoperability limitation
remains outside this correction's scope.

Fresh feature focus passes 349; full hardware-free pytest passes 924, zero
failures/errors/skips. Ruff passes; mypy three targeted/40 full files passes;
all three Import Linter contracts are kept (31 files/77 dependencies); tracked/
untracked whitespace checks pass. Commands used rtk proxy and uv run --no-sync
with UV_CACHE_DIR=/private/tmp/dutchmate-feature005-uv-cache.

Hashes preserve all other production/tests/fixtures/configuration; AST/prefix
checks confirm earlier model tests and executable composition tests unchanged.
Updated T024 checkbox, spec/plan/quickstart progress, development status and this
record. Normative Core/contracts, schema-v1, dependencies/lockfile, exports and
accepted baseline 6d10cf7 are unchanged. No Spec Kit, Graphify, commit or physical
hardware action/acceptance claim. The localized exception fix has no module/
shared-interface/dependency-direction trigger; whole-feature structural Graphify
assessment remains T027. Stopped after T024; T025–T028 remain unchecked and full
feature acceptance is deferred. T025 runs focused quickstart scenarios/scope
searches and fixes only demonstrated failures, deferring its final gate to T028.

## 2026-10-06 — Feature 005 T023 US3 Regression/Architecture Review GREEN

Executed only T023. Fresh feature-005 focus passes 335; the quickstart completed-
feature regression selection passes 565, including Acquisition/Basic/Profile/
SQLite compatibility. Fresh full hardware-free pytest passes 910 with no
failures/errors/skips. JUnit confirms the complete case set is exactly feature
focus plus completed regressions plus ten T019 fixture checks. All 58 T020/T021
cases are GREEN, including identical 12-case T021 sets on both backend shapes.
No test expectations, deterministic gates, shared fixtures or production changed.

Reviewed shared runtime/Acquisition and the fixture/integration/generation tests
for T023's four prohibited assumptions. No backend-identity policy branch or
host-clock assumption was found: capabilities/observability drive RX/loss checks,
reported timestamp domains/origins are preserved, and progression compares only
within the current domain/origin. Enhanced-specific fixture checks support event
emission/counters, not shared lifecycle policy or Basic capability emulation.
The fixture reports device ticks/scoped loss/non-serial disconnect and adds no
future GPIO/helper/USB/firmware/framing/timing or Enhanced Profile behavior.

Generation review confirms admitted ownership prevents replacement until
notification/startup/consumer/physical-close/recorder work is settled. The owner
drains notification waits and joins Acquisition before recorder close/terminal
publication. Only notification waits may be cancelled by runtime; no runtime
reader/close cancellation or reopen path is added. Captured old results and
guarded stop intent cannot publish into the next generation. No stale mutation
or other in-scope defect was found, so no code/test correction or RED cycle was
manufactured. The normalized snapshot retains direct primary/close facts and
committed historical provenance; runtime reconstructs no lifecycle facts from
journal records.

Ruff passes; mypy passes 40 files; all three Import Linter contracts are kept
(31 files/77 dependencies), without exemptions. Quickstart searches show schema
version 1 and no committed-baseline diff to SQLite, evidence/model or normalized
Backend contracts. Tracked/untracked whitespace checks pass. Commands used
rtk proxy and uv run --no-sync with
UV_CACHE_DIR=/private/tmp/dutchmate-feature005-uv-cache.

Hashes confirm all 42 source/test/configuration files, dependencies/lockfile and
architecture rules unchanged. Updated only T023 checkbox, spec/plan/quickstart
progress, development status and this record. Normative contracts/Core/schema-v1
and accepted baseline 6d10cf7 are unchanged. No Spec Kit, Graphify, commit, physical
hardware action or acceptance claim. Review/documentation-only work has no
structural Graphify trigger; whole-feature assessment remains T027. Stopped after
T023; T024–T028 remain unchecked. Complete runtime acceptance remains deferred;
T024 performs the full-diff/FR-001–030 contract, consumer/export and scope review.

## 2026-10-06 — Feature 005 T022 Autonomous Runtime Termination GREEN

Executed only T022. Runtime now handles autonomous Acquisition termination in
the existing generation owner. It races explicit stop and public termination
notification waits, publishes detaching, then drains both notification waiters.
Only an unfinished Event notification wait is cancelled; no Acquisition startup,
RX consumer, backend-close or join work is cancelled. Notification helpers
never publish independently, no extra reader/buffer is added, and all lifecycle
mutation remains on the bound owning loop/thread.

Successful public Acquisition.start return is tracked independently from active
publication. Only acquiring snapshots without observed terminal trigger or
pending stop publish active; early disconnect/recording/transport termination
instead enters cleanup and returns a historical terminal result. Observed
termination's final append/close work is joined without submitting another stop.
An unobserved explicit stop still calls Acquisition.stop. Both paths await
join_terminated before recorder close and settle all owned notification/resource
work before publishing the terminal summary. Admission/cancellation handling,
fresh-session-only activation and conservative uncertain-cleanup blocking remain
unchanged; late old-generation waiters retain captured immutable results.

Observed disconnected trigger now takes terminal-reason precedence over startup/
acquisition failure and detach/cancellation, even with final append/close errors.
Actual primary/cleanup failures independently force failed state. Existing direct
primary_failure_kind/close_failed projection remains separate from trigger,
committed historical provenance and physical release certainty. No legacy
Acquisition.failure decoding, private Acquisition access, evidence reconstruction,
backend/timestamp branch, automatic reconnect/reopen, deadline or abandonment.

Fresh pre-change T020/T021 run reproduced 41 assertion failures/17 passes; after
implementation the same unchanged 58 cases all pass. JUnit confirms exact case-set
identity, zero errors/skips and both backend shapes GREEN. Whole feature focus
passes 335, including earlier cancellation/failure/ordering contracts. Fresh full
hardware-free pytest passes 910, zero failures/errors/skips. Ruff passes; mypy
one targeted/40 full files passes; all three Import Linter contracts are kept
(31 files/77 dependencies); tracked/untracked whitespace checks pass. Commands
used rtk proxy and uv run --no-sync with
UV_CACHE_DIR=/private/tmp/dutchmate-feature005-uv-cache.

Only runtime.py changes among 42 source/test/configuration files; hashes preserve
all tests/fakes, Acquisition, Basic/composition/Profile/SQLite modules, dependencies/
lockfile and architecture rules. Updated T022 checkbox, spec/plan/quickstart
progress, development status and this record. Normative contracts/schema-v1 and
accepted baseline 6d10cf7 are unchanged. No Spec Kit, Graphify, commit or physical
hardware action/acceptance claim. This private lifecycle change adds no public
interface/module/dependency-direction change; whole-feature structural Graphify
assessment remains T027. Stopped after T022; T023–T028 remain unchecked. A passing
slice gate is not complete runtime acceptance. T023 performs the US3/current-
feature/completed-feature regression and architecture review specified in tasks.md.

## 2026-10-06 — Feature 005 T021 Parameterized Lifecycle/Readback Contracts

Executed only T021. Added 24 integration cases using the two existing fixture
factories: each runs the same 12 cases with eight passes/four expected failures.
The original six real Basic/fake-serial composition cases and their helpers
remain unchanged apart from imports. Each new preparation creates a temporary
fresh SQLite journal before constructing its unopened normalized fixture;
shared runtime receives the same resolved observation-only Profile. The test
edge supplies a generic version-1 provenance envelope with opaque backend
schema 37, without changing reported capabilities/timestamps/loss or implementing
Enhanced Profile selection, hardware/protocol behavior, or production code.

Sixteen cases pass: attaching/busy/active status with no repeated preparation,
exact binary/ambient byte capture and journal sequences, reported host/device
timestamp domains, commit-gated origin-reset publication with a lower new-clock
value, reported observer-loss scope versus upstream unobservability without
emulation, explicit missing-RX rejection before reader/segment creation with
retained empty journal, actual physical-close/consumer joining before recorder
close, fresh explicit run/session/connection/segment identities with historical
prior status, bounded fixed-snapshot continuation after ambient RX/detach/reopen,
and rolling expiry with original timestamp domain. Real reopen/readback confirms
persisted policy/envelope, fixed schema-v1 tables/columns/version and absence of
durable full-Profile identity/name/source path.

Eight cases are RED against the unchanged runtime: active disconnect (two),
disconnect observed before attach result delivery (two), and autonomous RX-
recording/transport failure cleanup (four). Assertions require autonomous
ordered cleanup, observed terminal cause, historical committed provenance,
independent actual failure/cleanup certainty, no fabricated evidence or reopen,
and idempotent settled detach. Both shapes produce matching case sets/results.
No xfail/skip, collection, watchdog or teardown errors. New-harness mistakes
were corrected before recording results: nonexistent capability attribute,
UTF-8 decoding of arbitrary binary persisted values, and assuming complete
retrieval after prefix expiry. Correct assertions use reported supports(), raw
bytes, and the documented partial outcome. No production defect was corrected.

Fresh earlier five-file focus passes 277, including all six original integration
cases. Full hardware-free pytest collects 910: 869 pass, with only 33 existing
T020/eight T021 assertion failures and no errors/skips. JUnit confirms focused/
full T021 failure identities, identical per-shape sets/results and unchanged
T020 failure families/counts. Required full gate remains intentionally RED.
Ruff passes, mypy passes 40 files, all three Import Linter contracts are kept
(31 files/77 dependencies), and tracked/untracked whitespace checks pass.
Commands used rtk proxy and uv run --no-sync with
UV_CACHE_DIR=/private/tmp/dutchmate-feature005-uv-cache.

Hashes confirm only the integration module changed among 42 source/test/
configuration files; all production, other tests/shared fixtures, dependencies/
lockfile and architecture rules are unchanged. Updated T021 checkbox, spec/plan/
quickstart progress, development status, and this record. Normative contracts,
schema-v1 and accepted baseline 6d10cf7 are unchanged. No Spec Kit, Graphify,
commit, physical hardware action or acceptance claim. Test-only work has no
production structural Graphify trigger. Stopped after T021; T022–T028 remain
unchecked. T022 implements autonomous normalized Acquisition observation,
terminal-before-active handling and independent cause/primary/close projection
on the owning loop/thread, then runs T020/T021.

## 2026-10-06 — Feature 005 T020 Runtime Termination Contracts RED

Executed only T020. Added 34 contracts in test_observation_runtime.py: eight
autonomous disconnect cases across final append/backend/recorder failures,
four autonomous RX-recording/transport failures, four immediate disconnect
and two acquisition-failure cases before active delivery, four start-return
disconnect/stop/cancellation races, eight disconnect/detach/failure combinations,
two cancelled-detach waiters, one historical late-result/new-generation case,
and one queued-but-unobserved disconnect plus failed initial append.

Real Acquisition and temporary SQLite journals remain authoritative. Test-local
recorder faults and start-return/consumer-tail gates control submitted work;
the existing normalized event-delivery gate distinguishes queued from observed
disconnect. A legacy-failure access tripwire requires normalized snapshot use.
Assertions keep observed trigger, actual primary failure, close_failed, committed
historical provenance and release certainty separate, require one open/reader/
close, join consumers before recorder close, retain journals, and forbid reopen
or stale-generation publication. Cleanup releases gates and drains real work
after assertions, without attesting production cleanup or adding product deadlines.

Focused RED run records 33 assertion failures and one pass. Twelve expose absent
autonomous cleanup; six expose active delivery after observed termination;
14 expose incorrect disconnect precedence over detach/cancellation or primary
failure; one late-generation case first exposes absent autonomous settlement.
The unobserved-event case passes: failed initial append prevents RX claim, so
disconnect cannot be asserted and committed connection identity remains absent.
No xfail/skip, watchdog, collection, or teardown failures. Initial test setup
cancelled two detach tasks before entry; confirmed admission now precedes
cancellation, and both cases fail for the intended terminal-reason defect.
No production defect was corrected in this test-only scope.

Fresh earlier five-file feature focus passes 277. Full hardware-free pytest
collects 886: 853 pass, with only the same 33 T020 assertion failures and zero
errors/skips. JUnit verifies exact focused/full failure identities. The full
gate is intentionally RED. Ruff passes, mypy passes 40 files, all three Import
Linter contracts are kept (31 files/77 dependencies), and tracked/untracked
whitespace checks pass. Commands ran through rtk proxy and uv run --no-sync
with UV_CACHE_DIR=/private/tmp/dutchmate-feature005-uv-cache.

SHA-256 comparison confirms only runtime contract tests changed among 42
source/test/configuration files. Earlier runtime tests/helpers are unchanged
apart from one import; all production, shared fakes, integration tests, other
tests, dependencies/lockfile and architecture rules are untouched. Updated
T020 checkbox, spec/plan/quickstart progress, development status, and this record.
Normative contracts, schema-v1 and accepted baseline 6d10cf7 are unchanged.
No Spec Kit, Graphify, commit, physical hardware action or acceptance claim.
The test-only addition has no production structural Graphify trigger.
Stopped after T020; T021–T028 remain unchecked, and T020 awaits T022 implementation.

## 2026-10-05 — Feature 005 T019 Shared Fixture Lifecycle Gates GREEN

Executed only T019. Shared fakes now expose default-open FixtureLifecycleGate
checkpoints for backend open, connection read, normalized event delivery,
consumer exit, and close. Each gate has entered/allow events and no elapsed-time
behavior. Tests opt in by clearing allow; default stream/factory behavior stays
the same. Simple counters record open invocations, successful reader claims,
and close invocations (including no-ops). A no-op close does not re-enter its
checkpoint. One authoritative normalized iterator is retained.

Ten fixture-focused checks in test_backend.py run identically against the two
existing factories: delayed open return (two), delayed read/event delivery with
exact binary bytes, reported timestamp domain, terminal ordering and rejection
of a second reader (four), independent close/consumer completion with idempotent
reclose (two), and reported missing-RX rejection that drains close before raising
without claiming a reader (two). They use actual normalized fixtures and the
existing Acquisition, not runtime status/cause policy from T020. All ten went
RED solely for missing gates, then all ten passed. No xfail/skip or production
implementation. Test watchdogs bound hangs without creating runtime deadlines.

Existing Enhanced-shaped device timestamps, scoped observer loss, origin reset,
normalized non-serial disconnect and reported capabilities are unchanged. RX
rejection reuses the existing descriptor. No new event, GPIO/helper/USB/framing/
firmware/device timing, Enhanced Profile selection, or Enhanced support claim.
All original 30 backend cases remain GREEN, as do current lifecycle/Acquisition
loss/origin/reset/disconnect cases. Compatibility passes 94 (40 backend,
22 lifecycle, 32 acquisition). Fresh full pytest passes 852, zero failures/errors/
skips, including all 277 previous feature-005 cases. JUnit verifies RED/GREEN
case-set identity and exact compatibility/full counts.

Ruff passes; mypy two targeted/40 full files pass; all three Import Linter
contracts kept (31 files, 77 dependencies); tracked/untracked whitespace clean.
New-harness B009 and typing issues were corrected using typed reflection only
for fixture-only metadata, direct known connection attributes, a coroutine
wrapper for anext, and cleanup over the declared iterator port rather than an
assumed aclose method. No rule/exemption or production API changed.

SHA-256 comparison confirms only shared fakes and the backend fixture contract
test changed among 42 source/test/configuration files; all production, runtime
tests, other tests, dependencies/lockfile, and architecture rules are untouched.
Original backend test bodies and the Enhanced connection semantics are unchanged.
Updated T019 checkbox, spec/plan/quickstart progress, development status, and
this record. No Spec Kit, Graphify, commit, or physical hardware action/acceptance
claim. The test-only extension adds no production structural Graphify trigger.
Accepted baseline remains 6d10cf7. Stopped at T019; T020–T028 remain unchecked.
T020 adds RED runtime status/immediate-active-disconnect/recording-failure/
racing-stop cases; autonomous runtime observation remains later T022 work.

## 2026-10-05 — Feature 005 T018 US2 Regression/Architecture Review GREEN

Executed only T018. All 94 US2 regressions pass: 35 request/cancellation cases
(T012), 27 preparation/transfer cases (T013), and 32 failure/teardown/certainty
cases (T014). Deterministic gates continue to hold actual prepare/open/append/
read/consumer/close work; no gate or expectation was weakened. Feature-005 focus
passes 277 and fresh full hardware-free pytest passes 842, zero failures/errors/
skips. JUnit reports confirm exact counts and all earlier work remains GREEN.

Reviewed every physical/recorder certainty assignment and admission/settlement
path in runtime.py and the composition adapter. Physical release comes only
from authoritative Acquisition snapshots; post-transfer recorder confirmation
requires successful original close. Settled detach returns the stored immutable
summary without retrying cleanup, and exact derived admission rejects uncertainty
before preparation. Failed-open release stays unconfirmed, and later library
no-op close cannot attest success or unblock another run. The edge owns local
cleanup until transfer, retains original primary/close outcomes and known IDs,
and keeps failed artifacts without probing/reopen/deletion/retry. Recorder close
follows Acquisition's actual consumer/close join. No no-op-close/reset path that
falsely clears uncertainty or other in-scope defect was found; no code correction.

Targeted Ruff and mypy (runtime/composition and their two contract test modules)
pass; full Ruff and mypy pass (40 files). All three Import Linter contracts kept
(31 files, 77 dependencies). Scope searches show no shared backend-identity
branch, legacy/private Acquisition failure access, physical-device call, owner
cancellation, or lifecycle deadline. Schema-v1 remains 1 and SQLite schema,
backend, and evidence contracts have no committed-baseline diff. No architecture
contract/exemption or dependency changed; tracked/untracked whitespace is clean.

SHA-256 comparison confirms all 42 source/test/configuration files unchanged,
including runtime, composition, Acquisition, shared fixtures, all deterministic
tests, pyproject.toml, and uv.lock. Only the T018 checkbox and progress in spec,
plan, quickstart, development status, and this newest-first record changed.
No production implementation, test rewrite, Spec Kit stage, Graphify update,
commit, or physical hardware action/acceptance claim. This review-only change
adds no structural Graphify trigger. Accepted baseline remains 6d10cf7.

Stopped at T018; T019–T028 remain unchecked. T019 extends only deterministic
current-contract gates in shared test fixtures, reusing existing Enhanced-shaped
timestamps/loss/origin-reset/non-serial-disconnect/RX-rejection behavior. US3
autonomous termination/neutrality and all accepted delivery/hardware deferrals
remain later work. This passing current suite is not complete runtime acceptance.

## 2026-10-05 — Feature 005 T017 Runtime Failure/Cleanup GREEN

Executed only T017 in runtime.py. Status now projects actual snapshot
primary_failure_kind separately from close_failed, preserving the first primary
and one acquisition/backend cleanup fact before one recorder fact. Physical
release certainty equals the snapshot's authoritative field; owned recorder
closure is confirmed only on successful close. No legacy failure decoding,
private Acquisition fields, evidence reconstruction, raw cause/context values,
or backend identity branch. Startup success/failure are private generation facts
used to distinguish startup primary from subsequent acquisition primary.

Normalized preparation failures retain reported identity, primary, and local
cleanup certainty/issue without reclosing untransferred resources. Unexpected
exceptions or invalid returned lifecycle subsets become internal contract
failure with unconfirmed recorder cleanup. A well-formed policy mismatch retains
its known ID and closes the recorder without constructing/opening Acquisition.
Failed Acquisition start/stop/backend close still joins actual consumer/close
work before recorder close; recorder failure is independent and never overwrites
the primary. Terminal settlement follows joined owned work, uses failed state
for any issue, and preserves the applicable explicit/startup cause and first stop
intent. No-op close/terminal detach cannot clear uncertainty; exact derived
admission blocks it for the runtime's lifetime. Confirmed cleanup allows only
a fresh explicit generation/session at a fresh destination.

Fresh pre-change T014: 29 RED failures and three passes. The same unchanged 32
cases now pass, including both legacy/snapshot counterexamples, first/final
append failures, reported missing RX, both close failure combinations, pending
consumer/journal gates, permanent uncertainty, idempotent detach, and confirmed-
cleanup retry. All 27 T013 cases pass too: the five formerly deferred failed-open/
policy-mismatch cases are GREEN. The 64 Acquisition regressions passed before
implementation and in the final suite. Combined feature-005 focus passes 277;
full hardware-free pytest passes 842, zero failures/errors/skips. JUnit reports
verify exact RED/GREEN case sets and removal of all 34 prior failures.

Ruff passes; mypy passes runtime.py and all 40 full files; all three Import
Linter contracts kept (31 files, 77 dependencies); tracked/untracked whitespace
clean. SHA-256 comparison confirms all 41 other source/test/configuration files
unchanged, including all tests, Acquisition, Basic composition/adapter, Profile,
SQLite schema/evidence semantics, dependencies/lockfile, and architecture rules.
Public method signatures/immutable values and normative contracts are unchanged.
Only shared runtime failure/projection/cleanup behavior and private preparation
validation/generation facts changed. No test correction or exemption was needed.

Updated T017 checkbox, spec/plan/quickstart progress, development status, and
this record. No Spec Kit rerun, commit, physical hardware action/acceptance claim,
or Graphify update. This single-module private lifecycle/projection change adds
no module/shared-interface/dependency-direction change requiring Graphify.
Accepted baseline remains 6d10cf7. Stopped at T017; T018–T028 remain unchecked.
T018 is the dedicated US2 regression/static/architecture review, including
elimination of any discovered no-op-close/reset path that clears uncertainty.
US3 autonomous termination observation, terminal-before-active/disconnect cause
priority, extended Enhanced-shaped neutrality, and all delivery/hardware work
remain deferred. A passing current suite is not complete runtime acceptance.

## 2026-10-05 — Feature 005 T016 Preparation Cleanup GREEN

Executed only T016 in adapters/observation_runtime.py. The edge still performs
nonmutating context validation and bounded explicit Profile resolution before
authoritative runtime admission. Its unsubmitted preparation closure creates
the fresh journal then translates/constructs one unopened Basic backend. Success
transfers those resources unchanged. No backend open/RX, discovery, fallback,
new schema, or lifecycle policy moves into the edge.

Creation and translation/construction exceptions now become PreparationFailure
with bounded normalized source/code facts. Existing JournalFailure, ProfileFailure,
and NormalizedBackendFailure categories are retained; unexpected exceptions use
internal_contract_failure. Only exact CREATE invalid_input/journal_exists prove
recorder pre-open closure; other create failures remain unconfirmed with absent
ID, even if committed metadata exists. No artifact identity probing, reopen,
deletion, or retry. After an obtained journal, failure closes it once before
reporting its known identity, retained file, first primary, and independent
recorder-close outcome. A failed close stays unconfirmed even if later close
would be a no-op. Failures are raised outside handlers so raw cause/context,
detail strings, and adapter objects do not cross the preparation boundary.

Fresh pre-change T013 run: 26 RED failures and one pass. Its unchanged 22
preparation cases comprised 21 RED failures/one pass; all 22 now pass. Whole
T013 now has 22 passes and five expected deferred failures:

- `test_t013_failed_open_keeps_session_but_never_proves_physical_release`:
  device_not_found, permission_denied, io_failure, unexpected (four cases).
- `test_t013_transferred_recorder_policy_mismatch_is_closed_before_any_open`:
  one case.

These require shared-runtime T017 handling, which was not implemented. All 29
T014 failures (families recorded below) also remain unchanged. Combined
feature-005 focus excluding those five T013 cases and T014 passes 240. Full
pytest collects 842: 808 pass and exactly 34 expected deferred failures, zero
errors/skips. JUnit confirms unchanged case sets, all 21 preparation fixes,
and no extra failure/watchdog/cleanup error. T015's 35 request/cancellation cases
and all earlier completed-feature/US1 tests remain GREEN. This is a GREEN edge-
preparation checkpoint, not a passing full gate or accepted runtime feature.

Ruff passes; mypy passes the changed adapter and all 40 full files; all three
Import Linter contracts kept (31 files, 77 dependencies); tracked/untracked
whitespace clean. The additional direct domain import uses the existing
normalized backend failure and preserves inward direction. SHA-256 comparison
confirms all 41 other source/test/configuration files unchanged: runtime.py,
Acquisition, Basic/SQLite/Profile implementations, every test, dependencies/
lockfile, and architecture rules. No test correction or exemption was needed.

Updated T016 checkbox, spec/plan/quickstart progress, development status, and
this record. No Spec Kit rerun, commit, physical hardware action/acceptance claim,
or Graphify update. The localized private normalization/cleanup change adds no
module/shared-interface/dependency-direction change requiring Graphify. Accepted
baseline remains 6d10cf7. Stopped at T016; T017–T028 remain unchecked. T017 is
shared-runtime failure/certainty/projection handling with T014 and Acquisition
regressions; autonomous observation and other accepted deferrals remain later.

## 2026-10-05 — Feature 005 T015 Request/Cancellation GREEN

Executed only T015 in runtime.py. Existing owning-loop/thread validation and
exact derived fail-fast admission are retained. Stop intent admits once under
the short lifecycle lock; later detach/attach_cancelled requests cannot replace
it. Stop handling checks generation identity before any mutation, protecting
new runs from late old-generation cancellation. Admitted attach/detach callers
shield and join their captured owner despite repeated cancellation, then
propagate the original CancelledError. Caller cancellation takes precedence if
the joined owner raises; owner failure normalization/cleanup remains later work.
No caller cancels the owner, no external I/O holds the lifecycle lock, and no
second open, runtime timeout, process lock, dispatch, or abandonment is added.
The normal terminal reason reflects the first detach/attach_cancelled intent.

Before production edits, the fresh unchanged T012 suite had 20 RED failures and
15 passes: six startup attach cancellations, two internal-active-publication
cancellations, nine detach checkpoints, two first-stop-intent races, and one
cancelled old-generation waiter. The same 35 cases then passed unchanged.
They cover before-admission versus admitted cancellation, repeated cancellation
during prepare/open/append/read/close, shared cleanup, retained journals,
post-success caller cancellation, busy/context rejection before preparation,
and captured old-generation results after a fresh explicit attach.

Combined feature-005 focus excluding T013/T014 passes 218. Fresh full pytest
collects 842: 787 pass, exactly 55 deferred failures (26 T013 and 29 T014), zero
errors/skips. JUnit confirms identical RED/GREEN case sets and removal of all
20 T012 failures, with unchanged T013/T014 sets. Their named failure families
remain recorded in the preceding T013/T014 entries. This is a GREEN request/
cancellation checkpoint, not a passing full gate or accepted runtime feature.
Preparation cleanup, failure/status/certainty handling, and autonomous terminal
observation remain later tasks; none was implemented here.

Ruff passes; mypy passes runtime.py and all 40 full files; all three Import
Linter contracts kept (31 files, 76 dependencies); tracked/untracked whitespace
checks clean. SHA-256 comparison confirms all 41 other source/test/configuration
files unchanged, including every test, Acquisition, Basic edge, SQLite schema,
dependencies/lockfile, and architecture rules. Public signatures, immutable
values, Profile association, evidence semantics, and composition boundary are
unchanged. Only two private request/cancellation helpers and normal request
handling/terminal-intent projection changed in production; no test correction.

Updated T015 checkbox, spec/plan/quickstart progress, development status, and
this record. No Spec Kit rerun, commit, or physical hardware action/acceptance
claim. Accepted baseline remains 6d10cf7. Graphify was not updated for a localized
private-helper behavior change without module/shared-interface/dependency
changes. Stopped at T015; T016–T028 remain unchecked. T016 is partial-preparation
cleanup and normalized PreparationFailure at the Basic composition edge, with
retained artifacts/known IDs, exact pre-open certainty exceptions, and T013 checks.

## 2026-10-05 — Feature 005 T014 Runtime Failure/Teardown RED

Executed only T014: added 32 deterministic cases to the existing runtime
contract module. Twelve projection cases exercise clean, close-only, recording,
and transport-before-failed-append snapshots, each with successful/failed
recorder close. They require actual snapshot primary_failure_kind independently
from close_failed, no legacy interpretation, first primary preservation, and
zero/one/two ordered normalized cleanup facts. Real counterexamples retain
transport primary despite legacy recording failure, and no primary despite
close-only legacy transport failure.

Eight startup cases cover failed first append/reported missing RX with every
backend/recorder close combination: retained known session, returned descriptor
but no fabricated committed provenance, startup cause independent of stop
intent, and attempted cleanup despite primary failure. Four consumer-tail cases
hold the actual consumer after its body/notification and require joining before
recorder close, including pending failure projection and owner settlement only
after resource work finishes. Four certainty cases check busy rejection during
physical and recorder cleanup, exact derived admission, permanent uncertainty,
idempotent terminal detach without cleanup retry, and rejection despite later
library no-op close. Two confirmed-cleanup retries require a fresh explicit
destination/run/session after primary failure. Two preparation reports preserve
primary/local-close facts and known identity without reclosing untransferred
resources.

Test fixtures use actual temporary SQLite journals and inherited Acquisition
start/stop/snapshot/join behavior. A legacy failure property tripwire rejects
runtime access; a test-only consumer tail gates actual task completion without
changing snapshots or implementing lifecycle policy. Explicit detach drives
active-failure cleanup; autonomous runtime observation remains later work.
Test-only cleanup releases gates, joins real Acquisition work, and closes
journals after assertions without attesting successful production cleanup.
No production timeout, forced abandonment, extra reader, shared-fake extension,
backend identity branch, or production change.

Focused result: 29 expected RED failures and three passes, zero errors/skips.

| RED test family | Failures |
|---|---|
| `test_t014_projects_primary_and_close_snapshot_facts_without_legacy_inference` | 11 |
| `test_t014_startup_primary_survives_both_ordered_cleanup_failures` | 8 |
| `test_t014_consumer_join_precedes_recorder_close_even_after_failure_notification` | 3 |
| `test_t014_admissibility_stays_blocked_until_settled_and_uncertainty_latches` | 3 |
| `test_t014_confirmed_cleanup_after_primary_failure_allows_only_new_explicit_run` | 2 |
| `test_t014_preparation_primary_and_local_cleanup_facts_survive_without_reclose` | 2 |

Failures expose missing primary/cleanup issue projection, leaked startup/
recorder-close/preparation exceptions, and failed cleanup reported as clean
termination. Clean projection, consumer-join ordering, and settled reuse pass.
No xfail/skip or implementation fix is added; T014 remains RED pending T017.

Earlier feature-005 focus passes 183 with T012/T013/T014 deselected. Fresh full
pytest collects 842: 767 pass and exactly 75 expected failures (29 T014, 26 T013,
20 T012), zero errors/skips. JUnit reports confirm the exact focused/full T014
failure set and no additional/watchdog/cleanup errors. All earlier completed-
feature and US1 cases remain GREEN; the existing T012/T013 RED sets are preserved.
This is a RED test-delivery checkpoint, not a passing full gate or runtime acceptance.

Ruff passes; mypy passes the changed test file and all 40 full files; all three
Import Linter contracts kept (31 files, 76 dependencies); tracked/untracked
whitespace checks clean. SHA-256 comparison of 42 source/test/configuration
files confirms only the runtime contract test changed. Its original 100
cases/helpers are unchanged apart from imports. Core/normative contracts,
production, shared fixtures, dependencies/lockfile, and schema-v1 are untouched.

Updated T014 checkbox, spec/plan progress, quickstart, development status, and
this record. No Spec Kit rerun, Graphify update, commit, physical hardware action,
or hardware acceptance claim. This test-only change adds no production structure
or contract requiring Graphify. Accepted baseline remains 6d10cf7. Stopped at
T014; T015–T028 remain unchecked. T015 is request/cancellation implementation
and T012 validation; failure/teardown implementation remains T017.

## 2026-10-05 — Feature 005 T013 Preparation/Ownership Transfer RED

Executed only T013: added 27 cases to the existing composition contract module.
Four category/operation cases check that only CREATE invalid_input/journal_exists
affirm pre-open recorder cleanup; a structural-invalid destination case uses
the actual SQLite validator. Nine failed-create cases cover before any artifact,
partial artifact, and actual committed metadata without returning the journal,
with normalized IO/capacity or unexpected failures. Guards prohibit identity
probing, reopen, deletion, and retry during failure normalization; unknown
SessionId remains absent even when the test fixture knows the committed ID.

Eight translation/construction cases fail after a real journal is obtained,
with normalized/unexpected primary errors and successful/failed local recorder
close. They require known identity, retained empty journal, one local close,
independent cleanup outcome, and no raw cause/context or arbitrary detail
crossing the preparation boundary. Four failed-open cases require failed status,
known session, absent invented descriptor/provenance, confirmed recorder close,
and unconfirmed physical release regardless of the backend's error category.
One mismatched-policy case requires closing the transferred recorder before
any backend open. Preparation uses the existing admission probe; transfer
tests exercise actual runtime/Acquisition. No substitute lifecycle or shared
fixture changes. Test-only cleanup releases obtained journals without claiming
that production cleanup succeeded; test watchdogs add no runtime deadline.

Focused result: 26 expected RED failures and one pass, zero errors/skips.
Failures expose leaked create/translation/construction/open exceptions instead
of normalized PreparationFailure/failed RuntimeStatus, and an attempted backend
open before policy-mismatch rejection. CREATE journal_exists already passes,
including cause/context suppression. No xfail/skip or production correction.
Preparation normalization and shared-runtime failure handling remain later work.

Earlier feature-005 focus passes 183 with T012/T013 deselected; the original
21 composition cases also passed before these additions. Fresh full pytest
collects 810: 764 pass, exactly 26 T013 plus the existing 20 T012 failures,
zero errors/skips. JUnit inspection confirms focused/full T013 failure sets,
the documented T012 assertion families, and no additional/watchdog/cleanup error.
This is an intentional RED test-delivery checkpoint, not a passing full gate.

Ruff passes; mypy passes the changed test file and all 40 full files; all three
Import Linter contracts are kept (31 files, 76 dependencies); diff whitespace
is clean. SHA-256 comparison confirms only the composition contract test changed
among 42 existing source/test/configuration files. Its original 21 cases/helpers
are unchanged apart from imports; all production/config/T012 work is untouched.

Updated T013 checkbox, spec/plan progress, quickstart, development status, and
this record. No Spec Kit rerun, Graphify update, new dependency/lockfile change,
commit, physical hardware action, or hardware acceptance claim. Graphify is
unneeded for this test-only change without production structure/contract changes.
Accepted baseline remains 6d10cf7. T014–T028 remain unchecked; stopped at T013.

## 2026-10-03 — Feature 005 T012 Request/Cancellation Races RED

Executed only T012: added 35 deterministic cases to the existing runtime
contract test module. Test-local gates exercise concurrent already-resolved
busy attach with forbidden Profile I/O/preparation, owning-context validation
before lock/mutation, detach during startup, three simultaneous detach waiters,
and cancellation before admission/during prepare/open/append/read/close.
Controlled first-commit callbacks test cancellation after internal active
publication but before attach delivery; recorder-close callbacks schedule a
fresh explicit run before old-generation caller-result delivery. Repeated
cancellation, first-stop-intent precedence, and post-success caller cancellation
are covered. Tests use actual runtime/Acquisition and temporary SQLite journals,
one normalized simulated RX path, and public status/results. No runtime
substitute, production change, shared fixture change, or physical access.

Focused result: 20 expected RED failures and 15 passes, zero errors/skips.
RED assertions show cancellation escaping before owned work settles: six
startup attach cases, two active-publication cases, nine detach checkpoints,
two stop-intent races, and one cancelled old-generation waiter. They remain
RED for the later T015 implementation; no xfail/skip or production fix was added.
The passing cases verify existing admission/context rejection, shared detach
cleanup, pre-admission and post-success cancellation behavior, and uncancelled
captured-generation delivery. Test-only watchdogs impose no runtime deadline.

Earlier feature-005 focus passed 183 with only the 35 T012 cases deselected.
Fresh full hardware-free pytest collected 783: 763 passes and exactly the same
20 expected T012 failures, zero errors/skips. JUnit reports confirmed both
failure sets and assertion reasons; no cleanup/watchdog failure occurred.
This is a RED test-delivery checkpoint, not a passing full gate or accepted
runtime feature. Cancellation/stop-intent production behavior is still deferred.

Ruff passes; mypy passes the changed test file and all 40 full files; all three
Import Linter contracts are kept (31 files, 76 dependencies); diff whitespace
is clean. Two test-harness typing errors were corrected without production
changes. SHA-256 comparison of 42 existing source/test/configuration files
confirms only the runtime contract test changed; its earlier 65 cases/helpers
are unchanged apart from the added evidence import.

Updated T012 checkbox and progress in spec/plan/tasks/quickstart, development
status, and this record. No Spec Kit rerun, dependency/lockfile change, commit,
or hardware acceptance claim. The accepted baseline remains 6d10cf7. Graphify
was not updated for this test-only change without production structure or
contract changes. T013–T028 remain unchecked; no later task was implemented.

## 2026-10-03 — Feature 005 T011 US1 Regression Checkpoint GREEN

Executed only T011: active quickstart US1/foundation checks passed 181 initially,
and all 565 completed-feature regressions passed. Reviewed the accepted Core,
spec/plan/internal contract, normal runtime/Basic composition, additive
Acquisition diff, immutable association, event-loop guards, derived admission,
single RX ownership, cleanup ordering, and unchanged journal contracts.
Cancellation/failure transfer and autonomous terminal behavior remain later work.

Review reproduced one in-scope defect: RuntimeRejectedError's frozen/slotted
dataclass blocked contextlib's standard __traceback__ assignment, masking the
normalized rejection with TypeError. Six regression cases went RED: all four
categories through a generator context manager, actual no-loop construction,
and actual invalid attach through an async generator context manager. Corrected
only that exception class in runtime.py to an ordinary RuntimeError with the
same validated, read-only kind and string. Normal exception transport fields
remain assignable; immutable run/status/issue values, context guards, resource
preparation, admission, and orchestration did not change. No new exception
framework or compatibility layer was introduced. All six went GREEN unchanged.

Final focused feature-005 tests passed 183; fresh full hardware-free pytest
passed 748, zero failures/errors/skips. JUnit reports verified exact RED/GREEN
sets and counts. Targeted Ruff/mypy/Import Linter and final full gate passed:
mypy eight targeted/40 full files, three import contracts kept (31 files,
76 dependencies), whitespace clean. A new-test Ruff B010 diagnostic was
corrected with the repository's dynamic-field assignment pattern; no rule or
exemption changed. Scope hashes verified all 40 other source/test/configuration
files unchanged, and reconstruction of the prior RuntimeRejectedError block
verified runtime.py's remaining code unchanged. Basic composition, Acquisition,
SQLite schema-v1, backend/evidence/Profile contracts, dependencies, and existing
contract/integration tests were untouched.

Updated T011 checkbox, spec/plan progress, quickstart, status, and this record.
No Graphify update was required for a localized fix without module/dependency
or normalized contract changes. The separate JournalFailure/contextlib defect
from T010 remains unmodified because evidence.py is outside the approved scope.
No Spec Kit stage, physical hardware action/acceptance, or commit occurred.
Accepted code baseline remains 6d10cf7. This is the US1 happy-path regression
checkpoint, not complete runtime acceptance; T012–T028 remain unchecked.

## 2026-10-03 — Feature 005 T010 End-to-End Readback GREEN

Added only T010's six cases in
`core/tests/integration/test_observation_runtime.py`. Real explicit TOML
resolution, ObservationRuntime, Basic adapter, Acquisition, and SQLite append/
reopen/retrieval compose the observation run. Only physical serial construction
uses the existing private fake seam; an append spy observes real durable commit
acknowledgments, and read gates supply deterministic ambient output.

Coverage proves exact binary/ambient bytes and ordered final explicit-stop
boundaries after detach/reopen; record-count and charged-byte rolling quotas,
coalesced discard counts/timestamps, explicit wholly/partly expired references;
fixed-snapshot pages across later RX, detach, and reopen; and expiry between
pages during continued capture. Removing the source Profile does not alter the
in-memory summary. Reopen preserves session policy and effective provenance,
while inspection of schema-v1 persisted values finds no DUT identity/name or
Profile source path. No durable full-Profile association is claimed.

The initial run passed four and failed two cases because new-test expectations
incorrectly assumed retrieval limits were clamped and Basic provenance fields
lacked their effective_* prefix. Existing feature-003/Basic contracts and code
identified both errors; only new tests were corrected. All six then passed.
This is compatibility coverage for existing code, not a production RED/GREEN
implementation pair. The error path additionally exposed an existing
JournalFailure interoperability defect: contextlib generator context managers
assign __traceback__, which frozen/slotted JournalFailure rejects with TypeError
on Python 3.14, masking the original normalized exception. A minimal independent
contextmanager reproduction confirmed it. It remains unmodified/outside this
task and outside T011's permitted production correction files.

Fresh full hardware-free pytest passed 746 with zero failures/errors/skips,
including the earlier 175 feature-005 cases. Ruff passed; mypy checked 40 files;
all three Import Linter contracts kept (31 files, 76 dependencies); diff
whitespace clean. JUnit reports verified focused/full counts. Hash verification
confirmed all 41 pre-existing source/test/configuration files unchanged.

Updated T010 checkbox, spec/plan progress headers, quickstart, status, and this
record. No runtime/Acquisition/adapter/schema/dependency/shared-fixture changes,
Graphify update (no production interface/dependency change), Spec Kit stage,
physical hardware action/acceptance, or commit occurred. Accepted code baseline
remains 6d10cf7. T011–T028 are unchecked; this checkpoint does not claim complete
feature-005 acceptance.

## 2026-10-03 — Feature 005 T009 Basic Observation Composition GREEN

Implemented only T009 in the new adapter module
`core/src/dutchmate_core/adapters/observation_runtime.py` and stopped.
attach_basic_observation checks context using nonmutating runtime.status,
resolves the bounded explicit Profile before admission without a busy precheck,
then hands runtime.attach a preparation closure capturing the explicit journal
destination. Busy may read/parse the Profile but creates/opens no journal,
constructs/opens no backend, and performs no run preparation or discovery.

Admitted preparation creates fresh SQLite with exactly Profile.session_policy,
then translates the captured values and constructs the unopened Basic backend.
It never opens the backend, starts RX, or resumes an existing journal. CREATE
journal_exists becomes the existing normalized PreparationFailure with no new
SessionId and confirmed pre-open recorder cleanup, without overwriting/reopening
the destination or constructing a backend. The existing Basic private serial
factory seam supports fake-only tests; no new public injection API, provider
hierarchy, or package re-export was introduced. Broader partial-preparation
failure/cleanup semantics remain the later T013/T016 work.

RED/GREEN: fresh T007 run failed all 21 cases on the missing composition API.
All unchanged cases passed after implementation, including context/read/admission
order, busy and invalid-Profile precedence, exact path/policy/configuration,
journal-before-backend startup, existing-file protection, and source replacement/
removal. Combined feature-005 focus passed 175; full hardware-free pytest passed
740, with zero failures/errors/skips. JUnit inspection verified the RED and GREEN
sets. Ruff passed; mypy no issues in 39 files; all three import contracts kept
(31 files, 76 dependencies); diff whitespace clean. No new defect was found.

Feature progress headers, T009 checkbox, quickstart, status, and this history
record were updated. One code-only Graphify update produced 2,240 nodes, 5,241
edges, 116 communities; 22 labels refreshed from hubs. The known non-fatal
zero-node pyproject.toml warning recurred; generated output stays ignored and no
semantic extraction ran. Existing source/config/tests, shared runtime and
Acquisition, adapters, package exports, dependencies, architecture rules, and
schema-v1 were unchanged. Accepted baseline remains 6d10cf7; no commit was made.

T010–T028 remain unchecked. End-to-end runtime composition readback acceptance,
US2 failure/cancellation/transfer validation, and US3 autonomous terminal behavior
remain pending; the passing current gate does not claim complete feature-005
acceptance. No Spec Kit stage or physical hardware access/acceptance occurred.

## 2026-10-03 — Feature 005 T008 Normal Observation Lifecycle GREEN

Implemented only T008 in `core/src/dutchmate_core/runtime.py` and stopped.
ObservationRuntime binds immediately to the constructing running loop/thread;
construction without a loop and lifecycle calls in other contexts reject before
validation, locks, mutation, or resource preparation. Synchronous status only
reads/project immutable Acquisition snapshots, without scheduling or mutation.

Derived admission creates one generation owner and captures the immutable
resolved Profile. Preparation occurs only after admission, followed by fresh
Acquisition.start and active-result publication. Normal explicit detach requests
stop, joins Acquisition stop/termination (including consumer/physical-close and
final evidence work), then closes the recorder. Terminal summary publication
follows quiescent resource work; detach waiters join the actual completed owner.
Only one current/last immutable summary remains and runtime resource references
are released. Locks do not span external awaits. No adapter import, backend
identity branch, alternative RX reader, process lock, resource/task handle,
retrieval surface, durable Profile field, or schema change was introduced.

RED/GREEN: fresh pre-implementation T006 run failed all 65 cases on missing
ObservationRuntime. The same unchanged cases passed after implementation;
foundation plus runtime focus passed 154 cases. The full hardware-free suite
collected 740: 719 passed, exactly 21 expected T007 missing-composition failures,
zero errors/skips. JUnit inspection verified the failure sets. Full pytest
exits 1 as intended; this is not complete runtime acceptance or a GREEN full gate.
Ruff passed; mypy reported no issues in 38 files; all three import contracts kept
(30 files, 68 dependencies); diff whitespace clean. Static checking caught an
optional RunId dereference in the task name; using the admitted local RunId
resolved it without changing behavior or tests.

Progress headers, T008 checkbox, quickstart, status, and this record were updated.
One code-only Graphify update produced 2,234 nodes, 5,199 edges, 108 communities;
24 labels refreshed from hubs. The known non-fatal zero-node pyproject.toml
warning recurred. Generated output stays ignored; no semantic extraction ran.
Existing tests, Acquisition and adapters, dependencies, schema-v1, architecture
rules, and committed baseline 6d10cf7 are unchanged; no commit was created.

T009–T028 remain unchecked. Basic composition, integration readback acceptance,
US2 cancellation/failure/transfer validation, and US3 autonomous termination
remain unimplemented/unaccepted. Normal-path evidence does not claim those
semantics. No Spec Kit stage or physical-hardware action/acceptance occurred.

## 2026-10-03 — Feature 005 T007 Basic Composition Contracts Staged RED

Delivered only the authorized T007 test step and stopped. Added
`core/tests/contract/test_observation_composition.py` with 21 cases. Each fails
explicitly on the missing Basic composition module/API (T009), without
collection errors, skips, xfail, production stubs, or lifecycle implementation.
A small admission probe captures guard/admission inputs and the preparation
callable; it implements no run ownership. T006 remains the runtime contract.

Contracts enforce context guard before any Profile read/stat; bounded explicit
Profile resolution before admission even while busy; invalid/missing/oversized/
unsupported Profile failure before busy; and no rejected journal create/open,
backend construct/open, Acquisition construction, destination inspection, or
hardware discovery. Preparation uses real temporary SQLite journals and the
actual Basic adapter with the existing private fake serial injection. Tests
cover exact path/policy/configuration, journal before unopened backend
construction/open, single existing Acquisition startup, no existing-file
overwrite/reopen, and captured values after Profile replacement/removal.

Fixture smoke passed bounded capture, immutable resolved values, exact journal
policy, fake-only Basic open, acknowledged segment provenance, single reader/
close, and existing-file protection, using existing production contracts only.
The initial full run found one new test-guard defect: a direct serial.tools
import violated the existing repository serial-surface contract. Reproduction
and source inspection isolated that import; a named fail-closed monkeypatch
target replaced it. The contract was not changed or exempted and passed again.

Final validation through uv with --no-sync and temporary UV_CACHE_DIR: Ruff
clean; mypy no issues in 38 files; all three import contracts kept (29 files,
66 dependencies); focused T001–T005 tests 89 passed; T007 focus 21 expected RED.
Full pytest collected 740, with 654 passed and exactly 86 expected failures:
65 T006 missing-runtime assertions and 21 T007 missing-composition assertions.
JUnit inspection verified those exact sets and zero errors/skips. This is an
intentional RED checkpoint, not a GREEN full gate or complete-feature acceptance.

Feature progress headers, task checkbox, quickstart, status, and this history
record were updated. T008–T028 remain unchecked. Production files, existing
foundation/T006 tests, shared fixtures, dependencies, schema-v1, and architecture
contracts are unchanged. No Spec Kit stage, Graphify update, or commit was run.
No physical hardware was discovered, enumerated, opened, accessed, or validated.

## 2026-10-03 — Feature 005 T006 Normal-Runtime Contracts Staged RED

Delivered only the authorized T006 test step and stopped. Added
`core/tests/contract/test_observation_runtime.py` with 65 collected cases over
the documented public lifecycle surface. A small test-only Protocol keeps
strict typing possible before the runtime implementation exists. Missing
ObservationRuntime produces explicit assertion failures rather than collection
errors; no fake runtime, production stub, skip, or xfail conceals the RED state.

Contracts cover construction on the owning running loop/thread; rejection
without a running loop before lock/task creation; same-context attach/detach
and nonmutating synchronous status; wrong context before locks, argument
validation, mutation, or preparation; and no rebinding after termination/loop
closure. The 45-case calling-context matrix covers attach/detach/status on
inactive/active/terminated runs in five contexts, including moving the same
loop to another thread to test thread binding separately from loop identity.
Returned immutable snapshots may be read elsewhere without runtime access.

Normal-run cases cover direct resolved-Profile busy rejection without any
Profile I/O/preparation; gated attaching/active/detaching status and committed
identity facts; fresh run/session/connection identities; exact policy by value;
idempotent inactive/settled detach; and physical close/consumer completion/final
append before recorder close. All resource work uses test-local deterministic
gates, the existing Basic-shaped normalized fake, and a real temporary SQLite
journal. Test watchdogs bound the checks, not production lifecycle behavior.

A fixture smoke check found that the Basic-shaped fake's default opaque
provenance intentionally lacks a durable envelope. Root-cause inspection of
the existing durable acquisition tests and feature-003 contract led to a
test-local normalized PersistedConnectionProvenance; the shared fixture and
journal code were unchanged. The corrected harness passed existing Acquisition
start/stop/join with exact teardown ordering and no runtime substitute.

Final verification through uv with --no-sync and a temporary UV_CACHE_DIR:
Ruff clean; mypy no issues in 37 files; all three import contracts kept (29
files, 66 dependencies); earlier feature-005 tests 89 passed; full pytest
collected 719, with 654 passed and exactly 65 expected T006 failures. JUnit
inspection confirmed every failure is the missing-runtime assertion in the new
file, with zero errors/skips and no earlier failure. Full pytest exits 1 as
intended; this is not a GREEN full software gate or feature acceptance.

Task/progress headers, quickstart, status, and this history record now describe
the RED checkpoint. T007–T028 remain unchecked; production runtime/composition,
cancellation/failure/disconnect implementation, delivery, and all accepted
deferrals remain unbuilt. No Spec Kit stage or Graphify update was run for this
test-only step; no dependency, architecture contract, schema-v1, or production
file was changed. The committed baseline remains 6d10cf7; no commit was created.
No physical hardware was discovered, enumerated, opened, accessed, or validated.

## 2026-10-03 — Feature 005 Foundations Complete (T001–T005 Only)

Completed the explicitly authorized first group and stopped at T005. The
accepted committed baseline remains `6d10cf7` on `main`; these changes are in
the working tree, with no new commit. T006–T028 are unchecked. No Spec Kit
stage was rerun, and no ObservationRuntime orchestration, Basic composition,
delivery, or deferred feature was implemented.

T001 confirmed the baseline and affected Acquisition/Basic/Profile/SQLite
consumers with 390 passing hardware-free tests. T002/T003 added the validated
frozen AcquisitionSnapshot and generation-captured join_terminated barrier.
Descriptor is distinct from acknowledged segment provenance; origin-reset
publication follows acknowledgment. Disconnect trigger is retained before a
possibly failed final append. The actual first non-close primary failure is
tracked at occurrence separately from physical-close failure and release
certainty, without decoding legacy failure. Legacy method returns, failure
objects, restart admission, Backend/evidence contracts, and schema-v1 remain
unchanged. The barrier waits startup settlement and actual consumer/close tasks,
returning its captured generation even if a newer start has replaced current
status.

T004/T005 added immutable run/state/intent/reason/issue/status values,
normalized request/preparation failures, and the minimal preparation/recorder
Protocols. RuntimeStatus computes admissibility from the exact state/settlement/
physical/recorder predicate and rejects impossible status combinations.
Prepared resources expose the immutable policy for comparison by value with
Profile; enforcement on runtime transfer remains orchestration work. Import
contracts now place runtime above Acquisition and prohibit runtime importing
adapters, with no exemption or dependency change. Complete Profile/session
association remains in-memory only as specified, not a new durable field.

RED/GREEN evidence: 15 initial Acquisition scenarios failed on missing additive
APIs, then passed. Review caught missing constructor validation that could admit
raw objects/non-boolean facts into the new snapshot; seven additional cases
failed with DID NOT RAISE, then passed after validation. All 67 runtime-value
cases failed because the planned module was absent, then passed; this includes
the complete 48-case state/owner/cleanup matrix. The final focused set passed
131 tests. No unresolved defect was found; existing cleanup-attestation limits
and legacy failure distinctions remain intentional documented constraints.

The full required gate passed through uv with --no-sync and an explicit
temporary UV_CACHE_DIR: Ruff clean; mypy no issues in 36 files; Import Linter
kept all three contracts (29 files, 66 dependencies); pytest passed 654 tests
with zero failures/skips; git diff --check clean. No lockfile changed. Partial
status, feature-artifact progress headers, and task checkboxes were updated.

One Graphify 0.9.48 code-only incremental update captured the new module and
shared interface additions: 2,113 nodes, 4,824 edges, 112 communities. It
reported the known non-fatal zero-node pyproject.toml warning and refreshed 23
community labels from their hubs. Generated output remains ignored; no semantic
extraction or labeling call was made.

All validation used fakes and temporary journals with the existing fail-closed
serial sentinel. No physical device was discovered, opened, modified, accessed,
or validated. Runtime orchestration and event-loop enforcement remain unbuilt;
Basic/SQLite composition, service/CLI, Monitor/TX/Control, reconnect/handoff,
session catalogue/durable Profile metadata, Enhanced/MCP/AI, and hardware
acceptance remain deferred.

## 2026-10-03 — Feature 005 Observation Runtime Planning Complete

Completed the explicitly authorized lean Spec Kit specify → plan → tasks
workflow for `005-observation-runtime`, using the repository's sequential
directory numbering. Git remains on `main`; no branch or commit was created.
The committed production baseline remains `6d10cf7` and features 001–004 remain
accepted. Feature 005 has eight planning artifacts and 28 unchecked future
implementation tasks; no production code or implementation test was written.

The internal contract defines inactive/attaching/active/detaching/terminated/
failed states, fail-fast busy attach, joined detach, one shielded generation
owner, immutable Profile activation, journal-before-backend startup, and
Acquisition/backend/consumer settlement before recorder close. Cancellation
requests stop and joins cleanup instead of cancelling physical/journal work;
partial failures preserve primary and bounded cleanup facts. Created journals
remain after failed/cancelled startup and later attaches create fresh sessions.

Profile/session association is one in-memory current/last run mapping only.
Existing durable policy and effective segment provenance remain historical;
schema-v1 is unchanged, and complete Profile or DUT/Profile identity recovery
after restart is not claimed. The plan adds only minimal normalized Acquisition
snapshot/join facts and a concrete Basic/SQLite composition edge, with shared
lifecycle tested identically against the existing Enhanced-shaped fixture.

Read-only research identified absent cleanup attestations in failed Basic open
and most failed journal-create paths. The design conservatively blocks reuse
of that runtime instance rather than silently inferring release or expanding
adapter contracts. Process restart/replacement is not proof of release.
Unexpected disconnect ends the run without automatic reopen and remains its
observed cause even if caller stop or cleanup failure races it.

Planning verification checked all eight artifacts for relative links, balanced
fences, missing template placeholders, sequential FR/SC/task identifiers,
required task format/file paths, story counts, parallel markers, and scope.
The document audit passed: 30 requirements, seven outcomes, 28 unchecked tasks
(US1 six, US2 seven, US3 five, setup/foundation/review ten), six parallel-marked
test tasks, and a 26-line Resume Here section. Diff whitespace and final changed
paths were also reviewed. uv's initial audit invocation could not write the
default cache in the sandbox; rerunning with an explicit temporary cache and
`--no-sync` succeeded without dependency changes.

No Ruff/mypy/Import Linter/pytest implementation gate was run: this task changed
planning/status/history documents only and introduced no executable code.
Future software validation is explicit in the task list/quickstart. No Graphify
update was required for documentation-only changes. Service/delivery, workflows,
TX/Control, reconnect/handoff, session catalogue, durable Profile metadata,
Enhanced production behavior, MCP/AI, and physical acceptance remain deferred.
No hardware was discovered, opened, accessed, modified, or validated.

## 2026-10-03 — Feature 004 Observation-Only DUT Profile Complete (T001–T021)

Completed the feature-004 production implementation and completion
documentation through T021. The software resolves one explicit caller-supplied
path containing strict, human-authored UTF-8 TOML with
`profile_version = 1`. The closed format is bounded to 65,536 serialized bytes;
resolution reads at most 65,537 bytes and enforces that ceiling on the captured
bytes before decoding or parsing. It returns immutable backend-neutral values
for DUT identity/name, explicit Basic selection and exact expected device, UART
configuration, DTR/RTS open intent, observation policy, and the existing
feature-003 `SessionPolicy` constructed directly from all six explicit finite
limits.

Profile v1 requires RX and evidence recording to remain enabled as mandatory
observation invariants. Its current permissions remain fail closed: UART TX,
semantic Control, and automatic reconnect are disabled. Opposite values and
recognized TX, Interact/console, Control, reconnect, or reacquire configuration
fail explicitly as `unsupported_behavior`; they are never silently ignored.
The deterministic failure matrix also distinguishes filesystem failures,
oversized input, invalid syntax, incompatible version, missing/unknown fields,
invalid values, and unsupported backends without exposing a parser tree,
partial result, or raw exception cause/context.

The generic Profile module contains no Basic or pySerial implementation type.
A TOML adapter owns filesystem/format resolution, and a separate pure Basic
adapter-side translator maps the resolved snapshot field-for-field into the
existing feature-002 `BasicSerialOpenRequest`. Resolution and translation do
not enumerate or open a device, construct a backend, start acquisition, create
a journal/session, or own lifecycle. No registry or generalized Profile manager
was introduced.

T018's final implementation review found and corrected four bounded defects.
Recognized Interact/console configuration had been classified as an unknown
field rather than unsupported behavior; invalid path values could leak a raw
`ValueError`; normalized failures retained raw exceptions through
`__context__`; and the quickstart import-search exclusion did not match the
nested Basic adapter path. Focused RED/GREEN regressions cover the behavioral
corrections, and the search was corrected and rerun.

Post-correction software validation passed 217 focused feature-004 tests and
565 full-repository tests with no failures or skips. Ruff passed, mypy reported
no issues in 33 source files, all 3 Import Linter contracts were kept after
analyzing 28 files and 56 dependencies, and `git diff --check` passed.

T020 confirmed that the shared Profile module and two adapter modules satisfy
Graphify's structural-change criteria, then ran the one required code-only
incremental update with Graphify 0.9.48. The ignored graph now contains 1,928
nodes, 4,471 edges, and 96 communities. Graphify reported one non-fatal
zero-node source (`pyproject.toml`) and refreshed 23 community names from their
hubs after the community set changed. No semantic/LLM extraction ran and no
generated Graphify output entered version control.

T021's fresh final gate passed: Ruff reported no violations; mypy reported no
issues in 33 source files; Import Linter kept all 3 contracts after analyzing 28
files and 56 dependencies; pytest passed 565 tests with 0 skipped and 0 failed;
and `git diff --check` passed. Feature 004 is software-complete and ready for
commit. The final pre-commit review corrected stale spec/status completion
metadata and found no production-contract defect.

Lifecycle and ownership, session orchestration, service/HTTP and authentication,
CLI, Monitor/follow, TX/Interact/console execution, semantic Control execution,
reconnect, release/reacquire/handoff, Enhanced, MCP, Profile discovery/default
paths, Profile writing/migration/overlay/reload, and numerical product defaults
remain deferred. No physical hardware was enumerated, opened, accessed,
modified, or validated, and no electrical or platform acceptance is claimed.

## 2026-10-01 — Feature 003 Durable Evidence Journal Complete (T001–T030)

Completed the feature-003 implementation and completion documentation for one
SQLite-backed durable session journal. The delivered software provides
immutable finite session policy, generic opaque provenance envelopes, canonical
exact-byte evidence storage, serialized durable append and reopen, rolling
bounded retention with a coalesced marker, stable reference resolution, bounded
fixed-snapshot raw pages, and fail-closed compatibility/corruption handling.
SQLite connections remain confined to their journal-owned single worker and
shared acquisition depends only on the backend-neutral recorder contract.

The accepted durability guarantee is intentionally limited to clean reopen and
tested software process-crash recovery under committed SQLite transactions.
Exactly-once retry after commit-before-return ambiguity, arbitrary power-loss or
lying flush hardware, and filesystem, media, directory, backup, or live-copy
survival are explicitly not guaranteed.

T028's final review found one lifecycle defect: cancellation of create/open
after worker submission could discard a successful bootstrap result without
closing its SQLite connection. A parametrized RED regression reproduced both
paths. The correction waits for the bootstrap worker, recovers a successful
result, closes the connection on that same owning worker, and then propagates
cancellation. The focused regression passed 2 tests, journal contract/recovery
passed 78 tests, the complete feature-003 group passed 137 tests, and the full
repository passed 347 tests with no failures. Ruff, mypy, all three Import
Linter contracts, and `git diff --check` passed in the T030 software validation.

Final pre-commit review found one further boundedness defect: corrupt persisted
sequence metadata could make open validation materialize an enormous expected
range before reporting corruption. A focused RED regression intercepted the
attempt at the signed-64-bit terminal value. Validation now compares row count
and contiguous sequence values without allocating from the persisted span; the
regression is GREEN. This is a fail-closed corruption correction only and adds
no persistence framework, migration, repair, or delivery behavior. The
corrected final candidate passed 348 tests with no failures or skips; Ruff,
mypy, all three Import Linter contracts, and `git diff --check` passed.

Graphify's structural-change criteria were evaluated. The one earlier
feature-003 incremental update already captured the new SQLite adapter and
shared provenance interface (1,426 nodes, 3,039 edges, 78 communities); T028's
localized private helper and regression test did not require another update.
No physical hardware was enumerated, opened, accessed, modified, or validated,
and no power-loss acceptance was performed.

## 2026-10-01 — Feature 003 Fail-Closed Open Validation (T026)

Made the T025 compatibility/corruption matrix GREEN with a bounded SQLite
adapter correction. Open now forces rollback-journal processing before
application validation, classifies stored decode failures as open failures,
maps malformed persisted invariants to corrupt-journal outcomes, and proves a
validated connection writable with a rolled-back no-op update before applying
the physical page ceiling. Supported generic envelopes still round-trip unknown
backend provenance kind/schema values opaquely, while SQLite operational errors
retain their normalized operational classifications. No migration, repair,
salvage, delivery behavior, or physical hardware work was added. The complete
feature-003 group passed 135 tests and the full repository passed 345 tests.

## 2026-10-01 — Feature 003 Compatibility/Corruption RED Matrix (T025)

Added 15 software-only contract cases for incompatible application, store,
record, and generic provenance-envelope versions; opaque unknown backend
provenance; missing schema objects; malformed metadata/payload invariants;
aggregate/sequence corruption; failed integrity checks; locked/read-only opens;
source preservation; and the rollback-recovery-before-validation exception.
The focused selection produced the intended 8 failures and 7 passing controls.
All 120 earlier feature-003 tests remain GREEN. No production code or physical
hardware was touched.

## 2026-10-01 — Feature 003 Pagination Validation Gate (T024)

Completed the software-only validation checkpoint before compatibility and
corruption work. The exact quickstart retention/reference/retrieval selection
passed 40 tests; the complete durable-journal model, codec, contract, recovery,
and acquisition-integration group passed 120 tests; and feature-001 evidence
ordering and timestamp regressions passed 64 tests. The full repository passed
330 tests. Ruff, mypy, all three Import Linter contracts, and
`git diff --check` passed. No defect was found and no production or test code
changed. No physical hardware was accessed.

## 2026-10-01 — Feature 003 Stable Pagination Continuation (T023)

Completed fixed-snapshot continuation and explicit between-page expiry for the
bounded raw evidence journal. Continuations now preserve the first page's
exclusive snapshot boundary, exclude later appends, report a newly expired
cursor-to-low-water interval with the current coalesced retention marker, and
resume retained sequence-key retrieval without changing T022's page bounds or
whole-record behavior. Both remaining T021 RED cases pass. No external cursor
encoding, delivery schema, or physical hardware behavior was added.

## 2026-10-01 — Feature 003 Bounded Raw Retrieval (T022)

Implemented policy-capped, whole-record raw evidence pages ordered by durable
sequence, with charged-byte accounting, oversized-next-record reporting, and
typed keyset continuation cursors. Retrieval values now live in the planned
backend-neutral `evidence.py` contract; SQLite remains confined to its adapter
and journal worker. T020's nine pagination cases pass. Five T021 cursor,
lock-release, and cancellation cases pass; fixed-snapshot continuation and
between-page expiry remain intentionally RED for T023. No physical hardware
was accessed.

## 2026-09-30 — Feature 003 Durable Journal Foundation (T001–T005)

Completed the software-only durable value, codec, and SQLite bootstrap
foundation. No physical device was enumerated, opened, modified, or validated.

### Delivered

- Added immutable session identity, finite session policy with independent
  retrieval ceilings, signed-64-bit persisted counter/sequence validation,
  stable references, retention endpoints, retrieval values, and normalized
  journal failures.
- Added generic provenance envelope version 1 with opaque backend kind/schema
  version and scalar-only sorted fields. Basic serial owns its flattened
  mapping; unknown conforming backend values remain opaque and round-trip.
- Added strict canonical JSON metadata codecs for all four current evidence
  variants, exact RX BLOB handling, and deterministic logical byte charge.
- Added one-session SQLite schema-version-1 create/open/close with `DUTM`
  application identity, 4096-byte pages, rollback `DELETE`, `synchronous=FULL`,
  persisted immutable policy, and no added runtime dependency.
- Persisted `max_database_pages` as policy while reapplying and verifying
  `max_page_count` on every writable create/open. Oversized databases and an
  unavailable requested ceiling have distinct normalized failures.
- Confined each connection's creation, use, and close to one journal-owned
  `ThreadPoolExecutor(max_workers=1)` worker with one asyncio serialization
  gate. Shared Core still does not import adapters; no architecture exemption
  was added.
- Stopped before durable append, retention, retrieval, recovery subprocesses,
  cancellation/commit ambiguity, delivery surfaces, or hardware behavior.

### Validation Evidence

- RED: the initial model suite failed 45 tests for missing feature-003 values;
  the codec/bootstrap suite failed 14 tests for absent codecs/journal behavior;
  two follow-up invariant tests failed before their minimal validations were
  added.
- `uv run --frozen pytest core/tests/unit/test_evidence_journal_model.py
  core/tests/unit/test_sqlite_evidence_codec.py
  core/tests/contract/test_sqlite_evidence_journal.py -q`: 62 passed.
- `uv run --frozen ruff check .`: passed.
- `uv run --frozen mypy .`: no issues in 25 source files.
- `uv run --frozen lint-imports`: 3 contracts kept, 0 broken.
- `uv run --frozen pytest`: 272 passed, 0 skipped, 0 failed.
- `git diff --check`: passed.
- No physical hardware was touched.

## 2026-09-30 — Feature 002 Basic Serial Backend Adapter (T001–T020)

Completed the first production Basic serial adapter behind feature 001's
normalized backend contract. This is a software-only completion record; no
physical serial device was accessed or validated.

### Delivered

- Added and locked pySerial 3.5 plus types-pyserial 3.5.0.20260712, confined
  pySerial imports and implementation types to
  `dutchmate_core.adapters.basic_serial`, and extended shared Core only with
  opaque immutable connection provenance and normalized failure values.
- Required an exact explicit platform device name. The adapter performs no
  enumeration, discovery, URL handling, automatic choice, implicit default, or
  fallback selection.
- Constructed `serial.Serial(port=None)`, configured the complete supported
  UART, flow-control, exclusivity, and line-state intent while closed, and
  called `open()` exactly once after configuration. Successful provenance
  preserves selected/opened names and requested/effective configuration.
- Applied DTR and applicable static RTS intent before open; under RTS/CTS, RTS
  remains driver-managed. Provenance records the preconfigured-while-closed
  strategy and honestly marks glitch-free transition as not guaranteed and
  physical electrical state as not verified. This is serial-open handling, not
  semantic Control.
- Reported only `uart_receive`. Successful connections receive fresh
  connection/segment identity and a fresh host-observation timestamp
  domain/origin; acquisition copies adapter provenance unchanged without a
  Basic identity branch.
- Implemented one sequential blocking `read()` at a time through
  `asyncio.to_thread`, capturing `monotonic_ns` immediately after read return
  in the same worker. Normalized RX preserves exact bytes and return order;
  empty reads emit nothing, and no adapter queue, prefetch path, or concurrent
  reader exists.
- Normalized open, read, and close failures without leaking pySerial/OS objects.
  Device loss is emitted only when stable exception attributes positively
  identify disappearance; ambiguous failures remain `read/io_failure`, and
  exception message text never controls classification.
- Implemented caller/lifecycle-thread `cancel_read()`, mandatory outstanding
  read completion before one physical close, and idempotent repeated/concurrent
  close. Acquisition remains non-restartable through physical teardown,
  preserves an established primary failure, blocks restart after unconfirmed
  release, and emits no duplicate terminal segment evidence.
- Added fake-driven adapter-through-acquisition coverage for immutable
  provenance, ambient exact-byte RX, host timestamp provenance, device loss,
  ambiguous read failure, explicit stop/close ordering, and second-owner
  rejection.
- Added fail-closed hardware-safety guards: the default test suite cannot invoke
  the physical serial factory, and static tests reject serial enumeration,
  pySerial URL handlers, URL-like selectors, or automatic device selection.

### T019 Correction

Final diff review found an FR-024 defect: a failing `cancel_read()` caused the
adapter to skip joining the outstanding blocking read and proceed to physical
close. A focused RED regression observed one physical close while the read was
still active. The corrected close path always awaits that read before its
single physical close while retaining the normalized cancellation failure;
the focused contract suite then passed 56 tests.

### Validation Evidence

- `uv run --frozen ruff check .`: passed.
- `uv run --frozen mypy .`: no issues in 20 source files.
- `uv run --frozen lint-imports`: 3 contracts kept, 0 broken.
- `uv run --frozen pytest`: 210 passed, 0 skipped, 0 failed.
- `git diff --check`: passed.
- Focused feature-002 model, adapter-contract, integration, and safety groups
  passed; all feature-001 regression groups remained GREEN.
- Focused diff/search review found no Basic identity branch or pySerial object
  outside the adapter boundary; no discovery/URL-handler path, raw exception
  leak, concurrent/duplicate RX path, timestamp-based evidence ordering,
  semantic Control, TX, reconnect, delivery surface, Enhanced implementation,
  firmware, or MCP was introduced.
- No physical serial hardware was enumerated, opened, modified, or validated.
  Platform/electrical acceptance remains explicitly deferred.

## 2026-09-29 — Feature 001 Lifecycle Correction

Closed the teardown and terminal-state gaps found in the final pre-commit
review.

### Delivered

- Acquisition now remains non-restartable in `stopping` until its one physical
  connection close finishes; successful teardown exposes `stopped` only after
  close completion.
- Each acquisition consumer captures its generation's termination event, so a
  prior task cannot signal a later generation.
- Backend-open failure now enters `failed`, signals termination, preserves and
  re-raises the original exception, creates no connection/segment evidence or
  consumer task, and permits a later valid start.
- Unexpected normal stream completion now records a transport-failure segment
  end before teardown.
- Close failure cannot strand acquisition in `stopping`. An existing primary
  recording/transport failure is preserved; otherwise close failure becomes the
  terminal transport failure. Because physical close is unconfirmed, a new
  owner remains rejected.
- Removed the deferred `ownership_lost` segment reason and ownership-loss
  lifecycle wording from the focused feature 001 documents.

### Validation Evidence

- RED: 5 focused lifecycle tests failed for the intended missing behavior:
  premature `stopped`, open failure left in `starting`, absent stream-end
  evidence, premature `failed` during close, and duplicate terminal evidence
  when close failed.
- GREEN: focused acquisition suite passed 29 tests; feature quickstart suites
  passed 31 model/backend tests and 35 evidence/acquisition tests.
- `uv run --frozen ruff check .`: passed.
- `uv run --frozen mypy .`: no issues in 15 source files.
- `uv run --frozen lint-imports`: 2 contracts kept, 0 broken.
- `uv run --frozen pytest`: 66 passed, 0 skipped, 0 failed.
- `git diff --check`: passed.
- No physical hardware was touched.

Feature `001-rx-continuous-evidence` is ready to commit against its focused
specification. Real adapters, durability, workflows, delivery surfaces, and
later phases remain deferred.

## 2026-09-29 — Feature 001 Timestamp-Regression Correction

Closed the final conformance gap found during T019–T021 review.

### Delivered

- Added acquisition regression coverage for decreasing timestamps and proved
  the original path incorrectly stopped normally while recording the offending
  observation.
- Added a per-segment baseline shared by timestamped RX/loss observations. The
  baseline advances only after successful evidence recording and resets after a
  successfully recorded timestamp-origin segment transition.
- A decreasing timestamp in the current domain/origin now ends the segment with
  an explicit transport failure. Earlier evidence and sequence values remain
  unchanged; the offending observation is not recorded.
- Strengthened origin-reset coverage to accept a lower timestamp in the new
  domain/origin, while preserving equal-timestamp behavior within a segment.

### Validation Evidence

- RED: 2 focused tests failed because acquisition returned `stopped` instead of
  `failed` for RX→RX and loss→RX timestamp regressions.
- GREEN: focused acquisition suite passed 24 tests.
- `uv run --frozen ruff check .`: passed.
- `uv run --frozen mypy .`: no issues in 15 source files.
- `uv run --frozen lint-imports`: 2 contracts kept, 0 broken.
- `uv run --frozen pytest`: 61 passed, 0 skipped, 0 failed.
- `git diff --check`: passed.
- No physical hardware was touched.

Feature `001-rx-continuous-evidence` now satisfies its focused specification.
Real adapters, durability, workflows, delivery surfaces, and later phases remain
deferred.

## 2026-09-29 — Feature 001 Validation and Documentation (T019–T021)

Completed the T019–T021 validation/documentation slice for the first Phase 1
software foundation. The feature remains open because final specification
review found one implementation gap not covered by the passing suite.

### Delivered

- Established the Python 3.14 uv workspace and `dutchmate-core` package.
- Added the normalized backend and single-consumer connection boundary.
- Added exact-byte RX evidence, Core-assigned journal sequence ordering,
  connection/segment provenance, timestamp-domain/origin validation, and
  observer-scoped loss evidence.
- Added exclusive continuous acquisition, explicit disconnect/stop/failure
  behavior, and timestamp-origin segment transitions.
- Proved backend-neutral shared behavior with hardware-free Basic-shaped and
  Enhanced-shaped test fixtures. The Enhanced-shaped fixture is not a real
  backend and simulates no helper protocol, firmware, USB framing, or hardware
  timing.
- Added import-linter contracts for inward Core module dependencies and the
  production/test-framework boundary.

### Validation Evidence

- `uv sync --all-packages --dev`: resolved 20 packages; audited 19 packages.
- Focused quickstart suites: 31 model/contract tests and 28
  evidence/acquisition tests passed.
- `uv run --frozen ruff check .`: passed.
- `uv run --frozen mypy .`: no issues in 15 source files.
- `uv run --frozen lint-imports`: 2 contracts kept, 0 broken.
- `uv run --frozen pytest`: 59 passed, 0 skipped, 0 failed.
- `git diff --check`: passed.
- Scope scan found no Basic identity branch, serial/framework dependency,
  Enhanced implementation, or later-phase product code above the normalized
  boundary.
- No physical hardware was touched.

### Limitations Retained

Real Basic serial transport and hardware acceptance, durable persistence and
retention, workflows, service/HTTP, CLI, Enhanced hardware/protocol/firmware,
and MCP remain deferred. The in-memory journal and both backend shapes are
software test infrastructure, not production adapters or durability claims.

Graphify's initial code-only structural index was generated for the new shared
interfaces. Its diagnostic reported 29 dangling endpoints and 62 same-endpoint
collapsed-edge candidates; documentation semantic indexing was unavailable
because Graphify's optional backend package is not installed.

Final specification review found that acquisition does not reject an undeclared
decreasing timestamp in the current domain/origin, contrary to the feature
specification's Edge Cases. No production behavior was added because this slice
was restricted to T019–T021. A focused red-green correction remains required
before feature `001` can be declared complete. That gap was closed by the newer
record above.
