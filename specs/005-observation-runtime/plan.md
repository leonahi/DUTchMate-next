# Implementation Plan: Observation-Only Device Core Runtime

**Branch**: `main` | **Date**: 2026-10-03 | **Spec**: [spec.md](spec.md)

**Feature directory**: `005-observation-runtime`, selected by the repository's
sequential workflow; numbering does not create a Git branch.

## Summary

Add one shared observation runtime over existing Profile, Acquisition, and
durable journal contracts. A concrete edge resolves an explicit Profile and
prepares a new journal/unopened Basic backend only after admission. One owner
task drives each run; callers request stop and join without cancelling it.
An additive Acquisition snapshot/join barrier supports safe recorder teardown.
Profile association is in memory only; durable schema-v1 stays unchanged.

T001–T028 are complete. The runtime, Basic/SQLite edge and additive Acquisition
snapshot/join interfaces are implemented and reviewed against the accepted
contract. T024's bounded preparation-error transport correction is covered by
14 regressions, and T025's focused/scenario checks passed. T026 reconciles status/
history and T027 completes one code-only incremental structural update with
ignored output. No normative product/scope/schema or dependency change.

T028's fresh final gate passes: Ruff clean, mypy 40 files clean, all three
import contracts kept (31 files/77 dependencies), pytest 924 passed with zero
failures/errors/skips, and diff/whitespace checks clean after documentation edits.
At T028, the working tree was software-complete and ready for final human review/commit;
that checkpoint claimed no commit, human acceptance, physical-hardware acceptance
or Phase 1 completion. Current progress is in `docs/development_status.md`, with detailed
completed-slice evidence in `docs/development_history.md`.

## Technical Context

**Language/Version**: Python `>=3.14,<3.15`, existing uv workspace.

**Primary Dependencies**: Standard-library asyncio, dataclasses, enum, typing,
uuid; existing pySerial/SQLite adapters unchanged in their dependency choices.
No new runtime/dev dependency or lockfile change is planned.

**Storage**: One new explicit SQLite journal per admitted/prepared run; existing
schema-v1/policy/sequence/retention/retrieval and record kinds unchanged. No
durable Profile metadata or run-status persistence.

**Testing**: pytest/pytest-asyncio, temporary journals, existing fake serial
injection, Enhanced-shaped fixture, deterministic asyncio gates. Existing
default hardware sentinel remains enforced.

**Target Platform**: Current local Python-supported platforms; no hardware or
OS/electrical acceptance claim.

**Project Type**: Existing `dutchmate-core` library; no service/CLI package.

**Performance Goals**: One reader and owner per run, no lifecycle lock across
external awaits, bounded one-summary metadata and at most two cleanup issues;
no additional RX buffering or invented throughput target.

**Constraints**: Confirmed cleanup before reuse; no automatic reconnect/open
retry; cancellation must not abandon workers; no deletion of failed-start
artifacts; status inspectable during pending I/O; no new lifecycle deadline.

**Scale/Scope**: One runtime/active observation run per event loop, with process
exclusivity deferred to the future service. Basic at production edge; neutral
substitution only in current-contract tests.
Construct runtime on its owning running loop/thread; context-check lifecycle
APIs and synchronous nonmutating status before touching state/resources. No
lazy binding, cross-thread dispatch, or process lock.

## Constitution Check

The constitution file is an unpopulated scaffold, not another normative rule
set. Governing gates are AGENTS.md, Core, and completed focused contracts.

| Gate | Pre-research / post-design assessment |
|---|---|
| Authority/scope | Pass: accepted runtime slice; no Core product rule changes |
| Single ownership | Pass by design: admission before preparation; one fresh Acquisition/owner |
| Continuous evidence | Pass by design: no competing reader; recorder before open and through final joins |
| Dependency direction | Pass by design: runtime above Acquisition/contracts; adapters depend inward |
| Backend neutrality | Pass by design: callable preparation; normalized snapshots; same fixture assertions |
| Human Profile/policy | Pass by design: immutable observation-only values and reported RX check |
| Evidence compatibility | Pass by design: unchanged schema-v1/record types/retention/retrieval |
| Safety/hardware | Pass by design: fakes/temp files and existing fail-closed sentinel |
| Simplicity | Pass by design: one callable and minimal lifecycle subset, no registry/framework |
| Phase/delivery | Pass: service/CLI/TX/reconnect/handoff/Enhanced/MCP excluded |
| Verification | Required future implementation gate; planning is document-validated separately |

