# Contract: Local Observation Service

This is the feature-006 local HTTP and bootstrap contract. Core and completed
001–005 contracts govern underlying execution. No evidence/Backend/Profile schema changes.

## 1. Supported composition and listener

Production entry is `run_service(ServiceConfig(port, host="127.0.0.1"))` in
`dutchmate_service.server`, not a DUT CLI. No client commands, daemon manager,
environment configuration loader or global ASGI app with import-time effects.
ServiceConfig requires an exact integer port 1..65535 (bool rejected); host is
exactly "127.0.0.1" or "::1". Initial support: Linux/macOS local POSIX filesystems.
Unsupported platforms fail as unsupported_platform before bootstrap/resources.

Use one controlled Uvicorn server, one process/worker, asyncio loop, HTTP h11,
lifespan enabled, reload disabled, proxy_headers=False, access_log=False,
debug=False, timeout_graceful_shutdown=None and no WebSocket delivery.
No externally supplied workers/reload/socket/proxy overrides. No fork after
ownership; lock fd is non-inheritable. Bare uvicorn/gunicorn factory launch is
unsupported; fail lifespan startup if the controlled launch context is absent.
A private test harness supplies the same bootstrap/security/lifespan paths,
not an authentication or process-ownership bypass.

Create exactly one socket for the selected numeric address. For ::1 set
IPV6_V6ONLY=1 before binding. Do not resolve localhost, accept wildcards,
IPv4-mapped IPv6, bind both families, change port or fall back when bind fails.
Only loopback peers of the selected family are accepted; forwarded/proxy headers
are ignored. A non-loopback/absent peer fails 403 request/peer_rejected before Host.
In-process ASGI tests must provide the explicit simulated loopback peer.

The original guarded process owns one persistent ObservationRuntime constructed
inside async lifespan on the serving loop/thread. All runtime-calling handlers,
dependencies and shutdown work execute on that context, never a sync threadpool.

## 2. Fixed bootstrap and duplicate/stale owners

Production state directory is `<account-home>/.local/state/dutchmate/service`,
where account-home comes from the effective UID's passwd entry, not HOME/XDG
environment overrides. No configurable production alternative can evade the guard.
Tests substitute account-home with an isolated temporary directory privately.

Account-home and private descendants must be effective-UID-owned real directories
with no symlink traversal or group/other write permission; service directory is0700.
Filesystem ancestors may be root-owned or effective-UID-owned, without group/other
write permission except a root-owned sticky directory such as /private/tmp.
Isolated test account-home is a UID-owned0700 descendant of such a trusted
temporary root and undergoes the same validation. Create private descendants with0700.
Do not chmod or repair existing unsafe paths automatically. Reject unsafe files:
anything not regular, not UID-owned, not0600, symlinked or with link count !=1.
Use no-follow, directory-relative descriptor operations and fstat validation;
avoid a path-check/open race. All operations fail closed if checks are unsupported.

Files: `owner.lock`, `owner.json`, `credential`. No session catalogue.
Open/create owner.lock0600 with a stable inode; acquire flock(LOCK_EX|LOCK_NB).
An unavailable lock is owner_active immediately, even on another host/port.
Do not read/replace credential or marker, create a runtime or prepare DUT resources
when rejected. Hold the same fd until complete cleanup. Never unlink/replace the
lock file, use PID liveness, kill a process, steal a lock, poll or wait for takeover.
This is cooperative per-UID service exclusion, not a machine-wide lock against
other accounts or arbitrary programs. Existing Basic exclusivity is independent.

owner.json is at most256 UTF-8 bytes, strict JSON object with exactly
`{"version":1,"cleanup_confirmed":boolean}`; no duplicate keys, extra fields,
PID authority, timestamps, paths, Profile/session IDs or secrets.
Absence is eligible only for fresh state with no credential; true is eligible;
false, malformed, incompatible or token-without-marker is previous_cleanup_unconfirmed.
A stale true marker can be replaced under the lock; a stale false marker cannot.
Keep uncertain/malformed state intact and release the newly obtained guard on
startup rejection; no HTTP listener/runtime is made available.

