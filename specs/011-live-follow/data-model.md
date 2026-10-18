# Data Model: Receive-Only Live Follow

[Contract](contracts/follow.md) owns exact values/wire grammar. Pure values/state
and coordinator registration/wakeup/pull plus T009 runtime/composition are implemented.
T011 service and T013 CLI US1 MVP are implemented; T019 hardening and T020 installed Follow are GREEN. T021 found no production defect; T022 completed-evidence/Core§16 reconciliation is verified. T023 completed one triggered code-only Graphify update with recorded health/zero-node limits. T024 fresh full/installed/artifact/privacy/Core/contract review passed without correction. Final separately authorized pre-commit/full/staged/installability/privacy review passed without correction. Feature011 is software-complete and committed; implementation commit is recorded in development_status.md. Nothing pushed; Phase1/native/physical/Enhanced acceptance remain incomplete.
No database/schema/evidence union change, migration, new durable identity or Profile setting.

## Values and boundaries

| Value | Fields / invariant |
|---|---|
|FollowRequest|Validated SessionId only; no historical position or filter|
|FollowStart|Captured run/session, start_sequence0..MAX, current SegmentProvenance; no synthetic segment-start record|
|PreparedFollowAccess|Optional captured coordinator/live reader association, same session and policy; defined with other preparation transfers to avoid module cycles|
|FollowGap|Nonempty missed_range starting at subscriber position; non-null unchanged RetentionMarker covering that range|
|FollowBatch|Optional gap followed by one bounded ordered tuple of existing records; no empty progress batch or heartbeat|
|FollowEnd|Closed reason and known source_end_exclusive orNone; Core source fact with no network-delivery position|
|Wire terminal|FollowEnd reason/cutoff plus service offered next_sequence; cutoff>=next when known; delivery report, not evidence|
|FollowRejected|Closed application rejection categories mapped exactly in contract; no path/detail/cause|
|Subscriber state|Captured generation/start, next read position, at most one page, one coalesced change signal, seal/end/close facts|

Reuse existing SessionId, SegmentProvenance, SequenceRange, EvidenceRecord,
EvidencePage and RetentionMarker. RunId stays in runtime.py; FollowStart carries
its immutable value string supplied by the captured runtime, without importing
runtime or defining another run identity. No duplicate normalized records, timestamp
envelope, cursor token, generic message bus or subscriber repository.
Pure Follow values/state belong in `core/src/dutchmate_core/follow.py`; transfer
wiring may stay beside PreparedObservationRun in runtime.py to avoid a reverse
dependency on Monitor/coordinator. Delivery frame dictionaries remain outside Core.

## State transitions

`admitting → live ↔ waiting → sealed → terminal → closed`.
Admission rejection/cancellation goes directly to joined cleanup/closed.
Client cancellation may close without a wire terminal. A live delivery/read
failure fixes its terminal reason once. Seal is synchronous/idempotent and wakes
waiting work; no new public pull is admitted afterward. A sealed idle pull returns
an end immediately, using an already-known final cutoff orNone. It never waits
for HTTP drain/lifespan cleanup. Teardown's optional final probe may fill a cutoff
only before an immutable FollowEnd is returned, never revise a delivered end.

The coalesced signal is cleared **before** the gated head snapshot, never after a
read that could race publication. A wake during subsequent selection/wait stays
observable. A boolean Event is sufficient; a bounded equivalent may be used.
No per-record notification list, copy of RX payloads, independent polling task,
clock sample or sequence claim is stored in a notification.

## Two positions, two facts

The internal page/read position can move while a page is materialized; the service's
**offered position** moves only after a complete frame send. Neither proves peer
consumption. The CLI separately advances its received position only after full
validation. Never use a prefetched page end to claim delivery.

A gap advances the offered/received position by its missed interval; a record
advances by1; heartbeat advances nothing. Shutdown can discard a prefetched tail.
Terminal uses the offered position and a frozen known/unknown source cutoff.
Core returns FollowEnd source facts, not a claim about socket delivery. The
service owns its offered counter; the CLI owns its independently received counter.
Ordinary retention metadata alone cannot prove a client missed every record in
the marker's whole prefix. No terminal-delivery suffix is relabelled as retention.

## Bound inventory

| Resource | Bound |
|---|---|
|Core subscriber / service Follow job|One each, no queue; independent existing slots|
|Pending public pull / page|One each|
|Page records|min(32, policy retrieval records)|
|Page charged bytes|min(1048576, policy retrieval charged bytes)|
|Idle notification|One coalesced signal|
|Submitted journal reads|Existing008 strong leases, at most eight across generations; idle Follow uses zero|
|Request body|16384 bytes, detect16385|
|Encoded frame|1048576 JSON bytes plus LF; overflow accumulator1048577|
|CLI partial-frame state|1048577 raw bytes maximum for detection, not a transcript|
|Human stream lifetime/total bytes|No aggregate bound; per-frame/send/handshake limits apply|
|Durable Follow state|None|

These are logical delivery/state bounds, not exact SQLite/Python/OS/RSS bounds.
One policy-bounded candidate record can be materialized before a charged-byte
shortage is known. Never claim the encoded-byte cap limits all infrastructure memory.

## Existing state preserved

Runtime lifecycle/association and permanent008 read-cleanup uncertainty remain
authoritative. No subscriber can promote a run to ACTIVE, attach/reacquire,
close a recorder, reset cleanup uncertainty or switch generations.
Service owns its request/socket; Core owns deterministic admission/order and
submitted journal work. CLI validates wire data only.
Existing003/v1,009/v2 and010/v3 stored values and exact bytes/charges do not change.
