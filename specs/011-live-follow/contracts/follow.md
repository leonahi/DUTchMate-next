# Contract: Receive-Only Live Follow

Contract for011. Pure foundation, coordinator, runtime/composition, service and CLI US1 MVP are implemented.
**T019 hardening and T020 installed Follow are GREEN; T021 found no production defect and T022 documentation/Core§16 reconciliation is verified. T023 completed one triggered code-only Graphify update with recorded health/zero-node limits. T024 fresh full/installed/artifact/privacy/Core/contract review passed without correction. Final separately authorized pre-commit/full/staged/installability/privacy review passed without correction. Feature011 is software-complete and committed; implementation commit is recorded in development_status.md. Nothing pushed; Phase1/native/physical/Enhanced acceptance remain incomplete.** [Spec](../spec.md) and Core govern.
Completed003/005–010 retain their meanings. No evidence/schema/Profile/backend
revision, additional physical reader, journal connection, migration or dependency.

## 1. Admission and live start

Application input is immutable `FollowRequest(session_id: SessionId)`. No start
cursor/range, filters, replay, timeout, byte transformation or client-selected path.
Use008's exact session validation: 1..256 UTF-8 bytes, no NUL/surrogates, no
normalization. Counters are exact integers (never bool) in0..9223372036854775807.

There is **one Follow subscription per runtime**, independent of Monitor and
annotation ownership. Admission binds the captured generation before its first
await. Require the currently associated explicit session, ACTIVE/not stopping,
valid optional prepared Follow access, a committed current segment and enabled
existing read access/cleanup latch. Order: context/request validation; global stop;
association/session; ACTIVE/seal; capability; occupied Follow slot; read capacity.
Revalidate generation/ACTIVE/seal under the coordinator gate after the head read.

Under the **same append gate**, capture the actual committed journal
`next_sequence` and current segment provenance and install the subscriber's
coalesced change registration. This is its start boundary. Include records with
sequence at or after that boundary only. Current provenance is a descriptor, not
a replayed segment-start record or a promise of complete prior observation.
The boundary claims observation order, never causal isolation.

Use the captured **live reader on the same journal instance/worker**. Existing003
metadata-only retrieval suffices: an internal empty range [MAX,MAX) returns actual
`snapshot_end_exclusive=min(MAX,next_sequence)` without selecting payload rows.
Its NOT_FOUND/COMPLETE outcome is irrelevant to this internal head probe. No new
SQL, persisted field, public cursor contract or terminal opener is needed.
The strong start owner joins a submitted query even if its waiter is cancelled;
a cancelled admission unregisters any captured result before releasing its slot.
No stale result may escape into a replacement run.

`PreparedObservationRun` gains optional Follow access, defaultNone; older prepares
remain valid. A present capability must identify the same recorder coordinator,
live reader, session and exact policy as the existing prepared run/read access.
Malformed transfer follows005's existing failed-preparation cleanup, not silently
unavailable fallback. Production composition adds it to the existing explicitv3
journal/coordinator; explicitv1/v2 entry paths stay unchanged.

The inward application boundary is `await runtime.start_follow(FollowRequest)`
returning a generation-bound `FollowSubscription`. Its immutable `start` is
FollowStart; `await subscription.pull()` returns one `FollowBatch` (optional
FollowGap followed by an ordered tuple of records) or `FollowEnd` (reason and
known/unknown source cutoff). Idle pull waits for change/seal, never returns a
heartbeat or empty progress batch. `await subscription.close()` is idempotent
subscriber-only cleanup. One pull may be pending; a concurrent pull raises
FollowRejected/busy. Callers finish/discard the current batch before pulling
again; no prefetch chain. These methods retain the runtime execution-context guard.
FollowEnd contains **no network-delivery position**. The service separately adds
its offered position to a terminal frame; Core cannot know peer consumption.

## 2. Notification, bounded reads and retention

