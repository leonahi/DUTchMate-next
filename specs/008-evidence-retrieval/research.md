# Research: Bounded Evidence Retrieval

Planning checkpoint2026-10-10; baseline007 a14d172. Two read-only research agents
inspected existing ownership and delivery code. No product dependencies installed,
production code edited, hardware accessed or new feature acceptance claimed.

## Association and read ownership

Decision: one current/last association per ObservationRuntime, containing immutable
RunId/known SessionId/SessionPolicy and an opaque composition-supplied read source.
Newly admitted attach clears the old association; rejected attach does not. Read
binding is linearized at Core admission, not earlier HTTP task registration. Already
bound reads may finish after replacement; unbound queued reads revalidate the
explicit session and can reject. No catalogue/history/restart lookup.

Rationale:005 already keeps one current/last summary and drops resource handles
at terminal publication.006 owns registered HTTP work even before Core entry.
Alternatives: path-supplied queries, journals keyed forever, implicit status and
private runtime/SQLite-handle inspection broaden authority or violate boundaries.
Sources: runtime.py299–308/424–481/617–733, observation_runtime.py,006 contract §6.

## Live versus terminal readers

Decision: live/draining reads use the authoritative journal's existing async gate
and single worker through a read-only port. After acquisition joins, seal admission,
join bound live reads and close recorder; only positive terminal recorder closure
publishes terminal read mode. Open one mode=ro/cache=private/query_only terminal
reader per query, validate v1/session/policy/native file identity and close it.
Use one read transaction over validation/state/row selection; no writable open,
recovery, journaling/physical-ceiling writes, immutable=1 or nolock.

