# Data Model: Bounded Evidence Retrieval

The application read boundary, active/terminal runtime association and cleanup,
read-only terminal adapter, authenticated service projections and thin CLI delivery
are implemented. Existing 003 values/codecs/schema-v1, Profile-v1 and 005–007
capture/lifecycle/security semantics remain unchanged. US1–US4 have passing software
evidence; T035 and the separately authorized final pre-commit review passed.
Implementation is recorded by Git revision `:/^Implement evidence retrieval`.
Native Linux/Windows and active-DUT/physical acceptance remain unexecuted.

[Contract](contracts/evidence-retrieval.md) owns semantics. Implementation progress
and actual counts/acceptance limits belong in [tasks](tasks.md),
[current status](../../docs/development_status.md) and
[history](../../docs/development_history.md), rather than a per-task model chronology.

## Existing values reused

SessionId/EvidenceReference/EvidenceRangeReference/EvidenceRetrievalRequest/
EvidenceCursor/EvidencePage/SessionPolicy and all four EvidenceRecord variants are
reused directly. Stable-reference sequence accepts0..9223372036854775807, including
MAX not_found. Stored record sequences remain0..MAX-1; next/snapshot/range counters
can equal MAX. No new persisted record kind/table/version or Profile key.

## Application read ports and values

| Value | Fields and constraints |
|---|---|
| EvidenceReadPort | session_id:SessionId; policy:SessionPolicy; async resolve_record(reference), retrieve(request). Read-only surface; no append/open/close exposed for live capture. |
| OwnedEvidenceReadPort | EvidenceReadPort + async close(); ownership only for one terminal read. |
| PreparedEvidenceAccess | Immutable session_id/policy; live_reader:EvidenceReadPort-or-null; terminal_opener:async callable-or-null. At least one usable read capability when supplied. No filesystem/SQLite/framework fields. |
| RunEvidencePage | Immutable run_id:RunId, session_id:SessionId, page:EvidencePage from the pinned association. No reconstructed facts. |
| EvidenceReadRejected | Ordinary exception; immutable kind in no_associated_session/session_not_associated/read_unavailable/source_changed/read_capacity; mutable standard exception metadata. |
| EvidenceSourceOpenFailure | Ordinary normalized exception; immutable primary:JournalFailure-or-EvidenceReadRejected and reader_close_confirmed:exact bool. No live handle/traceback retained after settlement. |
| JournalFailure | Existing operation/kind/detail constructor, validations and category/message semantics; fact fields remain read-only, standard exception traceback/cause/context/notes writable. |

EvidenceReadRejectedKind is a closed Literal of the five declared string kinds.
Exception facts have Final typing and sealed runtime assignment/deletion; ordinary
exception metadata remains writable. Frozen value dataclasses remain immutable.

PreparedObservationRun.evidence_access defaults null; old attach-only callers stay
valid. Access session/policy must equal recorder values. PreparationFailure gets
optional terminal_evidence_access after cleanup for a known returned session;
its existing facts/defaults/exception transport remain compatible. Optional means
unavailable when absent, never fake capability emulation. Final production SQLite
composition provides live reader and, when native target capture succeeds, terminal
opener. Failure to capture only terminal identity must not fail otherwise valid
capture; terminal capability then stays absent/unavailable, with no path fallback.

T018 implements optional PreparationFailure terminal handoff, terminal-opener
execution and the read-cleanup latch/service conjunction. Runtime retains known
run/session/policy and opaque opener metadata after draining live reads, drops its
live-reader reference before recorder close and does not reopen terminal capture.
Production005 composition supplies the same created capture journal as the
narrowed live reader, with exact session/policy and optional captured terminal
opener. Native target capture failure retains live-only access. It creates no
second active journal/connection/reader and changes no recorder ownership or cleanup.

## Internal association and bounded read owners

One current public slot: current/last run_id, nullable known session/policy, optional
access, mode pending/live/sealing/terminal/unavailable. These modes are private, not
new RuntimeState or HTTP status fields. New admitted attach replaces it atomically;
rejected attach leaves it. Restart has none. Query selection uses exact SessionId.

| Transition | Meaning |
|---|---|
| no run -> admitted attach/pending | Old slot no longer selectable; session may be unknown. |
| known successful preparation -> live | Same capture journal read gate available during attaching/active/draining. |
| acquisition joined -> sealing | New live reads reject; already pinned reads join before capture recorder close. |
| terminal + owner_settled + recorder_close_confirmed -> terminal | Release live port; retain only immutable opaque terminal opener/identity. |
| no source/unconfirmed recorder close -> unavailable | No speculative reopen or cleanup inference. |
| next attach | Replace public slot; already pinned old reads may finish from captured source. |

At most8 runtime-owned pinned read tasks and8 service read jobs, separate from006's
8 mutation jobs. Each read task captures run/session/source/mode before first await,
uses either live read or per-request terminal opener, and closes/join resources
before releasing its lease. No public jobs, queues, cursor-held resource or history.
Waiter cancellation never cancels the private read owner/submitted worker.

runtime.evidence_read_cleanup_confirmed starts true, is false permanently after
unconfirmed terminal/partial-open cleanup, and seals further read admission before
the failed lease/registry slot is released. Existing pinned tasks settle; max8 uncertain
read owners. It does not alter RuntimeStatus or attach eligibility. Service clean
marker requires existing capture/owner facts AND this read cleanup confirmation.
False =>006 teardown_incomplete/dirty marker, no auto-retry/reset. Unexpected terminal
opener faults with unknown resource cleanup also latch false conservatively.

