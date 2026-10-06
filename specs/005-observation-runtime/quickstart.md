# Quickstart Validation: Observation Runtime

T001–T028 are complete. T028's fresh full gate passes: Ruff clean, mypy 40 files
clean, three import contracts kept (31 files/77 dependencies), 924 hardware-free
pytest cases passed with zero failures/errors/skips, and clean diff/whitespace
checks after completion documentation. At T028, feature 005 was software-complete
and ready for final human review/commit. That checkpoint claimed no commit, human
acceptance, physical-hardware acceptance or Phase 1 completion. Earlier checkpoints below retain
their original evidence; current completion is in development status/history.

T001–T005 foundations are GREEN. T008 implements the normal ObservationRuntime
lifecycle and all 65 T006 cases are GREEN.
T009 implements the explicit Basic composition edge and all 21 T007 cases are
GREEN. T010 adds six end-to-end runtime/Basic/SQLite readback cases, all GREEN.
T011 verifies US1/completed-feature regressions and corrects normalized runtime
rejection propagation through standard generator context managers.

T015 implements request/cancellation behavior and makes all 35 unchanged T012
cases GREEN after a fresh run with 20 RED failures and 15 passes.
T016 makes all 22 unchanged T013 preparation cases GREEN after 21 RED failures
and one pass. T017 makes all 32 unchanged T014 cases GREEN after 29 RED failures
and three passes, and all 27 T013 cases now pass. T017 production changes are
confined to runtime.py. T018 verifies US2 with no production/test changes.
T019 adds only shared test-fixture gates/counters and ten fixture contract checks.
T020 adds 34 runtime termination contracts (33 expected RED failures/one GREEN).
T021 adds 24 identical fixture lifecycle/readback cases (16 GREEN/eight RED).
T022 makes all 58 unchanged T020/T021 cases GREEN after a fresh 41 RED/17 GREEN
baseline. T023 verifies US3/current/completed-feature regressions and architecture
without a code/test correction. T024 corrects preparation exception transport
after full contract/scope review. T025 runs all pre-final focused/scope commands
successfully; T026 reconciliation and T027's one code-only structural update are
complete. T028 passed the fresh final gate and stopped there; further work or
commit required a new instruction. Current commit/progress status is in development status.

Current US1 happy-path regression checks:

```bash
rtk proxy uv run --no-sync pytest core/tests/contract/test_acquisition_lifecycle.py core/tests/unit/test_runtime_model.py -k 'not t024'
rtk proxy uv run --no-sync pytest core/tests/contract/test_observation_runtime.py -k 'not t012 and not t014 and not t020'
rtk proxy uv run --no-sync pytest core/tests/contract/test_observation_composition.py -k 'not t013'
rtk proxy uv run --no-sync pytest core/tests/integration/test_observation_runtime.py -k 'not t021'
```

The first command passes 91 foundation/rejection cases; the second passes 65 normal
runtime cases; the third passes 21 composition cases; the fourth passes six
readback cases. The combined feature-005 focus passes 183; completed-feature
regressions remain GREEN (565 cases). At T024, full default pytest passed 924
with no failures/errors/skips; no unrestricted full run is performed in T025.
Whole five-file feature-005 focus still passes 349 after 14 T024 regressions;
all 335 earlier feature cases and ten T019 fixture checks remain GREEN.
T028 now confirms the same 924-pass full count with a fresh gate and final diff
review. At that checkpoint, the software-only implementation was ready for final human review/commit;
this does not claim hardware acceptance or a completed Phase 1.

Current T025 focused-scenario/scope result:

All 21 pytest commands printed in this quickstart before the final-gate section
were executed with their stated file selections/filters. All pass with zero
failures/errors/skips. The three canonical focused commands pass 105 foundational/
value, 214 runtime/composition and 30 integration cases; combined feature focus
passes 349. Completed-feature selection passes 565 and T019 fixtures ten.
US1 remains 91/65/21/six; T024 correction check 15; US3 58, including T020 34 and
T021 24; US2 94 (T012 35/T013 27/T014 32), T016 preparation subset 22, and
Acquisition regressions 64. Excluding T020/T021 now passes 291, including T024.