No RX-copy queue. Keep one coalesced revision/wakeup signal per subscriber.
Notify after all acknowledged append paths: acquisition, annotation, Monitor start
and Monitor end. A submitted append that raises may also signal possible change:
the journal remains authoritative if a commit acknowledgement was ambiguous.
Never notify a claimed record/time based on a failed acknowledgement. Preserve
existing Monitor publication, post-ACK clock samples, decisions and marker order;
Follow needs no new evidence-clock sampling.

One pull at a time. Reentrant pull rejects as busy, no queue. Bound each internal
page to `min(32, policy.max_retrieval_page_records)` records and
`min(1048576, policy.max_retrieval_page_charged_bytes)` charged bytes. Reuse existing
read leases and strong submitted-query ownership; idle subscriptions use **no**
008 read lease. Capacity exhaustion terminates the subscriber explicitly rather
than polling or changing the eight-lease limit.

Each pull captures a head, then retrieves the bounded half-open range
[next_sequence,head), using existing003 snapshot/retention selection. If empty,
arm/check the coalesced revision around the read-and-wait transition; a commit
during any query/clear/wait race must cause another read. A page with continuation
is consumed in order; the next pull uses the current subscriber position and a
fresh head, not an indefinitely held historical cursor. Idle heartbeats do not
poll storage. Query work and cancellation are joined, never forcibly abandoned.

Keep at most one materialized page, one currently encoded frame and one change
signal; no growing transcript, list of notifications or retained page chain.
Encoder accumulation is bounded to1048577 bytes for overflow detection.
Existing SQLite row/JSON materialization, Python scalars, socket buffers and one
policy-bounded candidate record are not claimed to fit this byte accumulator.
Release page payloads as consumed. A serialized page may contain expired
metadata plus later records; emit the gap first. Snapshot reads may materialize a
record before later eviction; delivering that retained copy is valid, without
promising future retrieval.

An expired unread interval is `[next_sequence,min(low_water,head))`.
Emit exactly that nonempty **missed_range**, with the unchanged003 coalesced
whole-prefix retention marker. Advance next_sequence to its end before later
records. Marker counters and timestamp endpoints describe the marker's entire
expired prefix, **not** just missed_range. No invented counts, synthetic observer
loss or per-record tombstones. Retention may advance again before another pull,
so multiple adjacent explicit gaps over time are valid.

If the first eligible record exceeds the fixed page charge cap (003's
zero-record charged-byte-shortage case), terminate `delivery_too_large` at that
sequence. The same reason applies if a started/record/gap frame cannot fit the
wire cap. Never spin on zero progress, skip a record, trim metadata, split a
record or tighten003's accepted policy. No retention pinning or network/stdout
await under the append gate. MAX exhaustion follows existing journal semantics;
an empty MAX boundary is legal, no sequence arithmetic beyond MAX.

## 3. Ownership and termination

The runtime owns the registration and each submitted journal query strongly.
The service owns its stream job strongly before Core admission. The client owns
only its socket/output. No idle subscriber holds a read lease, worker task,
journal-close lease or physical ownership. Network code never runs under the
coordinator gate. An in-flight query may briefly serialize with append exactly as
existing active retrieval does; no additional throughput/latency guarantee.

Client close, Ctrl-C, cancelled start/pull and service request cancellation close
the **captured subscriber** idempotently; they do not call runtime detach, stop
acquisition, cancel Monitor/annotation or close the recorder. Join already
submitted resource work, then unregister/free the Follow slot. Cancellation of an
idle wait must be immediately wakeable without waiting for another record.
A second run never inherits a prior registration or cursor.

