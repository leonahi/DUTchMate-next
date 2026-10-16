# Contract: Bounded Attributed Client Annotations

Core governs. Completed001–009 remain authoritative except the additive format/projection/composition revision below. Core values/codecs, explicit v3 journal/read-only terminal support, gated insertion, runtime admission/rate/ownership, production composition and authenticated service/thin CLI delivery are implemented. All T001–T024 tasks are complete; fresh final software/installed/artifact/privacy/Core/contract review passed without correction. T023 tooling/health limits remain recorded. Feature010 is software-complete; implementation commit is recorded in development_status.md; Phase1 and native/physical acceptance remain incomplete. [Spec](../spec.md) defines scope; [data model](../data-model.md) lists values; [tasks](../tasks.md) defines execution checkpoints.

## 1. Inputs and attribution

`AnnotationRequest(session_id:SessionId, text:str, client_surface:str)` is an immutable inward application value. Text is exactly **1..1024 UTF-8 bytes**, excluding U+0000 and surrogate code points; no coercion, stripping, Unicode normalization or line-ending transformation. Whitespace-only nonempty text and embedded LF/CR/tab are valid. `client_surface` is exactly `cli`, `http` or `core`. The HTTP route permits only `cli`/`http`; the CLI fixes `cli` and exposes no attribution override. Direct application callers may declare `core`.

Every persisted/wire annotation has `assertion_class:"client_assertion"` and `attribution_basis:"client_asserted"`. The surface is a bounded declaration by the caller, not attestation. A caller with the shared credential can submit `cli`; do not infer a verified executable, OS principal, PID, credential identity, verified transport client or truth of the text. Core never executes or verifies asserted actions. No arbitrary author/metadata/attachment/labels/schema/time/path/sequence/operation fields.

Wire session ID retains009: exact nonempty string, **1..256 UTF-8 bytes**, no NUL/normalization/path meaning. Existing Core SessionId semantics remain unchanged. No implicit current-session selection.

## 2. Core admission, limiter and ownership

Add `ObservationRuntime.annotate(AnnotationRequest)->AnnotationReceipt`. Check synchronously before first await, in order:

1. Existing loop/thread and application argument-type guard.
2. Incarnation annotation seal: `annotation_unavailable`.
3. Known association/session: `no_associated_session`, then `session_not_associated`.
4. ACTIVE current generation and per-run annotation seal: `not_active`.
5. Usable explicit annotation access, same recorder/session/policy/coordinator, committed current segment, callable clock interface and canonical/stable origin: `annotation_unavailable`. Admission time is sampled only at step8.
6. Conservative exact-codec charge preflight: `evidence_policy_incompatible`.
7. A generation-owned annotation is pending: `busy`.
8. Sample/validate the admission clock and prune the bounded rate window; exhausted budget: `rate_limited`.
9. Append admission time to the budget, bind the current run/access/request and strongly register one owner before yielding.

No UART-TX/control permission, backend-name test, emulated capability or new physical backend method. An annotation is host/session evidence, not a UART capability. Existing observation preparation still establishes mandatory recording.

The limiter permits **10 admitted attempts in a rolling 1,000,000,000 ns window per runtime incarnation**, shared across surfaces, sessions and attaches. Keep at most ten admission samples. At sample `now`, discard samples `<= now-1,000,000,000`; reject if ten remain. A sample exactly one second old no longer counts. One pending annotation per run, no application queue or sleep. Rate rejection, busy, invalid input, association/state/access/policy rejection consume no admission. Once admitted, an attempt consumes budget even if append fails, later clock sampling fails or delivery disappears; no refund/retry. Concurrent callers cannot race the synchronous sample/register step.

Use the existing runtime-scoped host clock from009 composition, already reused across attaches. Bind the limiter to its first admitted canonical clock-origin UUID; later annotation access with a different origin or a backwards/invalid admission sample rejects `annotation_unavailable` without resetting history. Track the last valid admission-check sample, even across a fully aged-out window. A valid step8 sample updates this last-check value even if rate rejection follows; it does not create a budget entry. Invalid samples change neither last-check value nor budget. Samples are exact integers, not bool, **0..9223372036854775807**. Clock-origin stability is an annotation capability requirement, not a new attach/Monitor rejection. A fresh runtime has a fresh budget/origin association; restart recovery is out of scope.

`PreparedObservationRun` gains optional `annotation_access=None`. `PreparedAnnotationAccess` holds session/policy, the **same MonitorRecordingCoordinator transferred as recorder**, existing host clock (**access.clock is coordinator.clock**) and pure annotation-charge callback. Present malformed/mismatched access follows existing preparation-transfer validation/cleanup conventions; missing access never fails old attach callers. V1/v2-only custom preparations can omit it; no annotation fallback or automatic upgrade. Production v3 preparation supplies evidence, Monitor and annotation capabilities over the same writer/coordinator and clock. No new recorder, port framework, subscription system, reader or sidecar.

