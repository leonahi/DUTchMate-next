# Tasks: Local Observation Service

**Input**: [spec.md](spec.md), [plan.md](plan.md), [research.md](research.md),
[data-model.md](data-model.md), [contract](contracts/local-observation-service.md).
**Status**: T001–T030 delivered; all30 tasks checked. T030 fresh full gate:1485
passes, zero failures/errors/skips; Ruff/mypy51 files/five import contracts/diff
clean. Final intended diff review found no new defect; no source/test/config change.
Feature006 is software-complete, uncommitted and ready for final review and commit.
T029 structural trigger met;
one code-only incremental Graphify update succeeded, generated output ignored.
T028 reconciles current
status/history, committed baseline and limits; documentation-only checks.
All14 unique focused
quickstart pytest commands GREEN, zero failures/errors/skips;1485 distinct tests
covered across overlapping selections. Scope/static/import/diff clean; all56
source/config hashes unchanged at that checkpoint. T030's final full gate is complete.
**Tests**: Required by FR-028–030; deterministic contract RED → focused GREEN.
**Baseline**: ed11051 on main;005 implementation2824c0d. Preserve001–005 semantics.

Task markers describe file independence, not automatic delegation authorization.
No CLI/retrieval/streaming/workflow/hardware or future-phase behavior belongs here.

## Phase 1: Setup

- [x] T001 Inspect docs/development_status.md, governing Core/service contract, actual git status/HEAD/diff, core/src/dutchmate_core/runtime.py and existing composition/tests; verify ed11051 or explain newer baseline; run the existing005 focused selection in specs/006-local-observation-service/quickstart.md with hardware guards. No dependencies or product resources yet.
- [x] T002 Create only minimal installable apps/service/pyproject.toml and src/dutchmate_service/__init__.py; use uv to add the workspace Core dependency, verified compatible FastAPI/Uvicorn and test-only httpx, recording resolved versions in research.md/uv.lock without unrelated upgrades. Extend root pyproject.toml test/mypy paths and import contracts after the package exists; add apps/service/ruff.toml with production subprocess/serial/MCP/CLI bans intact and no blanket TID251 exemptions. Add isolated apps/service/tests/conftest.py hardware/bootstrap guards; no routes/lifecycle/launcher behavior.

## Phase 2: Foundational bootstrap

- [x] T003 Add RED apps/service/tests/test_service_bootstrap.py for ServiceConfig port integer1..65535 (not bool), host exactly127.0.0.1/default or ::1; fixed effective-UID/passwd-home paths;0700 directory/0600 regular singly linked files; no-follow descriptor race checks; unsupported-platform rejection; stable-inode nonblocking flock different-port exclusion;256-bit64 lowercase hex token/65-byte file and rotation; strict max256-byte marker; stale false/malformed/token-without-marker rejection; partial publication/removal failures and no PID stealing/lock unlink.
- [x] T004 Implement only ServiceConfig, normalized bootstrap failure and private account-directory/lock/token/marker helpers in apps/service/src/dutchmate_service/bootstrap.py to make T003 GREEN. Preserve ordinary exception transport with read-only kinds, fixed per-user guard, safe bounded publication, entire-incarnation dirty marker and no automatic stale resolution. No runtime construction, HTTP routes or listener.
- [x] T005 Verify apps/service/tests/test_service_bootstrap.py RED/GREEN evidence, package installation through uv, unchanged001–005 contracts and full required Ruff/mypy/Import Linter/hardware-free pytest/diff gate. Record results for T001–T005 in docs/development_status.md and docs/development_history.md. Stop this first implementation group before T006.

T002's new service import bans apply to direct imports only
(allow_indirect_imports=true); preserve existing transitive Core contracts unchanged.
T003 includes root-owned trusted ancestors and isolated sticky-temp-root account
homes, with the same ownership/link safety checks as production.

**Exact first group: T001–T005.** Package/tooling and bootstrap foundation only;
no HTTP lifecycle, listener, Core mutation or physical activity.

## Phase 3: US1 - Reject unintended local access (P1)

**Goal**: Authenticated inactive status with complete security/privacy enforcement.
**Independent test**: Real isolated credential/bootstrap and raw ASGI security gates.

