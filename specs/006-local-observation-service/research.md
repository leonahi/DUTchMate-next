# Research: Local Observation Service

**Date**: 2026-10-07
**Baseline**: ed11051 (feature005 code2824c0d plus hash reconciliation).
Method: governing contracts/source, two bounded read-only planning research agents,
and primary FastAPI/Python/ASGI/Uvicorn documentation. No implementation or hardware.

## Persistent runtime and delivery

**Decision**: Async lifespan constructs one runtime; async handlers call it on its
owning loop/thread. No module-global owner or synchronous lifecycle endpoints.
**Rationale**: Feature005 binds at construction. FastAPI recommends lifespan for
shared startup/cleanup; synchronous path operations use a threadpool.
**Alternatives**: Per-request runtime/reader and threadpool dispatch violate ownership.
Sources: [FastAPI lifespan](https://fastapi.tiangolo.com/advanced/events/),
[FastAPI concurrency](https://fastapi.tiangolo.com/async/).

## Response cancellation versus lifecycle cancellation

**Decision**: Eight-entry maximum registry strongly owns mutation tasks; handlers
shield their delivery wait. Disconnect/cancel affects delivery only. Join registered
operations before final detach during shutdown, including not-yet-invoked attach.
**Rationale**: Cancelling runtime.attach would intentionally stop its run under005.
Shield does not itself retain tasks. ASGI disconnect notification/send failure can race.
**Alternatives**: Direct handler ownership, response BackgroundTasks, cancelling
TaskGroup, generic durable jobs/replay history are unnecessary or unsafe.
Sources: [Python shielding](https://docs.python.org/3/library/asyncio-task.html#shielding-from-cancellation),
[ASGI disconnect](https://asgi.readthedocs.io/en/latest/specs/www.html#disconnect-receive-event).

## Controlled local launcher

**Decision**: One worker/process, no reload/proxy trust, selected numeric loopback
family only; ::1 requires IPV6_V6ONLY. Explicit port; no DNS/fallback. Supported
launcher coalesces repeated shutdown signals and sets unbounded graceful draining.
**Rationale**: Uvicorn's source drains HTTP tasks before lifespan; its repeated
SIGINT force-exit path can skip cleanup, so do not use that path for cooperative stop.
The first shutdown request latches during bootstrap/startup, preventing later
ready/admission publication. **Alternatives**: Bare framework launch, multiprocess
supervision and daemon manager deferred.
Sources: [Uvicorn settings](https://uvicorn.dev/settings/),
[Uvicorn server source](https://raw.githubusercontent.com/Kludex/uvicorn/master/uvicorn/server.py).
Implementation must verify/pin its actual resolved dependency, not assume master is its API.

The h11 transport can reject malformed HTTP/Host before ASGI with fixed400 plain
text rather than the application's JSON error. Keep that distinction explicit;
disable pre-ASGI diagnostics, validate literal raw paths, and reject Upgrade.
Source: [Uvicorn h11 source](https://raw.githubusercontent.com/Kludex/uvicorn/master/uvicorn/protocols/http/h11_impl.py).

## Process guard and stale state

**Decision**: Initial Linux/macOS support with fixed per-UID flock and stable0600
lock inode. OS lock rejects duplicates on any port. Singleton bounded cleanliness
marker is false for the entire incarnation; only joined confirmed teardown sets true.
**Rationale**: PID/age and available lock cannot attest physical cleanup after death.
Even an idle crash can block restart: conservative false positives are accepted.
**Alternatives**: PID-only files, lock-inode replacement, automatic stale takeover
rejected. Per-run dirty tracking adds coordination with autonomous termination and
persistence writes; deferred. Windows permissions/locking require a separate supported
implementation; reject explicitly instead of claiming portability.
Sources: [Python fcntl](https://docs.python.org/3/library/fcntl.html),
[Linux flock](https://man7.org/linux/man-pages/man2/flock.2.html),
[Apple flock](https://developer.apple.com/library/archive/documentation/System/Conceptual/ManPages_iPhoneOS/man2/flock.2.html).

## Credential and security gate

**Decision**: Process-lifetime256-bit token in owned0700/0600 bootstrap, safely
published/rotated; single exact Bearer header and constant-time comparison.
Numeric Host exact allowlist; every present Origin/Sec-Fetch header rejected,
absent Origin still authenticated. Security before body/routes/Profile/resources.
Disable input-bearing logs and automatic docs/redirect endpoints.
**Rationale**: Core16.4 requires local caller and browser-origin defenses. Fixed
per-user location avoids alternate-port/state-root bypass by cooperating processes.
**Alternatives**: Cookies/OAuth/JWT, URL credentials, localhost/wildcards/proxy trust,
CORS-only and auth bypass for tests add risk or scope without current value.
Sources: [Python secrets](https://docs.python.org/3/library/secrets.html),
[Python file operations](https://docs.python.org/3/library/os.html).
Filesystem safety is a project design using descriptor checks/atomic publication;
no claim of protection from a malicious process already running as the same UID.

Directory validation separates UID-owned account/private descendants from trusted
root/UID-owned filesystem ancestors; root-owned sticky temporary ancestors permit
isolated test account homes. A true marker replacement can precede failed fsync:
report unsuccessful publication, not rollback. True is attempted only after all
resource cleanup facts are confirmed, so a visible true remains physically honest.

## Wire/status and compatibility

**Decision**: Three exact endpoints;200 for returned runtime status,409 for rejected
busy/uncertain admission,422 for request/Profile faults,500 for context/internal defects.
Generic closed status projection; no source paths/raw exceptions. Existing Basic edge
resolves Profile before authoritative runtime admission; security precedes that edge.
**Alternatives**: Reinterpreting failure kinds, exposing handles, adding retrieval,
schema metadata, new lifecycle timeouts, remote deployment and client workflow logic deferred.

All product/contract decisions for this slice are settled. Documents specify intended
future behavior, not tested software. No Core rule or003–005 contract revision is required.

## T002 actual dependency verification (2026-10-07)

uv added the service workspace dependency, FastAPI0.142.2/Uvicorn0.54.0 and
root test-only httpx0.28.1, then constrained their verified minor lines. uv.lock
records Starlette1.7.0/Pydantic2.13.5 and the needed transitives. All22 existing
locked package versions are unchanged;16 packages added including the service.
Actual installed Python3.14.3 imports and signatures verify FastAPI lifespan,
Uvicorn workers/reload/proxy/access-log/graceful-timeout/lifespan/h11 settings,
Server.handle_exit and HTTPX ASGITransport. MIT/BSD-3-Clause metadata verified.
Installed service/Core import from /private/tmp through uv without a cwd assumption.
Initial sandbox DNS failure was resolved by the authorized dependency-network
retry. No HTTP app/listener/runtime was constructed in this verification.

## T022 actual lifecycle integration verification (2026-10-07)

Inspected installed Uvicorn0.54.0 Config.load, Server.serve/_serve/startup/shutdown,
capture_signals and LifespanOn, plus Python3.14 Runner's SIGINT registration.
Retain actual protocol/startup/drain machinery. A checked LifespanOn stops between
ASGI startup and TCP acceptance when the private stop latch is set. Supported
launcher owns handlers before directory/guard preparation through resource release;
the server's capture_signals path does not install/replay framework handlers or
set force_exit. Config uses one worker, asyncio/h11/lifespan-on/no-WebSocket,
reload/proxy/access logs disabled and graceful timeoutNone. All three Uvicorn
input loggers disabled with propagationFalse; no dependency log config installed.

Native isolated IPv4/IPv6-only sockets, unavailable-family/port no-fallback,
different-port exclusion, h11 privacy and twelve startup signal cases verified.
Two dormant RED-test helper defects were exposed: os.mkdir did not accept mode=
and the signal mock did not reflect installed handlers through getsignal, allowing
Runner to substitute its cancellation handler. Corrected with focused RED/GREEN
regressions; production signal behavior agrees with the native subprocess cases.
T023 joins/certainty/positive cleanup marker remain unimplemented. Full gate was
attempted but a hardware-blocked test-runner watchdog stopped its pending active-
run drain; no full service/process shutdown or physical-hardware acceptance.

## T023 joined teardown verification (2026-10-07)

App cleanup closes admission, joins the finite registered-task snapshot, then
calls runtime.detach on the owning loop. Strongly owned shielded lifecycle tasks
absorb repeated waiter cancellation; no task queue/history/lifecycle timeout.
Final RuntimeStatus is captured on that loop and handed to bootstrap as an
immutable snapshot. Confirm all three runtime cleanup facts plus credential/
socket cleanup before true publication; state=failed alone is not uncertainty.
Actual Uvicorn connection/task drain precedes lifespan teardown; startup-stop
shutdown initializes an empty listener set because Uvicorn normally creates it
only after lifespan succeeds. Framework drain failure blocks clean confirmation.

Bootstrap records successful false publication explicitly, allowing cleanup after
a later partial-startup error without touching a pre-existing rejected marker.
Failed credential invalidation is sticky through release, preventing a hidden
second unlink attempt. Replacement/fsync failure retains the existing honest
publication model; no rollback claim, lifecycle timeout, cleanup retry or takeover.
All31 T021/38 process cases and fresh full1475 tests GREEN; three focused
regressions RED → GREEN. Native tests remain macOS software/loopback only;
T024's extra injected failure exercise and final acceptance remain pending.

## T024 actual OS publication fault exercise (2026-10-07)

Nine service-pipeline cases inject file fsync, replacement and containing-directory
fsync failures for false marker, credential and true marker publication. Actual
private OS files/atomic replacement/bootstrap are retained; only the failing
operation is injected. The true-marker cases run a real temporary SQLite journal
and existing fake Basic through attach/shutdown, asserting recorder/backend close,
credential removal/socket closure and held guard before true publication.
After successful true replacement and failed directory fsync, true may be observed
but the service raises teardown_incomplete; no completed confirmation is recorded,
no rollback attempted and no durable-success guarantee claimed. False publication
after-replace failure blocks restart; completed partial-startup cleanup can confirm
actual absence/closure without creating a runtime. No production defect found.
Suppressed-error mutation causes three intended failures; restored nine cases,
224 failure/process cases and full1484 GREEN. No hardware acceptance implied.

## T026 review correction and dependency cleanup (2026-10-07)

Installed FastAPI0.142.2's public TelemetryConfig defaults enable native tracing,
metrics, exception logs and environment setup when providers/exporters exist.
Uvicorn logger suppression does not suppress the independent OTel logger API.
A real ambient-provider-slot test captured a raw private delivery exception before
the correction; explicit tracing/metrics/logs/operation_spans/auto_configure=False
prevents emission. No exporter/SDK dependency added and no Core rule changed;
this implements the existing FR-026 prohibition through the framework boundary.

All tests use raw ASGI or loopback sockets; none use httpx. Removed historical
test-only httpx/httpcore/certifi with uv remove --dev httpx --offline. FastAPI/
Uvicorn/transitives and all22 baseline versions unchanged; bans against client
libraries remain enforced. Full1485 GREEN, five import contracts intact; wheel/
sdist built outside the repository and installed imports work from /private/tmp.
No new product decision, hardware action or broader scope added. T027 pending.
