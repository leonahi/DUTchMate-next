# Implementation Plan: Local Observation Service

**Branch**: main | **Date**: 2026-10-07 | **Spec**: [spec.md](spec.md)
**Feature directory**: 006-local-observation-service, assigned by sequential repository workflow.
Setup scripts label the resolved feature context as BRANCH; Git remains main.

## Summary

Current completion: T001–T030 delivered; fresh final gate1485 passes, zero failures/
errors/skips, static/import/diff checks clean. Feature006 is software-complete,
uncommitted and ready for separately authorized final review and commit. Earlier
checkpoint counts and scope boundaries below retain their historical meaning.

Add one local FastAPI delivery application around existing ObservationRuntime,
with fixed per-UID ownership/bootstrap, private process token, exact security
gate, three endpoints, strongly owned request operations and joined shutdown.
No Core/evidence/Profile/runtime semantics change. Original planning authorized
no implementation; the separately authorized T001–T005 now deliver package/tooling
and private bootstrap only, with89 bootstrap/1013 total software tests GREEN.
T006 now adds148 RED security contracts using real isolated bootstrap and raw ASGI;
all fail for missing http.py, while earlier1013 tests remain GREEN. T007 now adds111
RED closed-status/bounded-input contracts; full suite259 expected failures/1013
passes at that RED checkpoint. T008 now implements only http.py gate, bounded
validators/projector and normalized responses;267 HTTP/projection cases/1280 full
cases GREEN. T009 adds controlled async lifespan and inactive status app composition;
23 new cases RED → GREEN,1303 full cases GREEN. No attach/detach wiring,
operation registry, controlled listener or joined service shutdown yet.
T010 verifies all US1 quickstart selections and app/http logging/error paths:
no demonstrated security/projection defect, no production/test changes,1303 full
cases GREEN. Supported Uvicorn logger configuration remains assigned to T022;
this inactive ASGI checkpoint is not complete service/process acceptance.
T011 adds44 normal HTTP lifecycle/mapping cases using real guarded bootstrap,
runtime/Profile/Basic/SQLite and the existing strict fake serial dependency.
33 missing-route failures/11 validation passes; earlier1303 tests GREEN. Mapping
cases supply valid immutable Core results at the existing composition edge.
No route, operation-registry, cancellation or shutdown implementation was added.
T012 adds21 request-lifetime/registry cases:15 expected missing-route failures and
six pre-registration passes. Real ASGI/bootstrap/runtime and temporary composition
use test-owned call-progress gates and weak task/result/error references. Full
pytest48 expected failures/1320 passes; earlier1303 independently GREEN. No
production or registry implementation; T013/T014 remain separate authorized tasks.
T013 now supplies async POST attach/detach and normal captured results in app.py,
using existing Core composition/lifecycle and HTTP validators/mappers. All44 T011
cases/223 HTTP tests GREEN. One failed-open test assumption corrected to feature-005
release uncertainty; two historical absent-route tests migrated to auth tripwires.
Full pytest12 expected T014 ownership failures/1356 passes. No registry/shielding,
controlled launcher or joined service shutdown; this is not complete service acceptance.
T014 adds bounded operation ownership and shielded delivery: one private set of
eight pending tasks maximum, cancellation check/atomic registration before yield,
separate disconnect observation and completion consumption/removal. Owned tasks
normalize results/errors to closed responses so Python3.14 shield cannot report late
exceptions after delivery loss. All21 original lifetime cases plus two targeted
disconnect regressions GREEN; full1370 passes. No Core change or launcher/shutdown
implementation; T015 and later acceptance remain separately authorized work.
T015 adds24 failure/lifetime cases through actual service/Core/Basic/SQLite with
isolated dependency faults. All pass, including cause/primary/cleanup/certainty
separation, unchanged failed facts after repeated detach and retained journals.
Projection mutation probes independently fail for invented primary failure,
optimistic release certainty and relabelled disconnect cause. Full1394 GREEN;
no production defect found or code corrected. T016 remains separately authorized.
T016 reviews that evidence against app.py/http.py and authoritative005 facts;
no demonstrated integration defect or contract conflict. No production/test change
required; fresh24 focused and1394 full cases GREEN. T017 remains unexecuted.
T017 now adds six authenticated ASGI HTTP binary/idle/detach/readback scenarios:
actual Basic/SQLite and the same lifecycle/status checks for existing Basic/Enhanced-
shaped normalized fixtures. Real Core/Acquisition/journal persist bytes while clients
are idle or lose response delivery, retaining actual clock/loss/capability facts.
Paginated reopen uses existing journal APIs in tests only, after terminal cleanup.
Full1400 GREEN; no production/existing fixture change or Enhanced selection/implementation.
T018 scoped review confirms owning-loop runtime consumers, one physical reader,
closed immutable status without resource handles, public snapshot projection and
no backend identity branches or003–005 revision. No demonstrated defect or source/
test/config change; fresh53 runtime/six context/full1400 cases GREEN. T019 unexecuted.
T019 now verifies all unique US2 quickstart selections and completed005 focus:
44/223/53/244/24/six plus349 cases GREEN. Scope/static/import and full1400 gate clean;
all54 source/config hashes unchanged. This completes the US2 software checkpoint,
not process/listener/shutdown or complete service acceptance.
T020 adds35 process contracts:34 expected RED for missing server.py and one isolated
subprocess safety probe GREEN. Earlier1400 independently GREEN; full34 failures/
1401 passes, zero errors/skips. Ruff/mypy50 files/five import contracts/diff clean;
all54 prior source/config hashes unchanged. Tests cover controlled listener/ownership/
credential/h11 behavior and startup-stop latching; no launcher implementation or
actual listener acceptance. T021 was unexecuted at that checkpoint.
T021 adds31 RED shutdown/startup cases: eight actual app-level joins/detach gaps
and23 absent-launcher cases. Earlier1347 base plus53 runtime cases GREEN; full65
expected failures/1401 passes, zero errors/skips. Tests cover pre-drain admission,
pending/hung work, cancellation/signals, original uncertainty, cleanup errors,
reverse startup unwinding and latched stop. No production change;54 other source/
config hashes and original runtime test source unchanged. Static/import/diff clean.
At the T021 checkpoint, T022 remained unexecuted; controlled listener/signals came next.
T022 now delivers server.py plus minimal private app stop/settlement handoff.
Verified actual locked Uvicorn0.54.0 lifecycle and replaced its force-exit/replay
signal path; startup stop precedes TCP admission. Process37 passes/one T023 marker
failure;1124 base/279 delivery GREEN. Eight direct app shutdown cases remain RED.
Full gate attempted, collected1472 and blocked at deferred active-run drain;
test-tool watchdog124, not a completed gate. Static/import/diff clean. Six focused
regressions cover execution context/stop admission and two corrected test-helper
contracts. Known unsettled work holds the loop/guard; settled interim shutdown
retains false marker/reports teardown_incomplete. T023 joins/certainty/positive
publication remain unimplemented. No Core/dependency change;51 other prior hashes
unchanged. T023 is separately authorized next; no complete service acceptance.
T023 now supplies operation/runtime joins and truthful bootstrap teardown in
app.py/server.py/bootstrap.py. Strongly owned shielded lifecycle tasks preserve
the loop/guard through repeated cancellation/hung work, then capture immutable
RuntimeStatus before disposing credentials/socket and confirming actual cleanup.
False/uncertain state remains blocked without retry/reset. Partial startup unwinds
acquired resources; inspectable stopping status exposes no handles. Three focused
regressions are RED → GREEN; all31 T021/38 process cases and full1475 GREEN,
zero failures/errors/skips. Static/import/diff clean; no Core/dependency change,
51 other prior hashes unchanged. T024 was separately authorized and unexecuted
at that checkpoint.
T024 now verifies all224 bootstrap/runtime/process cases, including nine new OS
publication faults. After true replacement then failed directory fsync, visible
true reflects actual resource cleanup while the call reports teardown_incomplete;
no durable success/rollback claim. Faults before replacement preserve prior state;
uncertain false state blocks restart. No production defect/correction. Three
suppressed-publication-error mutations RED → restored nine GREEN; full1484 GREEN,
zero failures/errors/skips. Static/import/diff clean;55 other source/config hashes
and original runtime test source unchanged. T025 was separately authorized next
at that checkpoint.
T025 now verifies both US3 commands38/186 and completed regressions1014/349/244,
zero failures/errors/skips. Static/import/scope/diff and fresh full1484 gate GREEN.
All56 source/config hashes and22 baseline locked versions unchanged; no correction.
Native macOS IPv6 exercised, no hardware/other-platform acceptance. T026 remains pending.
T026 now reviews all FR-001–030/Core/001–005 against the complete feature diff.
Demonstrated ambient FastAPI telemetry emission is disabled with RED → GREEN
coverage, preserving the existing input-diagnostic prohibition. Unused httpx/
httpcore/certifi removed via uv;22 baseline versions unchanged. No other contract/
scope defect found. Full1485 GREEN, static/import/diff/build clean. T027 pending.
T027 now verifies all14 unique focused quickstart commands and scope searches.
All GREEN with zero failures/errors/skips; overlapping selections cover1485
distinct cases. Targeted/static/import/diff checks clean; no correction and all56
source/config hashes unchanged. Native macOS IPv6 runs, no hardware acceptance.
Final full-gate block left to T030; T028 was pending at that checkpoint.
T028 now reconciles current status/history, actual scope, committed baseline and
limits. Feature006 is uncommitted; final validation/acceptance remain pending.
Documentation-only checks; no source/test/config change, software gate or Graphify
update. T029–T030 were unchecked at that checkpoint; native evidence is macOS only and physical-
hardware/Windows service acceptance remain unexecuted.
T029 now verifies the structural trigger from added service modules/package and
delivery import boundaries, with unchanged shared Core interfaces. Exactly one
Graphify0.9.48 code-only incremental update of13 changed sources succeeds:
2891 nodes/8348 edges/123 communities, zero LLM tokens. Existing documentation
graph preserved; output/backups ignored. No source/test/config change or software
gate rerun; T030 remained unchecked at that checkpoint.
T030 now runs the fresh full gate and final intended diff review:1485 passes,
zero failures/errors/skips; Ruff/mypy51 files/five import contracts/diff clean.
Initial sandbox loopback denials resolved by permitted guarded full rerun; no
source/test/config correction or new contract/scope defect. All30 tasks complete;
ready for final review and commit, with no staging/commit/push/hardware action.