Core owner cancellation is shielded and joined as existing owned operations. Cancellation observed before admission submits nothing. After admission, cancelled waiters/disconnected clients do not cancel the owner, its gate wait or submitted append. Consume settled errors; retain no result history. Detach/autonomous termination seal the run; service stop seals the incarnation before taking its finite job snapshot. Already admitted insertion belongs to its captured run and **continues without rechecking ACTIVE/committed-segment state**. It may be committed after a segment-end record, before writer close: it remains session-level client context and claims no continuous DUT observation.

Preserve existing acquisition/Monitor/read teardown joins and add the annotation-owner join before recorder close/terminal publication. Do not hold the short lifecycle lock while joining; never cancel or abandon a submitted journal worker. No new operation is admitted after a seal. Pending work may keep stop pending; size/rate bounds do not bound durable I/O latency. Preserve005 lifecycle/status/attach results,008 permanent read-cleanup uncertainty and009 Monitor settlement. Annotation-only failure does not fabricate or overwrite capture/physical-release facts.

## 3. Receipt time and insertion order

Extend the existing committed recording coordinator with a narrow `append_client_annotation(client_surface, text)` operation. Under its **same append gate**, sample and validate the existing clock, construct the immutable pending annotation, append once through the underlying journal and publish the positively acknowledged record through the existing publication path. No new application dependency from monitor to annotation delivery values is needed: pending/committed records live in evidence/model. The annotation application values may depend on existing monitor capability types; dependencies remain inward.

`received_at_ns` is this Core insertion-boundary host monotonic sample, not HTTP socket/body arrival, prior admission-budget time, client event time, DUT/backend time, wall-clock UTC or commit-completion time. Record the same canonical `clock_origin_id` used by the run's host clock. A request can wait for the existing gate before this receipt boundary. Sequence is allocated by ordinary journal append and is authoritative ordering; timestamps never replace it or compare host and backend domains. No invented cross-domain continuity/backdating. Invalid clock at insertion fails before append; normalized unexpected failure, consumed admission and no fabricated timestamp/reference.

Annotation is a normal non-RX record in Monitor windows. It cannot feed/reset the literal matcher, consume examined RX bytes, add observer loss or become a backend timestamp endpoint. A match can span RX chunks separated by annotation. After positive append acknowledgement, Monitor publication must use a **fresh post-ACK clock sample**, as009 does, never the earlier stored annotation receipt timestamp. Existing deadline/byte/terminal races and marker facts remain009; a delayed durable write does not extend the observation deadline or erase ambient RX.

Positive ordinary append acknowledgement returns `AnnotationReceipt` containing `run_id`, `session_id`, `reference`, `annotation`. Reference session equals receipt session; reference sequence equals inserted annotation sequence. No operation ID/start/end markers, inline RX, verified-action outcome, idempotency key, retry or retained receipt catalogue.

On append failure, propagate normalized JournalFailure; unknown faults become private internal_failure. No successful reference is returned without acknowledgement. An ambiguous failure or lost response may leave a committed annotation; a manual repeat is a distinct assertion and may duplicate it. A successful receipt promises neither future retention nor power-loss/media guarantees beyond003.

## 4. Explicit persistence revision and compatibility

Add immutable normalized `ClientAnnotationEvidence` and `PendingClientAnnotationEvidence` to the existing closed unions. Sequence/session association and ordinary immutable reference semantics stay003. New pure helpers: `encode_evidence_record_v3`, `decode_evidence_record_v3`, `charge_client_annotation`.

| Kind | Record version in schema-v3 | Metadata/BLOB |
|---|---|---|
|Four existing003 kinds|1|Exactly old codec bytes, validation and charge|
|operation_started / operation_ended|2|Exactly009 codec bytes, validation and charge|
|client_annotation|3|Metadata below; BLOB is exact validated UTF-8 text|

Annotation metadata has **exactly** `assertion_class`, `client_surface`, `attribution_basis`, `clock_origin_id`, `received_at_ns`. First/third are fixed literals from §1; surface is `cli`/`http`/`core`; origin is canonical lowercase hyphenated UUID; received time exact int **0..9223372036854775807**. BLOB decodes strictly to the §1 text; never SQL NULL, UTF-8 replacement decoding or normalization. Persisted JSON uses existing **ensure_ascii=False, allow_nan=False, sort_keys=True**, compact recursive canonical encoding. Row sequence has existing **0..9223372036854775806** range.