Before creating any runtime, atomically publish cleanup_confirmed=false and
fsync the file plus containing directory. Mark the entire service incarnation,
not every run. Thus even idle crash/repeated external termination can block restart.
OS lock release on death is never treated as positive physical/recorder cleanup.
No automatic recovery/reset endpoint or startup override is supplied. An operator
must establish cleanup externally before explicitly resolving the marker; that
manual operational recovery is outside this slice and never advertised as proof.

Atomic marker/token writes use a same-directory exclusive private temporary
file, flush/fsync, replace and directory fsync, bounded contents, and remove
only the invocation's own temporary files. No power-loss/media guarantee is claimed.
These files are bootstrap state only, not additions to feature-003 schema-v1.

## 3. Credential bootstrap and lifetime

After lock/marker eligibility, generate secrets.token_hex(32): exactly64 lowercase
ASCII hexadecimal characters (256 random bits). Publish credential0600 as those
64 bytes plus LF, cache token in memory, and never reload it per request.
A safe stale credential from an eligible prior clean owner is replaced, not reused.
A malformed/unsafe credential file fails bootstrap; do not expose its contents.

No TTL, live rotation, login, logout, cookie or refresh endpoint. Credential lives
only for this incarnation; every new eligible startup rotates. Before ownership
release, stop admission and invalidate memory credential/remove its own validated
credential file. Publication/removal errors are bootstrap_io_failed/teardown_incomplete,
not falsely successful cleanup. Do not delete another file after identity mismatch.
External operator edits do not rotate a running process token.

Local callers read this owner-private file directly. Wire transport is only one
Authorization field with exact value `Bearer ` followed by64 lowercase hex bytes.
Header name is case-insensitive; value has exact scheme/space/token syntax.
Reject missing/duplicate/malformed/non-ASCII/oversized values with401.
Compare well-formed bytes using secrets.compare_digest. Never accept tokens in
URLs, query, cookies, body, command arguments or environment variables.
All application responses have Cache-Control:no-store.401 adds WWW-Authenticate:Bearer.

## 4. Security gate and request validation order

Pure ASGI middleware wraps all syntactically accepted HTTP traffic before routing/body validation.
Malformed HTTP rejected by h11 before ASGI may return its fixed input-free400
text/plain response and close the connection, rather than an application JSON
envelope. This includes protocol-level missing/duplicate Host rejection; no
Profile/body receive or operation occurs. Raw ASGI tests still exercise the
application's duplicate-header rules. Transport diagnostics remain disabled.
For valid loopback transport, exact order:
1. Host: exactly one raw Host header; value must equal selected authority
   `127.0.0.1:<port>` or `[::1]:<port>`, decimal port without leading zeros.
   Missing/duplicate/whitespace/case tricks/localhost/DNS/trailing dot/userinfo/
   comma/unbracketed IPv6/mismatching port or family reject400 request/host_rejected.
   No redirects, suffix matching, proxy-derived authority or DNS lookup.
2. Origin/browser provenance: reject403 request/origin_rejected if ANY Origin
   header exists, including empty, null, same authority or duplicates. Also reject
   when any header name starts sec-fetch- (case-insensitive), even without Origin.
   No Origin and no Sec-Fetch headers is eligible, never sufficient authentication.
3. Authorization: enforce §3; reject401 request/authentication_required.
4. Reject nonempty ASGI query_string400 request/query_not_allowed; nothing in a
   URL authenticates. URL fragments never reach HTTP and are not accepted transport.
5. Reject any HTTP Upgrade header400 request/upgrade_rejected; validate exact
   path/method, media/body/fields, then service registration. Require raw_path
   to equal the literal route bytes and decoded path to match; percent-encoded
   aliases/absolute-form targets do not become additional routes.
6. Only the registered operation invokes Profile resolution and runtime admission.

Host/Origin/auth failures must never receive/read body, read Profile or create
run resources. Security applies to unknown routes, unsupported methods and framework
errors too. Invalid Host wins over Origin/auth/body; Origin wins over auth/body.
No CORS middleware or OPTIONS exception. FastAPI docs/redoc/openapi and slash
redirects disabled. Authenticated unknown path404, known path wrong method405.
HEAD/OPTIONS are not extra status routes. WebSocket upgrade is unsupported/rejected,
never grants a bypass or starts an operation.

