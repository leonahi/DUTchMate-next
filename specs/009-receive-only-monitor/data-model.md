# Data Model: Receive-Only Monitor

[Contract](contracts/monitor.md) owns concrete input/wire/persistence rules; Core remains normative. This model is implemented in the existing Core, service and CLI packages. T001–T037 complete (37/37); all 37 implementation tasks are complete. [Current status](../../docs/development_status.md) and [history](../../docs/development_history.md) record implementation and software evidence; Feature 009 is software-complete; Phase 1 and physical acceptance remain incomplete.

## Values and dependency direction

Existing `model.py` remains the inward normalized evidence layer. It contains MonitorOutcome, byte-position/match/host-clock facts and immutable OperationStartedEvidence/OperationEndedEvidence, so evidence/codec/application can depend inward without a model→monitor/runtime cycle. `evidence.py` adds pending marker drafts and union/sequence assignment support; old four drafts/values and sealed JournalFailure facts/transport remain compatible.

`monitor.py` holds immutable MonitorRequest/MonitorReport, sealed MonitorRejected, meaningful MonitorClock/PreparedMonitorAccess boundaries and minimal concrete recording coordinator/matcher. It depends only on inward normalized/application contracts. Runtime imports Monitor; Monitor never imports runtime, adapters, FastAPI or Typer. Report run_id is the captured nonempty opaque run identity string, not a runtime-class back import. Host-clock adapter lives in infrastructure. Pure v2 codec helpers stay beside existing v1 codec in `adapters/sqlite_evidence.py`, avoiding a cyclic helper module and unnecessary extraction of old code.

## MonitorRequest

session_id uses existing SessionId; condition exact bytes1..256; timeout_ms exact int1..4000; max_rx_bytes exact int1..1048576. No mutable/decoded representation. Transport session cap is independent of legacy opaque SessionId. Pattern memory is bounded by256; processing count by1048576. No default values or client cursor.

## PreparedMonitorAccess and operation ownership

Optional immutable capability matches transferred recorder session/policy and references the same coordinator/clock and pure synchronous charge_markers(start_draft,maximum_end_drafts) callback returning exact positive signed-64-bit charges. This persistence boundary keeps private codecs outside Core and avoids a second charge formula. Absence preserves legacy attach-only construction; wrong present capability is an internal normalized preparation-contract issue, not new backend emulation. No terminal Monitor access, filesystem target or second connection in the application capability.

One owner state: ADMITTED → START_SUBMITTED → OBSERVING → DECIDED → END_SUBMITTED → SETTLED. Admission/gate revalidation may reject before submission; failed/ambiguous start settles as normalized error without positive ref. Stop during submitted start latches intent, waits positive acknowledgement and then decides immediately. Installed matcher, host deadline and timer are published atomically at start acknowledgement. Client cancellation removes no owner state. Busy lasts to SETTLED; settled reports are discarded after delivery/consumption.

Private state contains operation UUID, captured run/session/provenance, requested bounds, start reference, host origin/timing, last included sequence, examined count, observed-loss count, bounded prefix/positions, optional frozen decision and one owned timer/task. No RX history, full evidence window, unbounded listeners or jobs. Counter domains remain003 signed-64-bit; clock addition/marker charge overflow rejects or fails honestly, never wraps.

## Marker values and sequence references

OperationStartedEvidence: sequence, operation_id, operation_kind=monitor, provenance, timeout_ms, max_rx_bytes, clock_origin_id, condition bytes. Pending form lacks only assigned sequence. Provenance is actual committed SegmentProvenance; no invented ready segment.

OperationEndedEvidence: sequence, operation_id, operation_kind=monitor, start_sequence, window, outcome, examined_rx_bytes, observer_loss_records, match-or-null, clock. Pending form lacks assigned sequence. Window uses existing SequenceRange and start=start_sequence+1. Match has start(record sequence, byte_offset) and end(record sequence, byte_offset_exclusive). Clock has origin_id/start/deadline/decision exact host ns. Enums, structural nullability/order/counter/type bounds validated near the values/codec; byte offsets refer to unchanged RX, not reconstructed text.

