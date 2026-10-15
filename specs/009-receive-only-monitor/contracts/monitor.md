# Contract: Bounded Receive-Only Monitor

Core governs. Completed001–008 remain authoritative except the explicit additive persistence/projection revision in §4. This document defines the implemented Monitor contract. Acceptance evidence is recorded in [history](../../../docs/development_history.md); T001–T037 and final software verification are complete; native/physical acceptance remains pending. Contract requirements below are unchanged.

## 1. Application inputs, capability and admission

Pure application values in `core/src/dutchmate_core/monitor.py`: `MonitorRequest`, `MonitorReport`, `MonitorOutcome`, `MonitorRejected`, `PreparedMonitorAccess`, `MonitorClock`, and a small concrete committed-record coordinator. The coordinator wraps the existing `EvidenceRecorder`; it is neither another journal nor another RX reader. Clock port: synchronous `now_ns()->int`, asynchronous `wait_until(deadline_ns)->None`; monotonic nonnegative signed-64-bit ns, one Core-owned canonical UUID clock origin per runtime incarnation. Infrastructure supplies the real clock; application imports no framework, backend-specific, SQLite or filesystem implementation.

Required request: `session_id:SessionId`, exact `condition:bytes` length1..256, `timeout_ms` exact int1..4000 and `max_rx_bytes` exact int1..1048576. No bool/coercion/default/start-cursor/clock input. Wire session limit1..256 UTF-8 bytes, no NUL, stripping, normalization or path meaning; existing opaque Core SessionId semantics stay unchanged.

`PreparedObservationRun` gains optional `monitor_access=None`, preserving old constructors and attach-only callers. Present access identifies the transferred recorder session/policy and **same** coordinator. It supplies a synchronous pure `charge_markers(start_draft, maximum_end_drafts)->tuple[int,int]` persistence callback, returning exact positive signed-64-bit charges from the adapter codec. Core never imports or reproduces that private codec. Production preparation explicitly supplies it; missing access does not reject attach. Failed/terminal preparations never receive Monitor support. The coordinator implements existing ObservationRecorder session_id/policy/append/close; close delegates to the sole underlying journal after owners settle, creating no new resource. Composition transfers that coordinator as recorder; the existing journal remains the live read source and authoritative close target.

`ObservationRuntime.monitor(request)->MonitorReport` applies existing owner-loop/thread/type guard, rejects a global incarnation seal as monitor_unavailable, then checks in order: known association, explicit session equality, ACTIVE/per-run unsealed state, usable access and committed current segment, reported `uart_receive`, marker policy fit, free Monitor slot. Bind run/session/access before first await. One Core owner spans start, wait, end and settlement; busy persists through late marker settlement. No queue, cache, result history, task handles or operation catalogue.

Before submitting start, after waiting for the coordinator gate, revalidate run seal/current committed segment/readiness/policy. Detach before submission rejects without a marker; a committed segment change while waiting fails conservatively, never switches the pinned boundary silently. Coordinator provenance is authoritative because the acquisition status snapshot can lag append acknowledgement. No backend-name check or capability emulation. Terminal/attaching/draining runs cannot Monitor; a new admitted attach removes selection of the preceding association as in008.

## 2. Observation boundary, matching and deadline

Serialize acquisition and operation appends around the **existing journal gate/single worker**. After positive append acknowledgement, publish the returned immutable record synchronously on the owner loop before releasing the coordinator gate. No retrieval/polling loop, subscription framework, copied RX queue or independent reader/timestamp stream.

For start, revalidate/preflight, commit `operation_started`, sample `started_at_ns`, compute `deadline_at_ns=started_at_ns+timeout_ms*1000000`, install matcher/window/timer before releasing the same serialization point. Cursor is start sequence+1. Clock overflow/invalid infrastructure detected before submission rejects; unexpected post-start faults remain owned and normalized without invented clock/ref facts. Start evidence stores origin/request duration, not a fabricated post-commit timestamp; end/result store the actual sample. Pre-start bytes cannot match; previously emitted but buffered bytes committed later may match. No DUT-time or causal barrier.