The five architecture/scope commands are also executed as defined: all three
Import Linter contracts kept (31 files/77 dependencies), Ruff clean, mypy 40
files clean, schema version 1, and no SQLite/model/Backend contract diff.
Additional runtime searches find no backend/framework/physical-device dependency,
backend-identity branch, legacy/private Acquisition access, reconnect, timeout
or new evidence reconstruction. Basic/SQLite construction remains at the edge.
No production/test correction, fixture/gate change, or hardware access.

Only one stale count description is clarified: the earlier-subset command now
selects 291, comprising 277 earlier cases plus 14 T024 regressions. Test selectors
and normative contracts are unchanged. The final implementation-gate block below
was deliberately unrun in T025; standalone architecture checks above did not
claim that gate. T026/T027 are complete and T028 now runs the final gate below.

Current T024 focused correction check:

```bash
rtk proxy uv run --no-sync pytest core/tests/unit/test_runtime_model.py -k 't024 or preparation_failure_is' --tb=short
```

This passes 14 new regressions plus the unchanged preparation normalization
case. Before correction, six failed and eight read-only-fact checks passed.
The defect was frozen/slotted PreparationFailure rejecting contextlib's standard
__traceback__ assignment, masking itself with TypeError. Runtime then reported
internal_contract_failure and lost known session/primary/cleanup facts. Direct
sync/async propagation and four actual temporary-journal runtime cases reproduce
the failure and now preserve the report, including independent failed-close facts.

Normalized preparation facts remain read-only for assignment/deletion; validation,
constructor/replacement/equality/hash behavior and fixed message are preserved.
Standard RuntimeError transport metadata remains writable and is never copied
into status. Only PreparationFailure changed in production; new model regressions
and a stale composition-test comment changed in tests. All original tests,
lifecycle/Acquisition/edge/fixture/persistence behavior remain unchanged.
The existing feature-003 frozen JournalFailure limitation is still outside scope.

Full tracked/untracked diff and FR-001–030/internal-contract review found no other
scope/contract defect. Runtime/edge consumers use documented module surfaces;
root exports, dependencies/lockfile, schema-v1/evidence/Backend contracts and
deferrals remain unchanged. Import rules add runtime coverage without exemptions.
Status contains no Profile-source/journal-destination path or growing history;
resolved device identity/effective provenance remain their existing typed values.
Focus passes 349/full 924, with Ruff/mypy/import/whitespace checks clean.
No physical hardware action/acceptance. T025 focused results are recorded above.

Current T023 regression/architecture checkpoint:

```bash
rtk proxy uv run --no-sync pytest core/tests/contract/test_acquisition_lifecycle.py core/tests/unit/test_runtime_model.py core/tests/contract/test_observation_runtime.py core/tests/contract/test_observation_composition.py core/tests/integration/test_observation_runtime.py --tb=short
```

At T023 this passed all 335 feature cases, including 58 T020/T021 US3 cases;
the command now passes 349 after T024's 14 regressions. The completed-feature
regression command below remains 565. At T023 full default pytest passed 910;
current full count is 924, including ten T019 fixture checks. JUnit confirmed
the full case set is feature focus plus completed regressions plus T019, with
no failures/errors/skips, and identical 12-case T021 sets GREEN on both shapes.

Review found no prohibited backend-identity branch, host-clock assumption,
stale-generation mutation or simulated future capability in shared code/tests.
Reported observability/capabilities drive loss/RX checks; Enhanced-specific
fixture emission/type checks stay at the test edge. Timestamp domains/origins
are preserved without conversion into a host clock. The owner joins notification
waiters and actual Acquisition work before recorder close/terminal settlement;
old captured results cannot publish into a new run. No correction was needed;
all production/tests/fixtures and deterministic gates remain unchanged.

Ruff/mypy/import checks pass; all three architecture contracts are kept without
new exemptions. Quickstart scope checks show schema-v1 and no diff to SQLite,
evidence/model or normalized Backend contracts. No physical hardware access or
Enhanced hardware claim. T024's full-diff/FR-001–030 review is now recorded above.

Current T022 GREEN check:

