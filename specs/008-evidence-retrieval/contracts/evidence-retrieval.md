# Contract: Bounded Evidence Retrieval

Core and completed003/005–007 govern. This additive008 contract defines read access
and delivery, not new acquisition, policy, schema or hardware behavior. Existing
006 endpoints and007 commands retain their request/output/error meanings.

## 1. Current association and application boundary

Reuse003 SessionId/EvidenceReference/EvidenceRangeReference/EvidenceRetrievalRequest/
EvidenceCursor/EvidencePage unchanged. Add pure application values/ports in
core/src/dutchmate_core/evidence_access.py:

- EvidenceReadPort: session_id, policy, async resolve_record(reference) and retrieve(request).
  The live port has no client-accessible append/close/open method.
- OwnedEvidenceReadPort: the same read surface plus async close(), used only for
  a per-request terminal reader, never the capture recorder.
- PreparedEvidenceAccess: immutable session_id/policy, optional live read port and
  optional opaque async terminal opener returning OwnedEvidenceReadPort; at least
  one usable capability when supplied. The terminal opener
  captures only immutable private target facts, never a live recorder/connection/FD.
- RunEvidencePage: immutable run_id/session_id/page, returned by application reads.
- EvidenceReadRejected: ordinary sealed fixed-kind exception; kinds
  no_associated_session, session_not_associated, read_unavailable, source_changed,
  read_capacity. No paths, raw exceptions or database objects are delivery data.
- EvidenceSourceOpenFailure: ordinary sealed normalized partial-open failure with
  primary JournalFailure-or-EvidenceReadRejected and reader_close_confirmed:boolean;
  no resource handle. It preserves primary classification while reporting cleanup
  certainty internally, never as an extra wire field.

PreparedObservationRun gains optional evidence_access=None; PreparationFailure gains
optional terminal_evidence_access=None. Existing005 constructor/attach-only callers
remain valid. Present access must match the transferred recorder's SessionId/policy
and provide the declared callables. Missing access never creates a new attach
rejection; read attempts fail explicitly. JournalFailure becomes ordinary/sealed
with read-only operation/kind/detail and writable standard exception metadata;
constructor/validation/categories/message behavior remain003-compatible.

ObservationRuntime adds async read_record(EvidenceReference)->RunEvidencePage and
read_page(EvidenceRetrievalRequest)->RunEvidencePage on its established owner loop.
Wrong loop/thread remains500 runtime/wrong_execution_context; wrong application
argument type remains422 runtime/invalid_request. No framework, filesystem, SQLite
or physical backend type imports enter shared application code.

One internal association stores run_id, known session_id/policy and optional read
access/mode. It is created/cleared atomically with a newly admitted attach, published
when preparation transfers a known session, and retained after terminal settlement.
Rejected Profile/admission attempts preserve the preceding association. A successful
new attach admission removes public selection of the old run immediately, even if
its new session has not yet been allocated. Restart starts with no association.
No catalogue, historical paths, automatic discovery or client database selector.

Core read admission is the linearization point: guard owner context, validate the
supplied session against the one association, check readiness/capacity, capture its
run/source and increment a read lease before the first await. A service-registered
read job not yet inside Core is not bound; it may reject after another attach wins.
Already bound old reads may finish after replacement from their captured source,
but future old-session queries cannot select that source. At most8 Core leases
(including bound terminal reads) and one current public association; no queue/cache.
No association/known session =>no_associated_session. Known different session =>
session_not_associated before read source work. Matching known session without
usable source or during close sealing/unconfirmed close =>read_unavailable.
Runtime creates and strongly retains one private owned read task per bound lease,
then shields/joins it even if the calling waiter is cancelled. Cancellation before
Core admission submits no read; after admission it affects only the waiter. No
public task handles; settled results/errors are consumed and resources released.

## 2. Active, close and terminal read model

Attaching after journal transfer, active, and acquisition-draining states permit
live reads through the same journal instance/gate/worker that appends evidence.
003 serializes each query with append/retention and close. There is no second active
SQLite connection and no second UART reader. Reads can observe an empty journal
before the first committed segment; never invent connection/segment identities.

Runtime teardown order stays: join acquisition/consumer/backend-close work; seal
new live read admission; join all already bound live reads; close capture recorder;
publish terminal summary and terminal/unavailable read mode. Joins happen without
holding the short lifecycle lock. Requests during sealing/close reject immediately,
not wait for or reopen a possibly live recorder. Client loss cannot bypass the join.

