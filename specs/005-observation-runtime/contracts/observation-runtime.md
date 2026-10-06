# Internal Contract: Observation Runtime

This contract adds an application lifecycle over features 001–004. It defines
no HTTP route, command, cursor encoding, persistence schema, hardware action,
or external-program execution. Names below are the intended internal library
surface; completed contracts govern underlying behavior.

## 1. Application surface and preparation boundary

```text
ObservationRuntime()
runtime.attach(profile: ResolvedDutProfile, prepare: PrepareObservationRun)
    -> RuntimeStatus
runtime.status() -> RuntimeStatus
runtime.detach() -> RuntimeStatus

PrepareObservationRun = async callable(profile) -> PreparedObservationRun
PreparedObservationRun(recorder: ObservationRecorder, backend: Backend)
ObservationRecorder: EvidenceRecorder + session_id + policy + async close()
```

The recorder lifecycle subset uses existing SessionId, SessionPolicy, and
EvidenceRecorder.append meanings. It adds no retrieval methods, quotas,
storage selection, or repository hierarchy. The callable is the one external
creation boundary; shared runtime imports neither Basic nor SQLite.

The preparation caller owns all resources until returning PreparedObservationRun;
then the admitted runtime generation owns them. Preparation must create at
most one journal and construct one unopened backend, never call Backend.open,
start RX, enumerate devices, or retain ownership after transfer. Recorder policy
must equal the resolved Profile's SessionPolicy by value.

Preparation failure is normalized as PreparationFailure containing one
RuntimeIssue, optional created SessionId, recorder-close certainty, and at most
one recorder cleanup issue. It must clean up an obtained journal before raising.
No raw exception, file, SQLite handle, or serial object crosses this boundary.
Unexpected preparation exceptions/invalid returns become internal-contract
failure with unconfirmed recorder cleanup; runtime cannot assert cleanup of
resources never transferred. A well-formed returned recorder with mismatched
policy is rejected and closed without backend open.

## 2. Admission and request semantics

Construction must execute on a running event loop. ObservationRuntime() binds
immediately and permanently to that exact loop and its executing thread, before
any lifecycle lock/task is used; it creates no run resources. Construction
without a running loop raises RuntimeRejectedError(wrong_execution_context).
There is no lazy first-attach binding or later rebinding after termination.

At entry, attach() and detach() require the same running loop and owning thread.
Check this before argument validation, admission, lock acquisition, stop-intent
changes, or preparation. A wrong-loop/thread or no-running-loop execution
raises RuntimeRejectedError(wrong_execution_context), leaving status/ownership
unchanged and submitting no resource work. Owner tasks, terminal callbacks,
and cancellation handling mutate lifecycle only on that bound loop/thread.
No implicit cross-thread dispatch, process-wide lock, or thread-safe API is added.

Synchronous status() is supported only while the owning loop is running on its
owning thread, including initial inactive and settled states. It applies the
same context guard before reading lifecycle facts; unsupported contexts raise
wrong_execution_context. It returns an immutable snapshot without binding,
rebinding, scheduling work, refreshing state by mutation, or changing ownership.
Callers may inspect an already returned immutable value elsewhere; this does
not permit cross-thread calls into the runtime. Closed-loop runtimes cannot be
rebound or queried directly from another context.

Admission and all status mutations are serialized with a short lifecycle lock;
external awaits never hold it. The context guard precedes the lock.

- Validate Profile and callable before admission. Invalid request raises
  RuntimeRejectedError(invalid_request), creating no run/resources.
- Admit attach only when inactive or settled terminated/failed with all cleanup
  confirmed. Create fresh opaque RunId, capture immutable Profile, clear the
  previous summary, publish attaching, and create one generation-owned task.
- ObservationRuntime.attach() already receives a ResolvedDutProfile. In
  attaching/active/detaching it raises RuntimeRejectedError(busy) immediately
  without invoking preparation or performing Profile I/O. This is the runtime
  guarantee, not a promise that its outer convenience edge performs no I/O.
- Attach after settled unconfirmed cleanup raises
  RuntimeRejectedError(cleanup_unconfirmed). Rejection changes no summary and
  never invokes preparation. Requests are not queued for future activation.
  Admission uses exactly the derived attach_admissible predicate in §3.