```bash
rtk proxy uv run --no-sync pytest core/tests/contract/test_observation_runtime.py core/tests/integration/test_observation_runtime.py -k 't020 or t021' --tb=short
```

All 58 unchanged cases pass after a fresh baseline of 41 failures/17 passes;
JUnit confirms identical RED/GREEN case sets. T022 changes only runtime.py in
source. The one generation owner races stop and public Acquisition termination
notifications, publishes detaching, and drains both waiters. Cancellation is
limited to unused Event notification waits; Acquisition startup/RX/backend-close/
join work remains owned and uncancelled. Actual consumer/close joins precede
recorder close and terminal settlement; no notification task survives settlement.

Active publication requires successful public start, acquiring snapshot with
no observed terminal trigger, and no pending stop. Observed terminal processing
is joined without submitting stop; explicit unobserved stop still calls
Acquisition.stop. Disconnect reason precedes startup/acquisition failure and
stop intent; actual primary/cleanup failures independently force failed state.
Direct primary_failure_kind/close_failed projection, committed historical
provenance and conservative certainty remain unchanged. No legacy/private
Acquisition access, evidence reconstruction, second reader, automatic reopen,
backend-identity branch, lifecycle timeout or abandonment.

At T022 feature focus passed 335/full 910; current counts are above. Ruff/mypy/import
checks and tracked/untracked whitespace pass. All tests/shared fixtures, other
production, contracts/schema, dependencies and architecture rules are unchanged.
No physical hardware access/acceptance; T023 review is now complete as recorded above.

Current T021 parameterized integration check:

```bash
rtk proxy uv run --no-sync pytest core/tests/integration/test_observation_runtime.py -k t021 --tb=short
```

All 24 cases now pass after T022. Initially each existing fixture factory ran
the same 12 cases with eight passes/four failures. The earlier GREEN cases cover
attaching/busy/active status, exact binary/ambient bytes, reported host/device
domains, commit-gated origin reset, scoped observer loss versus upstream loss
unobservability, explicit missing-RX rejection, actual physical-close/consumer
joining before recorder close, fresh explicit sessions with historical status,
bounded fixed-snapshot pages, rolling expiry, and unchanged schema-v1/policy/
provenance envelopes without durable Profile identity.

The eight initial RED cases exposed missing autonomous active-disconnect cleanup (two),
incorrect active delivery after immediate observed disconnect (two), and absent
autonomous RX-recording/transport-failure cleanup (four). They now pass identically
for both shapes after T022. The original six Basic/fake-serial composition cases are
unchanged and GREEN. Actual Acquisition/SQLite behavior remains authoritative;
only test-edge preparation supplies a serializable generic provenance envelope.
No fixture capability/timestamp/loss emulation or Enhanced Profile selection.
Test-owned gates and append/close acknowledgments hold actual work, and cleanup
drains it after assertions without proving a production cleanup outcome.

The new harness initially used the wrong capability attribute, decoded binary
payloads as UTF-8 during schema inspection, and assumed a complete result after
prefix expiry. Those test-only errors were corrected to use reported supports(),
inspect bytes directly, and assert the documented partial outcome. The recorded
eight initial failures were all intended runtime assertions, with no errors/skips/xfail.
Ruff/mypy/import checks pass. T021 itself changed no production/shared fixtures,
schema, normative contracts or dependencies; T022 now implements runtime observation.

Current T020 GREEN check:

```bash
rtk proxy uv run --no-sync pytest core/tests/contract/test_observation_runtime.py -k t020 --tb=short
rtk proxy uv run --no-sync pytest core/tests/contract/test_acquisition_lifecycle.py core/tests/unit/test_runtime_model.py core/tests/contract/test_observation_runtime.py core/tests/contract/test_observation_composition.py core/tests/integration/test_observation_runtime.py -k 'not t020 and not t021' --tb=short
```