Terminal reads require owner_settled AND recorder_close_confirmed. Physical release
uncertainty alone does not forbid evidence access or become a successful-release
claim. Unconfirmed recorder closure forbids terminal reopening. Release all live
port/recorder references from association at terminal publication; keep only immutable
run/session/policy and opaque terminal target/opener. Never keep capture recorder open.

The Basic/SQLite composition supplies an opaque target after successful journal
creation: captured resolved destination, native device/inode identity, expected
SessionId and exact SessionPolicy. Paths never cross into the HTTP request or shared
application policy. A known session after backend construction/preparation failure
gets an optional terminal-only target in PreparationFailure after cleanup. If create
never returned a session/target, do not inspect a partial artifact to discover one.
Failure to capture only terminal identity must not fail otherwise valid capture:
retain live-only access, with explicit terminal unavailability and no path fallback.

One terminal query opens a fresh private worker/connection with SQLite URI
mode=ro/cache=private and PRAGMA query_only=ON, verified by reading it back. Use
explicit read transaction over v1 validation/reference state/row selection, then
rollback/end and close the reader/worker in finally before returning to delivery.
Reuse existing pure v1 schema/application/record/provenance/retention/policy validators
and retrieval workers; do not use SqliteEvidenceJournal.open(), mode=rw/rwc,
_force_rollback_recovery, writable proof, journal_mode/max_page_count writes,
immutable=1, nolock or a persistent reader pool. No create/repair/chmod/delete/recovery.
A hot/corrupt/incompatible journal that cannot be read as-is fails normalized.

Check captured native identity before/after opening and expected session/policy during
read-only validation. Missing destination =>journal/journal_missing; changed identity
or captured policy =>evidence/source_changed; actual stored session mismatch =>
journal/session_mismatch. Native checks are conservative and do not promise protection
against same-UID adversarial rename/restore, live copying or media/power-loss behavior.
Terminal failed runs with a known target and confirmed recorder closure are eligible;
known session without source remains explicitly unavailable. Retrieval never changes
RuntimeStatus/attach_admissible, cleanup facts, evidence or physical ownership.

Opening/reading/closing submitted worker work is joined cancellation-resistently.
Primary read/open failure wins over a secondary reader-close failure; if only close
fails, discard the page and report that normalized failure. No successful cleanup
attestation/retry, raw detail or unbounded cleanup list. Service must retain the read
job until resources settle; externally hung I/O keeps shutdown pending, never forces
abandonment or a falsely clean marker. No new Core lifecycle timeout.
Any terminal-reader close failure or partial-open cleanup uncertainty latches the
owner-loop runtime.evidence_read_cleanup_confirmed flag false and seals all further
read admission for this incarnation before releasing the failed lease/service slot.
Unexpected terminal-opener faults with unknown resource cleanup latch false too.
At most8 already bound readers may be uncertain;
there is no retry/unbounded resource leak loop. It does not alter RuntimeStatus,
attach_admissible or capture cleanup facts. Service final cleanup confirmation also
requires this flag true after read/mutation joins and existing detach; otherwise use
existing teardown_incomplete/dirty marker, never falsely publish clean. The opener
must normalize partial failure as EvidenceSourceOpenFailure with actual close certainty.

## 3. Reference, range, snapshot and retention semantics

Exactly003 contract §7 and code govern, including sequence MAX=9223372036854775807
for stable-reference not_found (never_existed_range may then be null to avoid overflow).
First page captures snapshot_end_exclusive; continuation keeps original session,
range, snapshot end and next position. Later append is outside that traversal.
Retention crossing next position reports expired interval/marker and resumes at low
water. No timestamp/offset pagination, record splitting, retention pin or tail cursor.

Keep003 outcome/truncation independent: a budget-limited retained page can be
complete AND truncated. A first record exceeding caller charged-byte budget yields
zero records, required charge, truncated=true and unchanged next continuation position.
Empty explicit range below low water can be complete; beyond next sequence is not_found.
Mixed expired/never-existent suffix preserves partial and all reported intervals.
A reader/projection never recomputes these facts from HTTP status or record count.

## 4. Exact authenticated HTTP requests