- Attach waits for active publication or settled terminal status. Expected
  preparation/start failures return failed RuntimeStatus, rather than leaking
  underlying exceptions. Immediate terminal Acquisition can return terminal
  status without promising active capture.
- Detach with no run returns inactive status. Detach on a settled run returns
  its unchanged summary and does not retry cleanup.
- Detach in attaching sets stop intent on that generation and waits for its
  startup work to reach a safe checkpoint; it does not call stop concurrently
  with unfinished Acquisition.start.
- Detach in active requests stop. Detach in detaching joins the same cleanup.
  All admitted detach waiters return their captured generation's settled
  status, even if a later attach has replaced the runtime's current summary.

No caller ever receives a writable recorder, connection, backend, or owner task
from runtime. Evidence remains available through existing bounded journal
interfaces used by future composition/delivery; no new retrieval API is added.

## 3. State and status model

| State | Meaning | New attach |
|---|---|---|
| inactive | No accepted run yet; no resources | Allowed |
| attaching | Accepted Profile; preparation/start pending | Busy rejection |
| active | Acquisition established and running | Busy rejection |
| detaching | Stop/failure/disconnect cleanup in progress | Busy rejection |
| terminated | Settled without primary or cleanup failure | Allowed if all cleanup confirmed |
| failed | Settled primary and/or cleanup failure | Allowed only if all cleanup confirmed |

Normal transitions: inactive/terminated/failed -> attaching -> active ->
detaching -> terminated/failed. Startup cancellation/failure/early disconnect
can take attaching -> detaching -> terminated/failed without active publication.
Failed admission is not a state transition. No released/reconnecting state exists.

RuntimeStatus is a frozen finite value containing:

- state, optional RunId and immutable resolved Profile;
- optional SessionId, learned from successful preparation or its failure report;
- optional AcquisitionSnapshot with established descriptor and current/last
  committed segment provenance; connection identity comes only from committed
  provenance, not a candidate that failed to record;
- first stop intent (none, detach, attach_cancelled), optional terminal reason;
- optional primary RuntimeIssue and tuple of at most two cleanup RuntimeIssues
  (one acquisition/backend-close fact and one recorder-close fact);
- owner_settled, physical_release_confirmed, recorder_close_confirmed, and the
  derived read-only attach_admissible property.

Initial inactive status has no run/Profile/session/acquisition/reason/failure,
owner_settled and both cleanup confirmations true, and attach_admissible true.
A created/open
recorder is not close-confirmed until its close succeeds; during pending creation
closure is unconfirmed. Physical release is confirmed until Acquisition begins
an open attempt, then unconfirmed until successful connection close.

The descriptor can exist before a segment commit; status must not invent a
segment/connection identity if initial append fails. Acquisition state reports
capture: acquiring means continuous capture; stopping means teardown/draining,
not guaranteed continued capture. Detaching may initially still be acquiring.
In terminal status the descriptor/provenance are historical, never live.
Origin resets update the snapshot only after new segment-start commit.

attaching may have no SessionId while creation is pending. Absence does not
prove no journal artifact exists. terminated/failed retain only the last
run's summary, replaced on next admitted attach. This is not a session catalogue.

owner_settled is an authoritative lifecycle fact: true initially with no owner,
or after all runtime-owned startup/acquisition/consumer/close/resource work
for the generation is joined and the owner can neither
perform further resource work nor publish lifecycle mutations. It is false
during attaching/active/detaching, including hung external work. Failed cleanup
can settle the owner while leaving cleanup certainty false. Publish terminal
state and this settlement fact together; never expose a terminal state early.
Caller waiters merely receiving their captured immutable result are not owned
resource work; they need not finish before this settlement is published.

Use this exact predicate for both status and admission:

```text
attach_admissible = (
    state in {inactive, terminated, failed}
    and owner_settled
    and physical_release_confirmed
    and recorder_close_confirmed
)
```

attach_admissible is computed, not an independently supplied/stored flag.
RuntimeStatus construction validates lifecycle invariants: inactive has no
owner/run, owner_settled true, and both cleanup facts true; attaching/active/detaching require
owner_settled false; terminated/failed require owner_settled true. Inconsistent
status values are rejected, never made admissible by an override. A settled
owner cannot coexist with an AcquisitionSnapshot in starting/acquiring/stopping
state. When an acquisition snapshot is present, runtime physical-release
certainty must equal that snapshot's authoritative fact, not an independent
override. Tests cover all state/settlement/cleanup combinations and these
contradictions, rejecting impossible states.