Sample host time once per committed record. **Strictly before** deadline, include the record in the Monitor watermark and process it synchronously. RX chunk eligibility is atomic; do not resample per byte. Literal matching is linear in examined bytes, supports overlap/chunk spans, and retains at most256 prefix/position entries. Empty RX consumes no byte budget. Observed loss increments `observer_loss_records`, resets the prefix and remains in evidence; unobservable loss stays unknown. Never span connection/segment/origin boundaries.

Examine RX in order, incrementing `examined_rx_bytes` per tested byte. First match wins; match on the last allowed byte beats `byte_limit`. Otherwise that byte decides byte exhaustion. Preserve the **entire** committed RX chunk, including unexamined trailing bytes; no asynchronous output is removed. The window uses record boundaries, while match positions/examined count express the finer tested boundary.

Before publishing a record or deciding a stop/failure, check host time: `now_ns>=deadline_at_ns` decides timeout and excludes that new record from the Monitor watermark. The timer uses the same rule. Timeout wins equality regardless of timer/record/stop scheduling. Before deadline the first owner-loop terminal decision wins. An eligible chunk finishes atomic processing even if CPU time crosses the deadline; its publication sample is the decision time for a match/byte-limit. The bound concerns observation eligibility, not CPU/durable I/O latency.

Freeze `window={start_inclusive:start_sequence+1,end_exclusive:last_included_sequence+1}` at decision. Initially last included sequence is the start marker, so an empty window is valid. Eligible loss/end-boundary records are included. End is **not** the later end-marker sequence; ambient RX and end latency cannot extend it. No window-byte copying/pinning/re-query for matching.

`match` is null except for `matched`, then `{start:{sequence,byte_offset},end:{sequence,byte_offset_exclusive}}`, zero-based positions in original RX payloads. It can span records, never observed loss/segment boundaries. End is after the matching byte, not the whole chunk. These derived facts survive eviction as references; subsequent retrieval may expire.

## 3. Outcomes, lifetime and independent durability

| Outcome | Terminal observation event |
|---|---|
|matched|First literal match before deadline/byte exhaustion|
|timeout|Host deadline reached, including equality|
|byte_limit|Last permitted examined byte did not complete a match|
|disconnected|Committed segment end or fallback acquisition fact disconnected|
|detached|Runtime explicit detach seals the run before deadline|
|timestamp_origin_reset|Origin/segment transition, never cross-boundary continuation|
|recording_failure|Acquisition recording failure before deadline|
|transport_failure|Acquisition transport failure before deadline|
|service_stopping|Service seals Monitor admission before deadline|

Segment `explicit_stop` maps to latched detach/service-stop intent, otherwise `detached`. Other existing segment reasons map directly. A new segment without an expected end conservatively terminates `timestamp_origin_reset`. Existing acquisition join/terminal publication supplies fallback facts when no end record positively commits; no snapshot polling or extra reader. If publication is delayed by capture cleanup beyond the deadline, timeout wins rather than inventing an earlier observed terminal event. Never rewrite capture/runtime outcomes. A timer/stop/fallback may decide without RX.

Detach seals admission/latches intent synchronously before acquisition stop; decide installed Monitor, join acquisition/consumer/backend close and all Monitor marker owners **before** existing live-read seal/join and authoritative recorder close. Joins never hold the short lifecycle lock. Stop after start worker submission latches pending intent, joins start and, if positively committed, immediately decides the installed operation before appending end. Start failure yields normalized error without reference/result/retry; ambiguous commit is not asserted absent on disk.

Shutdown immediately latches service stopping, seals all read/mutation/Monitor registration, and calls an owner-loop Core Monitor seal (no backend I/O). It permanently rejects new Monitor for the incarnation, latches `service_stopping` for pending owners and decides installed work. Registered-before-Core jobs reject. Join read/mutation/Monitor jobs, then existing final detach/token/listener/marker/lock sequence. Preserve008's permanent reader-cleanup latch and006's positive clean-marker conditions; no operation resets them or certifies physical cleanup.

Strong tasks are registered before yielding, shielded from cancelled delivery and consumed/joined through resource settlement. Client loss, local HTTP timeout, SIGINT or closed stdout affects delivery only. After decision cancel/join the internal deadline-wait task (never a submitted journal worker), so an early match need not wait to the timeout. No public cancellation, retries, replay or retained results. Hung journal/OS work keeps shutdown pending; **4000 ms observation does not bound total HTTP/cleanup** or permit worker abandonment.