Both routes pass006's same peer/Host/browser/Bearer/query/Upgrade/literal route/method
gate. They use POST with no URL query. After the security gate: check service ready,
validate strict body, check read registry capacity, register one owned read task;
only that job calls the owning-loop application read. Auth/browser failures never
read body, inspect association or open a journal. Stopping rejects new reads503.
No CORS/docs/slash alias/default path/launcher/authentication or bootstrap changes.

| Route | Exact JSON body |
|---|---|
| POST /v1/evidence/record | session_id:string, sequence:integer |
| POST /v1/evidence/page | session_id:string, start_inclusive:integer-or-null, end_exclusive:integer-or-null, max_records:integer, max_charged_bytes:integer, cursor:string-or-null |

Every listed field required; objects closed. GET/HEAD/OPTIONS are not additional
read routes. Content-Type is exactly006 application/json with optional sole UTF-8
charset. Strict UTF-8, duplicates/nonfinite/coercions rejected. Maximum actual body
16384 bytes, detect at16385, independent of declared Content-Length.

session_id: exact string,1..256 UTF-8 bytes, no NUL; never strip/normalize/interpret
as a path. sequence/start/end: exact int (not bool),0..9223372036854775807. start/end
both null select whole-session traversal; otherwise both present and start<=end
form half-open range. max_records:1..4096; max_charged_bytes:1..1048576. cursor:null
or1..1024 ASCII bytes, canonical token below. These extra wire caps do not change
003 SessionPolicy. Values above wire limits reject422 request/invalid_request;
within wire but above captured policy reject422 journal/invalid_input.

Cursor token: unpadded RFC4648 base64url of compact UTF-8 JSON with ordered exact keys:
version (integer1), session_id, range_start_inclusive, range_end_exclusive,
snapshot_end_exclusive, next_sequence. Non-ASCII preserved; no whitespace/duplicate
keys/nonfinite values/padding/noncanonical alphabet or re-encoding. Counters use003
persisted domain; nullable range_end_exclusive preserves whole-session selection.
Canonical decode/re-encode must equal the input token; construct003 EvidenceCursor.
No credential, signature, issued-token registry, TTL or proof against authenticated
editing. Structural token validation precedes Core admission;003 remains authority
for cursor/session/original-range/snapshot consistency against journal state. Page
budgets may change on continuation; session/original range/snapshot may not.

## 5. Exact evidence JSON response

HTTP200 has exactly run_id:string, session_id:string and page:object in that order. run_id is the
association captured at Core admission; it is not current state at response output
nor proof of causation. page has exactly these keys, in this canonical encoding order:
records, snapshot_end_exclusive, expired_range, retention_marker, never_existed_range,
outcome, truncated, continuation, charged_bytes, next_record_required_bytes.

Project003 page fields directly. Records are ordered arrays; no sorting/merging/
text conversion. Range objects have start_inclusive/end_exclusive. Optional facts
are null, not omitted. outcome is complete/partial/expired/not_found; continuation
is encoded token or null. Counters keep existing integer values; truncated is bool.
next_record_required_bytes is a positive integer or null. These fields never include
paths, SQL, live handles, tasks, Profile source paths or exception/detail messages.

Each record is a closed discriminated object; canonical key order is as listed:

| kind | Remaining keys after kind,sequence |
|---|---|
| segment_started | provenance |
| rx_bytes | connection_id, segment_id, observed_at, payload_base64 |
| observer_loss | connection_id, segment_id, observer_id, scope, cause, lost_bytes, observed_at |
| segment_ended | connection_id, segment_id, reason |

All IDs/observer/scope names in delivered records are nonempty exact strings.
Record sequence is an exact integer0..MAX-1; range/snapshot/next/charge/count fields
retain003 persisted nonnegative counter bounds, with next_record_required_bytes
positive-or-null. Optional ranges/marker/continuation are null as003 reports them.
observed_at has nonempty domain_id:string/value:nonnegative exact integer using003
persisted timestamp validation, never bool. RX payload_base64 uses standard
RFC4648 alphabet, required canonical padding, no whitespace/URL-safe alphabet/nonzero
pad bits; empty bytes =>empty string. Decode and re-encode exactly; no UTF-8/text
interpretation of payload. loss cause is overflow or other_observed_loss;
lost_bytes remains positive exact integer-or-null. Segment reason is explicit_stop/disconnected/
timestamp_origin_reset/recording_failure/transport_failure. Use exact current model
enum values; no hardware semantics added.

