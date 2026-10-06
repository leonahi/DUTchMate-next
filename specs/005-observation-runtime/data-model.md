# Data Model: Observation Runtime

All values below are planned internal Core values. There is no persistence
schema or evidence-union change. Exact transitions and failure rules are in
[the internal contract](contracts/observation-runtime.md).

## RunId

Fresh non-empty opaque string generated for each admitted attach; immutable.
Distinct from SessionId, ConnectionInstanceId, and SegmentId. Rejected attach
generates no accepted identity.

## ObservationRecorder and PreparedObservationRun

ObservationRecorder is the minimal lifecycle subset of production persistence:
existing async append, immutable SessionId/policy properties, and async close.
No retrieval schema or new storage implementation.

PreparedObservationRun is frozen and holds exactly one ObservationRecorder and
one unopened normalized Backend. Recorder policy must equal Profile session_policy
by value. Ownership transfers once on preparation success; failure cleanup
remains the preparation caller's responsibility.

## AcquisitionSnapshot (additive)

Frozen fields:

| Field | Rule |
|---|---|
| state | Existing AcquisitionState |
| descriptor | Optional established ConnectionDescriptor; no library object |
| provenance | Optional most recent successfully committed SegmentProvenance |
| terminal_trigger | Optional explicit_stop/disconnected/capability_rejection/recording_failure/transport_failure |
| primary_failure_kind | AcquisitionFailureKind or None for the first actual non-close acquisition failure; never copied/decoded from legacy failure |
| close_failed | Boolean separate from primary failure |
| physical_release_confirmed | True only before an open attempt or after successful returned-connection close |

New snapshot must not include raw exception objects. Descriptor can be known
when committed provenance is absent. An origin-reset segment becomes current
only after acknowledgment. join_terminated returns this same value after actual
task joins and no-further-append guarantee; existing methods keep their returns.

Actual capability/open/read/stream/recording failures set the first
primary_failure_kind at their occurrence; connection-close failures set only
close_failed. Close-only failure has primary_failure_kind None and close_failed
true. Combined failure exposes both; clean termination exposes None/false.
Runtime projects these facts directly. Legacy Acquisition.failure behavior and
method return values remain unchanged, even if legacy close-only failure is
TRANSPORT_FAILURE. Trigger/provenance/release certainty are independent facts.

## RuntimeState, stop intent, and terminal reason

RuntimeState: inactive, attaching, active, detaching, terminated, failed.
Stop intent: none, detach, attach_cancelled; first admitted intent wins.
Terminal reason: detached, attach_cancelled, disconnected, startup_failure,
acquisition_failure, cleanup_failure; absent before settlement.

State and cause are separate. Disconnected + cleanup issue means failed state
with disconnected reason. Failure must not be renamed to clean cancellation.

## RuntimeIssue and PreparationFailure

RuntimeIssue is immutable source/code only. Source is preparation,
acquisition_start, acquisition, backend_close, recorder_close, or internal_contract.
Code derives from existing normalized enum categories, fixed close_failed for
the snapshot's cleanup fact, or internal_contract_failure for undocumented
failures. No exception text parsing,
raw cause/context, traceback, arbitrary message, or growing diagnostics.

PreparationFailure holds one primary RuntimeIssue, optional known SessionId,
recorder_close_confirmed boolean, and optional recorder cleanup issue. Physical
open is forbidden in preparation, so physical release is confirmed there.
Existing CREATE/invalid_input and CREATE/journal_exists prove no recorder open;
other failed creates without transferred resources leave closure unconfirmed.

## RuntimeStatus

Frozen current/last summary:

| Field | Rule |
|---|---|
| state | RuntimeState |
| run_id/profile | Both absent in inactive; both present after admission; Profile unchanged |
| session_id | Optional, present only after successful create/report of known identity |
| acquisition | Optional AcquisitionSnapshot, no resource handle |
| stop_intent | First accepted stop request or none |
| terminal_reason | Absent until terminal settlement |
| primary_issue | Optional first normalized RuntimeIssue |
| cleanup_issues | Immutable tuple of at most two issues, acquisition/backend then recorder |
| owner_settled | Authoritative fact: no initial owner, or all generation work joined and no further resource work/lifecycle mutation possible |
| physical_release_confirmed | Independent positive release fact |
| recorder_close_confirmed | Independent positive recorder closure fact |
| attach_admissible | Computed read-only property using exactly the predicate below; not a constructor input or independently stored flag |

```text
attach_admissible = (
    state in {inactive, terminated, failed}
    and owner_settled
    and physical_release_confirmed
    and recorder_close_confirmed
)
```

Validate impossible combinations: inactive requires no run/owner, owner_settled
true, and both cleanup facts true; attaching/active/detaching require
owner_settled false; terminated/failed require owner_settled true. Reject
contradictory values, including owner_settled with starting/acquiring/stopping
Acquisition and any mismatch between runtime release certainty and its
AcquisitionSnapshot. Owner settlement does not imply successful cleanup:
terminal uncertainty keeps admissibility false. Test the state/fact matrix and
reject any independently supplied admissibility override.

Status stores no filesystem path/source bytes or live object references beyond
immutable Profile/provenance values. Terminal acquisition/provenance is
historical. Status keeps exactly one current or last run; no list/catalogue.
Rejected requests cannot mutate it. Cancellation/cleanup uncertainty stays
inspectable after the cancelled waiter raises.

## Private generation ownership

One admitted generation owns the preparation/start/observation/cleanup task,
stop request, captured waiter settlement, and transferred resources. The owner
is not cancelled by callers; it waits for stop or Acquisition termination.
Lifecycle lock covers admission/publication only, never external awaits.
Waiters return their captured generation's value; stale tasks cannot publish
to a newer generation. Settled generations release handles/tasks rather than
accumulating a resource history.

## Event-loop ownership

ObservationRuntime construction requires a running event loop and captures
that exact loop and its executing thread immediately, before lifecycle work.
It never lazily binds/rebinds. No running loop at construction is
RuntimeRejectedError(wrong_execution_context).

attach/detach and owner/cancellation/terminal mutation execute only on that
same running loop/thread. Wrong loop/thread or no running loop raises
wrong_execution_context before lock acquisition, mutation, or preparation.
Synchronous status() has the same supported context/guard and returns an
immutable projection without mutation or scheduling. Already returned values
can be read elsewhere, but direct cross-thread/closed-loop runtime access is
unsupported. No process-wide locking or implicit cross-thread dispatch.

The Basic convenience edge checks this context nonmutatingly, then resolves
the bounded Profile before runtime admission. Busy may entail that Profile read
only, never run preparation. Direct runtime.attach already has the resolved
value and rejects busy without Profile I/O or preparation.

## Durable and compatibility facts

Session policy and effective segment provenance retain their feature-003
durability. RunId, complete resolved Profile, DUT/Profile identity, runtime
failure summary, and association are not durable records. No schema-v1 table,
column, metadata field, new evidence kind, migration, or sidecar is added.
Persisted sequence and retention meanings remain exactly feature 003's.