Annotation `rx_payload_bytes=0`; cached first/last retention timestamp endpoints are NULL. Host receipt time stays metadata and must not be fabricated into backend timestamp provenance. Charge stays003: **16 + UTF-8 kind bytes + canonical metadata UTF-8 bytes + BLOB bytes**. Ordinary record/retained/page/counter/database limits apply; no extra table, pin, reservation, tombstone list or retention exception. Annotation eviction can evict RX/markers and vice versa.

Explicit `SqliteEvidenceJournal.create_v3/open_v3` require schema3 in PRAGMA user_version and session_metadata.schema_version, same APPLICATION_ID **0x4455544D**, same three-table organization and ordinary003 transaction/reopen/worker/retention mechanics. Default `create/open` remain strictv1; explicit `create_v2/open_v2` remain strictv2. Their codecs, old factories and Profile-v1 are not silently broadened. V3 delegates old six variants to exact legacy codecs; v1/v2 reject annotations/new schema. No migration, auto-detection, opening old files writable through a new version, recovery change, arbitrary history or schema selector in delivery.

Expected schema mismatch => `incompatible_schema_version`; unsupported known kind/version pairing => `incompatible_record_version`; unknown kind or malformed stored content => `corrupt_journal`; malformed new input => `invalid_input`; inconsistent retained operation pairs => `invariant_violation`. Preserve all twenty existing JournalFailure kinds and mappings.

Use explicit **1/2/3** dispatch in schema/table/row validation, append/query workers, retained operation-pair validation and terminal readers. Do not leave `if v1 else v2` defaults that misroute v3 or admit unknown versions. The operation-pair validator must decode intervening records with the selected format: annotation between RX match endpoints is valid and ignored by byte matching. Timestamp endpoint scans must skip host-only annotations exactly as operation markers; a following RX must not trigger a false stream-identity invariant failure. Preserve v2 standalone/retained-pair checks.

Pure charge callback accepts a maximum-shaped valid pending annotation using the actual text/surface/origin and `received_at_ns=9223372036854775807`; codec-assigned sequence0 is sufficient because sequence is not charged metadata. Core checks its exact positive signed-64-bit charge against **max_record_charged_bytes**, **max_retained_charged_bytes**, **max_retrieval_page_charged_bytes** before admission. Conservative timestamp width may reject a small policy. No private codec replication in Core, hand estimate, budget refund, policy inflation or later-capacity guarantee.

## 5. Existing retrieval, terminal readers and projections

Production Basic composition creates v3 and captures expected_schema_version=3 in its immutable terminal target; still one active journal/gate/worker for append and read. Existing terminal target default1/explicit2 behavior remains; explicit3 opens fresh **mode=ro&cache=private**, verified query_only and read transaction with the strict selected validator. No writable fallback, recovery, migration, shared active second connection or resource retention. Existing005/008 session association and confirmed-close/reader-cleanup rules remain.

Add exactly one closed evidence HTTP/CLI variant, canonical key order:

`kind, sequence, assertion_class, client_surface, attribution_basis, clock_origin_id, received_at_ns, text`

`kind` is `client_annotation`; remaining fields as §4. No wire record_version, translated timestamp, verified author, excerpt or invented segment provenance. Four old003 and two009 variants remain exact. An annotation submitted via HTTP has cli/http; direct-Core-created persisted records can project core without being accepted as an HTTP input surface.

Existing `/v1/evidence/record`, `/v1/evidence/page` and CLI evidence commands resolve references/ranges with ordinary retained/partial/expired/unknown outcomes, snapshot continuation, explicit truncation and exact charged-page limits. Zero-shortage pages and coalesced retention remain. Receipt record can already be expired when explicitly retrieved. Keep cursor **1024-byte** cap and whole-response **1048576-byte** service/CLI caps (CLI LF extra). Overflow is existing whole413, not trimming/splitting/auto-pagination. No annotation-specific retrieval/filter/search/history endpoint.

## 6. Authenticated HTTP and service jobs

Only literal **POST /v1/observation/annotations**; no query, slash, method or escaped-path alias. Same006 SecurityGate peer/Host/Origin/browser/Bearer/Upgrade checks and exact route/media rules before body/Core/journal. No CORS/docs/security/logging/bootstrap relaxation. Every success/error has **Cache-Control: no-store**.

Closed required request, canonical client encoding order:

```json
{"session_id":"known-session","text":"build abc123; step smoke","client_surface":"cli"}
```

Strict UTF-8 JSON, no duplicate keys/nonfinite values/coercions/extra fields. Text/session/surface bounds §1. Actual body **<=16384 bytes**, detect16385 independent of Content-Length using the existing bounded reader; worst-case escaped legal text/session fits. Media failures415 request/unsupported_media_type; body overflow413 request/payload_too_large; field/encoding errors422 request/invalid_request. Caller supplies no assertion_class, attribution_basis, time, origin or sequence.

