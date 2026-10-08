# Quickstart Validation: Local Observation Service

T001–T005 are complete:349 baseline tests GREEN;87 bootstrap RED then GREEN,
two focused correction cases RED → GREEN;89 bootstrap/1013 full-suite GREEN.
T008 makes all original259 T006/T007 cases GREEN after a fresh259 RED baseline.
Six typed-mapping regressions and two replay checks are also GREEN;267 HTTP/
projection cases and1280 full cases pass with zero failures/errors/skips.
Ruff/mypy47 files/five import contracts (40 files/104 dependencies)/diff checks pass.
T009 adds controlled async lifespan/inactive status app composition:23 RED → GREEN
cases;1303 full-suite passes, zero failures/errors/skips. Ruff/mypy48 files/five
import contracts (43 files/112 dependencies)/diff checks pass. No attach/detach
wiring, operation registry or controlled listener yet.
T010 revalidates all US1 commands below and app/http logging/error paths without
code changes:179 HTTP,1013 Core/bootstrap and290 combined US1 cases pass; full
gate1303 passes with zero failures/errors/skips. No demonstrated security/projection
defect. Uvicorn logger disabling and pre-ASGI diagnostics remain T020/T022 work;
US1 is an inactive ASGI checkpoint, not full service/process acceptance.
T011 adds44 HTTP lifecycle/mapping cases:33 expected missing-route failures,
11 validation passes. Earlier1303 remain GREEN; full pytest33 expected failures/
1314 passes, zero errors/skips. No route/registry implementation yet.
T012 adds21 lifetime/registry cases:15 expected missing-route failures and six
pre-registration passes. Full pytest48 expected failures/1320 passes, zero errors/
skips; earlier1303 independently GREEN. No production change; normal route wiring
and operation ownership remain T013/T014 respectively.
T013 adds normal POST attach/detach wiring: all44 T011 cases/223 HTTP cases GREEN.
The failed-open expectation now preserves feature-005's unconfirmed physical release;
historical absent-route checks migrate to authentication-before-preparation.
Full pytest12 expected T014 ownership failures/1356 passes, zero errors/skips.
Ruff/mypy49 files/five import contracts (43 files/113 dependencies)/diff clean.
No operation registry/shielding, listener or joined service shutdown yet.
T014 adds bounded owned mutations and shielded delivery: original21 lifetime
cases GREEN after12 RED, plus two pending-disconnect cases mutation-checked RED → GREEN.
Full1370 passes, zero failures/errors/skips; Ruff/mypy49 files/five import contracts
(43 files/114 dependencies)/diff clean. No listener or joined service shutdown yet.
T015 adds24 focused failure/lifetime regressions, all GREEN. Process-local
projection mutations verify five intended failures with no production file changes.
Full1394 passes, zero failures/errors/skips; static/import/diff checks clean.
No production defect found; T016 remains unexecuted.
T016 confirms no correction is warranted by T015:24 focused cases and fresh full1394
passes, zero failures/errors/skips. All54 source/config hashes unchanged; static/
import/diff gate clean. T017 idle/ambient/backend-neutral integration remains unexecuted.
T017 adds six binary/idle/readback/neutrality scenarios, all GREEN: actual Basic
composition plus identical assertions on existing Basic/Enhanced-shaped fixtures.
Readback is test-only bounded journal reopening after terminal cleanup, not an HTTP
retrieval API. Full1400 passes, zero failures/errors/skips; static/import/diff clean.
No production or existing fixture change; no actual listener/hardware acceptance.
T018's scoped consumer/test review finds no correction needed. Owning-loop calls,
single physical reader, public snapshot projection and003–005 compatibility remain
intact. Six context/53 runtime/full1400 cases GREEN; static/import/diff clean.
All54 source/config hashes unchanged. T019's US2 checkpoint remains separately authorized.
T019 runs all unique US2 pytest commands below and completed005 focus:44/223/53/
244/24/six and349 cases GREEN, zero failures/errors/skips. Static/import/scope and
fresh full1400 gate clean; all54 source/config hashes unchanged. US2 software
checkpoint verified; actual process/listener/shutdown and full service acceptance pending.
T020 adds35 process cases:34 expected missing-server RED failures and one
subprocess safety probe GREEN. Earlier1400 independently GREEN; full34 failures/
1401 passes, zero errors/skips; static/import/diff checks clean. No production
implementation or actual listener/h11/IPv6 acceptance. The helper installs its own
passwd-home and physical/real-bootstrap tripwires, rather than relying on inherited
pytest monkeypatches. T021 shutdown tests were unexecuted at that checkpoint.
T021 adds31 RED cases in test_service_runtime.py: eight app joins/detach gaps and
23 missing-launcher cases. Earlier1347 base/53 runtime cases independently GREEN;
full65 expected failures/1401 passes, zero errors/skips. Static/import/diff checks
clean. App tests use real guarded lifespan/Runtime/fake Basic/temporary SQLite;
launcher fault tests preserve actual bootstrap/app/Core/Uvicorn and substitute only
network operations. No production change, actual listener or hardware acceptance.
T022 remains unexecuted. Run just the new RED matrix with:
```bash
rtk proxy uv run pytest apps/service/tests/test_service_runtime.py -k test_t021 --tb=short
```
T022 now implements controlled listener/signals; process suite37 passes with one
expected T023 clean-marker failure. Base1124 and delivery279 cases pass; eight
direct app shutdown cases remain RED. Full gate attempted but blocked at T021's
active-run drain; the isolated test-tool watchdog exited124, without a completed
summary/JUnit result. No production timeout/abandonment or full-pass claim.
Until T023, known unsettled work holds the loop/guard; settled interim shutdown
reports teardown_incomplete and retains the false marker. Do not treat this as
complete service acceptance. Use the separate existing selections for fresh GREEN
evidence; the all-runtime/full commands can remain pending at joined-teardown cases.
At T023, ordered joins and confirmed bootstrap teardown are implemented. The
previous pending full gate now completes:1475 passes, zero failures/errors/skips.
All31 T021 and38 process cases GREEN; bootstrap90/runtime87 cases in the full run.
Draining status remains inspectable with mutations503; actual runtime certainty
and successful credential/socket cleanup gate true publication. Failed/uncertain
cleanup remains false and blocks restart; no retry/forced abandonment. Three
focused regressions verify invalidation, draining status and HTTP-drain failure.
Static/import/diff clean. T024's additional failure exercise remains unexecuted;
final service/physical-hardware acceptance is not claimed.
T024's failure exercise now passes224 bootstrap/runtime/process cases. Nine new
OS-level cases cover false marker/credential/true marker publication at file fsync,
replacement and directory fsync. Visible true after replacement/fsync failure is
accepted only after real cleanup facts and still returns teardown_incomplete;
never claim successful durable publication or rollback. No production correction.
Full1484 passes, zero failures/errors/skips; static/import/diff clean. Native
loopback tests remain macOS software evidence only; T025/final acceptance pending.
T025 verifies both US3 commands (38/186 GREEN), completed Core/bootstrap regressions
(1014 GREEN), complete005 focus (349 GREEN) and Core lifecycle focus (244 GREEN).
Every command has zero failures/errors/skips; counts overlap and are not added.
Static/import/scope/diff and fresh full1484 gate GREEN. All56 source/config hashes
unchanged; no correction. Native IPv6 runs on macOS; other-platform/hardware
acceptance remains unexecuted. T026 full feature review remains pending.
T026 completes the full feature review and corrects ambient FastAPI telemetry
emitting raw request exceptions, with RED → GREEN coverage. Explicit telemetry
channels/environment setup disabled; unused httpx/httpcore/certifi removed via uv.
Full1485 GREEN, zero failures/errors/skips; static/import/diff/build clean.
Core/001–005 and22 baseline versions unchanged; T027 remains separately authorized.
T027 runs all14 unique focused pytest commands below; duplicate runtime commands
are covered by one fresh invocation. Every command GREEN, zero failures/errors/
skips, covering1485 distinct cases across overlapping selections. Scope searches,
targeted Ruff/mypy51 files/five import contracts/diff clean. No source/test/config
change; all56 hashes unchanged. Native macOS IPv6 exercised, no physical-hardware
acceptance. The final full-gate block was not run in T027 and remains T030.
T028 reconciles current status/history, scope, committed baseline and limits using
documentation-only checks. Feature006 remained uncommitted with T029–T030 and final
validation/acceptance pending at that checkpoint. No software command or Graphify update rerun.
T029 now meets the actual structural trigger and completes one code-only incremental
Graphify0.9.48 update:2891 nodes/8348 edges/123 communities, zero LLM tokens.
Generated output/backups remain ignored and source/test/config unchanged. T030's
fresh final full gate was unexecuted at that checkpoint; feature006 uncommitted.
T030 now completes that fresh full gate:1485 passes, zero failures/errors/skips;
Ruff/mypy51 files/five import contracts/diff checks clean. Initial sandbox socket
denials resolved by permitted guarded rerun; no source/test/config correction.
Final intended diff review found no new defect. All30 tasks complete; feature006
software-complete, uncommitted and ready for separately authorized final review
and commit. No commit, push, next-slice work or physical-hardware action.
Subsequent explicitly authorized final pre-commit review/fresh gate passed with no
new defect; full intended set committed as b4c5730b2a5e593c10c06ad9e8f24c39e06f794b
(Implement local observation service). Actual baseline reconciled afterward with
documentation-only changes. Native validation macOS only; Linux/Windows native and
physical-hardware acceptance unexecuted. Nothing pushed; no next slice started.
Later scenario commands become runnable only after their listed tasks implement
the missing tests/HTTP behavior; no command here opens physical hardware. Contract examples
contain no real credential and never put credentials in URLs.

