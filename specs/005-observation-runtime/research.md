# Research: Observation Runtime

**Date**: 2026-10-03
**Baseline**: `6d10cf7`
**Method**: Governing documents, completed contracts, source inspection, and two
read-only research reviews required by the Spec Kit planning skill. No external
research, implementation, tests, or hardware access was needed.

## 1. Association and persistence compatibility

**Decision**: Associate one immutable resolved Profile with one created
SessionId only in the current/last in-memory run summary. Keep schema-v1,
record kinds, and provenance envelopes unchanged.

**Rationale**: Core §§13.3 and 14.2 require immutable effective configuration
and session evidence, not persistence of the complete source Profile. Feature
003 already stores immutable session policy and effective segment provenance;
feature 004 provides immutable resolved inputs. A full historical identity or
Profile snapshot is useful future work but not needed to own observation now.

**Alternatives**: Add metadata columns/table under schema-v1 (rejected: silently
breaks strict schema validation); introduce schema-v2/migration (rejected: new
persistence scope); sidecar Profile file (rejected: second durability/quota and
association contract); encode Profile into opaque Basic provenance (rejected:
confuses requested Profile and backend-effective facts).

## 2. One owner and one generation

**Decision**: One runtime-owned task per accepted attach, fresh Acquisition per
run, a short admission/status lock, generation-captured waiter results, and one
cleanup path. The owner drives prepare/start, then observes termination or a
stop request, then cleans up. Runtime attach takes an already resolved Profile
and is fail-fast while busy without I/O/preparation; detach joins. The Basic
edge intentionally resolves its bounded Profile first, so busy there can still
entail a Profile read, never journal/backend preparation.

**Decision**: Bind ObservationRuntime at construction to the current running
loop and executing thread, with no lazy binding/rebinding. Validate context
before attach/detach mutation or lock acquisition; synchronous status requires
that same running loop/thread and returns only an immutable nonmutating
projection. Wrong context is wrong_execution_context. Basic-edge context
validation precedes its Profile read; it does not precheck busy before resolution.

**Decision**: Derive attach_admissible from exactly
`(state in {inactive, terminated, failed}) and owner_settled and
physical_release_confirmed and recorder_close_confirmed`. owner_settled is
true initially or after all generation work is joined/quiescent. Reject
impossible lifecycle/settlement combinations; no independent admissibility flag.

**Rationale**: Acquisition.start already serializes its own open, but holding a
runtime lock across that await would prevent detach/status from progressing.
Caller cancellation must not cancel Acquisition.start, stop, backend close, or
SQLite work. New Acquisition instances avoid stale-generation coupling.
Construction-time context capture makes ownership explicit even before first
attach; a synchronous status read cannot introduce cross-thread mutation.
Derivation prevents cached/ad-hoc eligibility from contradicting cleanup facts.

**Alternatives**: Queue attaches (rejected: delayed unintended opens); cancel
the owner task (rejected: interrupts physical/journal work); use the Acquisition
state as the whole runtime model (rejected: excludes preparation and recorder
ownership); add a generalized job scheduler (rejected: unnecessary); lazy
loop binding or cross-thread dispatch (rejected: unclear initial ownership and
unneeded concurrency surface); independently stored admissibility (rejected:
permits inconsistent status/admission).

## 3. Preparation boundary

**Decision**: A single asynchronous callable accepts ResolvedDutProfile and
returns PreparedObservationRun(recorder, backend). A minimal recorder lifecycle
Protocol extends existing EvidenceRecorder with session_id, policy, and close.
It introduces no retrieval abstraction or second persistence implementation.
The concrete Basic preparation closure captures an explicit journal path.

**Rationale**: These are actual external resource creation/closure boundaries.
Shared lifecycle must await creation, verify the exact policy, and clean up
without importing SQLite or Basic types. Callable substitution allows precise
failure/cancellation tests without a factory hierarchy.

**Alternatives**: Runtime creates Basic/SQLite directly (boundary violation);
prepare all resources before admission (permits competing resources); runtime
accepts already opened connections (breaks sole Acquisition ownership); plugin
registry/repository hierarchy (not required).

## 4. Startup and journal survival

**Decision**: Resolve before runtime admission; create journal before backend
construction; start Acquisition only after recorder readiness. Keep every
created journal after failed/cancelled attach; each new attach creates a fresh
session. No append-resume or cleanup deletion.

**Rationale**: Capture must never start with an unavailable durable recorder.
Feature-003 commits session metadata before returning; later failures can
leave valid empty sessions or committed evidence. Removal would lose truthful
diagnostics. Startup failure is a runtime fact, not a new persisted evidence kind.