This predicate describes lifecycle eligibility on the owning loop. Context
validation still runs first even when it is true. It does not prove another
process/runtime cannot own the resource; process exclusivity remains deferred.

## 4. Startup order and checkpoints

1. At the Basic edge, enforce the runtime's calling context with its nonmutating
   status() guard, without treating the returned busy/admissibility state as an
   admission precheck. Then resolve the explicit Profile file using feature 004.
   Resolution
   failure leaves runtime unchanged. Create a preparation closure over the
   explicit destination; it has acquired no resources yet.
2. Runtime validates/adopts the resolved value and admits attaching before
   invoking that closure. If stop is already requested, skip preparation.
3. Closure creates a fresh SqliteEvidenceJournal using exactly session_policy.
   Existing files reject; no overwrite/open-resume/path default exists.
4. Closure translates the Profile and constructs BasicSerialBackend, unopened.
   If translation/construction fails, it closes the journal and reports its
   known identity and cleanup outcome; the file remains.
5. Successful preparation transfers recorder/backend. Publish known SessionId
   and verify exact policy before physical activity. A pending stop skips open.
6. Construct a fresh Acquisition using that recorder. Only Acquisition.start
   calls Backend.open, checks uart_receive, commits initial segment evidence,
   and starts the one authoritative consumer. Never open the backend twice.
7. After start settles, inspect normalized Acquisition snapshot. Pending stop
   or already-terminal acquisition enters cleanup; otherwise publish active
   and resolve attach. The owner continues waiting for stop/termination.

Cancellation does not interrupt steps already submitted. Check stop intent
before preparation, after preparation, and after Acquisition.start. There is
no extra RX reader or staging buffer; no runtime-caused gap while owning a
connected backend. Existing serial-open/first-read timing and upstream loss
limitations are unchanged and no earlier physical observation is claimed.

## 5. Teardown and additive Acquisition contract

All stop causes converge on one owner cleanup, never independent close tasks:

1. Publish detaching. If startup is unfinished, await its settled result before
   acting on transferred resources.
2. If Acquisition exists, await stop where appropriate and then the additive
   join_terminated() barrier. On observed terminal Acquisition, join it without
   relabeling its cause. The barrier ensures startup, consumer, and physical
   close tasks have settled and no later recorder appends can occur.
3. Record independent Acquisition release/close-failure facts. Never directly
   close a returned backend a second time; Acquisition owns that call.
4. Close the recorder after the barrier, even if Acquisition cleanup failed.
   Retain the original recorder-close outcome; later no-op close proves nothing.
5. Publish the generation's immutable terminal summary and release all resource
   references. Retain only bounded summary facts; settle captured waiters.

Acquisition gains snapshot() -> AcquisitionSnapshot and
join_terminated() -> AcquisitionSnapshot. Existing start/stop/wait_terminated
signatures and their return values stay compatible. The additive snapshot has:

- AcquisitionState;
- optional returned ConnectionDescriptor;
- optional latest committed SegmentProvenance;
- optional terminal trigger: explicit_stop, disconnected, capability_rejection,
  recording_failure, or transport_failure;
- primary_failure_kind: AcquisitionFailureKind | None, describing only the
  first actual non-close acquisition failure;
- a separate close_failed boolean;
- physical_release_confirmed boolean.

Set disconnect trigger upon observing Disconnected, before final append. A
subsequent append/close failure changes failure facts, not that observed trigger.
For other paths, an observed capability/recording/transport failure establishes
its trigger. A stop request alone is not an explicit_stop trigger: explicit_stop
describes owner-caused termination without an observed disconnect or non-close
failure. A physical-close-only failure keeps explicit_stop plus close_failed;
failure of the final evidence append is recording_failure. The additive
snapshot tracks actual primary failure separately from connection-close
failure at the point each occurs: capability rejection, open/read/stream
failure, and recorder failure set the first primary_failure_kind; physical
close failure sets only close_failed. Close-only failure therefore has
primary_failure_kind None and close_failed true, even when the unchanged legacy
Acquisition.failure reports TRANSPORT_FAILURE. Combined failure retains its
actual primary kind and independently sets close_failed. Clean termination has
primary_failure_kind None and close_failed false.

