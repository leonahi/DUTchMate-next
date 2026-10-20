# Contract: Bounded Interact and Minimum Audited TX

Core governs. Current implementation verification/progress is recorded in
development status; the sections below define the contracts independently of
task progress. Only explicit additive revisions extend completed001–011.

## 1. Inputs, versions and authorization

`InteractRequest` has exactly `session_id`, `payload:bytes`,
`conditions:tuple[bytes,...]`, `timeout_ms:int`, `max_rx_bytes:int`.
Payload length1..4096; conditions count1..4, each length1..256; timeout1..4000 ms;
max_rx_bytes1..1048576. Exact types; reject bool, mutable bytes/coercions, empty
conditions/payload, unknown fields and numeric overflow. Duplicate conditions are
allowed; order is meaningful. Wire sessions use008's1..256 UTF-8-byte/no-NUL
constraint. Core opaque SessionId semantics are unchanged. No text transformation,
caller cursor, permission, write timeout, clock, TX-only or streaming option.

Add `InteractionPolicy` and `ResolvedInteractionProfile` as immutable v2 values.
Keep existing `ObservationPolicy`, `ProfileFormatVersion(1)` and
`ResolvedDutProfile` constructors/validation unchanged; use a separate v2 version
value and a narrow resolved-profile union where existing runtime/composition
accepts either. No inheritance that relaxes v1 policy. TOML `profile_version=2`
uses exactly004's existing closed tables/keys/limits/error precedence except
`policy.uart_tx_enabled` may explicitly be true. Omitted TX remains false;
RX/recording must be true, Control/reconnect false, no mappings/new defaults.
The existing resolver dispatches on explicit version, never upgrades v1. V2
Basic translation reuses exact UART/open-line settings. Test/example Profiles
remain observation-only unless a test explicitly exercises TX authorization.

Profile-v1 production composition remains journal-v3 and receive-only Basic.
Profile-v2 composition selects journal-v4 and the opt-in write-capable Basic
configuration, even with TX policy false: physical capability and permission
are separate. Existing Basic constructor defaults, receive-only descriptor and
backend provenance-v1 stay unchanged. Write-capable Basic uses opaque backend
provenance schema2, preserving old fields and adding `write_timeout_ms=1000` and
`write_acknowledgement_scope="backend_acceptance"`. Effective settings reflect
the library-reported timeout; a mismatch fails configuration before use. No
electrical/wire verification is asserted. No shared code branches on Basic.

`PreparedObservationRun` gains optional `interact_access=None`, preserving old
constructors/preparations. Present `PreparedInteractAccess` binds session, policy,
the same coordinator/clock and a pure codec-supplied evidence-charge callback.
No new backend opens or connection escapes Acquisition. Runtime admission order:
existing loop/thread/type guard; global Interact seal; known association; exact
session; ACTIVE/unsealed run; usable access/current committed segment; Profile-v2
TX permission; reported RX+TX; usable normalized writer; exact policy preflight;
free Interact slot. Bind generation before first await and revalidate under the
append gate before intent submission and immediately before write admission.
Missing optional access never invalidates an existing attach.

One Core Interact owner spans intent, write, observation and all audit settlement.
One independent service Interact job covers its corresponding lifetime. Busy
rejects without queue/cache/retry. Monitor, one Follow, annotation admission, eight
read leases and existing eight service read/mutation capacities remain independent.

## 2. Normalized write and Basic implementation

UART_SEND already exists in `BackendCapability`. Add optional structural
`UartWriteConnection` alongside the unchanged receive-only `BackendConnection`:
`async write(payload:bytes)->BackendWriteResult`. Its supported payload is1..4096
and its finite library/backend wait is exactly1000 ms. It owns and joins its
submitted work even if its waiter is cancelled. No adapter/library types cross
the boundary. A connection reporting UART_SEND without this contract is unusable
for Interact, not silently emulated. No separate public Core/service/CLI send API.

Result fields are exactly `status`, `accepted_prefix_bytes`, `failure_code`:

| status | accepted_prefix_bytes | failure_code |
|---|---|---|
|acknowledged|exact payload length|always null|
|partial|exact integer0..length-1|always null|
|timeout|null|always null|
|disconnected|null|always null|
|failure|null|existing BackendFailureKind literal|