## Prerequisites and safety

Python3.14 uv workspace; completed001–005 baseline ed11051. T002 installed the bounded service dependencies through uv; T026 removed the unused test HTTP client. Initial platform Linux/macOS; test platform
skips are reported as skips, not acceptance. Isolate account-home/bootstrap and
use only existing fake serial/normalized fixtures plus temporary SQLite.
Service and Core test sentinels prohibit physical serial factories/enumeration.
HTTP tests use actual bootstrap/token/header validation with no bypass.
Raw ASGI requests alone do not start lifespan: tests manage async lifespan explicitly.

## First group T001–T005

T001 existing focused regressions, before dependency/production work:
```bash
rtk proxy uv run pytest core/tests/contract/test_acquisition_lifecycle.py core/tests/unit/test_runtime_model.py core/tests/contract/test_observation_runtime.py core/tests/contract/test_observation_composition.py core/tests/integration/test_observation_runtime.py --tb=short
```
Expected baseline349 cases, not a new feature006 result.

After T003/T004:
```bash
rtk proxy uv run pytest apps/service/tests/test_service_bootstrap.py --tb=short
rtk proxy uv run ruff check apps/service pyproject.toml
rtk proxy uv run mypy .
rtk proxy uv run lint-imports
```
Record bootstrap RED before implementation/GREEN afterward. No HTTP lifecycle
or backend resource work belongs to this first group.