The first command now passes all unchanged 34 cases after T022; initially it
recorded 33 failures/one pass. Eight active-disconnect and four
active recording/transport failure cases exposed missing autonomous cleanup;
four immediate-disconnect and two pre-active failure cases expose erroneous
active delivery after observed termination. Four attach/detach/cancellation
races, eight disconnect/primary/close combinations, and two cancelled-detach
waiters expose failure to prioritize actual disconnected trigger. One late
terminal/new-generation case requires autonomous settlement before new admission
and historical old-waiter results. The queued-but-unobserved disconnect case
passes: initial append failure prevents reader startup, so no disconnect is
claimed and no connection identity is invented.

Test-local gates wrap real Acquisition start return and consumer completion;
the legacy-failure tripwire remains active. Existing fixture event-delivery
gates distinguish enqueue from actual observation. Temporary SQLite journals
retain actual committed records. Cleanup releases gates and drains actual work
after assertions; it never attests production cleanup. No runtime timeout,
private runtime inspection, second reader, automatic reopen, xfail, or skip.
The second command confirms 291 cases GREEN: all 277 earlier cases plus 14 T024
regressions. Ruff/mypy/import
checks pass. T020 changed no production/integration tests, shared fixtures,
schema-v1 or normative contracts. T021 parameterization and T022's GREEN
implementation are recorded above.

Current T019 fixture GREEN check:

```bash
rtk proxy uv run --no-sync pytest core/tests/contract/test_backend.py -k t019 --tb=short
```

Ten checks, identical over both existing backend shapes, went RED for missing
gates then GREEN. Default-open FixtureLifecycleGate has entered/allow events;
open/read/event-delivery/consumer-exit/close checkpoints hold only when tests
explicitly clear allow. Open calls, claimed consumers, and close calls are
counted; close_calls counts invocations including no-ops, and a no-op never
re-enters the close checkpoint. Tests prove delayed return/delivery, exact binary
bytes and reported timestamp domain, one consumer, ordered terminal event,
independent close versus consumer completion, idempotent close, and reported
RX rejection without claiming a reader. Watchdogs bound tests only.

Existing Enhanced-shaped device timestamps, scoped observer loss, origin reset,
normalized non-serial disconnect, and capabilities are unchanged; rejection
uses the existing reported descriptor, without emulation or Profile selection.
All original 30 backend contract cases remain GREEN. Backend/Acquisition
compatibility passes 94 (40 backend, 22 additive lifecycle, 32 acquisition).
T019 changed no production/runtime tests or normative contracts. No GPIO,
helper protocol, USB/framing/firmware/timing behavior, or autonomous runtime
observer was added by T019. T020 runtime RED results are recorded above.

Current T018 US2 regression check:

```bash
rtk proxy uv run --no-sync pytest core/tests/contract/test_observation_runtime.py core/tests/contract/test_observation_composition.py -k 't012 or t013 or t014' --tb=short
```

All 94 cases pass (35 T012, 27 T013, 32 T014). Targeted Ruff/mypy over runtime,
composition, and their two contract test modules pass; all three Import Linter
contracts are kept (31 files, 77 dependencies). Full Ruff/mypy and hardware-free
pytest pass. Review found no reset/reclose path that clears uncertainty: terminal
detach returns the stored summary, rejection precedes preparation, original
close outcomes remain authoritative, and recorder close follows Acquisition
join. The composition edge keeps failed files/known IDs and never probes/reopens
them for identity. Deterministic gates and all production/test/configuration files
are unchanged. Schema-v1, backend, and evidence contracts have no baseline diff.
Shared runtime contains no backend-identity branch, legacy/private Acquisition
failure access, physical-device call, owner cancellation, or lifecycle deadline.

Current T012/T015 GREEN check:

```bash
rtk proxy uv run --no-sync pytest core/tests/contract/test_observation_runtime.py -k t012 --tb=short
```

The same unchanged 35 cases pass. The initial 20 RED failures showed cancelled
waiters escaping early: six startup attach cases, two internal-active-publication
cases, nine detach checkpoints, two first-stop-intent races, and one cancelled
old-generation waiter. T015 admits the first stop intent under the short lock
and waits for the captured owner despite repeated cancellation. Late handling
from a settled generation cannot alter a newer run. Cancelled callers raise
CancelledError after owner completion; post-success cancellation does not detach.
Other waiters receive their own generation's result. No owner cancellation,
second open, lock across external I/O, runtime deadline, or forced abandonment.
All earlier busy/context/startup/normal-detach checks remain GREEN. No tests,
Acquisition, Basic edge, journal/schema, or Profile behavior changed in T015.
Failure cleanup/status is now implemented by T017; autonomous terminal
observation remains later work.
Combined feature-005 focus excluding T013/T014 passes 218 cases.