**Alternatives**: Open before recorder (evidence gap); remove empty sessions
(adds deletion semantics and crash ambiguity); automatically reopen the prior
session (requires resume/provenance contracts).

## 5. Positive cleanup evidence and conservative blocking

**Decision**: Before any backend open attempt, release is confirmed. Once open
is attempted, release is unconfirmed until a returned connection closes
successfully. Every failed open blocks future attach for this runtime instance.
No backend error/schema contract is expanded to support retry in this slice.

**Evidence**: `BasicSerialBackend.open` uses `_best_effort_close` after failed
configuration/open/descriptor creation, and that helper suppresses close errors.
`Acquisition.start` catches open failure without a returned connection. Failure
category, including device-not-found, cannot prove physical release.

**Decision**: Failed journal create without a returned journal marks recorder
cleanup unconfirmed, except existing CREATE/INVALID_INPUT and
CREATE/JOURNAL_EXISTS failures, which precede opening a SQLite connection.
Structural validation before submission also confirms no recorder opened.
No reopen is attempted merely to discover a hidden committed session identity.

**Evidence**: `_create_on_worker` can fail after metadata commit and its cleanup
does not return an attestation or SessionId. Successful `create` provides known
identity; successful `close` confirms closure. `close` sets its closed flag even
if worker close fails, so a later no-op cannot establish certainty.

**Alternatives**: Infer release from absent handles/categories (unsafe);
introduce normalized bootstrap/open cleanup reports (reasonable later contract
revision, deferred); retry close automatically (breaks single-close and makes
uncertainty disappear without evidence).

## 6. Acquisition additions and recorder-close barrier

**Decision**: Add a read-only AcquisitionSnapshot and additive
join_terminated() barrier. Snapshot exposes returned descriptor, last committed
segment provenance, terminal trigger, primary_failure_kind:
AcquisitionFailureKind | None, separate close_failed, and physical-release
certainty. Acquisition tracks the first actual non-close failure at occurrence;
close-only failure exposes None/true, combined failure exposes the actual primary
kind plus true, and clean termination exposes None/false. Runtime projects these
facts directly. Existing methods and legacy Acquisition.failure stay unchanged,
including legacy TRANSPORT_FAILURE for close-only failure.

**Evidence**: Current wait_terminated waits an Event only; stop returns early
for FAILED/STOPPED. `_fail` currently discards a close failure after retaining
the primary. Runtime cannot inspect private tasks or reconstruct disconnect
from retained evidence that may expire.

**Rationale**: Explicit joins prove no more appends before journal close;
committed provenance avoids phantom segments; retaining actual disconnect
trigger preserves truth when detach/cancellation races it.
The additive failure field removes any need for runtime to reinterpret legacy
failure kind using trigger/close combinations.

**Alternatives**: Read private Acquisition fields (unstable); poll journal for
segment ends (expiry/race); assume terminal state means all tasks joined
(insufficient barrier); replace Acquisition (competing architecture); decode
legacy transport failure at runtime (rejected: ambiguous primary/cleanup meaning).

## 7. Cancellation and terminal precedence

**Decision**: Shield owner work. Cancellation of admitted attach requests stop
and joins settlement; cancellation of detach joins without cancelling cleanup.
First admitted stop request wins between detach and attach cancellation.
Observed Acquisition terminal trigger takes precedence over stop intent; any
primary/cleanup failure makes runtime failed. Cancellation still propagates to
its own waiter after settlement, with failures inspectable in status.

**Rationale**: Physical close/read workers must not be abandoned. Intent and
observed cause are different facts; a disconnect cannot be relabeled to fit a
caller request. Record this distinction without new evidence kinds.

**Limitation**: No numeric lifecycle deadline or forced-abandon semantics are
introduced. A non-settling OS call keeps attaching/detaching pending; status is
available and no new attach can proceed. Core §12 DUT-completion waits are not
introduced by resource draining.

## 8. Neutrality proof

**Decision**: Run shared lifecycle assertions with a fake Basic backend and
existing Enhanced-shaped fixture, each prepared with a temporary real SQLite
journal. Fixture preparation can substitute a normalized backend under the
same resolved observation Profile; it does not advertise Enhanced Profile-v1
selection or production support. Extend gates only as tests require.

**Rationale**: Device timestamps, scoped loss, origin reset, non-serial
disconnect, and reported capability rejection exercise actual current shared
contracts. No wire/protocol/firmware/GPIO simulation is needed.

## Resolved decisions

All requested lifecycle, association, compatibility, and composition decisions
are settled in the internal contract. No product-rule change or unresolved
product decision remains. Conservative reuse limitations are explicit, rather
than gaps delegated to implementation.