## US1: security and closed status projection

Completed US1 GREEN selection (exclude the new T011 RED lifecycle cases explicitly):
```bash
rtk proxy uv run pytest apps/service/tests/test_service_http.py -k 'not t011' --tb=no
rtk proxy uv run pytest core/tests apps/service/tests/test_service_bootstrap.py --tb=short
```
At T010, the first command passed179 security/mapping/replay/composition cases and
the second passed1013. At T025, the second passes1014 (924 Core/90 bootstrap).
The T010 combined US1 selection below passed290 cases including111 projection/
input tests. Before T008, the original259 cases were expected RED for absent http.py. T007 calls pure status_response and validate_request
helpers against real immutable Core values/raw body chunks, with no file/resource
work or test implementation of the renderer/validator. T009 drives the real app
with ASGI lifespan messages, an actual prepared private bootstrap and one real
runtime on its serving loop/thread. It verifies factory/startup ordering, singleton
ownership, foreign-loop/thread rejection and authenticated disabled paths. App
lifespan leaves bootstrap cleanup to its owner; no run can be attached yet. These
raw ASGI tests do not demonstrate an actual HTTP listener or h11 transport behavior,
which remain assigned to later tasks. No permissive auth substitute or DUT resource
preparation is used.


```bash
rtk proxy uv run pytest apps/service/tests/test_service_http.py apps/service/tests/test_service_projection.py -k 'not t011' --tb=short
```
Required: every raw security combination gives contract-ordered400/403/401 before
receive/body/Profile/preparation; absent Origin is allowed only with Host/token;
query rejection, strict body bounds, disabled docs/redirects, input-free errors,
constant-time comparison seam and private credential lifetime.
Use token read privately by test fixture; do not print/log it or show shell-expanded
Authorization commands in this guide. Unsupported routes/methods remain authenticated.