Preserve existing Acquisition.failure, state/method behavior, and method return
values outside the new snapshot. Do not derive primary_failure_kind by
reinterpreting legacy failure_kind/trigger/close_failed combinations. Runtime
projects the explicit snapshot field directly, never the legacy failure object.
Terminal trigger, committed provenance, and release certainty remain separate.
Never derive trigger from journal records.
Provenance is published only after its segment-start acknowledgment.

join_terminated captures its generation, waits startup settlement/termination,
and actually joins consumer and close tasks. It returns only when no more
appends from that generation are possible. A terminal state/Event alone is
insufficient. Runtime shields owner awaits; it never cancels these tasks.
Snapshot release certainty is true before any open attempt and only after
successful returned-connection close thereafter. Failed open without a returned
connection is unconfirmed. Existing Acquisition restart behavior need not change;
runtime uses a fresh Acquisition and enforces the stricter run-level reuse gate.

This is an explicit additive internal revision to feature 001, not a new reader,
backend contract, evidence kind, schema, timestamp, or matching model.

## 6. Cancellation and cause precedence

Caller cancellation before admission performs no preparation or mutation.
After admission, runtime shields its owner task. The cancelled attach waiter
requests attach_cancelled unless a stop intent already won admission, and
continues waiting cancellation-resistently until settlement; then it raises
CancelledError. This also applies if active publication raced delivery of the
attach result. Once a successful attach call has returned, later cancellation
of that caller task has no automatic detach semantics.

A cancelled detach waiter leaves its already-admitted stop request intact,
does not cancel shared work, joins settlement despite repeated cancellation,
then raises CancelledError. Other waiters receive normal results. Cooperative
cancellation is handled; process death is not a cancellation guarantee.

First admitted stop intent wins between detach and attach_cancelled. Compute
terminal reason in this exact priority order:

1. disconnected if Acquisition observed Disconnected, including failed final
   append or close and detach/cancellation races;
2. startup_failure if preparation or Acquisition.start raised before returning
   successful startup (including RX rejection and initial append failure);
3. acquisition_failure if successful startup was followed by observed
   capability/recording/transport failure, even before active publication;
4. detached or attach_cancelled from the first stop intent, including an
   explicit_stop trigger with a physical-close-only failure;
5. cleanup_failure if cleanup failed without any earlier cause above.

No successful startup means Acquisition.start never returned a connection
identity successfully. This is independent of whether active status was ever
published. A close-only issue must not masquerade as an RX transport failure.

Any primary/cleanup issue makes state failed, even when reason is disconnected
or detached. Intent remains separately visible. During failed start, an already
observed disconnect still wins reason; otherwise startup_failure wins over
caller intent. Cancelling a waiter always propagates cancellation after settlement,
even if a primary failure occurred; failures stay inspectable in status.

There is no new numeric lifecycle timeout. A hung adapter remains pending with
inspectable status and busy rejection. Cleanup cannot be made successful by
abandoning worker/reader tasks, nor can unconfirmed release enable another run.

## 7. Failure and certainty matrix

| Failure | Physical release | Recorder closure | Journal/session facts |
|---|---|---|---|
| Profile resolution/admission rejection | No mutation | No mutation | No runtime-created session |
| Stop before preparation begins | Confirmed, no open | Confirmed, no create | Session absent |
| Structural preparation validation or CREATE invalid_input/journal_exists | Confirmed, no open | Confirmed, no recorder opened | Existing file untouched; new SessionId absent |
| Other create failure without returned journal | Confirmed, no open | Unconfirmed | Keep artifact; SessionId may be absent |
| Backend construction failure after create | Confirmed, no open | Successful close only | Keep known SessionId and empty journal |
| Backend.open failure | Unconfirmed | Successful journal close only | Keep known SessionId; no invented segment |
| Initial append/capability failure after returned connection | Successful connection close only | Successful journal close only | Keep actual committed records |
| Active recording/transport failure | Successful connection close only | Successful journal close only | No fabricated final append |
| Backend close failure | Unconfirmed | Successful journal close only, after consumer join | Keep actual committed records |
| Journal close failure | Independent Acquisition result | Unconfirmed | Keep file; no no-op retry attestation |