An ordinary return count is a **backend-acknowledged prefix**, not measured wire
bytes. Unknown counts remain null; do not supply a lower-bound estimate. Exception
after progress can mean anything from zero to the whole requested payload was
accepted. Invalid result/count/bool is failure/internal_contract_failure with
unknown count. Pre-submission rejection is separate and cannot claim a write.
No new BackendEvent variant, backend timestamp or RX failure is invented for TX.

Standalone stored TX facts require acknowledged count1..4096 and partial count
0..4095; retained-start validation also requires acknowledged count equal to its
payload length or partial count strictly smaller. Unknown is null, never a
sentinel. Standalone structural validation never needs an evicted payload.

Basic opt-in configures `write_timeout=1.0` on the **closed** handle before open,
verifies/captures its effective value and performs exactly one pyserial
`write(payload)` in one strongly owned worker. Normal exact int0..N maps as above;
SerialTimeoutException maps timeout/unknown; positively classified disappearance
maps disconnected/unknown; other errors map normalized failure/unknown. Read
failure classification remains unchanged. No retries, remainder writes, flush,
drain, reset_input_buffer/reset_output_buffer, cancel_write, serial setting
mutation after open or synthetic wire timestamp. Preserve002 line setup/read
cancellation. One write worker may coexist with the existing read worker; no
second RX reader or reader-dependent executor deadlock.

The1000 ms value bounds the configured backend/library wait, not scheduling,
blocking OS behavior, journal latency or cancellation-resistant cleanup. Do not
abandon a thread with wait_for or force a clean-close claim on timeout.

## 3. Intent, observation boundary and ordering

Under the existing coordinator append gate, revalidate/preflight and append
`interact_started`. Only a positive durable acknowledgement permits progress.
Sample host `started_at_ns`, checked deadline=start+timeout_ms*1000000, and install
the observer before releasing the gate. Its start cursor is intent sequence+1.
After the ACK, synchronously recheck stop/cancellation/generation and admit the
one write through Acquisition while still at that serialization point. Admission
registers a strong write owner without awaiting backend I/O. Release the gate
before awaiting write completion. The registration is the Core submission
boundary: it commits to one invocation even if its worker has not run yet.
Cancellation arriving before registration suppresses TX; after it cannot retract
the write. The backend independently owns actual worker submission/join.

After positive intent ACK, a failed recheck is owned not_submitted settlement
with its stop/boundary/failure cause, never a fresh admission rejection leaving
the intent ownerless. Unexpected submission faults normalize to
transport_failure/internal_contract_failure and still attempt audit settlement.

No write occurs if intent append fails or its ACK is ambiguous; do not retry or
assert the intent absent on disk. An acknowledged intent is a **request**, not
proof of TX submission. A crash between request and settlement leaves TX status
unknown, even if the write did run. No exactly-once restart/replay/recovery feature.

Eligible evidence is committed/published after the start cursor and strictly
before the deadline; include records in the window before testing their RX bytes.
RX while the write is pending is eligible. Previously emitted bytes buffered in
hardware/USB/OS may therefore match. Results explicitly make no causal or DUT-time
barrier claim. Whole RX chunks remain evidence, including trailing/unexamined data.
No copied byte transcript, polling retrieval loop, extra reader or buffer flushing.

Match exact bytes with at most four bounded literal matchers. Earliest ending
byte wins; same-ending-byte tie uses smallest condition_index (zero based).
Support overlaps and chunk spans, never pre-boundary bytes. Loss resets every
prefix and increments observer_loss_records; loss is not RX byte budget. A match
on the last allowed examined byte wins over byte_limit. Empty RX is already
invalid under001. Never span segment/origin boundaries. Memory for matcher state
is bounded by total condition bytes (<=1024), not observation length.

Reuse009 clock semantics: host monotonic origin UUID, exact nonnegative signed
64-bit ns; sample once for each ordinary committed publication. At now>=deadline,
timeout wins and excludes that new record; a chunk admitted strictly before is
processed atomically. Freeze window at the first observation decision, using
record boundaries, not later TX/end marker sequences. Match records original RX
sequence/offsets plus condition_index; no match unless observation outcome matched.
Window starts intent+1 and ends last eligible record+1, initially empty.

All append paths use the same gate/journal worker and acknowledged sequence order:
RX, boundaries, loss, annotation, Monitor start/end and the three new kinds.
Monitor's direct start/end append paths must notify an installed Interact observer
as non-RX records without resampling/reordering its own009 decisions. Ordinary
publication shares the existing post-ACK sample when both observers are active;
new sampling for Interact-only paths must not change Monitor's existing sampling
when no Interact exists. New records are non-RX to Monitor: no byte feed/prefix
reset/observed loss. Follow's existing coalesced hint fires on all new append
attempts including ambiguous ACK; it never fabricates an acknowledged record.
No serial/network/stdout wait is held under the append gate.