Append end once with frozen facts. Positive acknowledgement: `durability:"complete"`, positive end ref, `end_failure:null`. This means acknowledged marker commits, not simultaneous retention or physical power-loss guarantees. End acknowledgement failure preserves observation outcome/window/match/timing with `durability:"end_unconfirmed"`, `ended_record:null`, `end_failure:{source:"journal",code:<declared kind>}`; unexpected end faults use service/internal_failure. Marker-only failure does not stop/reclassify capture. No ambiguous retry/fabricated ref. Unexpected faults preventing a valid observation decision return500 service/internal_failure after owned settlement, without inventing a report/end timestamp; an acknowledged start may remain unmatched on disk. Normal finite clocks/conditions produce the explicit outcomes above.

## 4. Exact operation records and persistence revision

Add normalized immutable `OperationStartedEvidence`/`OperationEndedEvidence` and pending drafts to existing unions. No sidecar/operation table/registry or extra retention mechanism.

| Kind (record_version2) | Exact metadata field set | BLOB |
|---|---|---|
|operation_started|operation_id, operation_kind, provenance, timeout_ms, max_rx_bytes, clock_origin_id|exact condition bytes|
|operation_ended|operation_id, operation_kind, start_sequence, window, outcome, examined_rx_bytes, observer_loss_records, match, clock|empty|

Kind/sequence remain existing columns. `operation_kind` exactly `monitor`; operation/host-origin IDs canonical lowercase hyphenated UUIDs. Provenance uses existing private record-v1 representation/validator, not HTTP spelling. Persisted metadata uses the existing canonical encoder: ensure_ascii=False, allow_nan=False, **sort_keys=True**, compact separators, recursively sorted keys; the table specifies fields, not insertion order. Exact additive pure helpers are `encode_evidence_record_v2/decode_evidence_record_v2`; default v1 helpers remain strict. Window/match are §2. Clock has `origin_id,started_at_ns,deadline_at_ns,decided_at_ns`; integers0..MAX, start<deadline, decision>=start. Timeout decision>=deadline; ordinary other decisions<deadline (eligible match/byte-limit uses publication sample). End start_sequence0..MAX-1, window.start=start_sequence+1, end>=start; examined0..1048576 (positive for matched/byte_limit), observed-loss0..MAX. Validate structural relationships without requiring evicted/failed paired records. If both markers remain retained, operation/configuration/match bounds must agree. End BLOB is exactly empty bytes, not SQL NULL.

Marker `rx_payload_bytes=0`, cached retention timestamp endpoints null: host timing is not backend timestamp evidence. Exact003 charge remains **16 + UTF-8 kind bytes + canonical compact metadata JSON bytes + BLOB bytes**. Pattern contributes charge, never UART RX telemetry. Existing total order, counters, rolling prefix eviction/coalescing, database ceiling and durable acknowledgement remain. Markers may evict RX/each other; no reservation/pin or simultaneous-retention promise.

Explicit infrastructure factories `SqliteEvidenceJournal.create_v2/open_v2`; default `create/open` remain strict schema-v1. Service composition creates v2. Keep003's APPLICATION_ID=0x4455544D and three-table organization/mechanics; PRAGMA user_version and session_metadata.schema_version are2 only in v2, with strict supported variant validation. Four old kinds keep record_version1 and **byte-identical metadata/charge** inside v2. Only two markers use record_version2; unknown kind/version rejects. Wrong expected schema maps incompatible_schema_version; unsupported kind/version pairing maps incompatible_record_version; unknown kind/malformed decoded marker maps corrupt_journal; invalid new input maps invalid_input; paired retained-record inconsistency maps invariant_violation. V1 rejects v2/new variants; no silent CHECK/codec reinterpretation, legacy migration/repair or record-based version guessing. Explicit infrastructure open_v2 retains003's existing reopen mechanics for an explicitly selected v2 artifact; no new recovery behavior, service restart browsing or use of writable open for terminal retrieval.