Disable access logs and request/header/body/URL logging throughout supported
launcher/app and dependency log config. Uvicorn access/error/general loggers are
disabled with propagation disabled, including malformed-HTTP diagnostics before ASGI.
FastAPI native telemetry channels and environment auto-configuration are explicitly
disabled, so ambient providers cannot emit request diagnostics outside those loggers.
No debug tracebacks, validation input echo,
raw exception messages, Profile/journal source paths or credentials in responses/
supported logs. Normalized enum categories only; do not stringify underlying
exceptions. Same-UID malicious tooling or external packet/log collectors are not
a protection guarantee. Plain HTTP is allowed only under this local model; remote
binding/TLS/proxies require a future explicit design.

## 5. Exact HTTP surface

| Method/path | Input | Success |
|---|---|---|
| POST /v1/observation/attach | JSON object with profile_path and journal_path |200 StatusEnvelope |
| GET /v1/observation/status | No body/query |200 StatusEnvelope |
| POST /v1/observation/detach | No body/query |200 StatusEnvelope |

Attach body: maximum16384 actual bytes, read at most16385 before rejecting413
request/payload_too_large. Require one Content-Type:application/json (case-insensitive
media type, optional sole charset=utf-8 parameter); other media415
request/unsupported_media_type. Strict UTF-8 JSON, reject duplicates/NaN/infinity,
non-object, unknown/missing fields and coerced types422 request/invalid_request.
Each path is string with1..4096 UTF-8 bytes, absolute POSIX path, no NUL.
No stripping, expanding ~, environment substitution, discovery or existence probe
during input validation. Existing Profile resolution and journal create decide
filesystem validity after security/registration. An existing destination is never overwritten.
Status/detach require zero body bytes; nonzero body422 request/invalid_request.
No query parameters on any route. Response JSON is UTF-8, application/json.

StatusEnvelope has exactly `{"service_state":"ready"|"stopping","runtime":RuntimeStatusView}`.
The runtime projection is defined in [data-model.md](../data-model.md).
Every returned RuntimeStatus maps200, including failed, immediate disconnect or
clean terminal attach. HTTP200 confirms delivery of the completed call, not active
capture; clients inspect runtime.state, terminal_reason and issue/cleanup facts.
Do not invent run IDs before admission or connection IDs before committed provenance.

Errors have exactly `{"error":{"source":source,"code":code}}`, no detail/context/input:
-400/403/401: request gate categories above.
-400 request/upgrade_rejected;404 request/route_not_found;405 request/method_not_allowed.
-413/415/422: request categories above.
-422 profile/<existing ProfileFailureKind value>, including invalid/missing files.
-409 runtime/busy or runtime/cleanup_unconfirmed.
-422 runtime/invalid_request.
-500 runtime/wrong_execution_context (implementation defect; no rebinding).
-503 service/stopping or service/operation_capacity.
-500 service/internal_failure, including projection overflow or unexpected wrapper fault.
No raw cause, retry loop or additional failure decoder. Startup/preparation failures
returned by runtime are already StatusEnvelope200 with failed facts.
Errors do not change or claim rollback of admitted runtime work.
No mutation response is automatically replayed; detach is idempotent only as005 defines.

## 6. Request ownership/cancellation

After security/body checks, check service ready/capacity and atomically register
one service-owned task on the owning loop before yielding. Maximum eight pending
attach/detach tasks total. No work queue/retry/job API; each task invokes existing
attach_basic_observation or runtime.detach immediately when scheduled.
Capacity503 precedes Profile I/O; it is distinct from runtime busy409.

Keep a strong reference independent of handler lifetime. Handler awaits shield(task);
HTTP cancellation, http.disconnect or send failure stops delivery only, never cancels
the task/owner, requests stop or creates attach_cancelled intent. A disconnect may
be unobservable until after registration/send; do not claim wire-level exact ordering.
Observed cancellation/disconnect before registration submits nothing. Once registered,
even a task not yet inside runtime must settle. Lost-response callers can use status;
no operation identity/history/idempotency/replay or result-recovery API is added.