All IDs new to this feature are canonical UUID strings except existing opaque run/session/connection/segment identities. Outcome matched requires a nonnull match, all others null; timeout decision>=deadline, ordinary others<deadline. Examined count0..1048576; matched/byte_limit require a positive examined count; observed-loss count0..MAX. Eligible atomic chunk match/limit stores publication sample. Match endpoints ordered and within frozen record window; nonempty match, offsets nonnegative/end positive. When paired start/end survive retention, validate request bound/timing/match length compatibility; do not require evicted pairs or duplicate end writes after ambiguity.

## MonitorReport and independent durability

Report fields/encoding order exactly contract §5. Preserve run/session/operation/provenance/outcome/start ref/frozen window/counts/match/clock. `complete`: positive end ref and end_failure null. `end_unconfirmed`: null end ref and normalized journal-kind or service/internal_failure. No raw exception object/detail enters report. Positive references are append acknowledgement facts, not assertions of current retention or OS/physical cleanup. An unexpected fault that prevents valid decision facts yields a normalized error, not invented report.

Observer loss count records reported losses seen inside the window, not byte loss quantity or proof of upstream losslessness. Provenance carries actual backend observation timestamp domain/loss scope/serial configuration; host origin is separate. Retention can expire all references and provenance markers; returned snapshot remains factual but cannot resurrect bytes.

## Schema-v2 compatibility and read modes

V2 uses same APPLICATION_ID=0x4455544D and same three table responsibilities (`session_metadata`, `evidence_records`, `retention_marker`). PRAGMA user_version=2 and session_metadata.schema_version=2; no extra operation table. Old kinds remain record_version1; operation kinds use2; generic provenance envelope stays1. Exact supported schema definitions/columns/indexes/constraints are strict v2 validators; legacy v1 definitions/default APIs/codec are unchanged. V2 rows use existing sequence allocation/transaction/charge/retention/capacity rules.

Operation charge16+kindUTF8+metadataUTF8+BLOB; condition contributes BLOB charge but rx_payload_bytes=0. End BLOB exactly empty bytes, not SQL NULL. Neither marker has cached backend timestamp endpoints. Metadata field sets match contract §4 and reuse existing private provenance codec/canonical recursively sorted JSON; delivery key order is separate. Preflight takes actual start plus exactly nine legal standalone maximum-shaped end drafts and their maximum canonical charge: matched/nonmatched nullability and clock inequalities remain legal, examined<=1048576, all other counters maximum legal width. It is conservative over feature-wide normalized values, without claiming reachability for each request. Both charges must fit all three policy ceilings; no reservation. Counter/physical failure can still prevent later end.

Live source: same capture journal instance/gate/worker, now explicitly created v2 by service composition. Terminal target adds immutable expected format default1, explicit2 for new composition; actual/native identity/session/policy/format must match within verified read-only transaction. No writable fallback/recovery/migration/pool/retained capture writer. Current/last association remains008's incarnation-local selection; terminal retrieval eligibility/cleanup latch unchanged. Evidence page values/cursor/outcomes/retention fields stay003; wire union alone adds two variants.

## Seals and teardown

Run seal prevents new Monitor and latches detach intent; service-wide incarnation seal prevents any later admission and latches service_stopping. Decision freezes watermark before later RX/end append. Deadline equality precedes stop/failure decisions; earlier decision is immutable.

Join acquisition and Monitor marker owners before live reads seal/join and writer close. Service joins all registered read/mutation/Monitor owners before final detach. None of these transitions changes RuntimeStatus, attach_admissible, capture cleanup or the permanently false008 evidence_read_cleanup_confirmed latch. Uncertain/blocked cleanup never becomes clean by elapsed time.