Preflight actual start charge (condition+captured provenance) and conservative maximum end charge using the same pure canonical codec. Core supplies exactly nine legal standalone maximum-shaped end drafts, one per outcome: matched has the nonnull maximum-width match, all other outcomes have null; clock facts satisfy that variant, examined count is at most1048576 and sequence/offset/loss/timing counters use maximum legal widths. The pure charge callback returns the start charge and **maximum** encoded end charge across that fixed tuple. These are feature-wide normalized maxima, not claims all variants are reachable for this particular request; never combine the longest nonmatched outcome with an invalid nonnull match. Both charges must fit `max_record_charged_bytes`, `max_retained_charged_bytes` and `max_retrieval_page_charged_bytes`; otherwise evidence_policy_incompatible before submission. No hand-estimated charge, policy inflation or guarantee against later counter/database/ambient/I/O failure. Profile-v1 is unchanged; conservative preflight may reject a valid small policy.

Terminal target captures expected journal format (default1 legacy, explicit2 new composition). Existing fresh `mode=ro&cache=private`, verified `query_only`, identity/session/policy read transaction dispatches to the **strict expected-version** validator and unchanged003 selectors. No writable fallback/recovery/migration, immutable/nolock/pool, retained writer or client-selected path. Still only current/last association in this incarnation, after confirmed writer close/owner settlement.008 cleanup uncertainty applies unchanged.

Add exactly these closed evidence HTTP/CLI variants:

| Kind | Canonical remaining JSON keys after kind,sequence |
|---|---|
|operation_started|operation_id, operation_kind, provenance, timeout_ms, max_rx_bytes, clock_origin_id, condition_base64|
|operation_ended|operation_id, operation_kind, start_sequence, window, outcome, examined_rx_bytes, observer_loss_records, match, clock|

Start provenance is existing public006/008 ProvenanceView; condition canonical padded base64. All fields project immutable facts. Four old shapes remain exact, with no added record_version wire key. All003 outcomes, zero-shortage pages, retention, snapshots, charge limits and008 cursor cap1024/whole413 remain unchanged. Oversized new marker/provenance follows existing overflow behavior, no split/trim/substitute cursor.

## 5. Authenticated HTTP and independent delivery bounds

Only literal `POST /v1/observation/monitor`, no query/slash/method aliases. Same006 peer/Host/Origin/browser/Bearer/Upgrade/literal route gate **before** body/session/journal; no-store and existing strict JSON media rules. No CORS/docs/bootstrap/token changes.

Closed required request, canonical order:

```json
{"session_id":"known-session","condition_base64":"UEFTUw==","timeout_ms":4000,"max_rx_bytes":65536}
```

Strict UTF-8, no duplicates/nonfinite/coercions/extra fields. Body<=16384 actual bytes, detect16385 independently of Content-Length. Session §1; standard RFC4648 canonical padded base64, no whitespace/URL alphabet/nonzero pad bits, decode/re-encode identical and decoded1..256 bytes. Timeout/byte bound exact ints §1. No run/path/profile/database/start/clock/output selector.

After security: readiness, strict body, independent single registered Monitor slot, strongly own job then Core admission. Slot separate from8 old mutation/8 read jobs/8 Core read leases. No queue. Service overflow503 service/operation_capacity; Core busy409 monitor/busy.

HTTP200 closed canonical result fields:

```text
run_id, session_id, operation_id, provenance, outcome, started_record,
ended_record, window, examined_rx_bytes, observer_loss_records, match,
clock, durability, end_failure
```

Run/session nonempty exact strings; operation UUID; provenance captured public view. Refs `{session_id,sequence}`; start acknowledged, end nullable per durability. Window start_inclusive/end_exclusive; match §2, clock §4; counts0..MAX, examined within request. Outcome §3. End error only `{source,code}`; no detail/operation/path/SQL/cause/traceback.200 means report delivered, not necessarily match/complete evidence.

Use008 canonical compact UTF-8 (`ensure_ascii=False`, `allow_nan=False`, separators comma/colon), declared nested order, independent **1048576-byte** service cap and bound+1 accumulation. No inline RX or text explanation. Whole overflow413 `{error:{source:"monitor",code:"delivery_too_large"}}`; operation already settled and references can be explicitly retrieved. No trimming/refetch/auto-pagination/substitute result; old evidence overflow keeps evidence/delivery_too_large. CLI independent JSON cap1048576 **plus LF**, raw response detection bound1048577, identity Content-Encoding/media checks unchanged. No claim of an exact SQLite/socket materialization ceiling.