For exact sample ordering: Monitor start already takes its started_at sample
after ACK; reuse it to publish that marker to Interact. Monitor end takes a
post-ACK sample only if an undecided Interact observation needs it; otherwise
retain its existing no-sample path. Interact start reuses its started_at sample
to publish that non-RX marker to an installed Monitor before releasing the gate.
Add sample-count/order assertions, not merely approximate deadline assertions.

## 4. Independent decisions, cancellation and resource ownership

Observation uses009's outcomes matched, timeout, byte_limit, disconnected, detached,
timestamp_origin_reset, recording_failure, transport_failure, service_stopping,
plus cancelled and tx_failed. `tx_failed` freezes a still-undecided observation
when write failure/partial/timeout settles before the deadline; if deadline has
already elapsed, freeze timeout. It carries no match. Already-frozen observation
facts are never rewritten. The deadline task is cancelled/joined at decision.

Overall outcome cannot become final while a submitted write is pending. Once
write and sufficient observation facts settle, choose:

1. First latched external termination before overall decision: service_stopping,
   detached, cancelled, disconnected, timestamp_origin_reset, recording_failure
   or transport_failure. Owner-loop order wins; at one synchronous seal checkpoint
   service stop takes precedence over detach, then cancellation. An already-final
   overall outcome is never rewritten during audit settlement.
2. Otherwise non-full TX: timeout→write_timeout, partial→partial_write,
   disconnected→disconnected, failure→transport_failure. A not_submitted result
   requires a latched termination; unexpected inability to submit maps
   transport_failure/internal_contract_failure without a write claim.
3. Otherwise full acknowledgement: use the frozen observation outcome. If no
   observation decision yet, keep waiting until its finite deadline/byte bound.

Freezing observation stops matching/window growth only. Continue consuming
committed connection/origin boundaries and acquisition fallback/stop facts for
the external-termination latch until **overall** decision, including after early
matched/timeout/byte_limit. Early match → disconnect → full ACK yields matched
observation and disconnected overall. Do not guard that latch with
`not observation.decided` or unsubscribe it at the early match.

An eligible early match is a frozen **observation** fact; it becomes overall
matched only with full backend ACK and no prior external termination. ACK arriving
after observation timeout does not turn timeout into success. A pre-deadline
match with a later full ACK may yield matched: observation and1000 ms write wait
are separate bounds. ACK completion/receipt is not the observation start time.

`ObservationRuntime.interact` registers its owner before yielding and shields
submitted resource work. Cancellation of its waiter latches cancelled for this
operation, suppresses write if not submitted and joins settlement before
propagating CancelledError. A lost HTTP peer/request or failed response send
latches the same operation-local cancellation; it never detaches. No cancellation
route/job IDs/results cache. After a decision has become final, delivery loss only
affects delivery. Existing Monitor/annotation delivery-only cancellation stays009/010.

Add narrow `Acquisition.submit_uart_write(payload)` admission on its existing
private connection: synchronous current-connected/capability/contract/seal checks,
one strong owner, no second open. At `_close_connection`, on explicit stop,
disconnect, origin teardown where applicable, RX/recording failure and startup
cleanup: synchronously seal write admission, join the owner, then close connection.
Basic close independently seals/joins its actual writer before handle close,
alongside002's read cleanup. Do not wait for journal audit while holding the
connection-close join: write owner settlement is independent of audit owner.

Runtime seals Interact and latches intent before requesting acquisition stop.
Join physical/acquisition owners and Interact TX-result/end audit before final
Follow head capture, read-source sealing/join and authoritative recorder close.
Existing005 terminal/cleanup facts and008 permanent uncertainty latch remain
independent; no new operation clears them or authorizes reacquisition.
Service request_stop synchronously seals/latches Core Interact **before HTTP
drain** along with009/011 seals, then joins service jobs before final detach and
006 bootstrap release. No lifecycle lock held during long joins. Hung OS/journal
work keeps ownership/shutdown pending; a finite transaction cannot license orphaning.

## 5. New evidence and journal-v4

Add exactly three kinds, each record_version4, ordinary sequence0..MAX-1,
MAX=9223372036854775807. Do not broaden Monitor's operation_kind=monitor union.