These are design assessments, not claims that future code passes checks.
No justified architecture violation or exemption is proposed.

## Project Structure

### Documentation (this feature)

```text
specs/005-observation-runtime/
  spec.md
  checklists/requirements.md
  plan.md
  research.md
  data-model.md
  contracts/observation-runtime.md
  quickstart.md
  tasks.md
```

### Planned source/test changes

```text
core/src/dutchmate_core/
  acquisition.py                  # additive snapshot and join barrier
  runtime.py                      # run values, lifecycle subset, state owner
  adapters/observation_runtime.py  # explicit Profile + Basic/SQLite edge
core/tests/
  fakes.py                        # minimal deterministic lifecycle gates
  unit/test_runtime_model.py
  contract/test_acquisition_lifecycle.py
  contract/test_observation_runtime.py
  contract/test_observation_composition.py
  integration/test_observation_runtime.py
pyproject.toml                    # extend existing import contracts only
docs/development_status.md
docs/development_history.md
```

Keep domain/status/lifecycle values in one cohesive runtime module initially.
Do not create one-class files, another app, a repository, provider registry,
compatibility facade, or generic execution framework. Existing backend,
Profile, model/evidence, Basic and SQLite implementations remain authoritative.

## Existing consumer and compatibility inventory

- Acquisition is used by acquisition integration tests, Basic adapter
  integration, durable acquisition integration, and test recovery tooling.
  Keep start/stop/wait_terminated return values; add snapshot/join and regress
  existing teardown/origin-reset/failure behavior.
- Snapshot joins/close certainty are new runtime-facing facts. Preserve
  legacy Acquisition.failure/method behavior; add primary_failure_kind for the
  actual first non-close failure and independent close_failed. Runtime projects
  the new fields directly, never decodes legacy failure/trigger combinations.
- Backend/BackendConnection and Basic open/close methods do not gain new
  execution or retry methods. Failed open remains conservatively uncertain.
- SQLite implements the new minimal lifecycle Protocol structurally using
  existing append/session_id/policy/close. Its schema/codec is untouched.
- ResolvedDutProfile and pure Basic translator keep their existing meanings.
  After nonmutating context validation, Profile parsing remains before runtime
  admission at the edge. A busy edge may read the bounded Profile; only direct
  runtime.attach guarantees busy rejection without Profile I/O. Both prohibit
  journal/backend preparation after rejection.
- No current runtime/delivery consumers require compatibility wrappers. Export
  only the intentional small library surface; no bulk root-package exports
  or adapter re-exports are required.

## Design decisions

Read [research.md](research.md) and the [internal contract](contracts/observation-runtime.md)
for authoritative implementation details for this feature.

1. One current/last immutable status and generation-scoped owner task; fail-fast
   runtime attach, coalesced detach, short mutation lock, and construction-time
   binding to a running loop/thread. Synchronous status requires that context
   without mutation; wrong-context calls reject before locks/preparation.
2. Prepare callable creates journal then unopened backend, transferring
   ownership atomically on success; failed preparation cleans up locally.
3. New Acquisition per run; normalized snapshot and actual consumer/close join
   before journal close. Snapshot's primary_failure_kind excludes close-only
   errors even when the preserved legacy failure is TRANSPORT_FAILURE.
   Runtime projects primary_failure_kind/close_failed directly. No reader redesign.
4. Admitted caller cancellation requests stop and joins settlement, shielding
   owner work even under repeated cancellation. Stop intent and observed cause
   remain separate.
5. Positive cleanup evidence required for reuse. Generic failed open and most
   failed create attempts block the runtime permanently; no speculative retry.
   Derive attach_admissible exactly as `(state in {inactive, terminated, failed})
   and owner_settled and physical_release_confirmed and recorder_close_confirmed`;
   validate impossible status combinations and use this predicate at admission.
6. In-memory Profile association, new session per attach, retained failed-start
   journals, unchanged persistence contracts and no append-resume.

## Implementation sequence and acceptance

1. **Establish baseline/inventory**: inspect current diff/contracts and run
   focused existing acquisition/Profile/SQLite tests before code changes.
2. **Add Acquisition observability**: test then implement committed descriptor/
   provenance snapshots, explicit primary_failure_kind separate from close_failed
   without decoding legacy failure, failed-open uncertainty,
   and actual generation-local join barrier.