After security/readiness/body validation, annotations use the **existing eight service mutation jobs shared with attach/detach**, not a new independent service slot or generic job registry. An annotation job is strongly registered before Core entry; normalize errors within retained owners and shield delivery as existing mutations. Core separately limits pending annotations to one. Preserve independent eight read jobs/Core read leases and one Monitor job. Overflow503 service/operation_capacity; no queue. Extend existing stop sealing to cover annotations before taking job snapshots; join all registered work before final detach/bootstrap release. No work starts merely because a service job was registered before Core admission.

HTTP200 receipt canonical key order: `run_id, session_id, reference, annotation`. `run_id` is the established exact nonempty run string; session is the associated SessionId string; reference is `{session_id,sequence}`; annotation is the full §5 variant. Receipt consistency follows §3. Project immutable acknowledged facts only, not caller dictionaries.

Use existing compact UTF-8 JSON encoding and independent **1048576-byte** service/CLI delivery bounds, bound+1 detection and existing identity Content-Encoding/media validation. Whole annotation receipt overflow413 annotation/delivery_too_large; insertion may already have committed. No trimming, inline unbounded diagnostics, auto-refetch or retry.

| HTTP | source/code | Meaning |
|---|---|---|
|404|annotation/no_associated_session|No known associated session|
|409|annotation/session_not_associated|Explicit session differs|
|409|annotation/not_active|Current run not ACTIVE or per-run sealed|
|503|annotation/annotation_unavailable|Global seal, unsupported preparation, missing committed segment or invalid/stale clock capability|
|422|annotation/evidence_policy_incompatible|Conservative charge cannot fit policy|
|409|annotation/busy|Core pending owner already exists|
|429|annotation/rate_limited|Incarnation's rolling budget exhausted|
|413|annotation/delivery_too_large|Whole receipt too large|
|503|service/operation_capacity|Existing eight mutation job slots exhausted|
|500|runtime/wrong_execution_context|Existing wrong loop/thread guard|
|422|runtime/invalid_request|Existing wrong application argument guard|
|500|service/internal_failure|Unexpected insertion/clock/projection fault|

All common006/008 security/readiness/body/routing errors remain exact, including503 service/stopping. JournalFailure mapping is exactly008/009: invalid_input422, session_mismatch409, journal_missing404, busy503, closed409, all other fifteen kinds500, source journal/exact code. Error envelope remains only `{error:{source,code}}`; no detail, operation, path, SQL, content, credentials, trace or cause. No Retry-After/new rate headers or diagnostic echo of text.

## 7. Thin CLI

```text
dutchmate [--host HOST] --port PORT annotate --session ID --text TEXT
dutchmate annotate --help
```

Both command inputs required, no implicit session/default/text normalization. Fixed client_surface=cli, no surface/author/time/path/token/file/stdin/follow/run/output option. Existing global numeric loopback/port grammar applies. Root/command static help performs no platform/account/credential/network I/O. Validate text/session locally before credentials; fixed invalid_arguments/exit2 for invalid inputs. One POST, no attach/status/evidence requests, polling, retries or exactly-once assumption.

Keep007 credential-once HTTP/1/numeric Host/Bearer/no proxy-env/redirect/fallback, **5s phase/10s absolute** transport budget. Local timeout/SIGINT can lose delivery while admitted Core insertion settles. Do not extend timing or implement Core rate/retention/clock policy in CLI. Closed reply checks exact fields/types/literals/UUID/ranges and receipt-reference identity, then canonical compact JSON+LF, **exit0 only for valid delivered receipt**. It proves recording of a claim, not the claim's truth. New recognized annotation errors use existing fixed stderr/exit4; invalid_response5, local input2, output/unexpected1, interrupt130 and unusable-stderr rules stay007. Add error support only to the new command; preserve old command validators except the single additive evidence variant.

## 8. Acceptance boundary

RED/GREEN pure values/codecs; explicit v1/v2/v3 mixed journal/reopen/read-only terminal matrix; identical Basic/Enhanced-shaped shared workflows with real temporary journal; deterministic rate/gate/cancel/detach/shutdown/Monitor races; all twenty journal mappings; eight mutation/eight read/one Monitor independence; retention/timestamp scans; strict HTTP/CLI/privacy/installed wheel/sdist behavior. Full uv/import/diff gates at defined coherent checkpoints and fresh final installability verification.

No default test opens/discovers physical serial or real account credentials. Self-created virtual ports and guarded loopback fixtures are software evidence only. Native Linux/Windows, active-DUT, physical/electrical and Enhanced hardware acceptance remain unexecuted/separately authorized. All spec FR-014 deferrals remain.