Detach intent and service-stop intent synchronously seal starts/new pulls and
wake subscribers. Service stop must do this at the existing launch-context
`request_stop` latch, **before Uvicorn HTTP drain**, not only at lifespan detach.
Natural acquisition termination seals at its existing generation teardown.
Already-submitted reads settle; no new payload read is admitted after sealing.
An idle sealed pull returns FollowEnd immediately with any already-frozen cutoff,
otherwiseNone. It MUST NOT wait for future teardown, recorder close, a final head
probe or lifespan detach: service HTTP drain precedes lifespan cleanup. A pull
with submitted journal work joins that work, then returns the available end facts.
A bounded already-materialized page may be discarded on seal; do not drain an
unbounded tail to finish the stream.

After acquisition/Monitor/annotation owners settle, teardown may capture at most
one final metadata head for a still-registered subscriber on the same live journal,
before sealing/joining remaining read work and closing the recorder. An already
closed subscriber needs no probe. This teardown-owned probe is the sole post-seal metadata
exception, not a new public pull. Failure produces an **unknown** source end.
The existing008 permanent cleanup-uncertainty latch and recorder-close facts
remain authoritative; no cleanup retry or forced timeout is added.
Teardown joins journal work, **never a socket, idle subscriber or peer receipt**.
Freeze terminal facts in bounded in-memory subscriber state and release live
reader/coordinator references after close; service delivery can finish separately.
Already-returned FollowEnd facts never change. A known cutoff may be used only
when final for that end decision, not a stale nonterminal head snapshot. Null is
the required honest result when a final cutoff is not yet available.

Terminal reason is exactly one of:
`detached`, `service_stopping`, `source_ended`, `source_failed`,
`read_capacity`, `delivery_too_large`.
Service-stop intent has precedence over detach, then source failure/end, when
seals coincide; a delivery/read-capacity decision already fixed is not overwritten.
A non-source terminal may attempt one metadata head while still active; if
unavailable/sealed/failing, source end is null. Final stop metadata takes precedence
if already available. No query solely for terminal reporting may postpone teardown
behind a client send.

Wire terminal `next_sequence` is the first position not covered by **emitted complete
record/gap frames**; started initializes it. `source_end_exclusive` is the known
cutoff (>=next_sequence), or null when unavailable. A greater cutoff exposes the
unoffered tail; null explicitly prevents any completeness claim. It is not a
retention marker or claim that a peer consumed bytes. A successful send only
advances the service's offered prefix; the CLI independently checks its received
prefix. A transport failure may prevent any terminal frame, and then EOF is
abnormal. No guaranteed final flush or exactly-once delivery across clients.

## 4. Literal HTTP and frame grammar

Only `POST /v1/observation/follow`. Closed JSON body:

```json
{"session_id":"explicit-active-session"}
```

Existing006 raw literal-path/method/query/Upgrade/peer/Host/Origin/browser/Bearer
gates apply **before body/source work**. Follow joins the existing observation
readiness bypass set only to return its precise runtime rejection; it does not
bypass authentication or the stop latch. Actual body<=16384 bytes; detect overflow
at16385. Unknown/duplicate fields, non-string/invalid session, malformed UTF-8/JSON,
NaN, media and size errors keep existing request errors. No echoed body/path/token.

Successful admission returns200 `Content-Type: application/x-ndjson`,
`Cache-Control: no-store`, no Content-Encoding and no Content-Length. No redirects,
SSE, WebSocket, compression, replay ID or reconnect instruction. Transfer chunk
boundaries are irrelevant; **one compact UTF-8 JSON object plus LF per frame**.
Within JSON use existing008/010 canonical escaping and exact scalar/array/object
projections; embedded LF/CR stays escaped. One JSON frame<=1048576 bytes, plus LF;
no total stream-size or human-session lifetime bound.

The following are **closed** shapes; keys are shown in canonical emission order:

```text
{"type":"started","run_id":RUN,"session_id":SESSION,"start_sequence":N,"provenance":P}
{"type":"record","record":R}
{"type":"gap","missed_range":{"start_inclusive":A,"end_exclusive":B},"retention_marker":M}
{"type":"heartbeat"}
{"type":"terminal","reason":REASON,"next_sequence":N,"source_end_exclusive":END_OR_NULL}
```