## Technical Context

**Language/Version**: Existing Python >=3.14,<3.15 and uv workspace.
**Dependencies**: FastAPI/Uvicorn in new dutchmate-service workspace package;
dutchmate-core workspace dependency; raw ASGI/loopback test tools need no HTTP client library.
Use standard-library fcntl/socket/os/pwd/secrets/asyncio; no auth/lock/daemon framework.
T002 resolved FastAPI0.142.2 (>=0.142.2,<0.143), Uvicorn0.54.0 (>=0.54.0,<0.55),
historical test-only httpx0.28.1, Starlette1.7.0 and compatible transitives
through uv. Verified actual imports/lifespan/config/signal APIs and MIT/BSD licenses.
All22 pre-existing locked package versions remain unchanged; details in research.
T026 removes unused httpx/httpcore/certifi; FastAPI/Uvicorn and required dependencies
remain unchanged.
**Storage**: Existing fresh SQLite journals unchanged; separate fixed private
bootstrap directory with one lock, credential and bounded cleanup marker.
**Testing**: Existing pytest/asyncio; raw ASGI gate/disconnect harness with
explicitly managed async lifespan; isolated process/socket tests; temporary
journals and fail-closed fake serial. No real account bootstrap used by tests.
**Target Platform**: Initial Linux/macOS local POSIX filesystem; unsupported Windows
service startup fails explicitly before bootstrap; no portable-Core support reduction.
**Project Type**: Modular-monolith delivery application apps/service.
**Performance Goals**: One runtime/run/RX owner; eight pending mutations maximum,
16384-byte input/1048576-byte status bounds; no guessed throughput/latency target.
**Constraints**: Fixed per-account exclusion independent of port; no worker/reload/
proxy overrides; no lifecycle timeout or forced cancellation; false stale marker
blocks restart even after idle crash; status/certainty projection remains honest.
**Scale/Scope**: One local account service instance, one selected loopback listener,
one DUT observation run; no clients/workflows/retrieval or daemon manager.

