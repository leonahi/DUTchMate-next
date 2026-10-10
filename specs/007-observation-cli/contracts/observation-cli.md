# Contract: Observation CLI

Core and [feature006's contract](../../006-local-observation-service/contracts/local-observation-service.md)
govern execution and HTTP. This document defines client delivery only. No Core,
Profile, journal, backend, authentication-policy or ownership behavior is added.

## 1. Supported command surface

Installable package dutchmate-cli, console script dutchmate, Typer mandatory:
```text
dutchmate [--host HOST] --port PORT status
dutchmate [--host HOST] --port PORT attach --profile PATH --journal PATH
dutchmate [--host HOST] --port PORT detach
dutchmate --help
dutchmate status --help
dutchmate attach --help
dutchmate detach --help
```

Only these three root commands; no observation subgroup, positional file arguments,
short aliases, service command, --url, --token, --credential, --timeout, --json,
--version or completion-install/show options. Global --host/--port precede the
command. Standard Typer --option=value syntax is supported. Repeated valued options
use the final occurrence as the pinned framework does; earlier values are never
contacted as fallbacks. Duplicate command tokens/unknown extra arguments reject.

Root --host is exactly127.0.0.1(default) or::1; no whitespace normalization,
localhost, DNS name, IPv4-mapped IPv6, wildcard or remote address. --port is required
for actual commands, integer1..65535, normalized to decimal for Host. No default
port or target environment/config file. Root parser may store optional port so
help works; command bodies enforce presence/range before any credential/network I/O.

Root no-command invocation (including no arguments) and supported help exit0,
print static help to stdout and nothing to stderr. No passwd/platform/credential/
network/resource work. Callback stores options only; subcommand help can run after
the callback. Malformed parser input emits fixed usage failure, exit2, no supplied
argument/option/value/usage interpolation or suggestions. Never call exception.show,
str(exception) or framework pretty traceback/locals rendering.

Actual-command initial platform: Linux/macOS POSIX with required no-follow/
descriptor primitives; unsupported platform exits3 before account/credential/network.
Help/import remain resource-free on unsupported platforms. No platform/hardware
acceptance is implied by mock/metadata tests.

## 2. Explicit Profile/journal arguments

Attach requires both --profile and --journal as strings. Lexical validation only:
each absolute POSIX,1..4096 UTF-8 bytes, no NUL, exactly006's wire bounds. No strip,
~ or environment expansion, resolve(), exists(), stat(), reads, directory creation,
Profile defaults/discovery or journal freshness/recovery checks. Shell expansion
before invocation is outside CLI. Symlink/path validity and existing destination
are decided by the service after its gate/admission.

Missing/lexically invalid inputs exit2 before credential/network work. Map to
exact JSON fields profile_path/journal_path, with no other fields. Lexical wire
validation does not interpret Profile contents/policy or claim a fresh session.
No client JSON-body/template-file input.

## 3. Read existing credential only

Fixed location: <effective-UID passwd home>/.local/state/dutchmate/service/credential.
Ignore HOME/XDG and all credential/token/path overrides; no file fallback.

Lookup occurs only after valid actual-command arguments/platform. Open each ancestor
descriptor-relative with O_DIRECTORY/O_NOFOLLOW/O_CLOEXEC; open credential read-only
with O_NOFOLLOW/O_CLOEXEC/O_NONBLOCK. Reject symlink traversal. Final fstat must show
regular file, effective UID, mode exactly0600 and nlink1. Bounded read: at most66
bytes (65 expected + one detection byte); require exactly64 lowercase ASCII hex
characters plus LF, discard LF for header. Missing paths/read I/O fail
credential_unavailable; unsafe types/links/modes/owner/content fail unsafe_credential.
No automatic chmod/mkdir/creation/publication/removal or contents/path diagnostics.
No-follow ELOOP/ENOTDIR and observed unsafe file/content facts map unsafe_credential;
other account lookup/open/read/descriptor I/O errors map credential_unavailable.
Close acquired descriptors on every result; no surviving credential handle.

This is client file-access hygiene, not duplicated PrivateBootstrap: do not enforce
service startup/marker eligibility, create or acquire owner.lock, read owner.json,
test PID liveness, repair directories, generate/compare/rotate tokens, or attest
service ownership. Server bootstrap/authentication remains authoritative.
Read once per invocation, keep only for its request, release references afterward.
A changed/stale token or401 never rereads/refreshed/replayed automatically.
Same-UID malicious tools/externally configured collectors are not added guarantees.

## 4. One concrete HTTP request

Target one already-running listener. URL is constructed internally:
http://127.0.0.1:<port> or http://[::1]:<port>, followed by one literal006 path.
No arbitrary URL, userinfo, path prefix, query, fragment, cookies, proxy mounts,
environment trust, redirects, alternate port/family, discovery or service autostart.

| Command | Request |
|---|---|
| status | GET /v1/observation/status, no body |
| attach | POST /v1/observation/attach, exact JSON from §2 |
| detach | POST /v1/observation/detach, no body |

Exactly one Host with selected numeric authority including port, even port80;
IPv6 brackets required. One Authorization:Bearer <cached token> with exact006
syntax. Accept:application/json, Accept-Encoding:identity; attach Content-Type:
application/json. No Origin/Sec-Fetch/Upgrade or token in another transport.
At most one operation request per invocation; no preliminary status/probe/HEAD,
automatic authentication refresh, redirect, transport retry or reconnect.

A fresh concrete HTTP client uses HTTP/1 only, one connection, zero retained
keepalive connections, retries0, trust_env=False and follow_redirects=False on all
relevant HTTPX client/transport configuration. No global client, plugins/auth
callbacks/cookie state/trace hooks or client operation queue.

## 5. Finite waits and bounded responses

Fixed overall monotonic10.0-second HTTP waiting budget begins immediately before
the first request attempt and covers connect/send/header/body waiting. Finite phase
limits: connect5.0s, read5.0s, write5.0s, pool5.0s; outer deadline takes precedence.
Use an absolute async deadline; repeated progressing chunks do not reset it.
No user override, retry or synchronous HTTP worker left running after interruption.
This is cooperative client HTTP waiting, not a hard real-time bound on passwd/
filesystem syscalls, synchronous decoding, terminal output or client socket cleanup.
It never becomes a service/Core lifecycle timeout or forced abandonment.

Stream raw body, reject unsupported encoding before decompression: Content-Encoding
absent or one identity value only. Retain at most1048577 bytes; >1048576 rejects
invalid_response and closes client response. Slice chunks to remaining bound+1
rather than accumulating whole over-limit chunks. HTTPX/OS may already buffer
transport chunks beyond that; do not promise exact socket-read byte counts.
Declared Content-Length >1048576 can reject early but never replaces actual cap.
No unbounded .read/.aread/.text/.json or HTTP response buffering.

Require exactly one Content-Type:application/json (case-insensitive media, optional
sole charset=utf-8); strict UTF-8 JSON, no duplicate object keys or NaN/infinity.
Malformed protocol, truncation, unsupported media/encoding, invalid envelopes,
unrecognized status/error category or body/output overflow =>invalid_response,
exit5. Native006 h11 fixed text/plain400 maps to this client protocol failure,
not an invented application rejection. Redirects are never followed.

Validate wire structure only against006 data-model/contract: closed top-level/
nested keys and JSON primitive types, documented string enums and arrays/nulls.
Do not construct Core values or reproduce Profile/lifecycle/capability/ownership
cross-field predicates. In particular do not derive attach_admissible, synthesize
primary_failure_kind, collapse close_failed/trigger/certainty, translate timestamp
domains or decode opaque backend provenance. Use the documented generic envelope.
Keep response JSON as delivery data, never backend resources or object dumps.

## 6. Output and exit contracts

After complete validation, emit exactly one compact UTF-8 JSON record plus LF.
Re-encode with non-ASCII preserved, no nonfinite numbers, no text/line summary,
color, progress/spinner/banner or extra stdout. Check encoded bound1048576 before
writing (LF excluded); no partial intentional report on validation/overflow.
Terminal write failure can be physically partial; it is reported as output_failed
if stderr remains writable and never causes a service cleanup request.

| Result | stdout | stderr | Exit |
|---|---|---|---|
| Help/no command | Static text help | Empty |0|
| Valid HTTP200 | Exact006 StatusEnvelope in JSON meaning | Empty |0|
| Valid documented non200 ErrorEnvelope | Empty | Same006 ErrorEnvelope |4|
| Client-local failure | Empty, except unavoidable interrupted/failed terminal write | ClientErrorEnvelope below | Per table below |

**Exit0 means a completed validated report exchange, not active capture, absence of
runtime failure, successful detach or confirmed cleanup.** This applies uniformly
to attach/status/detach, including HTTP200 with failed/immediately terminal state.
Users inspect actual runtime facts. No success/failed-runtime relabeling or local
reconstruction of005 outcomes. Retain every reported Profile/session/capability/
provenance/issue/cleanup/terminal/nullable fact. No hardware-support claim from fixture data.

Remote errors accept only documented006 HTTP/source/code pairs, referring to
existing004 ProfileFailureKind/005 RuntimeRejectedKind values as wire categories.
No Core imports or local policy decision. Unrecognized arbitrary diagnostics are
discarded and converted to invalid_response, never echoed.

ClientErrorEnvelope has exactly:
```json
{"error":{"source":"cli","code":"<fixed code>"},"request_outcome":"not_submitted|unknown|report_received"}
```

| Fixed local code | Exit |
|---|---|
| invalid_arguments |2|
| unsupported_platform, credential_unavailable, unsafe_credential |3|
| request_timeout, transport_failed, invalid_response |5|
| interrupted |130|
| output_failed, internal_failure |1|

Request_outcome describes client delivery only: not_submitted before request
attempt, unknown from just before attempting HTTP until a valid report is received,
report_received after a validated StatusEnvelope/ErrorEnvelope is received, even
if terminal output then fails/interruption occurs. Conservatively use unknown
when unable to establish receipt; never infer service admission from a client
socket event. No operation ID, replay result, job state or hardware outcome.

All caught diagnostics are these fixed categories: no paths, credential, supplied
arguments, request/response body/headers, exception text/cause/locals or traceback.
Disable HTTPX/httpcore debug/request logs and propagation. Typer completion/suggestions,
Rich traceback and locals display disabled; use public pinned exception APIs.
Client-local errors must not accidentally call Typer's value-echoing diagnostics.
Output failure with unusable stderr may provide only the exit status; no repeated
exception-print fallback. Help explains exit0 and request-loss semantics.

## 7. Ctrl-C, request loss and ownership honesty

First Ctrl-C ends client waiting, closes client delivery and exits130 with
interrupted/appropriate request_outcome where stderr is writable. Handle both
outer KeyboardInterrupt and Typer's public returned/raised interrupt paths;
plain default 'Aborted!' or tracebacks are not the output contract.
Repeated Ctrl-C grants no service signal, cleanup, retry or hardware action.
No assertion of service cancellation or rollback from a client interruption.

For attempted mutations, timeout, lost/malformed response or interruption can leave
the outcome unknown. Registered006 tasks continue even if not yet inside005.
Never send detach, signal the service, reread credentials/retry or auto-poll status.
Explicit later status observes current facts; it does not recover the lost response,
identify which caller caused a run, or prove mutation attribution/completion.
Successful client exit never stops capture; only explicit service/Core semantics do.

## 8. Composition and compatibility

Typer/context/HTTPX/filesystem/terminal handling remain solely in apps/cli.
Production dutchmate_cli imports neither dutchmate_core nor dutchmate_service,
serial/sqlite/HTTP-server/MCP/subprocess modules. Service/Core never import CLI. Product
CLI/Core/service separation is transitive; external import bans are direct-only
as documented in the plan, permitting required framework internals.
Test harness may import completed service/Core fixtures to prove the HTTP boundary,
with actual authentication and isolated accounts/ports/fake transports.
No changes to006 routes/auth/registry/launcher,003 schema-v1,004 Profile-v1 or005
lifecycle. No duplicated RX path, policy checks, timing/matching or backend identity cases.

Deferred: service startup/shutdown/daemon management, retrieval/streaming/formatting
modes, Monitor/follow, TX/Interact/console/Control, reconnect, release/reacquire/
handoff/external programs, annotations, session catalogue/naming/sealing/resumption,
Profile discovery/defaults, Enhanced production behavior, MCP/AI and hardware acceptance.