T012 extends the test-local temporary-journal harness with RX/append gates and
controlled commit/close callbacks. It uses actual runtime APIs and existing
Acquisition/SQLite, with no substitute lifecycle implementation or changes to
shared fixtures. Test-only watchdogs bound test hangs, never runtime cleanup.
Busy assertions apply to already-resolved runtime.attach; the Basic edge's
bounded Profile read before admission remains intentional and unchanged.

Current T013 GREEN check:

```bash
rtk proxy uv run --no-sync pytest core/tests/contract/test_observation_composition.py -k t013 --tb=short
```

All 22 preparation cases now pass: four operation/category cases, one invalid
destination, nine failed creates before artifact/with partial artifact/after
real metadata commit, and eight translation/construction cases with successful
or failed local recorder close. The 21 formerly RED preparation cases are GREEN
without changing any test. Four failed-open cases and one recorder-policy
mismatch now pass after T017 shared-runtime handling; whole T013 passes 27.

Current T016 preparation GREEN check:

```bash
rtk proxy uv run --no-sync pytest core/tests/contract/test_observation_composition.py -k 't013 and not failed_open and not transferred_recorder' --tb=short
```

T016 retains normalized journal/Profile/backend categories, maps unexpected
errors to internal_contract_failure, and raises PreparationFailure outside
handlers to exclude raw cause/context. Only CREATE invalid_input/journal_exists
confirm closure without a returned journal; other failed creates stay unconfirmed
with absent ID, even if metadata exists. After an obtained journal, failure
closes it once and retains its known identity, original primary, and independent
close outcome. No probing/reopen/deletion/retry or physical open is introduced.
Successful preparation transfers the same recorder and unopened Basic backend.
Shared runtime, Acquisition, SQLite schema/semantics, and tests were unchanged in T016.
Combined feature-005 focus excluding T014 and the five remaining T013 cases
passes 240; US1 and all 35 T012 cases remain GREEN.

The existing admission probe captures only the real edge's prepare callable;
failed-open and mismatched-policy cases use the actual runtime/Acquisition.
Temporary journals and fail-closed artifact guards prevent identity probing,
reopen, deletion, or retry during failure normalization. Explicit test readback
is separate, after those guards are restored. Test cleanup releases any obtained
journals without attesting successful production cleanup. No shared fake or
T014 acquisition/teardown failure matrix is added.

Current T014/T017 GREEN check:

```bash
rtk proxy uv run --no-sync pytest core/tests/contract/test_observation_runtime.py -k t014 --tb=short
```

The 32 cases cover twelve direct snapshot/close/recorder combinations, eight
first-append/capability startup failure combinations, four consumer-join cases,
four pending/terminal certainty and permanent-blocking cases, two confirmed-
cleanup fresh-destination retries after primary failure, and two preparation
primary/local-close reports. The fresh pre-change run had 29 RED failures: eleven
projection, eight startup, three join-status, three certainty, two retry, and
two preparation cases, plus three passing clean projection/join/reuse cases.
The same unchanged 32 cases all pass after T017. No xfail/skip or test changes.

T017 status projects snapshot.primary_failure_kind independently from close_failed,
preserves an earlier preparation/start primary, and exposes at most two ordered
cleanup facts. Preparation failures keep their known ID/local cleanup; invalid
transfer shapes remain unconfirmed, and policy mismatch closes the recorder
before open. Failed start/stop/close still joins Acquisition before recorder close.
Successful recorder close is the only post-transfer closure confirmation; failed
open and failed closes remain independently unconfirmed. Terminal publication
requires joined resource work, fails on any issue, preserves the cause/intent
for these explicit/startup paths, and drops owned resources. Settled detach
returns the unchanged summary, with no cleanup retry; the exact derived admission
predicate blocks uncertainty permanently. No raw cause/context, legacy failure
access, private Acquisition fields, evidence reconstruction, direct second close,
runtime deadline, automatic reconnect, or autonomous termination observer is added.