| kind | Exact metadata keys | BLOB |
|---|---|---|
|interact_started|operation_id, provenance, profile_version, authorization, conditions_base64, timeout_ms, max_rx_bytes, write_timeout_ms, clock_origin_id|exact requested payload|
|uart_tx_settled|operation_id, start_sequence, submitted, status, accepted_prefix_bytes, failure_code, acknowledgement_scope, clock_origin_id, settled_at_ns|empty bytes|
|interact_ended|operation_id, start_sequence, tx_settled_sequence, tx, tx_audit_failure, outcome, observation|empty bytes|

IDs canonical UUIDs; profile_version=2; authorization exactly
`{uart_tx_enabled:true}` (captured active policy, not caller assertion).
conditions_base64 is ordered canonical padded standard base64; provenance is
existing private003/009 representation; timeout/max_rx constraints §1;
write_timeout_ms=1000. Requested payload is never labeled actually transmitted.

TX facts are `{submitted,status,accepted_prefix_bytes,failure_code,
acknowledgement_scope,clock_origin_id,settled_at_ns}`. For submitted=true use §2;
submitted=false requires status=not_submitted, accepted_prefix_bytes=null and
failure_code=null. acknowledgement_scope is always `backend_acceptance` (a scope,
not proof that acceptance happened). settled_at_ns0..MAX is host result observation
or suppression decision time, never hardware ACK time; same origin as start.
`tx` in end is this exact summary, independent of tx_settled ACK. `observation`
is `{window,outcome,examined_rx_bytes,observer_loss_records,match,clock}`. Clock is
009's `{origin_id,started_at_ns,deadline_at_ns,decided_at_ns}`; start<deadline,
decision>=start; timeout decision>=deadline, other ordinary decisions<deadline.
If an external decision is first observed at/after deadline observation is timeout;
overall external termination may differ under §4. Match is null except matched,
then `{condition_index,start:{sequence,byte_offset},end:{sequence,byte_offset_exclusive}}`.
Examined0..1048576, loss0..MAX; window/match limits and count consistency follow009,
condition_index0..conditions.count-1. Validate paired facts only when both retained.

Each TX/end record has start_sequence strictly below its own sequence. A nonnull
tx_settled_sequence is strictly between start_sequence and end sequence. Retained
paired IDs/TX facts agree; TX origin equals start origin and settled_at_ns is at
least observation.clock.started_at_ns. Where the start is evicted, standalone
validation still enforces its own bounds without inventing the missing clock.

After write settlement/suppression, attempt uart_tx_settled once, possibly while
observation remains active. Wait for frozen observation and final overall decision
before attempting interact_ended once, after the TX-audit attempt, even if that
ACK failed. Its tx_settled_sequence is null
unless positively acknowledged; tx_audit_failure null on ACK, otherwise only
`{source:"journal",code:<existing kind>}` or service/internal_failure. End repeats
actual TX facts so a positively acknowledged end can honestly preserve them even
when the intermediate ACK was lost. No claimed missing record or synthetic ref.
Final report includes each acknowledged ref and each independent audit failure;
start ACK is mandatory. If clocks/infrastructure prevent valid facts, normalize
internal failure after joining work, without fabricated times/end/report.

Explicit `create_v4/open_v4` and `encode_evidence_record_v4/decode_evidence_record_v4`
select schema4 in PRAGMA user_version and session metadata. Preserve APPLICATION_ID
0x4455544D, three tables, single worker, atomic append/retention, strict selected
version dispatch and existing failure mapping. All seven old kinds retain their
exact record versions/canonical metadata/BLOB/charges; v4 delegates them to v3.
Default v1 factories/helpers and explicitv2/v3 stay strict; no migration/guessing.
V4 terminal targets explicitly select4 and read only through008's confirmed-close
mode=ro/query_only validator; no writable fallback or historical-session discovery.

Canonical metadata: ensure_ascii=False, allow_nan=False, sort_keys=True, compact
recursive JSON. Charge unchanged:16+kind UTF-8 bytes+metadata UTF-8 bytes+BLOB bytes.
All three new kinds have rx_payload_bytes=0 and null cached backend timestamp
endpoints; host timing never becomes backend observation provenance. Extend
timestamp-context dispatch/endpoint scans to skip new host-only records and
retained Monitor-pair validation to traverse them without false RX identity errors.
Retained Interact pairs must agree on IDs/start/request/condition/match/TX facts;
unpaired records remain legal after eviction or crash. Known unsupported record
version→incompatible_record_version, unknown/malformed→corrupt_journal, wrong
schema→incompatible_schema_version, bad new input→invalid_input, inconsistent
retained pairs→invariant_violation. Preserve all20 JournalFailure categories.