- [x] T006 [P] [US1] Add RED apps/service/tests/test_service_http.py for raw Host duplicates/exact authority/family/port, every present Origin including null/empty/duplicates, Sec-Fetch rejection, no-Origin authenticated eligibility, exact single Bearer syntax/constant-time seam, valid loopback peer and peer rejection, security-before-receive/body/Profile/resources on all paths/methods, query/token URL rejection, disabled docs/redirects and no input-bearing logs/errors.
- [x] T007 [P] [US1] Add RED apps/service/tests/test_service_projection.py for all exact StatusEnvelope/RuntimeStatusView keys and nulls, sorted capabilities/generic opaque provenance, actual primary_failure_kind versus close_failed, derived admissibility, historical descriptor/committed IDs, closed JSON, response max1048576 bytes without truncation, body max16384/read16385, paths1..4096 UTF-8 bytes absolute/no NUL, duplicate/extra/coercion/media failures and input-free error envelopes.
- [x] T008 [US1] Implement only pure ASGI security gate, bounded input validators, closed status projector and normalized response helpers in apps/service/src/dutchmate_service/http.py; enforce contract ordering and exact mappings, no BaseHTTPMiddleware cancellation policy, no backend-specific serialization or raw exception/input echo. Run T006/T007.
- [x] T009 [US1] Add async lifespan/inactive GET status composition in apps/service/src/dutchmate_service/app.py, one runtime created on the serving loop/thread only after controlled bootstrap, default docs/OpenAPI/redirect disabled and outer gate applied to every HTTP path. Use private isolated test launch context with actual credential checks; no per-request owner/sync endpoint. Add bootstrap-before-runtime and wrong-context regressions in apps/service/tests/test_service_http.py.
- [x] T010 [US1] Run US1 quickstart tests, targeted/static/import checks and inspect supported logging configuration in apps/service/src/dutchmate_service/http.py and app.py; correct only demonstrated service security/projection defects. US1 is not full service acceptance.

T006 includes exact raw-path versus decoded-path checks and authenticated Upgrade
rejection. T020 includes actual h11 pre-ASGI malformed/missing/duplicate Host400
responses with no supplied-input logging or Profile/resource work; those transport
responses need not be application JSON envelopes.

## Phase 4: US2 - Own observation across requests (P2)

**Goal**: Existing005 semantics delivered through three endpoints independently of response lifetime.
**Independent test**: Fake Basic + temporary SQLite, deterministic request gates and readback.

- [x] T011 [P] [US2] Add RED normal attach/detach/status and mapping tests in apps/service/tests/test_service_http.py: exact paths/methods, explicit fresh destinations, Profile failure422, runtime busy/uncertain409, wrong-context500, every returned status200 including failed/immediate terminal, Basic busy bounded Profile read only, no query/default/discovery/overwrite/reopen.
- [x] T012 [P] [US2] Add RED apps/service/tests/test_service_runtime.py for observed pre-registration cancel/disconnect with zero submission, registration-before-first-yield, delivery cancellation/send failure after registration/active publication, unchanged runtime stop intent, strong task ownership, maximum8 pending mutations with503 before Profile I/O, exception/result consumption and no history/replay/unbounded references.
- [x] T013 [US2] Add POST attach/detach route wiring and normal captured results in apps/service/src/dutchmate_service/app.py using existing attach_basic_observation/runtime.detach, owner-loop async execution, http.py validators/mappers and single persistent runtime. No new Core/adapter factory or evidence surface. Make T011 GREEN.
- [x] T014 [US2] Implement bounded strongly owned operation registry and shielded delivery waiters in apps/service/src/dutchmate_service/app.py; never cancel admitted service tasks, synthesize005 attach_cancelled or abandon a not-yet-invoked attach. Consume/remove completed entries and discard paths/results; no cancelling TaskGroup/queue/replay. Make T012 GREEN.
- [x] T015 [US2] Add focused normalized failure/lifetime regressions in apps/service/tests/test_service_runtime.py for preparation failure, failed open/append/backend/recorder close, observed autonomous disconnect and repeated client cancellation. Assert reason/primary/cleanup/certainty separation, no second close/reopen and retained failed journals.
- [x] T016 [US2] Correct only service wrapper/failure/projection integration in apps/service/src/dutchmate_service/app.py and http.py demonstrated by T015;005 statuses/cleanup semantics remain authority and no underlying Core change is authorized. If a governing contract conflict appears, report it instead of weakening it.
- [x] T017 [US2] Add end-to-end HTTP idle/ambient binary capture and detach/readback tests in apps/service/tests/test_service_runtime.py through real SQLite and fake Basic composition. Parameterize identical applicable lifecycle/status assertions over existing Basic/Enhanced-shaped normalized fixtures, preserving reported domains/loss/capabilities; no production Enhanced selection or behavior.
- [x] T018 [US2] Review service consumers and tests in apps/service/src/dutchmate_service/ and apps/service/tests/test_service_runtime.py for wrong-loop calls, extra physical reader/resource handles, legacy/private Acquisition decoding, backend identity branches and changed003–005 semantics; make focused corrections only within feature006.
- [x] T019 [US2] Execute US2 quickstart selections and completed005 regressions plus static/import checks from specs/006-local-observation-service/quickstart.md; record results in docs/development_history.md without claiming complete service/process acceptance.