## Constitution Check

Constitution is an unpopulated scaffold, not another authority. AGENTS/Core and
completed contracts govern. Pre-research and post-design checks pass by design:

| Gate | Assessment |
|---|---|
| Core authority | No Core product rule changed; service/J access-control scope accepted |
| Ownership/RX | Persistent005 runtime; sole Acquisition opener/reader; per-UID guard |
| Loop/context | Runtime in async lifespan; lifecycle APIs on same loop/thread |
| Security | Host/Origin/auth before body/Profile/resources, same testing path |
| Compatibility |003 schema-v1,004 Profile-v1,005 lifecycle untouched |
| Dependency direction | New delivery package imports Core; Core cannot import service |
| Neutrality | Generic fact projection; same fixture lifecycle tests, no Enhanced behavior |
| Cleanup | Join registered tasks before detach; certainty/marker preserved |
| Simplicity | Four cohesive delivery modules; no generic job/auth/plugin framework |
| Hardware | All tests isolated, fakes/temp journals; default hardware sentinel extended |

These are planning assessments, not claims future code passes gates. No architecture
violation, ignore_imports, Core banned-API exemption or schema migration proposed.

## Project Structure

Documentation:
```text
specs/006-local-observation-service/
  spec.md
  checklists/requirements.md
  plan.md
  research.md
  data-model.md
  contracts/local-observation-service.md
  quickstart.md
  tasks.md
```