Current Acquisition regression check (64 cases):

```bash
rtk proxy uv run --no-sync pytest core/tests/contract/test_acquisition_lifecycle.py core/tests/integration/test_acquisition.py core/tests/integration/test_basic_serial_acquisition.py core/tests/integration/test_durable_acquisition.py
```

The test-local Acquisition subclass inherits actual start/stop/snapshot/join
behavior. Its legacy failure property raises on runtime access, and its
consumer tail holds the actual task after its body/notification without
altering snapshots. Real counterexamples prove close-only legacy transport
failure has no snapshot primary, and transport-before-failed-append retains
transport primary despite legacy recording failure. Temporary SQLite journals
and normalized fixture failures preserve actual commits and cleanup ordering.
Explicit detach drives active-failure cleanup; autonomous terminal observation
remains deferred. Test-only cleanup joins work and closes journals after
assertions, without attesting production cleanup or adding a runtime deadline.

T007 captures the edge's guard/admission handoff with a small test-only probe
that implements no ownership/lifecycle. Preparation assertions use real SQLite
and Basic adapters with an injected fake serial factory; existing Acquisition
exercises startup after that preparation. T006 covers runtime ownership itself.

T010 uses real Profile resolution, runtime ownership, Basic acquisition, and
SQLite append/reopen/retrieval; only physical serial construction is substituted
through the existing private fake seam. Commit acknowledgments and read gates
make byte/record retention and between-page expiry deterministic. Pages preserve
their snapshot fence across later RX, detach, and reopen. Schema-v1 retains policy
and effective provenance, with no durable DUT identity/name or Profile source.
Requests stay within persisted retrieval ceilings; oversized limits are rejected,
not clamped. Initial new-test expectation errors were corrected without production
changes; this test-only task introduces no production RED/GREEN implementation pair.

T011 separately reproduced six RED rejection-propagation cases, then verified
all six GREEN after correcting only RuntimeRejectedError in runtime.py. It is
an ordinary RuntimeError with the same validated, read-only kind and string;
standard exception transport fields such as __traceback__ remain assignable.
The regressions exercise all four categories plus actual no-loop construction
and invalid attach, with no resource preparation. Immutable status/run/issue
values and lifecycle orchestration stay unchanged. The separate JournalFailure
contextlib issue is documented and outside T011's allowed production files.

The completed-feature regression command excludes only feature-005 tests:

```bash
rtk proxy uv run --no-sync pytest core/tests -k 'not t019' \
  --ignore=core/tests/contract/test_acquisition_lifecycle.py \
  --ignore=core/tests/unit/test_runtime_model.py \
  --ignore=core/tests/contract/test_observation_runtime.py \
  --ignore=core/tests/contract/test_observation_composition.py \
  --ignore=core/tests/integration/test_observation_runtime.py
```

## Prerequisites

- Repository's declared Python 3.14 uv environment and locked dependencies.
- Temporary Profile/journal paths and fake serial construction only.
- Default fail-closed serial sentinel remains installed; attach tests must
  inject fake Basic or current Enhanced-shaped backends.
- No real device, port enumeration, TX, Control, or physical acceptance.
- Construct ObservationRuntime inside its running owning event loop/thread;
  attach/detach and synchronous status must execute in that same context.
  Already returned immutable status values may be inspected elsewhere.

Run from the repository root. No service process or CLI is required.

## Focused software checks after implementation

```bash
rtk proxy uv run pytest core/tests/contract/test_acquisition_lifecycle.py core/tests/unit/test_runtime_model.py
rtk proxy uv run pytest core/tests/contract/test_observation_runtime.py core/tests/contract/test_observation_composition.py
rtk proxy uv run pytest core/tests/integration/test_observation_runtime.py
```

Expected scenarios:

1. Resolve a strict Profile-v1 temp file. Attach to a fresh temp journal using
   fake serial construction; status passes attaching -> active.
2. Feed exact binary and ambient bytes through the sole existing reader. No
   operation/subscriber is created; all received bytes are durable evidence.