Exactly one started first; zero or more records/gaps/heartbeats; exactly one
terminal last when delivery completes. No frame after terminal. RUN uses the
existing009 run-id representation; SESSION must equal the request.
P is exactly the existing008 segment-start provenance projection:
connection_id, segment_id, capabilities, backend_observation_timestamp_domain,
loss_observability, connection_provenance. Preserve opaque backend envelopes and
timestamp/loss scope; do not assume Basic or host timestamps.
R is exactly one of the **seven** existing008/009/010 closed record projections,
including canonical padded base64 RX and conditions, operation markers and
client_assertion/client_asserted annotations. No Follow evidence variant.
M is exactly008's retention-marker projection and is non-null for a gap.
No added timestamps, arbitrary errors, human text or diagnostic fields.

Service offers a heartbeat after **1 second without a completed frame** while
the stream is open, including while a journal operation is pending. Heartbeats
mean delivery liveness only; they do not sample Core's evidence clock or imply
capture health/progress. Only one pending source pull and one send at a time.
Each ASGI frame send has a **5 second cooperative deadline**, from the first
attempt for that frame, not reset by partial progress. On timeout/peer loss, close
the stream/subscriber and join submitted resource work; do not block recorder
cleanup or retry a terminal on an unusable socket. These deadlines do not
interrupt synchronous OS writes or bound durable I/O/cleanup.

Construct/validate the started frame before committing HTTP200. If it cannot fit,
unregister admission and return413 follow/delivery_too_large. Once headers are
sent, do not attempt another HTTP error: expected failures become the terminal
reason, unexpected projection/journal faults become source_failed with unknown
end if necessary. If even that cannot be sent, close; client sees abnormal EOF.
Always preserve no-store, including error responses and post-header failures.
No logging of frame contents, annotations, UART bytes, credentials or exceptions.

### Admission errors

Envelope is only `{"error":{"source":SOURCE,"code":CODE}}`.

| HTTP | source/code | Meaning |
|---|---|---|
|404|follow/no_associated_session|No associated session|
|409|follow/session_not_associated|Wrong explicit session|
|409|follow/not_active|Run inactive, per-run sealed or stale admission|
|503|follow/follow_unavailable|Missing optional capability/current provenance, read access or cleanup latch|
|409|follow/busy|Core Follow owner occupied|
|503|follow/read_capacity|All eight Core read leases occupied at start|
|413|follow/delivery_too_large|Started frame cannot fit|
|503|service/follow_capacity|Independent single service Follow job occupied|
|503|service/stopping|Existing global service stop latch|
|500|runtime/wrong_execution_context|Existing execution-context guard|
|422|runtime/invalid_request|Existing application input guard|
|500|service/internal_failure|Unexpected pre-header fault|

All common006/008 security/body/routing/readiness error pairs stay exact.
All20 JournalFailure categories before headers reuse008/009/010 mapping:
invalid_input422, session_mismatch409, journal_missing404, busy503, closed409,
all other15 kinds500, source journal/exact code. No detail, SQL, cause, path,
credential, annotation or traceback. Post-header faults use terminal/EOF above,
not these envelopes. No Retry-After, public job ID, cancellation route or result cache.

## 5. Thin CLI streaming boundary

```text
dutchmate [--host HOST] --port PORT follow --session ID
dutchmate follow --help
```

Only required session and existing global numeric loopback/port options.
No cursor/output/text/path/file/token/timeout/retry/reconnect/detach options.
Resource-free help and local lexical validation precede credential/network work.
Read the existing per-user credential once; one authenticated HTTP/1 request;
no proxy/environment/redirect/address fallback or second service request.
Old finite exchanges retain5s phases/10s absolute limits, unchanged.