## Phase 5: US3 - Start and stop one honest owner (P3)

**Goal**: Controlled loopback server, duplicate/stale safety and joined cooperative shutdown.
**Independent test**: Isolated bootstrap/process/socket tests, fake startup/close gates.

- [x] T020 [P] [US3] Add RED apps/service/tests/test_service_process.py for controlled one-worker launch, no reload/fork/proxy overrides, default numeric IPv4 and explicit IPv6-only bind, unavailable IPv6/no fallback, duplicate per-UID guard on different ports, stale clean/unclean/malformed markers and safe credential lifetime. Helper processes may only use temporary state/loopback sockets, never hardware.
- [x] T021 [P] [US3] Add RED shutdown/startup tests in apps/service/tests/test_service_runtime.py: close admission before HTTP draining, registered not-yet-invoked attach joined before detach, repeated cancellation/signals without force_exit, pending hung startup/close, original cleanup uncertainty, credential/socket/marker cleanup errors, bootstrap partial failure reverse unwinding and lock held through resource settlement.
- [x] T022 [US3] Implement controlled run_service listener/signal integration in apps/service/src/dutchmate_service/server.py with one process/worker, no import-time effects, required bootstrap launch context, socket family/V6ONLY settings, disabled input logs/proxy trust, unbounded graceful draining and coalesced repeated SIGINT/SIGTERM. Verify actual locked Uvicorn lifecycle/signal API; no general manager/CLI.
- [x] T023 [US3] Implement admission-close → registry join → runtime.detach/join → certainty inspection → token/socket cleanup → bounded marker publication → guard release in apps/service/src/dutchmate_service/app.py, server.py and bootstrap.py. Cooperative cancellation cannot interrupt draining; false marker retains settled uncertainty and blocks restart, with no close retry or takeover.
- [x] T024 [US3] Run injected partial-startup/shutdown/marker-publication failure cases in apps/service/tests/test_service_bootstrap.py and test_service_runtime.py plus real isolated process cases in test_service_process.py; fix only demonstrated feature006 failures and confirm no false durable/physical cleanup assertion.
- [x] T025 [US3] Run all US3 and completed001–005 regression selections plus static/import checks in specs/006-local-observation-service/quickstart.md; report unsupported-platform/IPv6 skips accurately, not as acceptance, and preserve all hardware guards.

T020/T021 include signals latched during directory/lock/marker/socket/token/lifespan
startup: no subsequent ready publication or admission reopen. T022/T023 implement
that latch without setting force_exit. T024 explicitly injects marker replacement
success followed by fsync failure: true can already be visible only after all
resources closed; report publication failure without claiming rollback or durable success.

## Phase 6: Final review and completion

- [x] T026 Review full diff against specs/006-local-observation-service/spec.md FR-001–030 and contracts/local-observation-service.md, Core and001–005 contracts; inspect apps/service/, pyproject.toml and uv.lock for insecure launch/test bypasses, unnecessary dependencies, source/secret logging, generated files and accidental deferrals. Correct genuine feature006 defects with regression coverage only.
- [x] T027 Execute all focused quickstart scenarios and scope searches in specs/006-local-observation-service/quickstart.md; correct only demonstrated failures. Leave its final full-gate block to T030.
- [x] T028 Update docs/development_status.md and newest-first docs/development_history.md with actual service software scope, task/test progress, committed baseline, limits and unexecuted hardware/Windows cases; Resume Here about40 lines maximum, no unmade commit/acceptance claim.
- [x] T029 Read docs/agent_tooling.md, assess actual service/package/shared-interface structural changes and run exactly one code-only incremental Graphify update if triggered; record evidence in docs/development_history.md and keep outputs ignored. No update for planning only.
- [x] T030 Use verification-before-completion; run fresh full uv Ruff/mypy/Import Linter/hardware-free pytest/git diff --check gate, inspect final intended diff and record actual counts in docs/development_status.md and docs/development_history.md. Rerun diff checking after docs; stop without auto-commit, push, new slice or hardware action.