3. **Define runtime values**: test immutable values, exact derived admissibility,
   impossible status combinations, and minimal
   preparation/recorder lifecycle boundary; extend architecture contracts when
   the runtime module exists.
4. **Implement normal run ownership**: tests then admitted prepare/start,
   construction-time context binding/checks, continuous capture, nonmutating
   status, and detach/recorder order at the Basic edge. Test bounded Profile reads
   before busy rejection at the edge separately from zero-I/O runtime rejection.
5. **Implement races/cancellation/failures**: deterministic gates cover every
   submitted stage, cleanup uncertainty, kept artifacts, and captured-generation
   waiter behavior. Normalize without raw cause/context leakage.
6. **Implement autonomous terminal observation**: immediate/active disconnect,
   actual cause precedence, fresh explicit later run, origin reset, capability
   rejection, and identical Enhanced-shaped fixture assertions.
7. **Validate compatibility and full scope**: unchanged journal readback and
   all completed-feature regressions; quickstart, architecture and full gate.
8. **Record implementation evidence**: update status/history, perform one
   structural Graphify update if triggered, then fresh final gate/diff review.

US1 is a happy-path development checkpoint, not a releasable claim that this
feature is complete; US2/US3 safety/termination acceptance are mandatory.
The final authorized implementation step ends at T028. T001–T011 remain GREEN; T015 makes
all 35 unchanged T012 request/cancellation tests GREEN.
The normal generation owner, explicit Basic edge, and end-to-end readback tests
are present, and US1 regressions pass. T017 adds failure/cleanup handling and
transfer validation; autonomous termination remains later shared-runtime work.
T016 now implements the broader preparation-failure/cleanup matrix at the edge.
No production behavior changed in T012. T015 now implements its cancellation-
resistant waiters, stop-intent arbitration, and captured-generation results.
T013 added only preparation/transfer failure tests. T016 makes all 22 preparation
cases GREEN, preserving first normalized primary, obtained journal identity,
one local close outcome, and kept artifacts. Only CREATE invalid_input/
journal_exists affirm closure without an obtained recorder; other create failures
remain unconfirmed with absent ID, without probing/reopen/deletion/retry.
Known normalized categories are retained; unexpected errors use the fixed
internal_contract_failure code. Raise outside handlers to strip raw cause/context.
T017 now handles the four failed-open and one transfer-policy mismatch cases.
No production behavior changed in T013 itself.
T014 adds only snapshot-projection/failure/teardown/reuse tests, with 29 RED
failures and three passes. Real Acquisition methods are inherited; a test-only
legacy-access tripwire and consumer tail gate verify direct projection and
actual joining. No production behavior changed. T014 failure/cleanup certainty
implementation is now T017 work, verified GREEN. T015 changed only runtime.py: already-resolved
admission/context checks are retained, stop intent admits once under the short
lock, cancelled callers shield/join their captured owner, and stale generation
stop handling cannot mutate a newer run. No resource await holds the lock;
no owner is cancelled or another open submitted. The normal terminal reason
uses the first detach/attach_cancelled intent. T016 changes only the Basic
composition adapter; shared runtime, Acquisition, SQLite/Profile, tests, and
normative contracts were unchanged in T016. T017 changes only runtime.py:
direct nonmutating snapshot primary/close projection, first-primary preservation,
one acquisition/backend cleanup fact before one recorder fact, and independent
recorder-close certainty. Preparation failures retain known facts; invalid
returns/unexpected exceptions remain conservatively unconfirmed, and policy
mismatch closes a well-formed recorder before any open. Acquisition stop and
actual join precede recorder close after failure; final owner settlement preserves
uncertainty, permanently blocks admission, and makes terminal detach idempotent.
No legacy/private Acquisition failure decoding, evidence reconstruction, second
backend close, timeout, or automatic observer is added. Autonomous termination,
terminal-before-active/disconnect priority and extended neutrality remain US3 work.
T018 verifies the derived admission gate, cached settled detach, join-before-
recorder-close order, single original close outcome, exact pre-open certainty
exceptions, and preserved failed artifacts. No no-op-close/reset path that clears
uncertainty was found; all production/tests and deterministic gates are unchanged.
Ruff/mypy/import checks pass, schema-v1/backend/evidence contracts remain unchanged,
and scope searches show no legacy/private Acquisition access or backend-identity
branch in shared runtime. T019 now adds default-open fixture gates for open,
read, event delivery, consumer exit, and close, with simple invocation/consumer
counters. Both Basic/Enhanced-shaped fixtures use the same checkpoints; existing
timestamp/loss/origin-reset/disconnect/capability behavior and factory signatures
are preserved. Ten parameterized backend-fixture checks went RED for missing
gates then GREEN; no runtime/service, Enhanced mechanics/Profile selection,
new event, or resource policy is added. T020 adds test-local fault recorders and
gates around real Acquisition start return/consumer joining, reusing the shared
normalized event-delivery gate and real temporary SQLite journals. It records
33 RED failures: autonomous disconnect (eight), autonomous recording/transport
failure (four), terminal-before-active disconnect/failure (six), observed
disconnect versus stop/cancellation (14), and late old-generation delivery (one).
One queued-but-unobserved disconnect/startup-failure case passes. Assertions keep
cause, primary failure, cleanup, committed historical provenance, and certainty
independent, require one open/reader/close, and forbid old-generation publication.
Only tests/progress records changed; no autonomous runtime observer is added.
T021 adds identical lifecycle/readback assertions over the two existing fixture
factories, each prepared after admission with a real fresh SQLite journal and
the same resolved observation-only Profile. A test-edge generic provenance
envelope enables durable readback without changing reported timestamps/loss/
capabilities or adding Enhanced Profile selection. Sixteen cases pass, covering
startup/busy/active status, exact binary/ambient capture, host/device domains,
commit-gated origin reset, reported observer scope versus unobservable upstream
loss, missing-RX rejection, actual close/consumer joining, explicit fresh sessions,
historical status, bounded snapshot pagination, retention expiry, and schema-v1
without durable Profile fields. Eight cases are RED for active/immediate
disconnect and autonomous recording/transport failure, identically per shape.
Only integration tests/progress records changed; original six Basic-composition
cases, shared fixtures, and production remain unchanged.
T022 changes only runtime.py in source. Successful public Acquisition startup
is tracked separately from active publication. The owner publishes active only
for acquiring snapshots with no observed terminal trigger and no pending stop;
otherwise it enters cleanup without active delivery. While capturing, the owner
races stop and public Acquisition termination notification, publishes detaching,
and joins the two notification waiters. Only unfinished Event notification waits
are cancelled; no startup/reader/backend-close/join work is cancelled. No helper
publishes lifecycle changes independently of the owner.