## 6. Exact errors and privacy

ErrorEnvelope remains `{error:{source,code}}`; all common006/008 gates/media/privacy pairs unchanged.

| HTTP | source/code | Meaning |
|---|---|---|
|404|monitor/no_associated_session|No known current session|
|409|monitor/session_not_associated|Explicit session differs|
|409|monitor/not_active|Run not ACTIVE/per-run sealed|
|503|monitor/monitor_unavailable|Missing support/committed ready segment or global seal|
|409|monitor/capability_unavailable|No reported uart_receive|
|409|monitor/busy|Core owned slot busy|
|422|monitor/evidence_policy_incompatible|Either marker cannot fit policy|
|413|monitor/delivery_too_large|Whole result cannot fit|
|422|request/invalid_request|Wire fields/bounds/body/encoding invalid|
|503|service/operation_capacity|Registered Monitor slot exhausted|
|500|runtime/wrong_execution_context|Wrong loop/thread|
|422|runtime/invalid_request|Wrong application request type|
|500|service/internal_failure|Unexpected infrastructure/application/projection fault|

Checked unusable injected clock/access before start is monitor_unavailable. Unknown later faults remain owned/normalized as §3. Start `JournalFailure` mapping exactly008: invalid_input422, session_mismatch409, journal_missing404, busy503, closed409; other15 kinds500. Source journal and exact declared code, including slash capacity codes. End embeds journal code independently of outcome. Existing008 writable standard exception metadata/sealed fact fields stay intact; no frozen-exception regression or detail leakage.

Security/body/capacity rejection causes no Core/marker work. No raw diagnostics echo credentials, condition/request body, paths or remote errors. Authenticated condition evidence is intentional content, never a diagnostic log/credential. Original commands retain their error validators except additive marker shapes in evidence.

## 7. Exact thin CLI

```text
dutchmate [--host HOST] --port PORT monitor --session ID --condition-base64 B64 --timeout-ms N --max-rx-bytes N
dutchmate monitor --help
```

Four required inputs, no defaults/follow/text/regex/stdin/file/output/run/path/database/token/profile options. Global numeric loopback/port and repeat grammar stay007. Static root/command help performs no platform/account/credential/network I/O. Validate lexical integers/session/canonical binary input before credentials; fixed invalid_arguments2. One request, no status/attach/read loop/retry/replay/poll/automatic evidence retrieval and no Core imports.

Existing credential once, HTTP/1/numeric Host/Bearer/no proxy-env/redirect/fallback,5s phase/10s absolute budget, receipts/SIGINT/closed pipes remain007. Local timeout may lose remote result; no retry. Closed fields/types/enums/base64/nullability are checked, without reconstructing Core values or recomputing clock/match/journal/retention policy.

Re-emit canonical compact JSON+LF, exit0 for **all outcomes and both durability states** (valid delivery only). Recognized new/common/journal error fixed stderr/exit4; invalid_response5, input2, output/unexpected1, interrupt130 and unusable-stderr behavior stay007. Original commands are not globally loosened.

## 8. Acceptance and exclusions

RED/GREEN model/codec/matcher/journal/coordinator/runtime/service/CLI tests; injected clock/append gates; real temporary v1/v2 active/terminal read-only transactions; identical backend-shaped fixtures; guarded outside-cwd non-editable wheel/sdist flows. All20 journal mappings,8-read/8-mutation/1-Monitor independence, cleanup latch, timing/pattern/counter/JSON/cursor boundaries, whole413 after settled operation, cancellation/shutdown. Full uv/import/diff/installability gate before software completion.

No physical device opens in default tests; self-created virtual ports allowed. Native Linux/Windows, active-DUT, physical/electrical and Enhanced hardware acceptance remain separate/unexecuted here. Follow/streaming, TX/Interact/console, Control, handoff/reconnect, unrelated Phase1, multiple/text/regex conditions, annotations/discovery/history/restart/service management/Enhanced production/MCP/AI are deferred.