## Dependencies and execution order

T001 → T002 → T003 RED → T004 GREEN → T005 → US1(T006–T010)
→ US2(T011–T019) → US3(T020–T025) → final(T026–T030).
Within stories, tests precede code: T006/T007→T008; T011→T013;
T012→T014; T015→T016; T020→T022; T021→T023.
US2/US3 share the same persistent app owner; do not assign competing production edits.
US1 has independent inactive security acceptance; every story remains mandatory.

Parallel opportunities: T006 security tests and T007 projection tests;
T011 normal HTTP tests and T012 request-lifetime tests; T020 process tests and
T021 shutdown tests. Each pair uses separate files after earlier prerequisites.
These are scheduling opportunities, not permission to spawn agents automatically.

## Requirement coverage

| Requirements | Tasks |
|---|---|
| FR-001–004 persistent composition/listener | T002,T009,T017,T020,T022 |
| FR-005–008 process/bootstrap/credential | T003–005,T006,T020,T022–024 |
| FR-009–012 security/order | T006,T008–010,T026 |
| FR-013–017 HTTP/inputs/normalized projection | T007–009,T011,T013,T015–018 |
| FR-018–020 request lifetime/bounds | T012,T014,T017,T021,T023 |
| FR-021–025 shutdown/stale/failure | T003–004,T020–025 |
| FR-026 logging/privacy | T006,T008,T010,T020,T022,T026 |
| FR-027 compatibility | T001,T015–019,T025–027 |
| FR-028–030 tests/neutrality/gates | T003–030 as applicable, T017,T025,T030 |

## Implementation strategy

Exact first group is T001–T005: baseline, installable service/tooling,
bootstrap RED/GREEN and verification. No lifecycle/HTTP behavior until T006.
Security US1 precedes attach endpoints; happy-path US2 is not service completion.
Process/shutdown US3 is mandatory before software acceptance.