Before start, use pure codec callback for the actual start charge and conservative
max charges for valid TX settlement and end variants, including full/partial/
unknown/suppressed writes, each observation/outcome, match/no match and missing TX
audit ACK. Use maximum-width legal counters/times/positions and fixed bounded
failure literals; never invalid combinations or a hand-estimated charge. Each of
the three maxima must fit max_record_charged_bytes, max_retained_charged_bytes and
max_retrieval_page_charged_bytes. Preflight maximum-shape arithmetic must be legal,
but makes no sequence-capacity promise or reservation against ambient RX; no new
head query/cache/lease is introduced. Start append exhaustion suppresses TX;
later audit exhaustion preserves actual TX facts with unconfirmed references.
No policy inflation,
pinning or guarantee against subsequent storage/counter/retention failure. Ordinary
rolling retention may evict any of these records before the report is delivered.

## 6. Explicit delivery compatibility

Add a literal API-v2 allowlist, reusing existing handlers/owners, not a router or
command framework: `/v2/observation/{status,attach,detach,monitor,annotations,follow}`
and `/v2/evidence/{record,page}`, with the **same methods** as corresponding v1
routes. Add only `POST /v2/observation/interact` for the new workflow. No v1 Interact.
All existing raw-path/method/query/media/security checks apply; no aliases or
automatic negotiation. V2 can carry existing v1 Profiles/legacy journals too.

API-v1 remains001–011: its attach accepts only Profile-v1 and produces journal3;
it never emits Profile-v2 or new evidence kinds. If v1 selects a known Profile-v2/
schema4 run, return409 `request/unsupported_api_version` before mutation, subscriber
admission or query (attach may resolve its bounded Profile to detect2, but creates
no journal/backend). This restriction covers status/detach/Monitor/annotation/
Follow/retrieval too, so old projections never see a partial filtered stream.
Security and existing session/association validation precede this version check;
it precedes state-changing/Core query admission. No fabricated v1 snapshot or
silent field stripping. Legacy clients can reject this new explicit error; their
supported v1 runs and all existing errors/shapes remain unchanged.

Attach resolves its Profile once: version validation and runtime preparation use
the **same immutable resolved value**, never a precheck followed by path reread.
Other version checks bind the actual captured Core generation at admission under
the existing lifecycle serialization; a stale service status snapshot cannot
authorize a job against a replacement run. This includes status/detach without
an explicit session and registered-but-not-yet-invoked service jobs. No additional
request, lock held over I/O or generic admission framework is required.

V2 lifecycle responses reuse the existing closed shape, allowing format_version2
and the corresponding v2 policy; v1 keeps its validator unchanged. V2 evidence
adds three closed projections: kind,sequence followed by the §5 metadata in table
order; interact_started additionally ends with payload_base64. Empty BLOBs omitted
as in existing non-RX projections. All old seven projections are byte-identical.
New interact_started provenance uses the **public008 segment provenance
projection**, not §5's private persisted codec spelling. The remaining fields
follow §5's closed scalar/array/object shapes.
V2 Follow keeps011's five-frame grammar and bounds, with only this expanded record
union. Same journal/read leases/snapshot/cursor/retention gaps, not a second stream.
V2 Monitor/annotation requests/reports unchanged; provenance envelope remains opaque.

CLI adds global `--api-version 1|2`, default1; invalid values fail before credentials.
Version2 selects the literal corresponding v2 path for each existing command;
there is no probing/fallback/status preflight. Version1 preserves every existing
command/request/output and validator. Version2 selects the explicit expanded
Profile/evidence validators; shared validation of old kinds remains exact.
Thus v4 readback/Follow requires explicit --api-version2, including from new CLI.

## 7. Authenticated bounded Interact delivery

Closed POST body, canonical order:

```json
{"session_id":"explicit-session","payload_base64":"AAH/","conditions_base64":["T0s=","RkFJTA=="],"timeout_ms":4000,"max_rx_bytes":1048576}
```