Rationale: existing SqliteEvidenceJournal.open is mode=rw, performs rollback
recovery/writable proof/journal configuration/physical ceiling. Independent active
read connections could hold DELETE-journal read locks and make authoritative append
commit fail BUSY (busy_timeout=0). Terminal reads must preserve close confirmation.
Alternatives: retain capture recorder after detach, reopen active DB or use existing
writable open; all either weaken lifecycle or risk acquisition. Copying files and
persistent connection pools are unnecessary and outside accepted guarantees.
Sources: sqlite_evidence.py731–831/936–978/1484–1660,003 contract §§2–3/7,
[SQLite URI modes](https://www.sqlite.org/uri.html),
[query_only](https://www.sqlite.org/pragma.html#pragma_query_only).

Research-only temporary SQLite3.51.3 probe: mode=ro + query_only reads all256 bytes,
rejects INSERT, leaves database bytes unchanged and creates no sidecar. This checks
local mechanisms only, not the proposed reader or terminal/hardware acceptance.

## Failed preparation and source identity

Decision: optional normalized read access on PreparedObservationRun; optional opaque
terminal source on PreparationFailure after cleanup when a returned journal/session
exists. Missing capability does not invalidate old005 attach-only preparations;
reads report unavailable. Fact fields remain immutable. The concrete source captures
resolved destination, native device/inode, expected session and policy at creation;
only those immutable facts survive terminal settlement, never a live writer/FD.
Both live and terminal capabilities are optional, with at least one when supplied.
Native target capture failure alone retains valid live capture/read access and
explicit terminal unavailability; no lookup/path fallback or extra attach rejection.

Rationale: failed create without returned session cannot be rediscovered. A known
session after construction failure remains inspectable only if closure was confirmed.
Sources must not retarget after path replacement. Identity checks before/after readonly
open plus expected session/policy fail closed; they are not guarantees against
same-UID adversarial rename/restore or live copying.
Alternatives: reconstruct paths from status, preserve a writer, infer creation from
an artifact or query arbitrary historical journals; rejected for scope/provenance.

## Pagination and representation

Decision: use003 EvidenceReference/EvidenceRetrievalRequest/EvidencePage unchanged.
Canonical JSON v1 routes carry all four record variants, padded standard base64 RX,
006 public provenance shape and all page/marker fields. Continuation is canonical
base64url-without-padding JSON with version/session/original range/snapshot/next.
No signature/registry: cursor is a bounded value, never an authentication credential.

Rationale:003 private codecs use different names/shapes from006's public provenance;
exposing them would create accidental persistence-to-HTTP coupling. Snapshot end is
not a tail cursor. Stable-reference sequence MAX is permitted by EvidenceReference
and existing resolver returns not_found without overflowing its suffix range.
Alternatives: JSON integer-byte arrays, hex, private storage codecs, offset/timestamp
pagination or client-side decoding; unnecessary expansion or semantic violations.
Sources: model.py426–591, evidence.py85–189, sqlite_evidence.py1420–1660,
http.py235–272,003 contract §7,
[RFC4648](https://www.rfc-editor.org/rfc/rfc4648),
[Python base64](https://docs.python.org/3.14/library/base64.html).

## Independent delivery limits

Decision: requests <=16384 actual bytes; session1..256 UTF-8 bytes/no NUL; cursor
<=1024 ASCII bytes; page max_records1..4096/max_charged_bytes1..1048576. These are new
delivery admission ceilings, not changes to SessionPolicy. Within wire ceilings,
003 still rejects requests above captured policy. Both encoded response and CLI JSON
cap1048576 bytes (CLI LF excluded). Overflow returns413 evidence/delivery_too_large
for the entire page, without adjustment/retry. An irreducibly oversized record or
metadata receives the same rejection;003 shortage pages remain valid200 reports.

Rationale: charged bytes exclude base64/key overhead. Finite wire request caps limit
page projection work but cannot prove an encoded report fits. Single-reference reads
can still materialize a003 policy-sized record before transport preflight; no exact
1MiB total-memory or OS-read claim. Compute base64 encoded size before oversized
allocation, or use aligned bounded chunks. Server/client share exact compact escaping
and key order so client re-encoding does not unexpectedly expand a fitting report.
Alternatives: silent page trimming/cursor rewriting, partial base64, automatic smaller
refetch or tightening Profile record ceilings; violate003 results or client authority.

## Lifetime and capacity

Decision:8 service read tasks separately from006's8 mutation slots,8 Core bound reads,
no queue/history/public job IDs. Service registry owns waiter loss; Core admission
owns a pinned source/read lease. Seal admission on shutdown, join both service
registries, then existing final detach; runtime detaches seal/join live reads before
recorder close. Join submitted worker/open/close cancellation-resistently.

Rationale: bounded retained work and safe resources, without imposing a new Core
lifecycle deadline. Shutdown never detaches before registered mutations/read waiters
have settled. First read failure remains primary; if reader cleanup alone fails,
return that normalized failure and discard report. Secondary cleanup never replaces
an existing primary; no extra detail/cleanup arrays or falsely successful closure.
Unconfirmed terminal/partial-open cleanup (including unexpected opener faults with
unknown resource state) latches further read admission closed before releasing the
failed slot. Already pinned reads settle. The service clean-marker conjunction adds
this positive read-cleanup confirmation; capture/attach facts remain unchanged.
Alternatives: cancel tasks on HTTP loss, close a worker early, abandon blocking I/O
or introduce jobs/queues; conflict with003/005/006 ownership.

## Exception transport

Decision: focused sync/async generator context-manager RED, then ordinary sealed
JournalFailure preserving constructor(operation,kind,detail), exact field/value/type
validation and fixed existing message behavior. Fact fields read-only; standard
traceback/cause/context/notes transport writable. No schema/codec/category change.

Rationale: frozen/slotted exception metadata can mask real journal failures with
TypeError on Python3.14; terminal resource scopes make this relevant now. Existing
PreparationFailure provides the precedent. Wire never exposes detail or exception text.
Alternative: avoid all context managers/catch arbitrary TypeError instead; hides the
known cause and propagates a fragile exception contract.

## Dependencies and deferred work

Use existing Python3.14/uv/FastAPI/Uvicorn/Typer/HTTPX and standard-library base64/json/
os/stat/sqlite3/asyncio. No new dependency, Core framework import, registry or parser
framework. No schema/Profile/backend revision;006/007 gain explicitly specified
additive read routes/commands, leaving existing endpoint/command semantics intact.
All requested deferrals are in the spec and contract. No unresolved decision remains;
implementation must validate mechanics/fixtures/native installs without hardware.