## Concrete terminal target (adapter-private)

Resolved destination, native device/inode identity, expected SessionId and exact
SessionPolicy are captured from successful composition-owned creation. No target
comes from retrieval input; target never retains a writer/connection/FD. A fresh
mode=ro/cache=private/query_only reader owns a dedicated worker for one request,
read transaction, full pure v1 validation and existing bounded selection. Identity
before/after open + session/policy validation; no recovery/writable fallback. No new
same-UID malicious race or live-file-copy guarantee. Read/close failure precedence
and cleanup latch are in contract §§2/7.

T016 implements this adapter with unchanged003 validators/selection workers and
no writable reopen/recovery, schema/codecs change or persistent reader pool. The
capture/open seam remains adapter-private; T018 production composition captures
the optional target after successful creation. A failed close stays failed on subsequent calls
without retry; cancellation joins close and cannot hide uncertain cleanup.

## HTTP request values

Both body objects are closed; all listed keys required; strict JSON primitive types,
no duplicate keys/nonfinite numbers/coercion. Request body16384 actual bytes maximum,
16385 detection. JSON/media/privacy/security exactly006.

| Field | Verbatim wire constraint |
|---|---|
| session_id | "1..256 UTF-8 bytes, no NUL; exact string, no normalization" |
| sequence | "exact integer0..9223372036854775807, not bool" |
| start_inclusive/end_exclusive | "both null or both exact integers0..9223372036854775807 with start<=end" |
| max_records | "exact integer1..4096, not bool; also no greater than SessionPolicy ceiling" |
| max_charged_bytes | "exact integer1..1048576, not bool; also no greater than SessionPolicy ceiling" |
| cursor | "null or1..1024 ASCII bytes, canonical unpadded base64url token" |

record request: session_id/sequence. page request: session_id/start_inclusive/
end_exclusive/max_records/max_charged_bytes/cursor. No run/path/database input.
Wire ceiling rejection is422 request/invalid_request; existing policy rejection is
422 journal/invalid_input. This is not a policy/schema/default revision.

## Fixed-snapshot cursor

Canonical ordered token JSON keys: version:integer1, session_id:string,
range_start_inclusive:integer, range_end_exclusive:integer-or-null,
snapshot_end_exclusive:integer, next_sequence:integer. Compact UTF-8/non-ASCII
preserved, then unpadded standard base64url. Exact canonical round trip, no padding/
whitespace/unknown fields/duplicate keys. Counters are003 persisted values;003
constructor/reader owns their range/session/snapshot predicates. Later append never
extends a continuation; later eviction is explicit. Token is a value, not an
authentication credential, signature, issuance registry or retained connection.
CLI input cursor validation is lexical only; response token gets closed wire
validation, never reconstructed Core policy. Page budgets may change between calls.

## Delivered evidence values

Closed EvidenceEnvelope: run_id/session_id/page. Exact page keys/order from contract
§5; all003 fields retained: records, snapshot_end_exclusive, expired_range,
retention_marker, never_existed_range, outcome, truncated, continuation, charged_bytes,
next_record_required_bytes. Outcomes "complete|partial|expired|not_found" are all
HTTP200/report exit0. Truncation is independent; byte shortage is the unchanged003
zero-record page with required charge and same continuation position.

Four closed variants: segment_started/provenance; rx_bytes/identities/observed_at/
payload_base64; observer_loss/identities/observer/scope/cause/lost_bytes/observed_at;
segment_ended/identities/reason. All have kind/sequence. Loss causes
"overflow|other_observed_loss"; segment reasons "explicit_stop|disconnected|timestamp_origin_reset|recording_failure|transport_failure".
lost_bytes is "positive exact integer-or-null"; observed timestamp value is
"nonnegative exact integer, never bool" under003 persisted validation. Timestamp
value/domain remain exact. Retention endpoints retain timestamp + full
descriptor separately. Use006 public provenance/loss keys and ordered scalar-fields
array; never expose003 private persistence representation or interpret backend kind.

RX "RFC4648 standard alphabet with canonical padding, no whitespace/nonzero pad bits";
empty bytes encode empty string. No UART decoding, replacement or line normalization.
Closed enum/type/value representation validation in CLI is not recomputation of
outcomes, charge, cursor validity against retained state or cross-domain comparisons.

## Independent delivery budgets

"Service UTF-8 JSON <=1048576 bytes; CLI JSON <=1048576 bytes plus one LF".
"Accumulate at most1048577 raw/encoded bytes for overflow detection".
Wire query limits differ from003 record/page policy; page-native allocations and
single-reference materialization may exceed encoded delivery cap under policy.
No exact socket/SQLite/materialization byte-ceiling claim. Base64 must preflight
encoded length or emit aligned chunks before oversized allocation.

Whole-envelope overflow =>413 evidence/delivery_too_large, no fragments/trimming/
splitting/altered continuation/refetch. Same for irreducible record/marker/provenance.
Lower-budget retry is explicit; continuation retry keeps snapshot, initial retry
captures new snapshot. All exact error pairs/exit/receipt categories are contract §§7–8.

## Compatibility and exclusions

Only normalized read capability/lifetime and additive service/CLI delivery are new.
Keep003 codecs/schema,004 Profile and physical backend contract unchanged.005–007
capture/security/old routes/commands remain authoritative. No deferral is represented
as an implemented value; all requested exclusions are in spec/contract.