Positive recorder pre-open exceptions are identified from existing JournalFailure
operation/category values, not error text. Any undocumented exception is
conservatively unconfirmed. No failed-create artifact is reopened to discover
identity. Failed-open categories never prove release. All uncertainties latch
for this runtime instance; settled detach returns them unchanged.

RuntimeIssue is a frozen normalized source/code fact, never a raw cause or
arbitrary exception message. The Acquisition close_failed boolean projects to
the fixed cleanup code close_failed; it does not invent an underlying exception
category that the snapshot did not expose. Sources are preparation, acquisition_start,
acquisition, backend_close, recorder_close, or internal_contract. Known codes
come from existing normalized categories; unexpected exceptions use
internal_contract_failure. Primary issue is first; cleanup issues never replace
it. No unbounded diagnostic list/traceback/history is retained.

Project snapshot.primary_failure_kind directly to the acquisition primary
issue when present, and close_failed directly to the backend_close cleanup
issue when true. A close-only snapshot has no acquisition primary issue;
combined failure yields both facts. Runtime must not inspect legacy
Acquisition.failure or infer primary-versus-cleanup meaning from trigger/kind/
close combinations. Other primary sources, such as preparation failure, retain
their existing projection. Trigger remains a cause fact, not a failure decoder.

## 8. Association, composition, and compatibility

In memory, RunId -> (ResolvedDutProfile, SessionId when known) identifies this
run. Kept terminal status is the last association only. After process restart,
the journal proves session policy, evidence, and effective segment provenance;
it does not recover DUT identity/name, Profile identity, source path, or the
complete resolved Profile. No field is smuggled into backend provenance.

The Basic edge function is:

```text
attach_basic_observation(runtime, explicit_profile_path, explicit_journal_path)
    -> RuntimeStatus
```

It checks the owning-loop/thread context through nonmutating status(), then
intentionally resolves the bounded explicit Profile file with feature 004
before calling runtime.attach. A busy convenience call may read/parse that
Profile, and an invalid Profile can fail resolution before busy is reported.
There is no resource preparation during that read or when runtime rejects:
no journal create/open, backend construction/open, hardware enumeration, or
other run-resource activity. It does not precheck busy or reserve admission
before resolution; runtime.attach performs authoritative admission afterwards.

It captures a concrete preparation closure only after resolution and calls
runtime.attach. The closure creates feature-003 SQLite then uses existing
Basic translation/construction. It normalizes construction/preparation failures
and closes any journal not transferred. Private injection seams may reuse the
existing fake serial construction path. No service/app package is created now.

Shared runtime sees only resolved values, normalized Backend, and recorder
lifecycle contract. Basic selection handling lives solely at this edge.
Shared code never switches on backend_kind, serial settings type, or host
timestamp assumptions. It adds no backend factory hierarchy.

Feature-003 schema-v1, record codecs, provenance envelopes, sequence assignment,
retention and retrieval remain unchanged. A future durable full-Profile
association must explicitly revise its persistence contract/versioning; it
cannot add schema-v1 columns/tables implicitly. Opening prior journals for
bounded retrieval does not resume runtime ownership.

## 9. Required neutrality and lifecycle validation

Use the same parameterized lifecycle assertions for fake Basic and the existing
Enhanced-shaped fixture. Each preparation supplies a temporary real SQLite
journal. Fixture substitution is a test of shared lifecycle, not Enhanced
Profile-v1 selection or hardware support. Extend only deterministic gates,
reported RX capability rejection, and normalized current-contract events.

Cover binary/ambient capture, host/device provenance, scoped loss, origin reset,
concurrent attach/detach, direct primary/close snapshot projection, derived
admissibility and impossible statuses, construction-time loop binding, wrong
loop/thread rejection, runtime busy with no preparation versus Basic-edge
busy with a bounded Profile read only, cancellation at each submitted-work stage, partial
startup failures, actual reader/close join ordering, retained journals,
immediate/active disconnect, cleanup certainty, and stale-generation results.
Maintain hardware guards and unchanged completed-feature regressions.

## 10. Explicitly absent

Delivery/service/process locks; Monitor/follow; TX/Interact/console/Control;
reconnect/topology/handoff; new evidence/annotations/derived retrieval; durable
Profile identity/schema migration; session catalogue/naming/sealing/resume;
Enhanced production behavior; MCP/AI; physical hardware access/acceptance.