Observed terminal processing is joined without submitting stop, preserving its
final evidence/close work. Unobserved explicit stop still uses Acquisition.stop;
both paths join_terminated before recorder close. Direct primary_failure_kind/
close_failed projection and committed provenance remain unchanged. Observed
disconnect precedes startup/acquisition failure and stop intent for terminal
reason; failures independently require failed state and unknown cleanup blocks
reuse. All 58 unchanged T020/T021 tests pass; feature focus passes 335/full 910.
No new public contract/module/dependency/schema/fixture or backend assumption.
T023 verifies the unchanged US3/current-feature and completed Acquisition/Basic/
Profile/SQLite regressions, plus the quickstart architecture checks. Review
follows normalized timestamp/loss/capability facts, generation-captured waiters,
notification draining and settlement, and fixture scope. Capability-dependent
loss emission remains at the test fixture edge; shared policy never switches on
backend identity. No host-clock assumption, stale-generation publication, or
simulated future GPIO/helper/USB/firmware behavior was found, so no code/test
correction. Fresh focus passes 335, completed regressions 565, and full 910;
all 58 T020/T021 and ten T019 fixture checks are GREEN. Ruff/mypy/import gates
pass and schema-v1/evidence/backend contracts remain unchanged.
T024 inventories the tracked and untracked feature diff, production/test
consumers, package exports and architecture configuration, and reviews all
FR-001–030 plus the internal contract. The additive Acquisition API retains
legacy behavior; runtime/edge are the only new production modules. Root exports,
dependencies/lockfile, schema-v1, evidence/Backend contracts and all deferrals
remain unchanged. Import constraints gain runtime coverage without exemptions.
Status retains only normalized current/last Profile/provenance/identity facts;
no Profile-source/journal destination, live handle, raw diagnostic or unbounded
summary history is introduced.

