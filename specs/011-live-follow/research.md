# Research: Receive-Only Live Follow

2026-10-16. Read-only research against governing Core/current status and the
committed001–010 source/contracts. Two bounded research agents inspected Core
lifetime/journal races and service/CLI streaming, as required by the plan skill.
No runtime experiment, hardware access, dependency lookup or production edit.

## 1. Live head on the authoritative journal

**Decision:** Capture actual journal next_sequence under the recorder coordinator
gate, then register Follow atomically with current provenance. Reuse003's
metadata-only empty[MAX,MAX) retrieval on the live reader.

**Rationale:** Existing sqlite_evidence.py retrieval computes snapshot end before
its empty-range return, selecting no payload. This avoids a mirrored last-ACK
tail (ambiguous ACK failures), a new persistence method/schema and a historical
first-row scan. Gate order remains coordinator→journal.

**Alternatives:** Tracking successful ACK sequence alone misses an ambiguously
committed row; replay from zero violates live start; opening another connection
violates the intended active read ownership. No selected alternative needs a
product-level Core change.

## 2. Coalesced notification and bounded same-journal pulls

**Decision:** One subscriber, one coalesced wakeup, one bounded page, ordinary
rolling retention, explicit gap then continued live delivery.

**Rationale:** Existing003/008 reads already provide exact ordered records,
snapshot low-water expiry and unchanged coalesced markers. No copied RX queue,
retention pin or transcript is needed. Core§8 permits multiple subscribers but
does not require them; one independent slot is the smallest coherent scope.

**Alternatives:** Unbounded broadcast loses bounds; bounded copies need another
overflow/loss store; treating retrieval as repeated HTTP polling is not Follow.
Terminate-on-any-retention would be honest but less useful than reporting a
precise gap and continuing. Future fanout/filtering/history remains deferred.

**Source inventory:** monitor.py has four append-ACK paths: ordinary append,
append_client_annotation, Monitor start, and _MonitorOperation settlement/end.
The latter two bypass ordinary _publish. Notify all four without changing their
gate/clock/matcher order. An ambiguous submitted append may notify possible
change; only the next journal snapshot supplies facts. Clear-before-head-snapshot
and wake-race tests prevent lost idle wakeups.

## 3. Resource ownership and stopping

**Decision:** Optional prepared transfer, strong captured-generation start/query
owners, no idle read lease; synchronous seals, optional teardown-owned head probe,
join resource work before close, terminal delivery independent of recorder lifetime.

**Rationale:**005/008 already establish cleanup owners and uncertainty. Runtime
teardown currently joins acquisition, Monitor, annotation and reads before
recorder close. Follow extends that ordering minimally and never waits for an
idle socket. server.py calls request_stop before HTTP drain: sealing only at
lifespan detach would deadlock a long-lived stream against shutdown.
The sealed idle pull therefore returns immediately with an already-known cutoff
orNone; it never waits for the optional final probe or future lifespan cleanup.

**Alternatives:** Shielding the whole infinite subscription prevents cancellation;
holding a read lease/connection for its life harms existing reads; waiting to
drain all unread evidence can make shutdown unbounded. A final known cutoff or
explicit unknown end reports an honest unoffered tail without a drain promise.

## 4. NDJSON and exact evidence frames

**Decision:** Authenticated literal POST, closed started/record/gap/heartbeat/
terminal NDJSON, existing seven record projections and canonical base64.

**Rationale:** Raw octets cannot report provenance/annotations/gaps; line-delimited
JSON can reuse strict validators and bounded serialization. SSE adds browser/
EventSource/reconnect conventions irrelevant to this authenticated thin client.
No text decoding or new evidence variant is required. A per-frame1MiB cap
preserves bounded delivery without limiting total human session length.

**Alternatives:** WebSocket adds a bidirectional protocol not needed here; a
whole buffered JSON report cannot deliver live data; silently dropping metadata
or splitting a record weakens evidence semantics.

## 5. Thin streaming transport

**Decision:** Preserve finite exchanges verbatim; add one narrow Follow exchange,
10s handshake,5s absolute complete-frame receive/send budgets,1s idle heartbeat,
no whole-session timeout/retry. Flush validated canonical frames immediately.

**Rationale:** Existing007 client has5s phases/10s absolute and whole-response
buffering; applying it unchanged would end every Follow. New per-frame logic
protects idle/trickling peers while a heartbeat supports human-controlled lifetime.
Cooperative stdout/OS writes and durable cleanup have no invented hard timeout.

**Alternatives:** A read timeout reset by every byte permits indefinite trickle;
a global client timeout contradicts human Follow; automatic reconnect silently
changes start boundaries. Exit0 keeps existing report-delivery meaning even for
a terminal failure/unknown cutoff; abnormal EOF remains invalid response.

## 6. Verification, packaging and deferred acceptance

**Decision:** Both backend shapes plus real temporary journal, deterministic race/
retention tests and actual guarded loopback/installable wheel/sdist processes.
In-process HTTPX ASGI transports can buffer streams and are insufficient alone.

**Rationale:** Existing service security gate wraps raw paths/headers and applies
no-store at response start; after headers errors need terminal/EOF handling.
Tests must cover raw security, service stop before HTTP drain, Ctrl-C/pipe and
fragmented/chunked framing outside the checkout with hardware/account guards.

**Alternatives:** Physical acceptance is not automatically selected. No new package,
release machinery, Graphify update during planning or architecture redesign.
