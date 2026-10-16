# Data Model: Bounded Attributed Client Annotations

Annotation values, explicit v3 persistence, gated coordinator insertion, runtime admission/rate/ownership, production composition and service/thin CLI delivery are implemented. All T001–T024 tasks are complete; fresh final software/installed/artifact/privacy/Core/contract review passed without correction. T023 tooling/health limits remain recorded. Feature010 is software-complete; implementation commit is recorded in development_status.md; Phase1 and native/physical acceptance remain incomplete. [Contract](contracts/annotations.md) fixes exact behavior. Core/003/005–009 values remain authoritative.

## Request and normalized record

| Value | Fields and constraints |
|---|---|
|AnnotationRequest|session_id: existing SessionId; text: exact str, **1..1024 UTF-8 bytes**, no NUL/surrogates; client_surface: **cli/http/core**, exact str|
|PendingClientAnnotationEvidence|text and client_surface as above; assertion_class **client_assertion**; attribution_basis **client_asserted**; clock_origin_id canonical lowercase hyphenated UUID; received_at_ns exact int **0..9223372036854775807**|
|ClientAnnotationEvidence|Same immutable fields plus existing sequence **0..9223372036854775806**; kind **client_annotation**|
|AnnotationReceipt|run_id established nonempty exact str; session_id existing SessionId; reference existing EvidenceReference; annotation ClientAnnotationEvidence; reference session/sequence must equal receipt session/record sequence|
|AnnotationRejected|Ordinary sealed normalized fixed-kind exception; no_associated_session, session_not_associated, not_active, annotation_unavailable, evidence_policy_incompatible, busy, rate_limited. Writable standard exception transport metadata; no raw cause/path/content|
|PreparedAnnotationAccess|session_id/policy; exact shared coordinator; existing host clock; pure maximum-shape charge callback. Optional None on existing preparation; identity/session/policy coherence validated on transfer/admission|

Fixed assertion/attribution literals may be invariant properties rather than caller-selectable constructor inputs; the external/persisted record always has the exact closed field set. No user/process identity or hardware-action verification. Text is never UART bytes.

## Ownership and bounded state

Per generation: optional access, annotation_sealed flag, at most one strongly owned pending insertion bound to that run. The owner holds the immutable request/access until settled, and clears only its own generation slot. No receipt/history cache or task handle exposed to clients.

Per incarnation: global annotation seal; one canonical admission clock origin bound at first admission; last valid admission-check time (also updated by a valid check followed by rate rejection); deque of **at most ten** admitted times. Window is **(now-1,000,000,000, now]**; discard exact-one-second-old entries. Cross-attach clock change/backward/invalid sample rejects without resetting history or last-check time. A new runtime alone resets the budget.

Request transitions: validated → admitted/owned → waits for same recorder gate → insertion receipt time sampled → append submitted → acknowledged receipt OR normalized failure → owner joined/slot cleared. Pre-admission rejections create no owner/append/budget entry. Post-admission failure consumes budget and may leave an unacknowledged committed record. Cancellation only ends delivery; admitted work settles.

Run sealing blocks new admission, not an existing owner. A bound annotation may follow segment_end in the same session and remains host-only context. Acquisition/Monitor/live reads/annotation owners settle before recorder close and terminal publication; retain existing008 read-cleanup latch. Failed cleanup never creates a new terminal-reader permission.

## Persistence and retrieval

Schema3 permits original four record-v1 variants, two operation-v2 variants and one annotation-v3 variant. Old six encodings/charges remain byte-identical. New text is exact UTF-8 BLOB; closed canonical metadata carries classification/surface/basis/origin/time. Sequence is the ordinary column; rx_payload_bytes=0, cached backend timestamp endpoints NULL. Ordinary policy/retention/cursor/reference behavior, no second store.

No migration or automatic version inference. Explicit v1/v2 factories/codecs/read-only expectations remain strict; explicit v3 supports the new union. Terminal mode keeps immutable expected format, identity/session/policy and confirmed writer/reader cleanup requirements.

## Delivery representation

Request fields: session_id, text, client_surface (HTTP cli/http only). Record fields: kind, sequence, assertion_class, client_surface, attribution_basis, clock_origin_id, received_at_ns, text. Receipt: run_id, session_id, reference, annotation. Old evidence variants have no added keys. Whole service/CLI JSON caps remain1048576 bytes, CLI LF extra; request remains16384, cursor1024. No caller-supplied record kind/version, timestamp, reference or provenance.