## US2: HTTP lifecycle, request independence and existing readback

T013 normal lifecycle/mapping GREEN checkpoint:
```bash
rtk proxy uv run pytest apps/service/tests/test_service_http.py -k t011 --tb=short
rtk proxy uv run pytest apps/service/tests/test_service_http.py --tb=short
```
First command now has44 passes after33 expected RED failures; second has223 HTTP
passes. T013 supplies normal route wiring and reconciles the historical T009 absence
checks as auth-before-body/preparation checks. No auth/security bypass was introduced.
The T011 fixture opts into only isolated real Profile/SQLite/Basic work with fake
serial, retains physical/discovery guards, and uses joined test-only runtime cleanup.
Uncertain fake cleanup retains the false owner marker. Normal request delivery stays
connected after its body. T012 now adds the request cancellation/registry RED cases.
Core test files include older tests also named T012;
do not use a global 'not t012' selector that silently omits those regressions.

T014 lifetime GREEN selection:
```bash
rtk proxy uv run pytest apps/service/tests/test_service_runtime.py --tb=short
```
At T014 this selection had23 passes:21 original T012 cases plus two pending-disconnect
regressions. At T019 the same file has53 passes, including later failure/integration
cases. Tests gate
Core invocation, journal startup/close and response publication; cancel only HTTP
delivery tasks. Weak-reference assertions cover strong pending ownership and collection of
completed tasks/results/errors; combined attach/detach capacity is eight with503
before Profile I/O. Normalized errors cannot cancel siblings; completed requests
do not become history/replay. T014's implementation satisfies those assertions;
pending cancellation submits nothing, while admitted work outlives delivery loss.
Owned tasks render bounded normalized responses before shielding; late errors never
become Python3.14 shield loop diagnostics. Disconnect observation uses a separate
delivery task; only that observer and the outer shield future are cancelled.
The operation itself is never cancelled. This does not establish launcher/shutdown
or complete service/hardware acceptance.

Later US2 integration selection (T015–T019):
```bash
rtk proxy uv run pytest apps/service/tests/test_service_runtime.py --tb=short
rtk proxy uv run pytest core/tests/contract/test_observation_runtime.py core/tests/contract/test_observation_composition.py core/tests/integration/test_observation_runtime.py --tb=short
```
At T017 the first command passes53 cases (23 lifetime,24 failure and six integration).
For just the new focused matrix:
```bash
rtk proxy uv run pytest apps/service/tests/test_service_runtime.py -k test_t015 --tb=short
```
Required: real preparation/constructor/open/initial-RX-final append/cleanup faults;
all independent reason/primary/cleanup/release facts; observed disconnect wins cause
even when final append and cleanup fail; no retry/reopen/reconnect; retained files/
known session IDs; no invented provenance before initial commit. HTTP cancellation
repeated during failing startup preserves the underlying failure and stop intent.
Fault injection uses temporary journals and the existing strict fake serial only;
no physical hardware or T016 production correction is authorized by these commands.