Planned new application:
```text
apps/service/
  pyproject.toml
  ruff.toml
  src/dutchmate_service/
    __init__.py
    bootstrap.py   # Config, account paths, lock, token, marker, normalized errors
    http.py        # ASGI gate, bounded wire validation/projection, normalized responses
    app.py         # Async lifespan, route wiring, finite operation owner, joined shutdown
    server.py      # Controlled one-worker loopback listener and coalesced signals
  tests/
    conftest.py
    test_service_bootstrap.py
    test_service_http.py
    test_service_projection.py
    test_service_runtime.py
    test_service_process.py
pyproject.toml      # Workspace/dev tests/static paths/service-Core import contracts
uv.lock            # Intentional dependency resolution only during implementation
docs/development_status.md
docs/development_history.md
```

No apps/cli package. Service tests do not add a second Python package named tests,
avoiding collision with core/tests; unique test_service_* module names and explicit
pytest-only access to existing Core fixtures. No production imports from test code.

## Consumer/configuration inventory

- ObservationRuntime constructor, attach/status/detach and rejection/status values
  remain unchanged; service-owned tasks call the existing edge, never expose handles.
- attach_basic_observation retains its bounded Profile-before-runtime-admission rule;
  authentication precedes invoking it. No backend/journal factory redesign.
- Existing SQLite/Profile/Backend/model exports, record codecs and schema untouched.
- Root uv workspace currently has only core. T002 adds apps/service and its own
  hatchling package with dutchmate-core workspace source; no editable/import-path hack.
- Root pytest/mypy paths must include service and its tests; service test conftest
  must fail on real serial factories/enumeration and supply isolated account-home.
- Import Linter must analyze both installed packages, preserve three existing
  contracts, add Core-forbidden-service and delivery-forbidden-serial/subprocess/
  client-framework contracts after modules exist. New service bans cover direct
  imports (allow_indirect_imports=true), permitting legitimate service → existing
  Basic composition → serial and framework-internal dependencies. All existing
  Core contracts remain unchanged; no ignore_imports.
- Root Ruff Core banned APIs stay intact. New apps/service/ruff.toml explicitly
  permits its required HTTP framework while keeping subprocess/serial/MCP/CLI
  framework bans in service production. Do not ignore TID251 in service product
  files; test-only exemptions remain limited to development tests.
- Public product name remains DUTchMate; internal package dutchmate-service.
  No credentials, local bootstrap, journals, generated graph or workstation config committed.