Counts: setup/foundation5; US1 five; US2 nine; US3 six; final five; total30.
Six [P] test tasks in three pairs. T001–T030 are checked; no implementation task
remains unchecked. T001 baseline349 GREEN; T003 87 RED; T004 87 GREEN then two focused
correction regressions RED → GREEN; bootstrap89 GREEN. T005 full gate1013 passes,
Ruff clean, mypy44 files, five import contracts kept (37 files/90 dependencies).
T006 adds148 raw-ASGI security contracts, all expected RED because http.py is
absent. Earlier1013 tests remain GREEN; full pytest records148 expected failures
and1013 passes, no errors/skips. Ruff/mypy45 files/import checks pass. The internal
SecurityGate(app, config=config, credential=callable) seam is exercised using real
isolated bootstrap and a policy-free downstream probe. T007 adds111 RED projection/input tests using real immutable Core values and raw
body messages. Internal status_response(status, service_state=...) and async
validate_request(scope, receive) helper seams are tested, without helper substitutes.
All259 T006/T007 failures are missing http.py; earlier1013 remain GREEN. Full
pytest:259 expected failures/1013 passes, no errors/skips; mypy46 files clean.
T008 now implements the pure ASGI gate, bounded validators/status JSON and normalized
responses in http.py only. Fresh original259 RED → GREEN; six typed-mapping RED
regressions → GREEN, two replay mutation checks RED → GREEN;267 HTTP/projection
cases pass and full1280 pass. Ruff/mypy47 files/five import contracts kept (40 files/
104 dependencies) and whitespace checks pass. Original T006 test/function ASTs and
all T007 tests unchanged;49 other prior source/config hashes unchanged. Explicit
mapped-IPv6 rejection preserves peer precedence; known rejection categories no
longer collapse to generic500. At T008 there was no app/lifespan/runtime ownership/listener/hardware.
T009 adds controlled async lifespan/inactive status composition with23 RED → GREEN
cases, one real owning-loop runtime and unchanged bootstrap ownership; full1303 GREEN.
T010 verifies179 HTTP cases,1013 Core/bootstrap regressions and combined290 US1
cases, reviews input-free app/http errors/logging and passes the full1303 gate.
No production/test correction is required; all53 prior source/config hashes unchanged.
Uvicorn logger configuration and pre-ASGI diagnostics remain T020/T022 work;
no complete service/process/listener acceptance is claimed.
T011 adds14 test functions/44 cases. All33 RED failures are absent attach/detach
routes returning404;11 path/method/query/default validation cases already pass.
Real guarded bootstrap/runtime/Profile/Basic/SQLite fixtures preserve physical/
discovery tripwires; mapping-only cases substitute the existing edge result, not
runtime ownership or security. Core-seeded busy/uncertain states are real; bounded
Profile reads and resource no-preparation tripwires remain explicit.
Earlier1303 tests pass; full pytest33 expected failures/1314 passes, zero errors/skips;
Ruff/mypy48 files/five import contracts clean. No production or T012 behavior added.
T012 adds eight functions/21 lifetime cases:15 expected missing-route failures,
six observed pre-registration cancellation/disconnect cases already pass. Passive
Core-call probes, real runtime/temporary composition and weak task/value references
test admission, retention, result/error consumption, no replay and a shared eight-
mutation limit. Test-owned gates never cancel service operation tasks. Full pytest
48 expected failures/1320 passes, zero errors/skips; earlier1303 independently GREEN.
Ruff/mypy49 files/five import contracts clean; all53 existing source/config hashes
unchanged. T013 supplies normal route wiring; T014 supplies operation ownership.
T013 adds normal async POST route wiring in app.py only, using existing bounded
validators/response mappers and Basic edge/runtime.detach. T01133 RED →44 GREEN;
all223 HTTP tests pass. Historical T009 absence checks become auth-before-body/
preparation checks. One T011 failed-open expectation is corrected to feature-005's
unconfirmed physical release with confirmed recorder close (admissibility false).
Full pytest12 expected T012/T014 ownership failures/1356 passes, zero errors/skips;
Ruff/mypy49 files/five import contracts kept (43 files/113 dependencies).52 other
source/config hashes unchanged; no registry/shielding/launcher/shutdown implementation.
T014 adds a single private set of at most eight pending service tasks; atomic
registration precedes yielding and Profile I/O. HTTP cancellation/disconnect/send
loss affects delivery only, including work not yet in Core. Completion is consumed
and removed; no task/path/result history. Owned tasks normalize outcomes before
shielding to avoid Python3.14's late shield-exception loop report. Original21 lifetime
cases GREEN after12 RED; two pending-disconnect cases mutation-checked RED → GREEN.
Full1370 passes, zero errors/skips; Ruff/mypy49 files/five import contracts kept
(43 files/114 dependencies).52 other source/config hashes and original test ASTs
unchanged. Launcher and joined shutdown remain later tasks; no T015 behavior added.
T015 adds six parameterized functions/24 cases covering preparation/open/initial,
active and final append/close failures, autonomous disconnect and repeated delivery
cancellation. Literal cause/primary/cleanup/certainty assertions, stable historical
status, one-time cleanup and retained failed artifacts pass. Three process-local
projection mutations produce five intended failures; unmodified production passes.
Full1394 GREEN; original1370 remain GREEN and original test ASTs/53 other source/config
hashes unchanged. No production defect or T016 correction was introduced.
T016 reviews T015's demonstrated outcomes against the active delivery contract and
feature-005 failure/certainty matrix. No defect/conflict found; no correction or
production/test change required. Fresh24 focused cases and full1394 GREEN; Ruff/
mypy49 files/five import contracts/diff clean. All54 source/config hashes unchanged.
T017 remains separately authorized; no idle/ambient integration or fixture extension added.
T017 adds two parameterized functions/six cases: actual Basic/SQLite idle/lost-attach-
response binary capture and identical detach/autonomous-disconnect assertions over
existing Basic/Enhanced-shaped normalized fixtures. Journal readback occurs only
after confirmed HTTP detach/terminal close, bounded to two records per page. Reported
domain/loss/capability facts and generic opaque provenance remain unchanged. Byte,
host-only clock and loss mutations produce six/two/two intended failures; normal
six cases and full1400 GREEN. No production/existing fixture change;53 other source/
config hashes and original runtime test ASTs unchanged. No T018 work performed.
T018 reviews context, physical ownership, status/private handles, snapshot decoding,
neutrality and003–005 compatibility across current service consumers/runtime tests.
No defect found; no production/test/config correction. Source search matches are
bootstrap file descriptors, public normalized facts, or test-only fixtures/readback;
not extra readers or private Acquisition decoding. All54 source/config hashes and
Core/003–005 baseline diff unchanged; six context/53 runtime/full1400 cases GREEN.
T019 remains separately authorized and unexecuted.
T019 runs all unique US2 quickstart pytest selections (44/223/53/244/24/six cases)
plus complete005 focus349; every command GREEN with zero errors/skips. Targeted/
full Ruff, mypy49 files, five import contracts, scope searches and full1400 gate
clean. No source/test/config change; all54 hashes and22 baseline locked versions
unchanged. Evidence recorded in history; US2 is not full process/service acceptance.
T020 adds35 isolated process contracts:34 expected missing-server failures and
one independently executed subprocess guard probe GREEN. Real-loopback scenarios
cover controlled Uvicorn settings, selected numeric family/V6ONLY/no fallback,
different-port exclusion, stale/crashed owners, cached private token/clean rotation,
fixed h11 rejection/privacy and repeated startup signals at six boundaries.
Earlier1400 independently GREEN; full34 failures/1401 passes, zero errors/skips.
Ruff/mypy50 files/five import contracts/diff clean; all54 prior source/config hashes
unchanged. No production implementation or actual listener/h11 acceptance yet.
At the T020 checkpoint, T021 remained separately authorized and unexecuted.
T021 adds ten functions/31 RED cases. Eight execute actual guarded app/Runtime/
temporary Basic/SQLite paths and expose absent lifespan joins/detach. Twenty-three
launcher-level cases stop at missing server.py; future assertions retain actual
bootstrap/app/Core/Uvicorn lifecycle, replace only the network edge, and deliver
signals to installed callbacks without signalling pytest. Cover pre-drain admission,
pending/hung work, repeated cancellation/signals, old/new cleanup uncertainty,
failed-but-confirmed runtime cleanup, bootstrap errors/reverse unwinding and six
startup stop boundaries. No production change. Earlier1347 plus53 GREEN; full65
failures/1401 passes, zero errors/skips. Ruff/mypy50 files/five import contracts/diff
clean;54 other source/config hashes and original runtime source unchanged.
At the T021 checkpoint, T022 remained separately authorized and unexecuted.
T022 supplies controlled server.py and minimal private app stop/settlement handoff.
Actual Uvicorn0.54.0 startup/protocol/drain retained; guarded lifespan blocks TCP
admission after startup stop; default force_exit/replay disabled. One main-thread
asyncio loop, selected numeric family/V6ONLY, fixed bootstrap and disabled input
loggers/proxies verified with actual loopback processes. Process suite37 passes/
one expected T023 clean-marker failure;1124 base and279 delivery passes. Eight
direct app shutdown cases remain RED. Six new regression cases include wrong
calling context, immediate stop admission and two corrected test-helper defects
(os mode= forwarding and coherent signal.signal/getsignal emulation), with RED/
GREEN evidence. No Core/dependency change;51 other prior hashes unchanged.
Full pytest collected1472, then blocked at T021 active-run drain; isolated test-tool
watchdog exited124, so no completed full gate/complete service acceptance claim.
Known unsettled work holds loop/guard; settled interim shutdown reports
teardown_incomplete and retains false marker. Joins/certainty/true publication
remain T023, not implemented. Static/import/diff clean; stopped before T023.
T023 now implements the ordered cleanup pipeline. Strongly owned shielded lifecycle
tasks join registered operations before runtime.detach, retain the owning loop and
guard through hung work/repeated cancellation, and hand off an immutable final
RuntimeStatus. Actual three certainty facts plus successful bootstrap cleanup gate
true publication; failed-but-confirmed runtime is eligible, settled uncertainty
remains false/teardown_incomplete. Partial startup unwinds only acquired resources.
Status projects stopping facts while mutations stay closed. Sticky credential
invalidation prevents release retry; failed HTTP drain blocks a clean marker.
Original31 T021 cases and38 process cases GREEN; three focused regressions verified
RED → GREEN (invalidation, draining status and HTTP-drain failure). Full1475 GREEN,
zero failures/errors/skips; Ruff/mypy51 files/five import contracts/diff clean.
No Core/dependency change;51 other source/config hashes unchanged. T024 was unexecuted
at the T023 checkpoint.
T024 executes all224 bootstrap/runtime/process cases and adds nine OS-level fault
cases across false marker/credential/true marker publication at file-fsync,
replacement and directory-fsync. True replacement followed by failed fsync leaves
visible true only after actual cleanup; reports teardown_incomplete without
successful/durable confirmation or rollback claim. Other failure states preserve
the authoritative prior marker or block restart appropriately. No production
defect/correction. Three suppressed-error mutations are RED; restored nine cases
GREEN. Full1484 GREEN, zero failures/errors/skips; static/import/diff clean.
55 other source/config hashes and original runtime test source unchanged. T025 was
pending at that checkpoint.
T025 runs both US3 quickstart commands (38/186 GREEN) and completed001–005/Core
regression selections (1014/349/244 GREEN). Counts overlap and are not added.
All commands zero failures/errors/skips; native macOS IPv6 runs, no hardware
acceptance. Static/import/scope searches and full1484 gate GREEN. No code/test/
config correction; all56 hashes and22 baseline locked versions unchanged. T026 pending.
T026 reviews complete source/config/artifact diff against FR-001–030, Core and
001–005. Corrects one demonstrated privacy defect: FastAPI0.142 native telemetry
inherits ambient providers and emits raw delivery exceptions independently of
disabled Uvicorn loggers. Explicit telemetry/auto-configuration off, real-provider
regression RED → GREEN. Removes unused test-only httpx and its exclusive httpcore/
certifi dependencies via uv; all22 baseline versions unchanged, import bans intact.
No other scope/ownership/schema/Profile/backend-neutrality defect found. Full1485
GREEN, zero failures/errors/skips; static/import/diff and build/import checks clean.
52 other prior source/config hashes unchanged; no Core/001–005 revision. T027 pending.
T027 runs all14 unique focused pytest commands from quickstart, deduplicating
repeated runtime commands. Every command GREEN, zero failures/errors/skips; XML
union1485 distinct cases, not an added sum or a fresh default-suite invocation.
Scope searches, targeted Ruff, mypy51 files/five import contracts/diff clean.
No demonstrated failure/correction; all56 source/config hashes and22 baseline
versions unchanged. Native macOS IPv6 runs; no hardware/other-platform acceptance.
Final full-gate block unexecuted here, reserved T030. T028 was pending at that checkpoint.
T028 now reconciles current status/history, actual service scope, committed baseline,
task/test evidence and limits. Feature006 remains uncommitted with final validation/
acceptance pending; native software evidence is macOS only, Windows service and
physical-hardware acceptance unexecuted. Documentation-only checks; no software
test, Graphify update or final full gate rerun. T029–T030 were unchecked at that checkpoint.
T029 now assesses actual new service modules/package and delivery import boundaries:
the structural trigger is met; shared Core interfaces are unchanged. Exactly one
Graphify0.9.48 code-only incremental update of13 changed sources succeeds:
2891 nodes/8348 edges/123 communities, zero LLM tokens. No semantic extraction or
second update; output/backups ignored. Source/test/config unchanged; T030 remains
unchecked and its fresh final full gate was not executed at that checkpoint.
T030 now completes the fresh full gate:1485 passes, zero failures/errors/skips;
Ruff clean, mypy51 files clean, five import contracts kept/zero broken (49 files/
125 dependencies), diff checks clean before/after docs. Initial full suite recorded
34 loopback PermissionError failures/1451 passes under the sandbox; the permitted
guarded rerun passed all1485, including38 native macOS process cases. Final intended
diff review found no new defect, unrelated/generated/runtime files or contract/scope
revision. No source/test/config corrections, second Graphify update or hardware
action. All30 tasks complete; feature006 software-complete, uncommitted and ready
for separately authorized final review and commit. Stopped T030 without staging,
commit, push or next-slice work.