Completion consumes normalized result/exception, removes registry entry and releases
input/task references; no retained result list. Capture may remain active afterward.
Operation errors do not cancel sibling operations; no cancelling TaskGroup.
Ordinary explicit detach still requests005 stop, preserving races/cause/cleanup.
Tests/development cannot directly cancel service operation tasks as client behavior.

## 7. Startup/shutdown and failure ordering

Startup in the actual serving process:
1. Validate platform/config/context, private directories/files, acquire fixed guard.
2. Validate prior marker; publish unconfirmed marker durably.
3. Prepare selected bound socket (not accepting HTTP), publish fresh credential.
4. Enter async lifespan, construct one inactive runtime on the serving loop/thread.
5. Check the shutdown-request latch; only if unset publish ready/open mutation
   admission and permit server accepting requests. A latched stop enters joined
   cleanup without opening admission or reverting stopping to ready.
No startup auto-attach, Profile read, journal create or backend open.

Bootstrap owner/lock lives around the server including lifespan. Async lifespan owns
runtime plus operation registry; listener/token/marker cleanup completes before guard release.
Supported launcher coalesces repeated SIGINT/SIGTERM into one shutdown request, never
sets force_exit or cancels lifecycle work. The first request latches throughout
bootstrap/lifespan startup. Close service mutation admission immediately on that
request, before server HTTP-task draining; never reopen after the latch.
No finite graceful lifecycle timeout.

Shutdown:
1. Publish stopping and reject new mutations503; status on already served connections
   may still project inspectable draining facts. Stop accepting new connections.
2. Join all registered operations, including those not yet entered runtime. Never
   detach first: inactive detach could otherwise miss a later queued attach.
3. Call runtime.detach and await its settlement cancellation-resistently. Preserve
   actual primary/cleanup/trigger/certainty. No extra direct backend/journal close.
4. Only if owner_settled AND physical_release_confirmed AND recorder_close_confirmed
   may service cleanup be confirmed. Runtime failed state with confirmed cleanup is allowed;
   uncertain cleanup is teardown_incomplete, marker stays false, no retry/reset.
5. Invalidate/remove credential, close listener and verify bootstrap cleanup.
6. If all cleanup confirmed, atomically write true marker; otherwise retain false
   and report normalized teardown_incomplete. True is attempted only after all
   resources are confirmed closed. Replacement followed by fsync failure may
   leave true visible: report teardown_incomplete/publication failure without
   claiming rollback or durable success. Such true still reflects actual confirmed
   cleanup; do not invent an uncertain physical fact. Release lock after joined work;
   settled but uncertain cleanup exits unsuccessfully, and the retained marker blocks restart.

Hung external work keeps shutdown pending, guard held and false marker; repeated
cooperative cancellation cannot release early. SIGKILL/process death is outside
cooperative guarantees and leaves conservative stale state. No forced-abandon switch.

Partial startup unwinds acquired listener/token/runtime in reverse order. If runtime
exists, close admission/join any tasks/detach before token/socket cleanup. Earlier failures
do not skip later cleanup. After resources are confirmed absent/closed, true marker may
be written if this invocation wrote false. A failure before writing false must never
rewrite a pre-existing stale marker. Token/socket errors remain explicit and do
not authorize true publication. Marker errors follow the replacement/fsync rule
above; failed false publication precedes all runtime/run resources and may leave
conservative blocking state. Failed publication is never claimed to roll back.
Do not unlink the lock inode or retain public task/resource handles.

## 8. Compatibility and exclusions

Basic/SQLite construction stays in existing Core adapter edge; FastAPI models,
bootstrap, process signals, OS files and HTTP mapping stay in apps/service.
Shared Core uses normalized capabilities/provenance without backend identity checks.
Feature003 schema-v1,004 Profile-v1,005 lifecycle/cleanup are unchanged.
Profile/session association stays in memory; fresh destination/session per attach,
kept failed/cancelled journals, one reader, no automatic reconnect remain invariant.

No evidence retrieval/streaming, CLI, Monitor/follow, TX/Interact/console/Control,
reconnect, release/reacquire/handoff, session catalogue/naming/sealing,
Profile discovery/defaults, Enhanced production support, MCP/AI or hardware acceptance.