provenance exactly reuses006 public ProvenanceView: connection_id, segment_id,
capabilities (sorted reported values), backend_observation_timestamp_domain,
loss_observability, connection_provenance. Timestamp descriptor fields are
domain_id/observer/meaning/unit/origin_id; normalized loss variants are
upstream_loss_not_observable or observer_reports_uart_loss with observer_id/scope.
Opaque envelope has envelope_version,backend_kind,backend_schema_version and ordered
fields ARRAY of {name,value}; scalar value null/bool/int/string, never decode backend
identity. Do not expose003 private codec names/field objects or import those codecs
into service/CLI. Missing segment-start after retention never causes invented provenance.

retention_marker has expired_range, first_discarded_timestamp, last_discarded_timestamp,
discarded_record_count, discarded_rx_payload_byte_count, discarded_charged_bytes.
Each timestamp endpoint is null or {timestamp:{domain_id,value},domain:{domain_id,
observer,meaning,unit,origin_id}}. Preserve first/last distinct domains/origins; no
subtraction, clock equivalence or losslessness claim. No new evidence kind/schema row.

## 6. Independent delivery cap and overflow

Service compact UTF-8 JSON <=1048576 bytes; CLI compact UTF-8 JSON <=1048576 bytes
plus one LF. Raw HTTP client retains <=1048577 bytes for detection. Use exact compact
escaping, non-ASCII preservation and canonical field/key order in server and CLI so
re-encoding a fitting response stays bounded. Accept only raw absent/single identity
Content-Encoding and006 JSON media rules; no decompression/unbounded response buffering.
Do not claim an exact socket/SQLite buffering or003 record-materialization ceiling.
Canonical serialization uses standard-library JSON ensure_ascii=False,
allow_nan=False and separators=(",",":"): quoted/backslash/control characters
receive that encoder's escapes, all other valid Unicode is emitted as UTF-8;
no slash escaping, sorting of object keys or formatting whitespace. Nested reused006
objects follow their declared field order, ranges start_inclusive then end_exclusive,
timestamp endpoints timestamp then domain, and opaque field entries name then value.

Server encoding accumulates at most bound+1. Preflight base64 length4*ceil(n/3) before
oversized allocation or encode aligned bounded chunks; encoder stops on overflowing
metadata too. If the whole canonical envelope does not fit, return413
{"error":{"source":"evidence","code":"delivery_too_large"}} with no partial
report or altered003 page/cursor. This also covers an irreducibly oversized single
record or mandatory marker/provenance. Do not tighten schema/Profile/SessionPolicy,
split payload, drop metadata, trim pages, provide substitute continuation or refetch.
A caller may explicitly request lower page limits. With an existing cursor that
keeps the same snapshot; retrying without it starts a new003 snapshot. A tiny byte-
budget003 report remains200 even if required record charge exceeds delivery cap.
CLI protocol/base64/shape/encoded overflow is local invalid_response5, never echoed.

## 7. Exact errors, service lifetime and privacy

ErrorEnvelope remains exactly {error:{source,code}}; Cache-Control:no-store on every
response, same006 gate/auth headers. Existing006 HTTP/source/code pairs remain for
common request/service/runtime failures. Additional pairs:

| HTTP | source/code | Meaning |
|---|---|---|
|404|evidence/no_associated_session|No known current/last session; no browsing|
|409|evidence/session_not_associated|Explicit session differs from retained association|
|503|evidence/read_unavailable|No source, preparation pending, close sealing or unconfirmed recorder close|
|409|evidence/source_changed|Captured file identity or exact policy changed|
|503|evidence/read_capacity|Core8-lease capacity exhausted|
|413|evidence/delivery_too_large|Whole canonical report cannot fit|
|422|journal/invalid_input|003 request/policy/cursor consistency rejection|
|409|journal/session_mismatch|003 cursor or stored session mismatch|
|404|journal/journal_missing|Captured terminal destination unavailable|
|503|journal/busy|Normalized SQLite/resource busy|
|409|journal/closed|Unexpected closed read resource|
|500|journal/<remaining declared003 JournalFailureKind>|Normalized read/open/close failure|