Follow alone bounds connection/request/response headers/first complete started
frame by an **absolute10 seconds**, with existing5s phases. Afterwards no whole
session deadline; each next complete frame has an **absolute5 second budget**
starting after processing/output of the preceding frame. Trickle bytes do not
reset it. The1s heartbeat supports idle streams. Require exact NDJSON media
(allow only optional UTF-8 charset by the existing media parser conventions),
identity encoding and no unexpected content framing. Admission error JSON uses
the unchanged1MiB finite-response/error rules within the handshake budget.

Incrementally retain at most1048577 raw bytes to detect a frame overflow;
an HTTP chunk containing multiple frames must be consumed incrementally without
copying an unbounded chunk/transcript. UTF-8/JSON duplicate-key/NaN rejection,
closed keys/types/literals, canonical base64 and existing record/provenance
validation apply before output. Counters reject bool/out-of-range values.
No blank lines, missing LF, second started/terminal, unknown types or frames
after terminal. EOF without a valid terminal is invalid_response/exit5;
trickle timeout is request_timeout/exit5. No retry or synthetic terminal.
After terminal, require clean response EOF within the same5s frame budget;
any additional byte/frame is invalid. Do not wait indefinitely after terminal.

The CLI maintains only current stream position and bounded validation facts:
started selects the requested session and next sequence; each record must have
that exact sequence and advance it by1; each gap starts at next, is nonempty,
ends within M.expired_range, and advances to its end. M has existing coherent
whole-prefix counters/endpoints. Heartbeat does not advance. Terminal next must
equal the received position; known end>=next. Validate each record's own declared
provenance/clock/marker/annotation shape using existing delivery validators;
do not reconstruct Monitor policy, prove cross-client causation or rederive
retention counters.

Print each validated frame immediately as canonical compact JSON+LF and flush;
do not accumulate a report or decode UART text. A later failure leaves the
already-emitted valid prefix in stdout and a fixed private diagnostic in stderr.
A valid terminal exits0 (report delivered), **including a failure reason,
explicit gaps, unknown cutoff or undelivered tail**. Exit0 does not mean complete
capture, successful cleanup or no loss; terminal facts remain authoritative,
matching existing report-delivery semantics. Recognized pre-header remote
errors exit4; local input2, platform/credential3, invalid/timeout/transport5,
output/unexpected1, interrupt130 retain007 fixed diagnostic shapes.
Ctrl-C or broken pipe closes only this subscription/HTTP exchange; no detach,
synthetic terminal or final status request. Synchronous stdout writes remain
cooperative; no hard OS-write deadline or forced thread abandonment is promised.
Update help narrowly so Follow's delivered-terminal meaning is explicit.

## 6. Compatibility and acceptance

No new evidence union, codec, journal version, backend method, clock port or
Profile revision. Production stays explicitv3; oldv1/v2 factories/readers and
all seven codecs/charges stay unchanged. Active and confirmed-close terminal
ordinary retrieval remain available with the same eight leases and uncertainty
latch. Follow itself never opens a terminal reader or follows an old/restarted run.

Existing service eight mutation/eight read/one Monitor slots remain independent
of the single Follow job. Follow never takes a mutation slot for its session
lifetime. Idle Follow leaves all existing read leases free.
Monitor timestamps/matching/start/end order and annotation limiter/attribution
are unchanged. No network await, extra DUT reader, scheduler polling loop or
future reconnect/fanout framework is introduced.

Require deterministic contract and real-journal tests against both backend
fixtures; actual guarded loopback streaming (in-process buffered ASGI clients
alone are insufficient); wheel/sdist non-editable outside-cwd flows with
physical/discovery/account tripwires; existing003/005–010 regressions; defined
full checkpoints/fresh final artifact/privacy/Core review. Native Linux/Windows,
active-DUT, physical/electrical and Enhanced hardware acceptance stay outstanding.
All FR-024 deferrals remain. Planning completion is not implementation readiness.