Canonical padded standard base64 only; payload encoded length<=5464 and each
condition<=344. Actual UTF-8 body<=16384 bytes, detect16385 independently of
Content-Length; all legal values fit with worst-case escaped session. Preserve
duplicate-key/NaN/unknown-key/type rejection and006 peer/Host/Origin/browser/Bearer/
Upgrade checks **before body work**, no-store on every response, private diagnostics.
Existing415/413/422 request errors unchanged. No CORS/docs/logging/security bypass.

Service registers one independent strong Interact job before Core admission;
capacity503 service/interact_capacity, no queue. Registered-before-stop jobs
recheck global seal. Monitor/Follow slots and mutation/read capacities unchanged.
Watch request disconnect while waiting, cancel only that Interact waiter/latch,
retain/join its owner; cancellation of HTTP task also follows this path. No
abandoned task, retry, public handle, cancellation endpoint or result retrieval API.

HTTP200 report canonical keys:
`run_id,session_id,operation_id,provenance,payload_base64,conditions_base64,outcome,
started_record,tx_settled_record,ended_record,tx,observation,durability,audit_failures`.
Refs are008 session/sequence objects or null; started_record never null. TX and
observation exactly§5 with original backend provenance projected as008. Add
`boundary_basis:"core_observation_order"` and
`causation:"not_established"` inside provenance beside the existing segment
projection; these are explicit result limits, not backend measurements.
`durability` is complete/tx_unconfirmed/end_unconfirmed/both_unconfirmed according
to positive TX/end refs. audit_failures is ordered array length0..2 of
`{record_kind,source,code}` for failed tx/end ACKs only. No inline RX excerpt,
unbounded evidence or derived text. Complete means acknowledged appends, never
simultaneous retention, power-loss guarantee or physical transmission.

Whole JSON<=1048576 bytes; oversized response returns413
interact/delivery_too_large after owned settlement, without trimming or replay.
No network wait under append gate. All common security/body/lifecycle journal
errors retain existing source/code mapping. Additional Interact rejections:

| HTTP | source/code |
|---|---|
|404|interact/no_associated_session|
|409|interact/session_not_associated, interact/not_active, interact/busy|
|409|interact/policy_denied, interact/capability_unavailable|
|503|interact/interact_unavailable|
|422|interact/evidence_policy_incompatible|
|503|service/interact_capacity, service/stopping|
|409|request/unsupported_api_version|
|413|interact/delivery_too_large|

Unexpected invalid clock/application-report invariant/projection faults→500 service/internal_failure
after joining work; start JournalFailure uses008 mapping, no report/reference.
Malformed backend returns normalize to §2 failure/internal_contract_failure and
remain audited report facts, like other backend write failures after start;
they are not HTTP rejections.

CLI grammar (all options required):

```text
dutchmate --api-version 2 [--host HOST] --port PORT interact --session ID --payload-base64 BASE64 --condition-base64 BASE64 [--condition-base64 BASE64 ...] --timeout-ms MS --max-rx-bytes N
dutchmate interact --help
```

Interact with version1 fails locally before account/credentials/network. Help
remains resource-free. Bounds/base64 validated before credential lookup; no file,
stdin, text, line endings or secret argv diagnostics. One credential read/one
finite authenticated exchange; unchanged0075s phase/10s whole deadline and1MiB
response cap (+LF output), identity encoding and strict error/report validation.
No sleeps, local timing model, read loop, retry or implicit attach/detach.
Validate identities/refs/TX/observation/outcome/durability relationships and closed
field sets before emitting one compact JSON+LF. A valid report exits0, including
timeout/partial/cancelled/failure; this means delivered facts, not DUT success.
Existing local2/credential3/remote4/delivery5/unexpected-output1/interrupt130 exits
remain; new version error is recognized remote4. Timeout/interrupt/pipe loss may
leave submitted bytes accepted: report no invented cancelled result, no proof of
zero TX and no follow-up status request. Server independently joins cancellation.

## 8. Acceptance boundaries

Require deterministic tests for every result/count, multiple-condition ordering,
write-time RX, gate interleavings, all audit ACK ambiguities, pre/post-submission
cancellation, natural disconnect/recording failure and join-before-close, same-run
Monitor/Follow/annotations/readback, v1/v2 delivery isolation, all legacy codecs,
policy bounds/retention, security and actual guarded installed-process behavior.
Default pytest must not discover/open real devices. Use both backend shapes
identically, varying only reported capabilities/provenance, plus Basic library
fakes and real temporary SQLite. No hardware, Console, generic TX/framework,
Control, handoff/reconnect, text/regex, Enhanced production, MCP or AI.