3. Gate physical close/final append, request detach, and verify recorder close
   has not started. Release the gate; consumer/close join precedes journal close.
4. Reopen the known journal through existing feature-003 methods and retrieve
   bounded pages containing RX and final segment boundaries, or explicit
   retained/expired/partial outcomes under intentionally small quotas.
5. Cancel attach/detach waiters repeatedly while create/open/read/append/close
   is pending. Their owner is never cancelled; they propagate cancellation only
   after cleanup settles. Other waiters receive captured-generation status.
6. Inject failures before/after journal creation and after open. Keep the file;
   expose known SessionId only when returned. Unknown bootstrap/open cleanup
   remains unconfirmed and further attach is rejected.
7. Emit immediate/active normalized disconnect; verify automatic cleanup and
   no second open. A fresh explicit attach is possible only after confirmed
   cleanup and uses a new destination/session.
8. Repeat shared assertions against the existing Enhanced-shaped fixture with
   device timestamps, observer loss, origin reset, and RX capability rejection.
   This is neutrality proof only, not Enhanced hardware/Profile support.
9. Verify snapshot.primary_failure_kind/close_failed directly for clean
   None/false, close-only None/true, and combined actual-primary/true outcomes.
   Legacy Acquisition.failure may still be TRANSPORT_FAILURE for close-only
   failure; runtime must not decode it. Trigger/provenance/release stay separate.
10. Exercise the exact derived admissibility predicate below across all
    state/settlement/cleanup combinations, rejecting impossible statuses and
    any independently supplied admissibility override. Pending owner or either
    unconfirmed cleanup fact cannot report admissible.
    Reject settled-owner/live-Acquisition combinations and any mismatch between
    runtime release certainty and its authoritative AcquisitionSnapshot.
11. Construct on one running loop/thread, then exercise attach/detach/status
    from wrong-loop/thread/no-running-loop contexts; verify wrong_execution_context
    before mutation, locks, or preparation. No-loop construction fails and
    terminated runtimes never rebind. Same-context status only reads/project facts.
12. Compare busy calls: direct runtime.attach with a resolved Profile performs
    no Profile I/O/preparation; attach_basic_observation checks calling context
    then intentionally reads/resolves the bounded explicit Profile before
    runtime admission. A valid busy edge call returns busy after the read; an
    invalid Profile may fail first. Neither creates/opens a journal, constructs/
    opens a backend, enumerates hardware, or prepares run resources when rejected.

```text
attach_admissible = (
    state in {inactive, terminated, failed}
    and owner_settled
    and physical_release_confirmed
    and recorder_close_confirmed
)
```

See [the contract](contracts/observation-runtime.md) for exact cause/status
precedence and [tasks.md](tasks.md) for the corresponding test groups.

## Architecture and scope checks

```bash
rtk proxy uv run lint-imports
rtk proxy uv run ruff check .
rtk proxy uv run mypy .
rtk proxy rg -n 'SCHEMA_VERSION|_SCHEMA_STATEMENTS' core/src/dutchmate_core/adapters/sqlite_evidence.py
rtk proxy git diff -- core/src/dutchmate_core/adapters/sqlite_evidence.py core/src/dutchmate_core/model.py core/src/dutchmate_core/backend.py
```

Expected: runtime imports no adapter/framework; schema-v1, evidence unions and
normalized backend execution contract unchanged. Any diff to those existing
contracts must be justified against the explicit scope, not silently accepted.
Review shared runtime for backend identity branches and physical-device calls.
Generic Profile/provenance fields are allowed; lifecycle branches on Basic/
Enhanced identity are not. No new banned-API exemption is permitted.

## Final implementation gate

```bash
rtk proxy uv run ruff check .
rtk proxy uv run mypy .
rtk proxy uv run lint-imports
rtk proxy uv run pytest
rtk proxy git diff --check
```

Record actual counts/errors in development status/history during implementation,
then review the complete diff. T027 has already performed exactly one code-only
incremental structural Graphify update; do not repeat it for these documentation
edits. Skipped hardware validation is never reported as passed. This slice has
software acceptance only; existing physical/electrical cases remain separately
authorized future work.
