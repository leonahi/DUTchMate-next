# Research: Receive-Only Monitor

**Planning research date**: 2026-10-14. This historical investigation used local governing sources and read-only code inspection; it performed no external service/hardware research or implementation. The selected decisions were subsequently implemented; [tasks](tasks.md) and [history](../../docs/development_history.md) record progress/evidence, with T001–T037 complete and native/physical acceptance still pending. Spec Kit's plan research was split into two read-only investigations: committed-stream/lifecycle boundary and versioned evidence/terminal retrieval. Their findings were checked against source and consolidated here.

## 1. Monitor over acknowledged records

**Decision**: A small application recording coordinator publishes positively acknowledged records on the owner loop around the existing recorder. It serializes start-boundary installation with acquisition appends and tracks committed segment provenance.

**Rationale**: `acquisition.py` already has the sole sequential backend consumer and awaits `recorder.append`; its public provenance snapshot updates after append. Feature003 has one gate/worker. A wrapper can establish the boundary without a reader, queue or broad acquisition refactor. Core §§5/6/18 require this ownership/order.

**Alternatives considered**: polling008 pages misses evicted chunks/adds lag; another UART/SQLite connection violates active ownership; matching before durable acknowledgement can report non-evidence; post-ack asynchronous subscription races lose the first chunk. None selected.

## 2. Smallest condition and finite bounds

**Decision**: One literal binary condition1..256 bytes, mandatory timeout1..4000 ms and examined-byte bound1..1048576; one operation per active run. Host monotonic publication eligibility, equality timeout, atomic eligible chunks, match wins on final allowed byte.

**Rationale**: Core §12 delegates matching specifics to this spec. Binary literals avoid text/regex semantics and span chunks with bounded prefix state. The4s ceiling leaves nominal room inside007's5s phase/10s overall budgets without changing them; it is not a bound on journal I/O/cleanup or a delivery guarantee. Explicit byte bound limits processing independently of retention/output.

**Alternatives considered**: multiple/regex/text conditions and capture-only/time-only modes are useful later but not needed for the accepted smallest slice. Client timing loops violate thin-client ownership. Per-byte host sampling makes results CPU-speed-dependent within a record. Unlimited/concurrent queued waits unnecessarily expand ownership and memory.

## 3. Window, loss and provenance

**Decision**: Start is the first sequence after committed start marker; freeze exclusive end at decision watermark, not eventual end-marker sequence. Match endpoints are sequence+byte offsets. Reset prefix on observed loss; terminate at segment/origin boundary. Preserve whole RX chunks and full captured provenance.

**Rationale**: Core §§7.1/11/12/14 preserve raw asynchronous output and separate observation order from DUT-time/causation. Feature003 retention can discard referenced bytes; a performed match stays a derived fact, with later expiry explicit. Host timing is separate from backend clock origin/loss observability.

**Alternatives considered**: using end-marker sequence includes later ambient bytes; trimming chunks fabricates raw evidence; matching across known loss creates false continuity; keeping/pinning all window bytes would compete with rolling retention. No selected alternative requires changing existing RX contracts.

## 4. Required operation evidence and explicit schema revision

**Decision**: Introduce schema-v2, only two operation-record-v2 variants, keep old four record-v1 encodings and default schema-v1 factories exact. New service-composed runs explicitly choose v2; default legacy create/open stay v1. Same APPLICATION_ID, three tables and mechanics; PRAGMA user_version and session_metadata.schema_version become2 only in explicitly v2 artifacts.

**Rationale**: Core §14.1 requires operation markers, while the committed planning baseline of `adapters/sqlite_evidence.py` strictly validated version1/four variants. Silent acceptance under schema-v1 would change its compatibility contract. Existing canonical charge is16+kind+metadata+BLOB; marker condition bytes are not RX. Preflight actual start/worst end protects immutable Profile-v1 policy without inflation/reservation.

**Alternatives considered**: overloading segment/loss records invents their meaning; sidecar/operation table splits sequence/retention and adds needless persistence; migration/recovery/catalogue exceed scope; replacing the whole journal risks003 semantics. Explicit additive v2 is the narrow required revision.

## 5. Active and terminal retrieval

**Decision**: Active reads keep the same authoritative journal worker; terminal target records expected format(default1 legacy,2 new), validated strictly in existing fresh read-only transaction after confirmed writer closure.

**Rationale**: `evidence_access.py`, `runtime.py`, `adapters/terminal_evidence.py` and008 retain only immutable target facts after settlement. Version-aware pure validation can reuse003 selection/snapshot/retention while preserving mode=ro/query_only/native identity and cleanup latch.

**Alternatives considered**: holding the recorder open, writable fallback/recovery, immutable/nolock, version guessing or persistent reader pools contradict008. No historical path browsing or restart association is added.

## 6. Owned operation lifetime and incomplete durability

**Decision**: One separate service Monitor slot and one Core owner, shield/join after client loss; detach seals/settles markers before close. Shutdown seals Monitor Core admission and joins all job categories before final detach. End-marker failure preserves the decided outcome plus explicit end_unconfirmed/null ref/normalized failure.

**Rationale**:005/006/008 require truthful ownership/cleanup; a normal finite clock cannot abandon submitted journal I/O. A matched observation and failed durable end are separate facts. Start failure cannot supply a positive reference.008 already corrected JournalFailure standard exception transport; preserve its sealed facts/writable metadata.

**Alternatives considered**: cancelling on disconnect changes service ownership; forcing journal close permits false settlement; rewriting capture failures or reporting a fabricated end is dishonest; retrying an ambiguous commit can duplicate evidence. Public jobs/replay/cancel APIs are unnecessary here.

## 7. Delivery and acceptance

**Decision**: One authenticated POST and thin CLI command, existing binary encoding/security/receipts/timeouts/errors, independent1MiB response and output bounds, whole413 on overflow. Add exactly two evidence wire variants; default v1/Profile/backend contract and dependencies remain.

**Rationale**:006–008 already provide bounded authenticated HTTP, closed projections and guarded installed tests. Reuse those mechanisms without lowering journal policy or loosening old commands. Run shared fixture assertions identically; Enhanced-shaped fixtures prove software neutrality only.

**Alternatives considered**: inline full RX, raw/text output, auto-pages/refetch/follow, client clock policy and new dependencies are outside the bounded reporting purpose.

**Unresolved decisions**: None. Native Linux/Windows, active-DUT, physical/electrical and Enhanced hardware acceptance are not selected or performed.