The500 journal set is exactly journal_exists,incompatible_application,
incompatible_schema_version,incompatible_record_version,
incompatible_provenance_envelope_version,corrupt_journal,invariant_violation,capacity,
capacity/database_over_ceiling,capacity/physical_ceiling_unavailable,
capacity/sequence_exhausted,capacity/counter_exhausted,read_only,permission_denied,
io_failure. No raw detail/operation/path/cause/traceback. Unexpected application/
projection/wrapper failures =>500 service/internal_failure. Error mapping does not
rewrite runtime cleanup facts or attest rollback.403/401/gate validation precede
association/read work; wrong owning context preserves500 runtime/wrong_execution_context.

Exactly8 strongly owned registered read jobs, separate from006's8 mutation slots;
registry overflow uses503 service/operation_capacity. No hidden queue or IDs. Tasks
registered before yielding, awaiters shielded, results/failures consumed and discarded
only after resource settlement. Client loss leaves the read job to finish/close; it
never cancels acquisition/mutations/submitted worker work, signals service or retries.

Shutdown latches stopping and seals both registrations immediately; join all read
and mutation jobs (including queued-before-Core ones), then existing final runtime
detach/ownership cleanup/token/listener/marker/lock sequence. Runtime detach itself
seals/joins live leases before recorder close. Require the latched read-cleanup fact
in final service clean-marker eligibility. Never hold lifecycle lock while waiting
for leases, force-close a submitted worker or weaken006's positive cleanup marker.

## 8. Exact thin CLI

```text
dutchmate [--host HOST] --port PORT evidence record --session ID --sequence N
dutchmate [--host HOST] --port PORT evidence page --session ID --max-records N --max-charged-bytes N [--start N --end N] [--cursor TOKEN]
dutchmate evidence --help
dutchmate evidence record --help
dutchmate evidence page --help
```

One new root evidence subgroup with record/page; existing attach/status/detach remain.
Global numeric host/required port and repeated valued-option behavior stay007. Every
shown --session/sequence/page-budget option is required; no defaults. --start/--end
both absent selects whole session, both supplied selects half-open range. Map absent
range/cursor to explicit JSON nulls. No run-id/path/--journal/--database/URL/token-file/
JSON-input/output-format/raw-file/shell/timeout options. No automatic status or pages.

Root/group callbacks only store/show static help; no platform/account/credential/
network/resource I/O. Supported root/group/no-command/help invocations exit0 with
static stdout and empty stderr. Invalid grammar/lexical ID/counter/range/cursor cap/
alphabet fails fixed invalid_arguments2 before credential/network; input cursor is
opaque beyond bounded ASCII/base64url lexical check, server owns canonical semantics.
Read credential once after valid arguments, one fresh HTTP exchange, same007 absolute
10s/5s phase settings, HTTP/1/numeric Host/Bearer/no env/proxy/retry/redirect/fallback.

Validate closed evidence wire keys/types/enums/canonical base64 and bounded canonical
cursor shape; preserve all facts/array order, never construct Core values or
recompute003 outcome/cursor/domain/retention predicates. Re-emit canonical compact
JSON plus LF. Valid200 stdout/exit0 includes all four outcomes; recognized008 or
common006 errors stderr/exit4. Original007 commands keep their original validators
and accepted error pairs. Local errors/exits/receipt phase exactly007, including130
interrupt,5 protocol/timeout,1 output/unexpected and unusable-stderr exit-only behavior.
Disable SDK/framework input-bearing diagnostics; no token/body/SQL/path echo.

## 9. Compatibility, tests and exclusions

No schema-v1/Profile-v1/Backend contract change; no writable historical reopen,
client storage import or Basic-specific read branch. Existing001–007 suites and
strengthened import contracts remain intact. Public additions are explicit008
contracts, not a rewrite of old command meanings. Optional new preparation fields
preserve old attach-only callers and report unavailable read access rather than
forcing fixture emulation. Identical read assertions use Basic/Enhanced-shaped
fixtures with actual temporary SQLite; actual006 authentication/guards stay active.

Deferred: streaming/follow, text/line decoding, regex/patterns, Monitor, annotations,
catalogue/discovery, restart/arbitrary historical browsing, TX/Interact/console,
Control, reconnect/handoff, service management, Enhanced production, MCP/AI and
physical-hardware acceptance. No planning action implements these or touches a DUT.