## Settled design

[Research](research.md), [data model](data-model.md) and
[contract](contracts/local-observation-service.md) settle exact behavior.
1. Fixed POSIX account bootstrap; nonblocking kernel lock; no unlink/replacement
   of lock inode; bounded whole-incarnation cleanup marker with conservative restart.
2. Numeric IPv4 default/explicit IPv6-only listener; no DNS/proxy/fallback; controlled
   server coalesces repeated signals with a latched startup stop, prevents later
   ready/admission publication and keeps graceful lifecycle draining unbounded.
3. Private fresh256-bit process token; exact Host → Origin/Sec-Fetch → Bearer gates,
   no credential/input logs or URL credentials. No auth bypass in tests.
4. Three exact closed HTTP operations.200 projects returned status including failed;
  409 rejects busy/uncertain runtime;422 Profile/request;500 defect;503 stopping/capacity.
5. Finite strongly owned request tasks with shielded delivery waiters; HTTP loss
   does not translate to005 attach cancellation. No queue/replay/job surface.
6. Close admission → join registered tasks → detach/join runtime → confirm facts
   → token/socket cleanup → marker confirmation → release guard.

## Implementation sequence and acceptance

1. Verify committed baseline/contracts and focused005 regressions; inspect config.
2. Add minimal installable service package/tooling and bootstrap RED/GREEN foundation.
3. Specify tests then implement security/status projection with real isolated bootstrap;
   US1 is an authenticated inactive-service checkpoint, not a usable insecure skeleton.
4. Add normal HTTP lifecycle/readback tests, then route operations through existing edge.
5. Add cancellation/capacity/shutdown-race tests; implement strong request ownership,
   explicit admission closure and joins without changing005 cancellation semantics.
6. Add real isolated process tests for different-port duplicates, stale markers,
   safe IPv4/IPv6 startup and repeated signals; implement controlled server.
7. Review all FR-001–030 and completed-contract compatibility; run quickstart/scopes.
8. Update status/history, assess Graphify structural trigger near implementation
   completion, then fresh full gate/diff and honest software-only completion report.

All stories mandatory. Security cannot be postponed behind working endpoints;
a US1 checkpoint is not complete service acceptance. First implementation group
is T001–T005 only, as defined in [tasks.md](tasks.md).

## Critical regression matrix

| Area | Required proof |
|---|---|
| Security | Raw duplicates/malformed headers, origin absence/presence/Sec-Fetch, constant-time path, all-route ordering |
| Privacy | No tokens/URL/input/traceback logging or validation echo; private file permissions |
| Process | Fixed per-UID exclusion on different ports, stable inode, stale false/malformed rejection |
| Lifetime | Async lifespan singleton, owning-loop status, ambient RX between calls |
| HTTP | Exact methods/paths/body/wire bounds, normalized projection/mapping, no docs/redirects |
| Cancellation | Delivery-only loss before/after registration, strong refs, no attach_cancelled |
| Shutdown | Queued attach joined before detach; repeated cancellation; hung work never abandoned |
| Failure | Partial bootstrap reverse cleanup, failed runtime status, uncertain recorder/physical release |
| Compatibility | Unchanged schema/Profile/evidence/runtime; fresh retained journals |
| Neutrality | Same fixture behavior, device/host provenance and honest capability/loss differences |

## Validation and tooling

Focused tests precede code. Required implementation gate:
```bash
rtk proxy uv run ruff check .
rtk proxy uv run mypy .
rtk proxy uv run lint-imports
rtk proxy uv run pytest
rtk proxy git diff --check
```
Test gate remains hardware-free. Packaging/install reproducibility verified through uv.
Exactly one Graphify update if actual implementation structure triggers it; none
for this documentation-only planning. Do not automatically run extra Spec Kit stages.

## Remaining decisions and limitations

No unresolved product decision. Chosen limitations: POSIX service first, one service
per UID, strict non-browser clients, process-lifetime token, conservative idle-crash
restart rejection, local filesystem permission guarantees and no forced-abandon.
External operator recovery and other-user/arbitrary-tool exclusion are not supplied.