T017 focused integration selection:
```bash
rtk proxy uv run pytest apps/service/tests/test_service_runtime.py -k test_t017 --tb=short
```
Six cases must preserve exact binary/ambient bytes across idle clients and lost
attach delivery; one reader; final segment commit before recorder close; stable
run/session/Profile and repeat detach/status; and bounded two-record-page durable
readback after close. Existing normalized fixtures run the same attaching/busy/
active/explicit-detach/autonomous-disconnect assertions with their actual reported
timestamp domains, scoped loss and capabilities. Opaque schema37/scalar provenance
is supplied at the test composition edge only. Production Profile still selects
Basic exclusively; Enhanced-shaped coverage proves software neutrality only.

Use deterministic gates at registration, Profile/preparation/open/append/close;
cancel/disconnect delivery and confirm registered service operation settles.
A lost attach response must not trigger005 attach_cancelled or cancel its owner.
Competing attach preserves bounded Profile-read-only busy behavior; capacity
rejection creates no Profile read.200 failed status versus409 admission is explicit.
Capture exact ambient binary bytes between requests; final appends/Acquisition join
precede recorder close. Reopen temp journal in tests only for existing bounded readback.
That test assertion does not add HTTP evidence retrieval.
Same applicable assertions run on Basic/Enhanced-shaped fixtures with their actual
reported capabilities, timestamp domains, scoped loss and generic provenance.

## US3: duplicate process, listener and shutdown

```bash
rtk proxy uv run pytest apps/service/tests/test_service_process.py --tb=short
rtk proxy uv run pytest apps/service/tests/test_service_bootstrap.py apps/service/tests/test_service_runtime.py --tb=short
```
Isolated helper processes bind only test loopback sockets and touch temporary
bootstrap; no helper process opens DUT transports. Tests prove different-port
duplicates reject on the fixed guard, lock inode remains unchanged, stale false/
malformed marker rejects without token replacement or journal access.
Test default127.0.0.1, explicit::1/IPV6_V6ONLY, unavailable IPv6 with no fallback.
An unavailable host IPv6 case may skip the real socket exercise with a clear reason;
deterministic socket-failure/no-fallback tests still run.

Actual malformed h11 requests may reject before ASGI with fixed400 plain text;
verify no supplied-input logging/resources, not an invented JSON mapping.
Signals during bootstrap/socket/token/lifespan startup must latch and prevent
subsequent ready/admission publication. Shutdown while an accepted attach has not entered runtime must drain it before
detach. Repeated signals/cancellation never force_exit or cancel lifecycle work.
Hung adapter remains pending under a test-owned gate/watchdog, never a product timeout.
Confirmed primary failure may exit clean if both cleanup facts true; uncertain
cleanup retains false marker and normalized unsuccessful shutdown. Inject true
marker replacement followed by fsync failure: it may be visible after resources
were confirmed closed, but successful durable publication/rollback is not claimed.
Crash helper
tests leave conservative stale state; no automatic recovery is attempted.

## Scope and architecture

```bash
rtk proxy rg -n 'fastapi|uvicorn|httpx|dutchmate_service' core/src
rtk proxy rg -n 'subprocess|serial\.Serial|list_ports|backend_kind.*==|\.failure|_consumer_task|_close_task' apps/service/src
rtk proxy git diff ed11051 -- core/src core/pyproject.toml
rtk proxy git ls-files graphify-out
```
Expected first search no matches; inspect other search hits rather than treating
all as failures (generic backend_kind projection is allowed, identity branching is not).
No Core/003–005 contract changes or generated graph files. Inspect uv.lock for only
intentional service/test dependencies. Import gates forbid service/adapter leakage.

## Final implementation gate

Run only near implementation completion, not during this planning turn:
```bash
rtk proxy uv run ruff check .
rtk proxy uv run mypy .
rtk proxy uv run lint-imports
rtk proxy uv run pytest
rtk proxy git diff --check
```
Review tracked/untracked diff, task markers, paths and docs after recording actual
counts. Report hardware/platform skips truthfully and no hardware acceptance.
No CLI, retrieval, streaming, Monitor/TX/Control/reconnect/handoff/Enhanced/MCP work.