Review reproduces one feature-005 defect: frozen/slotted PreparationFailure
rejects contextlib's standard __traceback__ assignment and becomes TypeError,
losing normalized session/primary/cleanup facts. Only its exception transport
is corrected. All four fact fields remain read-only and retain constructor
validation, dataclass replacement/equality/hash behavior and fixed message;
standard RuntimeError metadata remains writable and never enters RuntimeStatus.
Four real temporary-journal runtime regressions and two direct sync/async
transport regressions go RED then GREEN; eight fact assignment/deletion checks
remain GREEN. No lifecycle, Acquisition, edge, persistence or fixture behavior
changes. The separate feature-003 JournalFailure limitation remains deferred.
Feature focus passes 349/full 924; all static/import gates pass.
T025 runs the quickstart commands/selectors as written, including the three
canonical focused runs (105 foundational/value, 214 runtime/composition and 30
integration cases), historical focused groups, feature focus 349 and completed
regressions 565. All 21 test commands pass with no failures/errors/skips. Five
architecture/scope commands pass: import contracts are kept, Ruff/mypy are clean,
schema-v1 remains 1 and SQLite/model/Backend contract diff is empty. Shared-runtime
searches find no backend/framework/physical-device dependency, identity branch,
legacy/private Acquisition access, reconnect or lifecycle deadline.

No production/test defect was demonstrated; code, fixtures and gates remain
unchanged. Only the documented earlier-subset count is clarified: excluding
T020/T021 now selects 291 (277 earlier cases plus 14 T024 cases). No unrestricted
pytest invocation or final full-gate block is run; that remains T028. Routine
T025 progress recording does not complete T026's feature-level reconciliation.
T026 documentation reconciliation is complete; T027's structural trigger was
satisfied and exactly one changed-code-only incremental update completed with
2,435 nodes/6,370 edges/117 communities and zero LLM tokens. T028 now passes the
fresh full gate and final diff review. All task markers are reconciled against
completed evidence, including T026's previously restricted marker. No source/test
change was needed during T028, and no further task/feature or commit is started.
The feature is ready for final human review and commit within its software-only
scope; all hardware/delivery/workflow/persistence deferrals remain intact.

## Critical regression matrix

| Area | Required evidence |
|---|---|
| Admission | Direct resolved-Profile attach rejects busy without I/O/preparing; Basic edge may read bounded Profile only; no overwrite |
| Loop ownership | Bind at construction; wrong-loop/thread/no-loop calls reject before locks/mutation/preparation; status cannot rebind or dispatch |
| Ordering | Create -> construct -> open -> commit segment -> consume |
| Teardown | Stop/close/consumer join -> final appends settled -> journal close |
| Cancellation | Before admission and at create/open/append/close; repeat cancellation |
| Failure | Explicit snapshot primary_failure_kind versus close_failed for clean/close-only/combined cases; legacy behavior unchanged; unknown cleanup blocks |
| Disconnect | Immediate and active; no reopening; concurrent detach preserves observed trigger |
| Status | Exact derived admissibility/state-fact matrix; impossible combinations rejected; known/absent IDs; historical/live distinction |
| Generations | Old waiters return old result; stale owner cannot publish new status |
| Compatibility | Retained empty/partial journal; bounded reopen/pages/expiry; schema-v1 unchanged |
| Neutrality | Host/device origins, loss, reset, missing RX capability, no identity branches |

## Validation and tooling

Use focused tests/static checks during implementation. Final required gate:

```bash
rtk proxy uv run ruff check .
rtk proxy uv run mypy .
rtk proxy uv run lint-imports
rtk proxy uv run pytest
rtk proxy git diff --check
```

Extend the existing shared-Core-forbidden-adapters contract to runtime.py.
Add runtime above acquisition in the existing layer contract without weakening
other boundaries. Protocol/type dependencies must remain inward; only name
modules after they exist. No new Ruff banned-API exemption is warranted.

Tests use fakes and temp journals only. See quickstart for focused targets.
Graphify update occurs once after implementation's structural changes, not for
this documentation-only planning. Do not run extra Spec Kit stages by default.

## Remaining decisions and limitations

No unresolved product decision. In-memory association, conservative uncertain
cleanup blocking, pending hung-adapter status, fresh-session-only activation,
and process-level ownership deferral are intentional settled boundaries.
Durable historical association and retry attestations are future explicit
contract revisions, not implementation discretion.
