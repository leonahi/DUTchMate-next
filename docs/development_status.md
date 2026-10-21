# DUTchMate Development Status

This is the single authority for current progress, active phase, blockers,
milestone, and next work. It is subordinate to
[Core](project_context_core.md) and active focused implementation specifications.
Completed-slice evidence is kept in [development history](development_history.md).

## Resume Here

- **Active phase**: Phase 1 — Basic backend through CLI; Phase 1 remains incomplete.
- **Committed baseline**: Features 001–012 on main. Feature 012 implementation:
  `:/^Implement bounded interact`, `Implement bounded interact`; accepted parent
  `a28acc363f0ee81e9f269c9a92e55e314bf0f062` (Feature 011).
- **Completed slice**: Feature 012 `bounded-interact`; T001–T030 complete (30/30),
  software-complete and committed within macOS/arm64 Python 3.14.3 software scope.
- **Acceptance infrastructure**: RP2040 test-DUT fixture implemented in
  `hardware/firmware/test_dut/rpi_pico/`; pristine Zephyr build and 14 host C tests
  (also under ASan/UBSan) pass. Monitor checkpoint race reproduced/corrected in its
  test only; fresh host gate:11,403 pass, zero failures/errors/skips,1032.65s.
- **Physical acceptance**: Identified macOS/FTDI/Pico Stage1 RX-only passes55 checks;
  approved Stage2 single PING/independent PONG passes76 through authenticated
  service/API2/CLI and real v4 journals. Concurrent Follow/Monitor, durable readback,
  joined detach/stop and explicit reopen verified. Port released; TX restored off.
- **Acceptance review**:17-file fixture/evidence/Monitor-test scope reviewed;
  fresh cross-build reproduces the accepted UF2 exactly,14 C tests pass normally
  and sanitized, five archive/install/privacy audits pass. Associated change:
  `:/^Add RP2040 UART acceptance fixture` (`Add RP2040 UART acceptance fixture`).
- **Feature012 review**:61-file diff/Core/contract review; retained-end v4
  settlement-before-start defect corrected with six RED→GREEN cases on both
  backend shapes. Existing error/cleanup categories and legacy versions retained.
- **Feature012 final gate**: 11,399 tests passed in 1021.96s (JUnit1021.782s), warnings
  as errors, zero failures/errors/skips: Core4545/service2777/CLI4077. Ruff clean;
  mypy142; seven import contracts kept (77 files/312 dependencies); diff clean.
- **Feature012 package/privacy**:197 Interact/artifact and625 legacy process
  cases;287 index blobs exported, six archives,39 modules/stack,25 pins,127 RECORD
  rows verified. Private/generated/runtime/credential/Graphify/tooling excluded.
- **Compatibility/ownership**: Profile1, journals1/2/3, API1/default CLI, old codecs/
  charges, Monitor clocks/security/cleanup retained. One authoritative RX/private
  Acquisition connection; intent ACK before write registration; join before close.
  Backend ACK proves acceptance only, never physical wire/DUT receipt or causation.
- **Tooling**: No Graphify rerun at pre-commit; T029 result/health limits remain
  historical and predate this narrow correction. Outputs/backups/tooling stay ignored.
- **Limits**: Acceptance covers only this setup and one benign exchange; no wire/
  DTR/RTS waveform, in-flight write cancellation, native Linux/Windows or Enhanced
  acceptance. Disconnected DTR/RTS and library state do not establish glitch safety.
- **Next action**: Separately scope native Linux software acceptance on an identified
  Linux host/toolchain, initially hardware-free with existing guarded installed
  suites. No native acceptance, hardware activity or software slice started.
- **Stop**: Acceptance review/validation complete; no further hardware/account
  access, Graphify or push. Stage2's original TX-disabled Profile retained.

## Repository Baseline

| Feature | Committed software scope | Implementation commit |
|---|---|---|
| [001](../specs/001-rx-continuous-evidence/spec.md) | Normalized backend, continuous exact-byte RX, evidence ordering/provenance | `a13522c` |
| [002](../specs/002-basic-serial-adapter/spec.md) | Explicit-device receive-only Basic adapter, configure-before-open, joined read/close | `e2cd2cf` |
| [003](../specs/003-durable-evidence-journal/spec.md) | SQLite schema-v1 durable append/reopen, bounded retention/references/retrieval | `15890e59` |
| [004](../specs/004-dut-profile-policy/spec.md) | Strict observation-only TOML-v1 Profile, immutable values and Basic translation | `6d10cf72014c46d7eeb5481b26857222ee40b7fd` |
| [005](../specs/005-observation-runtime/spec.md) | Backend-neutral runtime, in-memory Profile/session association, serialized lifecycle | `2824c0dc3ecc63684f573b3b0a55c621e18e069f` |
| [006](../specs/006-local-observation-service/spec.md) | Authenticated local service, persistent runtime, private bootstrap, joined shutdown | `b4c5730b2a5e593c10c06ad9e8f24c39e06f794b` |
| [007](../specs/007-observation-cli/spec.md) | Thin authenticated Typer observation CLI, bounded HTTP delivery, reported facts and private exits | `a14d1727f5a9a2dd1cab59ac2b662f47919bbe9d` |
| [008](../specs/008-evidence-retrieval/spec.md) | Bounded authenticated active/terminal evidence retrieval, exact binary pages and read-cleanup ownership | `11e9ce6d4b47fe8bfa7ecb99e174f4f469e53701` |
| [009](../specs/009-receive-only-monitor/spec.md) | Bounded receive-only Monitor, explicit v2 markers, authenticated service/CLI and owned settlement | `:/^Implement receive-only monitor` |
| [010](../specs/010-client-annotations/spec.md) | Bounded attributed client assertions, explicitv3 evidence, authenticated service/thin CLI and owned insertion | `:/^Implement client annotations` |
| [011](../specs/011-live-follow/spec.md) | Receive-only live-tail Follow, bounded exact evidence/gaps, owned stop/cleanup, authenticated NDJSON and thin streaming CLI | `:/^Implement live follow` |
| [012](../specs/012-bounded-interact/spec.md) | Bounded exact-byte Interact, minimum owned Basic TX, explicit Profile2/journal4/API2, authenticated service/thin CLI and joined settlement | `:/^Implement bounded interact` |

All prior implementation commits remain ancestors of feature 007. Its accepted
parent `c2c9ce3` records feature 006; `b4c5730` is the service implementation.
The separately authorized feature 007 pre-commit review passed on 2026-10-10:
2261 tests (Core 924/service 561/CLI 776), zero failures/errors/skips; Ruff,
mypy 61 files, seven import contracts and working/staged diff checks passed.
Wheel/sdist installs and outside-cwd entry/import checks passed. Features 006/007
completed their code-only Graphify updates before commit; generated output and
backups remain ignored. Detailed earlier checkpoints belong in history.

Feature 008's implementation commit is
`11e9ce6d4b47fe8bfa7ecb99e174f4f469e53701`, `Implement evidence retrieval`.
The earlier title-based reference `:/^Implement evidence retrieval` resolves to
the same committed baseline. Its accepted parent is
`a14d1727f5a9a2dd1cab59ac2b662f47919bbe9d`. All prior implementation commits remain
ancestors. Nothing was pushed. Feature 008 T034's code-only Graphify update remains
recorded; outputs/backups are ignored and excluded from the commit.

Feature 009's implementation commit is `:/^Implement receive-only monitor`,
`Implement receive-only monitor`, with accepted parent `11e9ce6d4b47fe8bfa7ecb99e174f4f469e53701`.
The title-based reference resolves to the implementation commit; prior baselines
remain ancestors. Nothing was pushed.

Feature010's implementation commit is `:/^Implement client annotations`, `Implement client annotations`,
with accepted parent `2fdebaf4aa3df815be9f2ce223c832e70c739569`. The title-based reference resolves to
the implementation commit without a self-referential hash; prior baselines remain
ancestors. Nothing was pushed.

Feature012's implementation commit is `:/^Implement bounded interact`,
`Implement bounded interact`, with accepted parent
`a28acc363f0ee81e9f269c9a92e55e314bf0f062`. The title-based reference resolves to
the implementation commit without a self-referential hash. Nothing was pushed.

## Completed Feature: Bounded Interact (012; Software-Complete)

Artifacts: [spec](../specs/012-bounded-interact/spec.md),
[plan](../specs/012-bounded-interact/plan.md),
[research](../specs/012-bounded-interact/research.md),
[model](../specs/012-bounded-interact/data-model.md),
[contract](../specs/012-bounded-interact/contracts/interact.md),
[guide](../specs/012-bounded-interact/quickstart.md),
[planning-quality checklist](../specs/012-bounded-interact/checklists/requirements.md)
and [tasks](../specs/012-bounded-interact/tasks.md).

Sequential identifier012 follows completed001–011. All30 tasks and the separately
authorized final pre-commit review/implementation commit are complete. Feature012
is software-complete and committed on main within the observed macOS/arm64 scope;
Phase1 remains incomplete. Resume Here owns the current action; dated task stops,
corrections and actual validation remain in [history](development_history.md).

### Implemented Software Scope

Core implements one bounded exact-byte Interact through the existing owned backend
and authoritative RX stream. Immutable Profile-v2 authorization, reported RX/TX
capabilities and exact evidence-policy preflight precede one serialized write.
Positive intent ACK precedes registration; observation starts at intent+1 and can
match RX before write ACK. Matching, TX settlement, overall outcome and audit ACKs
remain independent facts; whole RX chunks and ambient evidence remain authoritative.

Acquisition seals/joins admitted writes before physical close independently of
audit. Runtime joins Interact audit before final Follow/read/recorder cleanup;
service stop seals before HTTP drain and joins its admitted jobs. Pre-registration
cancellation suppresses TX; post-registration cancellation joins settlement.
Existing Monitor clocks, Follow hints/gaps, annotations, independent slots/read
leases and permanent cleanup uncertainty retain their contracts.

| Boundary | Implemented selection and compatibility |
|---|---|
|Profile/Basic|Distinct immutable v2 policy, TX false by default; explicit opt-in writer has one strongly owned worker and fixed 1000ms library wait. Existing v1 values/defaults/open/read behavior retained.|
|Composition/journal|Profile 1 creates journal 3/RX; Profile 2 creates journal 4/write capability independently of permission. Explicit v4 adds three kinds; legacy factories/codecs/charges unchanged.|
|Service/API|Authenticated literal API-v2 routes and independent Interact ownership; API-v1 keeps legacy shapes and rejects known v2-only runs without downgrade.|
|CLI|Explicit --api-version 2 for Interact, one credential/request and finite delivery. Default API-v1/no-flag behavior retained; delivered valid reports exit0 even for failed outcomes.|
|ACK/boundary|Backend acceptance never proves physical wire/DUT receipt. Start cursor establishes Core observation order, not DUT causation. Unknown progress/ACKs remain unknown.|

Console, arbitrary streaming TX, Control, handoff/reconnect, text/line/regex
conveniences, a generic command framework, Enhanced production and MCP remain
outside this slice. No physical/native-driver acceptance is inferred from fakes.

### Observed Checkpoints

These checkpoint executions overlap; their counts are not added together.
Earlier foundation/RED/GREEN counts and diagnostics remain in history.

| Checkpoint | Recorded result |
|---|---|
|T019 US1 MVP|Core/service/thin CLI and four authenticated two-shape/real-journal acceptance cases; full gate 10,392 passes.|
|T020–T022 US2|256 Core and 296 delivery assertions already GREEN; T022 no-change result and 7,641 focused passes.|
|T023–T025 US3|Two Core failures expose one pre-registration cancellation gap; T024 adds 64 already-GREEN lifetime cases; T025 corrects the gap, with 184 T023/64 T024 cases GREEN and 11,192 full passes.|
|T026 installed|192 guarded Interact cases (24 per artifact/host/backend cell) and 625 legacy process cases pass, 817 total; no shared-fixture edit.|
|T027 review|One v4 consistency defect corrected; four new regressions RED→GREEN, 1,507 Core/2,350 delivery passes and five fresh artifact audits. Full gate 11,393 passes; 197 installed Interact/artifact plus 625 legacy process cases (822 total).|
|T028 documentation|Evidence/progress reconciled and existing architecture explanation confirmed; fresh import-contract/doc/scope checks only. No code/test/contract or full-gate rerun.|
|T029 tooling|One code-only incremental Graphify update: 6,941 nodes/24,546 edges/302 communities, zero LLM tokens, no retry. Limits: 492 dangling edges, 178 duplicates, 918 directed/928 undirected collapsed edges; changed documents excluded and pyproject.toml unindexed. Navigation may be incomplete/corrupt; full limits remain in history.|
|T030 final closure|Fresh full gate: 11,393 passes, zero failures/errors/skips; Ruff/mypy142/seven import contracts/diff clean. Includes 197 Interact/artifact and 625 legacy process cases; five fresh artifact audits also pass separately. No production/test correction.|
|Final pre-commit review|One unpaired-v4-end timestamp invariant corrected; six RED→GREEN cases and780 focused passes. Fresh full11,399 passes, zero failures/errors/skips; Ruff/mypy142/import7, exact staged/index-export artifact/privacy checks pass. Implementation committed; nothing pushed.|

T027's full XML (/private/tmp/dutchmate-012-t027-full.xml) has zero failures/errors/
skips with warnings as errors. Its earlier standalone installed XML retains three
intermediate authoring/stale-artifact failures and is not final acceptance evidence.
The final full run includes all 197 cases in that module. T027 also verifies six
archives, 39 product modules per installation, 49 wheel/127 installed RECORD
entries, 25 locked external versions, non-editable imports outside checkout and
private/generated exclusions. Package/dependency/lock declarations remain unchanged.

The existing architecture explanation in Core §16 and rationale §15 remains
accurate; internal optional writers/owners stay within its established roles and
inward dependencies. No explanation or Core rule is changed. The 012 plan records
actual consumers, including the authorized Follow union extension and unchanged
terminal/server wiring. T030 final full/installed/artifact/privacy/Core review
passes without a new defect at that checkpoint. The subsequent pre-commit review
corrects only the self-contained v4 end timestamp check in sqlite_evidence.py,
with six new journal regressions. Final11,399-test/staged/installability/privacy
verification passes before commit; architecture explanation remains unchanged.
Native Linux/Windows serial/driver behavior, safe-open
DTR/RTS transitions/glitches, electrical pins/voltage/wiring, physical UART/DUT
receipt and Enhanced hardware/protocols remain outside software acceptance.

## Completed Feature: Receive-Only Live Follow (011; Software-Complete)

Artifacts: [spec](../specs/011-live-follow/spec.md),
[plan](../specs/011-live-follow/plan.md),
[research](../specs/011-live-follow/research.md),
[model](../specs/011-live-follow/data-model.md),
[contract](../specs/011-live-follow/contracts/follow.md),
[quickstart](../specs/011-live-follow/quickstart.md),
[quality checklist](../specs/011-live-follow/checklists/requirements.md) and
[tasks](../specs/011-live-follow/tasks.md).

**Progress: T001–T024 complete (24/24); Feature011 is software-complete and committed.**
Implementation commit: `:/^Implement live follow`, `Implement live follow`; accepted parent
`b6b043c50d8536d6569bbc52579f11a9eda5aa5e`. Phase1 remains incomplete; nothing pushed.
Task-specific notes below retain their historical checkpoint boundaries; current
authorization/validation are in Resume Here and the final pre-commit record below.
Sequential identifier follows010; no branch hook exists and Git remains main.
The ignored local Spec Kit pointer selects011. Pure values/state and private
coordinator registration/wakeup/pull are implemented in follow.py/monitor.py. One
T006 guard-order correction awaits the existing first RX reader before forbidding
extras. T009 adds runtime/composition only; no service/CLI, schema/Profile/backend/
dependency/lock change or Graphify update. Existing import coverage remains unchanged.

Foundation evidence:122 new pure tests (72 values/50 state),316 focused cases
including directly affected value regressions, full7073-test gate, Ruff/mypy110,
seven import contracts and diff/Markdown checks. Initial denied-loopback/empty
offline-cache run is recorded as failed in history; the unchanged tree passed the
full guarded rerun outside the sandbox with the populated uv cache. At foundation,
no separate Follow installed/live acceptance existed; hardware/native acceptance remains
unexecuted. Existing installed-process regressions are included in the full gate.

Implemented T007 mechanics: one coordinator registration captures actual committed
head and acknowledged provenance atomically under the append gate. One coalesced
Event hints all four append paths, including ambiguous-ACK possibilities. The same
live journal supplies fresh capped ranges to pure state; no copied RX queue,
retention pin, idle worker/polling, extra evidence clock sample or reader. Exact
records/gaps remain source facts, with no network-delivery position. Existing
Monitor ACK/publication/clock order is preserved. Close is subscriber-only.

At T007, T00654 passed, including all50 formerly missing-entry cases. Combined
required Monitor/annotation/journal/integration and foundation regressions518 pass
in1.92s; Ruff/mypy112/seven import contracts pass. Initial52-pass/2-fail run exposed
a test guard armed before the first scheduled RX reader; the existing first-read
checkpoint fixes only that test without weakening its extra-reader/connection guards.
No new full repository pytest/installed gate at this focused task; T005 remains
historical evidence. Tests prove only software behavior on this host.

T008 added RED tests only in `core/tests/contract/test_follow_runtime.py` and existing
`core/tests/contract/test_observation_composition.py`: optional capability default
None/valid/malformed transfer, current ACTIVE session checks/rejection precedence,
captured-generation revalidation, independent single subscriber/one pull/eight
shared submitted-read leases/no idle lease, cancelled start/result cleanup,
synchronous seal/wakeup, final cutoff/join-before-close, unchanged v1/v2 and explicit
v3 preparation. T008 adds no production behavior. Its RED selection:89 expected
missing-feature failures/8 prerequisite passes, no collection/teardown errors.
Those failures identified missing runtime entry, optional transfer or production wiring.
T009 now executes all deeper assertions GREEN. At T008, existing runtime/composition/
read/Monitor/annotation and T006 regressions:760 pass. Targeted Ruff/mypy2 and seven
import contracts pass. A new test-helper import cycle was corrected before this run.

T009 adds immutable optional Follow access matched to the actual coordinator/live
reader/session/policy. Admission captures the current generation before any await;
one subscriber/pull uses the existing eight submitted-read leases and no idle lease.
Cancellation joins query work and unregisters only the captured subscriber. Detach,
natural termination and the exposed synchronous `_seal_follows()` stop latch seal
and wake without waiting for delivery. After acquisition/Monitor/annotation join,
one optional final metadata head precedes read joins/unregister and recorder close.
Unknown/frozen end facts and permanent008 cleanup/release facts remain authoritative.
Production adds the capability to its existing explicitv3 preparation; v1/v2 remain.
One T008 helper cast retains its synchronous-None assertion after the real typed
method exists. No other test/fake or T007 implementation change.

T009 GREEN:97 T008 cases pass;857 required combined cases and1302 expanded focused
cases pass, zero failures/errors/skips. Ruff/mypy113/seven import contracts pass;
scope and diff checks are clean. These overlapping selections are not added.
No new full repository pytest/installed gate at this focused task. T005 is historical.
At T009, service stop wiring remained T011; exposing the latch was not HTTP acceptance.

T010 added RED tests only in `apps/service/tests/test_follow_http.py`: literal route/
readiness and16KiB closed request/session bounds, exact rejection/journal mappings,
five frame/seven record projections/provenance/gaps, no-store/security-before-body,
independent Follow job vs existing slots, pre-header oversize/post-header terminal/
EOF,1s heartbeat/5s send bound, actual guarded loopback where ASGI buffers.
The real app, auth/body gates and job owners are exercised with typed Core facts
at runtime entry; no service behavior or Core policy is implemented by the tests.
Six actual guarded Uvicorn/IPv4/IPv6 loopback cases author incremental/heartbeat
expectations. Final160 cases:136 missing-route failures, one missing synchronous
request_stop seal,23 planned existing security/alias passes; no errors/skips.
At T010, deeper streaming/capacity/deadline assertions remained unreachable.
Actual loopback received404 then; T011 now verifies successful Follow delivery.
Ruff/mypy114/seven import contracts pass;1466 old service HTTP/runtime/read/Monitor/
annotation regressions pass. Initial test-probe/Uvicorn setup defects were corrected
before final RED measurement. All existing production/config/tests match entry.

T011 adds only service Follow in new follow_http.py and existing app.py/http.py.
The literal authenticated route strongly registers one independent stream owner
before Core admission, preflights started before200, then projects the existing
seven records/markers/provenance with the unchanged evidence encoder. It retains
one bounded page/frame, one pending pull/send,1s delivery-only heartbeats and5s
cooperative sends; failures preserve the offered prefix or close an unusable peer.
Cancellation joins subscriber cleanup without detaching capture. request_stop
synchronously seals/wakes Follow before HTTP drain through the existing launch
context; server.py already invokes that hook and stays unchanged. Lifespan joins
cancelled stream cleanup before the unchanged final detach/bootstrap release.

Fresh T010 baseline:137 expected failures/23 planned passes. First implementation:
116 pass/44 fail, exposing two T010 oracle mistakes: rewriting stdlib short control
escapes contradicted008§6, and old read/Monitor overflow expected invented service
codes instead of existing operation_capacity. Only that helper/two literals changed;
reversing them reproduces T010 entry bytes exactly. All160 cases then passed.
A focused diagnostic also reproduced/fixed cancellation before the new owner task's
first step, ensuring its finally joins the receive observer and settles admission.

Final T011 GREEN:1862 combined required service HTTP/runtime/process/evidence/
Monitor/annotation plus directly affected existing lifetime cases pass in78.42s,
zero failures/errors/skips. This includes all160 Follow and38 existing installed
service-process cases. Ruff/mypy115/seven import contracts pass. No Core/CLI,
evidence_http.py, server.py, old test/fixture, dependency or import configuration
change at T011. T005's full7073 gate is historical; no new full repository or
installed Follow gate is claimed. Full checkpoints remain T013/T019/T024.

T012 adds only apps/cli/tests/test_cli_follow.py. The actual console/Typer/HTTPX
path uses existing isolated credentials and test-owned external raw byte streams;
no fake command, frame parser/validator, Core/service policy or capture behavior.
Hand-declared existing golden fixtures supply seven records/provenance/markers.
Coverage includes exact grammar/help/local validation, one credential/request,
closed NDJSON/identity media/five frames, sequence/gap/terminal facts, all256 RX
bytes, canonical output,1MiB+LF arbitrary chunk framing, bounded accumulators,
incremental flush/no transcript,10s handshake/5s complete-frame trickle deadlines,
no whole-session limit, clean terminal/abnormal EOF exits, Ctrl-C130 and broken
pipe. A controlled loop monotonic source drives real asyncio timeout callbacks;
an independent diagnostic confirms cumulative deadlines and fresh frame budgets.

Final T012 RED:235 expected failures/38 planned local-input prerequisite passes
in4.17s, zero collection/teardown errors/skips.233 failures identify missing Follow
command/help and two identify its missing streaming module. The38 passes exercise
existing private invalid-input/resource-free rejection; deeper Follow assertions
were authored then and now reach GREEN at T013. Existing command/finite transport/
evidence/Monitor/annotation regressions1775 pass in27.10s. Ruff/mypy116/seven import
contracts pass. Before recording, all252 protected existing inputs match entry.
No existing production/test/fixture/config/dependency changes, full repository
pytest or installed Follow gate at this focused RED task; T005 remains historical.

T013 implements only the narrow streaming command/validation in new CLI follow.py
and additive main.py/client.py blocks. Existing evidence validators, JSON decoder/
encoder, diagnostics and cooperative output are reused. One bounded partial frame
and chunk offset feed closed started/record/gap/heartbeat/terminal validation with
an independently checked received position. A10s absolute handshake ends at the
first complete started frame; fresh5s complete-frame budgets exclude preceding
output and cannot be extended by trickle bytes. Terminal requires clean EOF within
its existing budget. No whole-session deadline, transcript, UART text decoding,
retry/reconnect, Core/service import or finite-exchange relaxation.

T013's four actual guarded Uvicorn IPv4/IPv6 cases run the real CLI/HTTPX client,
authenticated app, runtime/coordinator/v3 journal and both backend fixtures.
Monitor, annotation and active retrieval coexist with Follow; exact records/all256
RX bytes, attributed assertion, reported loss and genuine origin boundaries agree
with retrieval. A cooperative CLI interrupt closes the subscriber, capture stays
ACTIVE and later RX commits; a replacement view starts at the fresh tail. Service
stop delivers its unknown-cutoff terminal before HTTP drain/recorder teardown.
No extra backend/RX reader/journal connection is permitted. OS-signal/installed
Follow validation remains T020; these fixtures prove software neutrality only.

Fresh T012 baseline235 RED/38 prerequisite passes became273 GREEN in2.57s;
four US1 cases pass in5.37s. Combined required CLI selection2052 passes in33.78s.
Full US1 gate:7661 pass in502.66s (Core2790/service2063/CLI2808), zero failures/
errors/skips; includes529 existing CLI process-suite and38 service-process cases.
Ruff/mypy117/seven import contracts/diff pass. The initial full run had7137 passes/
524 setup errors solely because the temporary offline cache lacked Hatchling;
two installed packaging probes passed with the populated cache, then the unchanged
tree passed the full rerun. No production/test/dependency workaround was used.

Only CLI follow.py and additive client.py/main.py plus appended US1 tests changed
at T013. Removing the added blocks reproduces finite client, existing commands
and all original T012 test bytes exactly. Core/service/old tests/fixtures/schema/
Profile/backend/validators/dependency/import configuration remain unchanged.
This is the US1 MVP checkpoint, not full011 or Phase1 closure.

T014 adds only core/tests/contract/test_follow_retention.py:52 cases over realv3
journals and both backend shapes. All are already GREEN: minimum active policies,
record/page charge edges, eviction before/during/after materialization, repeated
adjacent gaps, exact missed-range/head intersection, unchanged whole-prefix counts/
charges and distinct timestamp domains, Monitor/annotation interleaving and no
retention pinning. Exhausted-MAX and malformed zero-progress fault cases are
explicitly injected; oversized-first-record cases use actual003 shortage pages.
There is no production/old-test/shared-fixture change or genuine defect to defer
from T014 to T016. An initial18 failures came solely from the new tests mixing
direct append with the backend probe's queue; only those new sample calls changed.
Fresh52 pass in5.41s; combined1777 pass in7.39s, zero failures/errors/skips;
Ruff/mypy118/seven import contracts pass. No full repository gate was repeated at
this focused test-only task; T013's7661 passes remain historical evidence.

T015 appended163 delivery-edge cases only to apps/service/tests/test_follow_http.py
and apps/cli/tests/test_cli_follow.py. All47 service cases pass, including four
guarded IPv4/IPv6 actual-runtime/v3-journal worker-blocked heartbeat cases with
both fake backends. At T015, CLI110 passed/six genuine cases were RED: Follow
printed incoherent retention markers and accepted the subsequent valid terminal
with exit0. All six are now corrected at T016 below. Cases
cover mismatched/zero whole-prefix counts, non-prefix expired range, first-only/
last-only endpoints and timestamp/domain ID mismatch. Contract§5 requires coherent
whole-prefix facts; these checks do not rederive discarded byte counts or compare
timestamp values across domains. Existing shape-only marker validation missed
the relationships. No production/shared-validator/old-test fix was made at T015.

All other new cap/escape/base64/seven-variant/nested duplicate/unknown/NaN/bool/
sequence/delimiter/partial EOF/trailing/identity/framing/trickle/send/accumulator/
private-diagnostic cases are GREEN. Opaque field-array order remains preserved
under008; JSON object key reordering is accepted and canonicalized. Original
T010/T012/T013 helpers/tests remain byte-identical after removing only three
new service imports and appended T015 blocks. New harness mistakes were corrected
only in those blocks; no failure was hidden with skip/xfail or weaker assertions.

Focused delivery validation:4033 passed/six failed in126.81s; zero errors/skips,
all3876 selected pre-existing cases passed. Ruff/mypy118/seven import contracts/
format/diff pass. No full repository/installed Follow/native/hardware gate was
rerun for this focused test-only task; T013's7661 passes remain historical.

T016 changes only the gap branch in apps/cli/src/dutchmate_cli/follow.py's
Position.accept. It requires an expired prefix starting at0, a matching whole-prefix
record count, both timestamp endpoints present or both absent, and each timestamp's
domain_id equal to its own descriptor. All checks precede received-position
advancement/output. Nonempty missed-range containment remains required. No byte/
charge count rederivation, cross-domain timestamp comparison, metadata rewrite,
new public helper or Core/service/shared-validator/test change.

Consumer inventory: client.exchange_follow creates Position and _follow_frame calls
accept before encoding; its existing private invalid_response/exit5 path handles
the new rejection. main.follow's output/diagnostic path is unchanged. Shared
evidence._marker/_endpoint and primitive validators remain unchanged, including
finite exchange_evidence -> _evidence_reply -> evidence.reply. Other Follow branches,
framing/deadlines, opaque array order and valid gaps/terminal facts remain unchanged.
Core/journal/service producers already supply coherent facts; no upstream fix.

Fresh unchanged T015 coherence cases: six RED/six controls in0.18s became12 GREEN
in0.19s. Combined full T014/T015 test files plus required003/008–010 regressions:
5816 passed in155.04s (Core1777/service1871/CLI2168), zero failures/errors/skips.
Edge-file counts:52 Core retention/207 service Follow/393 CLI Follow; all652 pass,
plus5164 other regressions. Ruff/mypy118/seven import contracts/format/diff pass.
Only Follow-local validation changed; the next planned full gate remainsT019,
and T013's7661-test pass is historical. No full repository/installed/native/hardware
gate was repeated at this focused correction.

T017 adds only core/tests/contract/test_follow_lifetime.py:120 cases,60 per backend
shape, with real journals and deterministic append/query/result gates. Coverage
includes pre/post-registration cancellation, idle/submitted pull cancellation,
reentrant pull/close waiter loss/read capacity, detach vs RX/Monitor/annotation/
ordinary reads, synchronous seals and source/stop precedence, known/unknown immutable
cutoffs, prefetched-tail discard without a Core delivery claim, uncertain writer/
terminal-reader cleanup and old preparation/replacement-generation isolation.
Native worker gates verify24 submitted/materialized start/head/page read races;
teardown joins resource work before recorder close and finishes independently of
a gated consumer return. No socket, delivery adapter or physical device is needed.

All120 new cases pass in0.72s with warnings treated as errors. The combined23-file
Core selection passes1844 cases in11.13s (1724 existing), zero failures/errors/skips;
Ruff/mypy119/seven import contracts/format/diff pass. Initial112 passes/eight
failures/two warnings exposed only new-test enum/cleanup/task-wrapper mistakes;
those harness issues were corrected without production/shared-fixture changes.
No genuine T017 defect is deferred to T019. Entry hashes protect all existing
production/tests/configuration and governing contract bodies. No full repository,
service/CLI/loopback/installed/native/hardware gate was run at this Core-only task;
the next planned full checkpoint remains T019.

T018 adds only apps/service/tests/test_follow_lifetime.py:90 cases covering client
loss before/during admission, pending pulls and sends, strong registration/cleanup
and slot release under repeated cancellation, native query joins before final
detach, five-second send expiry despite progress, terminal offered-prefix/cutoff/
EOF honesty and no-store/security-before-body while stopped cleanup owns the slot.
Thirty-six cases use both actual normalized backend fixtures and real journals.
Eight actual guarded IPv4/IPv6 loopback cases verify peer disappearance with
continuing Monitor/annotation/read/RX and synchronous stop before controlled-server
HTTP drain, heartbeat during a submitted native query, discarded unoffered payload,
unknown terminal cutoff/clean EOF before app lifespan recorder cleanup.

All90 cases already GREEN:82 local cases in21.27s and8 loopback cases in5.17s.
Combined12-file service selection:2089 passed in132.49s (1999 existing), zero
failures/errors/skips, warnings treated as errors. Includes006 HTTP/runtime/
bootstrap/process,008 evidence HTTP/read,009 Monitor HTTP/lifetime,010 annotation
HTTP/lifetime and prior011 Follow HTTP tests. Ruff/mypy120/seven import contracts/
format/diff pass. Initial failures were new-test finite-response/annotation-input
and borrowed-lifespan fixture mistakes; corrected only in the new test file.
No genuine T018 defect is deferred to T019. Entry131 protected inputs prove all
production, existing tests/shared fixtures/configuration/contracts unchanged.
No repository-wide pytest or new installed Follow/native/hardware acceptance was
run; T019 remains the next planned full gate. Existing guarded006 process tests
are included, without claiming installed011 Follow acceptance ahead of T020.

T019 is a no-change hardening checkpoint: no validation/review defect required
production or test correction. Both lifetime suites pass all210 cases unchanged.
Required43-file focused selection:6240 passed in188.46s (Core1895/service2089/
CLI2256), zero failures/errors/skips. Covers005/006/008–010 lifecycle/read-cleanup/
security/Monitor/annotation and existing Follow boundary/retention/finite CLI cases.
The subsequent full combined US2/US3 gate passes8086 cases in567.03s
(Core2962/service2200/CLI2924), zero failures/errors/skips, warnings treated as
errors. Ruff/mypy120/seven import contracts/diff pass. Existing guarded installed
service/finite CLI process tests were included; no new installed Follow test existed at T019.

Final checkpoint diff review confirms existing single RX/journal/worker ownership,
coalesced append hints and Monitor timing, captured-generation/read cleanup and
seal/frozen-cutoff facts, independent service job/security/no-store/send behavior,
and thin CLI framing/received-prefix validation. Finite client/main ASTs match
the committed baseline after excluding only their Follow additions. Entry135
protected inputs remain unchanged until documentation-only result recording;
no executable/configuration or normative contract change. Progress headers only
are reconciled in011 artifacts, including the model/contract/quickstart, with no
new recipe, installed acceptance or future task implementation. The next planned
full checkpoint is T024; T021 corrections still require their specified rerun.

T020 adds only apps/cli/tests/test_cli_follow_process.py:96 guarded installed
cases using unchanged non-editable wheel/sdist builders and outside-checkout
service/CLI children. All workflows run on both backend fixtures/numericIPv4+IPv6:
incremental exact RX with concurrent Monitor/annotation/ordinary reads,11 real
heartbeats beyond the10s handshake bound, actual retention eviction/gap, independent
Follow/read capacity, pre-header/source errors, policy-legal oversized RX, Ctrl-C,
closed pipe, normalized disconnect, detach, abnormal EOF and joined service stop.
Installed imports, one credential/request, private output and physical/account/
discovery guards remain asserted. Shared helper/fake files are unchanged; all
extensions and assertion-failure pipe cleanup are local to the new test module.

Combined installed selection:625 passed in526.36s, zero failures/errors/skips,
warnings as errors (Follow96, CLI112, evidence111, Monitor153, annotations153).
Initial pilot9 passes/2 failures were new-harness defects: invalid6000ms Monitor
test input and consequent unreaped-pipe warnings. Corrected only the new module
to4000ms, bounded progress waits and local child cleanup; pilot11 passes, then the
complete625-case run passes. No production defect/correction or shared-file edit.
Ruff/mypy121/seven import contracts/format/diff pass. Entry135 existing inputs
remained byte-identical until observed documentation/progress recording. No new
repository-wide pytest was required/run; T019's8086 full pass remains historical.

T021 reviewed the complete011 production/test/configuration/documentation diff
against Core, active spec/plan/model/contract/tasks, completed003/005–010 contracts
and current status. No production defect, correction or consumer migration was
required. Same-journal ordering/provenance, four append paths/Monitor timing,
generation/read-cleanup ownership, synchronous stop sealing and secured independent
delivery remain coherent. AST comparison preserves finite CLI client/main code
after excluding Follow additions and preserves the shared read-submission logic.
Legacy codecs, package metadata, lockfile, backend fakes and old tests are intact.

Fresh22-file focused selection:3444 passed in115.42s (Core979/service297/CLI2168).
Fresh installed selection:625 passed in525.55s (Follow96/CLI112/evidence111/
Monitor153/annotations153), both fixtures/numericIPv4+IPv6/wheel+sdist outside
checkout. Both have zero failures/errors/skips, warnings as errors. Ruff/mypy121/
seven import contracts/diff pass. Read-only inspection of26 fresh archive files
and10 non-editable environments confirms exact module/source/test bytes, metadata/
Python requirements, console entry, locked dependencies and private/generated
exclusions. Wheels contain product modules/metadata; public Python tests remain
in sdists. Existing builders/guards were reused unchanged.

Quickstart now names the two actually executed guarded pytest selections and
their observed coverage; test-only guard PYTHONPATH is distinguished from absent
checkout product/editable fallback. No invented standalone fixture launch or
manual credential/device step. Only documentation/progress changed at T021;
all136 protected entry files matched until this recording. No executable or
governing-contract correction required a full rerun; T0198086 full passes remain
historical and T024 final validation remains unexecuted.

T022 reconciles only completed evidence/progress and acceptance limits. Prior
reports agree with the recorded results: T0198086 full, T020625 installed,
T0213444 focused/625 process, zero failures/errors/skips; T02126 archive files/
10 installations/196 wheel RECORD entries audited. These are historical results,
not T022 reruns. The tested executable/configuration tree remains unchanged.

Core§16 review confirms actual inward dependencies and ownership: deterministic
Core owns generation/order/journal-query cleanup; the service owns its runtime,
secured local HTTP and strong stream jobs; the thin CLI owns only its HTTP/output
delivery. Follow uses the same live journal/coordinator/read leases and single RX
path. Client exit is subscriber-only, and recorder cleanup does not depend on an
idle socket. Existing authentication/browser rejection and no-store remain at
the delivery boundary; MCP stays deferred. Fresh import-linter keeps all seven
contracts (73 modules/274 dependencies). Source/ownership inspection agrees with
Core§16 and the existing rationale§§6/15 explanation. That explanation remains
accurate; no architecture document or Core/rationale/README change was needed.

Updated only observed status/history and011 progress, including stale global
footer stop/installed-acceptance references. Quickstart's executed commands and
normative spec/plan/model/contract/task definitions remain unchanged. T022 ran
documentation/link/scope/diff checks and import-linter only; no new pytest,
installed process/artifact build or full gate. T024 fresh final verification is
pending. Committed001–010 remain unchanged at the same010 HEAD; Phase1 and
Feature011 remain incomplete. Software evidence is macOS/arm64 Python3.14.3 only;
native Linux/Windows, active-DUT, physical/electrical/safe-open and Enhanced
production/hardware acceptance remain unexecuted. Actual Windows commands remain
unsupported; the Enhanced-shaped fixture proves software neutrality only.

T023's separately authorized scope is to read agent tooling and the Graphify skill,
evaluate the final011 structural/shared-interface trigger, and if triggered perform
one code-only incremental update. Previous feature runs do not satisfy it. Keep
outputs/backups/local tooling ignored/excluded; never read graph.json directly.
If the run stalls/fails, stop/report without an unauthorized retry; record actual
outcome/limits in history/status. At T022, T023–T024 remained unstarted. No T023 trigger
decision, Graphify invocation, physical hardware, commit or push occurred at T022.

T023 evaluated actual final011 code against agent tooling and the local Graphify
skill. The trigger is met: new Core/service/CLI Follow modules and changed shared
coordinator/preparation/runtime/service-job/client interfaces. One Graphify0.9.48
code-only incremental update succeeded in5.478s, with normal lock/shrink guards,
no force/full rebuild/semantic extraction/LLM:6095 nodes/20503 edges/254 communities
(+659/+2448/+8 from010). Selected23 changed code/config files:22 Python (ten
product/twelve test) plus pyproject.toml; all22 Python AST stamps match current
bytes.16 changed documents were excluded from extraction; unchanged sources
provided resolution context. No retry or separate labeling run occurred.

Graph-health warning:289 dangling endpoints,244 directed/246 undirected collapsed
same-endpoint edges; zero missing endpoints/self-loops/unverified code nodes.
These limit navigation accuracy and are not repaired by this task. pyproject.toml
produced zero nodes and remains unstamped; no retry.92 changed community labels
were regenerated deterministically. HTML aggregates254 communities/724 links;
report shows212 of254 communities and counts256 code-corpus files versus258 in
the full detector. No raw graph.json content was read directly by the agent.
Native outputs/five-file backup and local tooling remain ignored/untracked;
temporary old-graph backup was removed after success. Cost record adds zero input/
output tokens. Source/configuration/001–010 identity, documentation consistency,
ignore/exclusion and diff checks pass. No tests/full gate/installed flows rerun
at T023; T024 is still the fresh final checkpoint. Phase1 remains incomplete.

T024's exact remaining scope is the fresh Ruff/mypy/import-linter/pytest/diff
gate and non-editable wheel/sdist installability/compatibility/privacy review,
including guarded Follow and007–010 process suites; review Core/contract/complete
diff/artifact scope. Correct genuine defects only with focused evidence and rerun
the full gate after corrective executable/governing-contract changes. Record only
completed progress, report011 software readiness/Phase1 incompleteness/native,
physical and Enhanced limits/exact next action, then stop for separately authorized
pre-commit review. No T024 work, further Graphify, hardware, commit or push is
authorized by T023.

T024 fresh final checkpoint passed without a genuine defect or corrective code/
test/shared-fixture/configuration/governing-contract change. Ruff is clean; mypy
checks121 source files; all seven import contracts are kept (73 modules/274
dependencies). Full pytest passes8182 cases in724.907s (JUnit), zero failures/
errors/skips, warnings as errors. The same full run includes all625 required
installed process cases:96 Follow/112 CLI/111 evidence/153 Monitor/153 annotations;
these overlap the full total and are not a separate added count. Both backend
fixtures, real journals, numeric IPv4/IPv6 and non-editable wheel/sdist children
outside checkout execute with independent physical/discovery/account guards.

Fresh read-only artifact audit passes26 archives/10 isolated installations/
196 wheel RECORD rows (183 payload hashes/sizes). Exact product/source/test/config bytes,
metadata/Python range/console entry, locked runtime closure and non-editable
installation targets match; no credential/journal/private/generated/agent output
is packaged. Complete33-file Feature011 review covers ten product modules, twelve
test files, root import coverage and ten documentation/specification files. Core/
011/completed003/005–010 conformance is clean: single RX/journal/worker, atomic
tail/provenance, bounded gaps/pages, strong generation/query/job ownership,
synchronous seals before HTTP drain, honest offered/unknown cutoff facts, inward
dependencies and existing local security. No architecture rewrite is needed.

Finite client/main AST, prior read/cleanup and annotation helpers and original
composition assertions remain unchanged;187 protected baseline inputs match HEAD.
All258 entry files matched before recording, and only observed progress/history
documents changed afterward. Documentation/link/fence/task-marker/stop/scope and
working/staged diff checks pass. All24 tasks are checked. Graphify was not rerun;
T023's actual outcome/navigation limits remain historical. No physical device,
real-account credential, commit, push or next slice was selected/performed.

Feature011 is software-complete on macOS/arm64 Python3.14.3 and remains uncommitted.
Phase1 remains incomplete. Native Linux/Windows, active-DUT, physical/electrical/
safe-open/OS-driver loss/re-enumeration and Enhanced production/hardware acceptance
remain unexecuted; actual Windows commands remain unsupported. The simulated
Enhanced-shaped fixture proves software neutrality only. TX/Interact/console,
Control, release/reacquire/handoff/reconnect, text/regex/history, MCP/AI and other
Phase1 work remain deferred. The next action is exactly: **Await separate authorization for final Feature011 pre-commit review.**
T024 stops here; no automatic commit/push/Graphify/hardware or new slice.


The separately authorized final pre-commit review passed without a genuine011
defect or correction. Reviewed the complete33-file change set against Core,
011 spec/plan/model/contract/tasks, completed003/005–010 and current status.
Finite client/main, read/cleanup/annotation helpers and original composition
assertions retain their established behavior;187 protected baseline inputs match
the accepted010 parent. No Core/schema/Profile/backend/dependency/architecture
change or hardware acceptance claim was added.

Fresh pre-commit gate: Ruff clean; mypy121 files; all seven import contracts kept
(73 modules/274 dependencies);8182 full tests pass in727.597s (JUnit), zero
failures/errors/skips, warnings as errors. The625 installed cases are included:
96 Follow/112 CLI/111 evidence/153 Monitor/153 annotations, both backend fixtures,
real journals/numeric IPv4+IPv6/non-editable wheel+sdist outside checkout, with
independent hardware/discovery/account guards. No new fixture or production fix.

Staged verification starts with all258 index/worktree inputs identical and the
exact33 intended files. Full-run artifact audit passes26 archives/10 environments;
an additional258-file index export independently builds all three wheel/sdist
packages and passes guarded installed entry/direct Follow help and installed
module imports outside both checkout/export. Its six archives/two environments
also pass exact source/test/config/metadata/locked-dependency/entry/.pth/direct_url/
privacy checks against staged blobs. Total:32 archives/12 environments/
242 RECORD rows (226 hashed payloads). No credential/network work in smoke
children; no checkout/editable product fallback. Staged diff/stat/names/content/
cached whitespace exclude unrelated/generated/runtime/credential/Graphify/local
tool files. No Git hooks are installed; Graphify is not rerun. Generated outputs,
backups and local tooling remain ignored. Final result recording changes only
progress/history documents; executable/governing bytes still match the tested
index, so documentation consistency/diff checks apply without another full run.

Feature011's implementation commit is `:/^Implement live follow`, `Implement live follow`,
with accepted parent `b6b043c50d8536d6569bbc52579f11a9eda5aa5e`; prior baseline
commits remain ancestors. The title reference resolves to that commit without
a self-referential hash. Nothing was pushed. Phase1 remains incomplete; existing
macOS/arm64 Python3.14.3 software evidence does not prove native Linux/Windows,
active-DUT, physical/electrical/safe-open or Enhanced acceptance. Actual Windows
commands remain unsupported. No physical device was accessed or next slice begun.

## Completed Feature: Client Annotations (010; Software-Complete)

Artifacts: [spec](../specs/010-client-annotations/spec.md),
[plan](../specs/010-client-annotations/plan.md),
[research](../specs/010-client-annotations/research.md),
[model](../specs/010-client-annotations/data-model.md),
[contract](../specs/010-client-annotations/contracts/annotations.md),
[quickstart](../specs/010-client-annotations/quickstart.md),
[quality checklist](../specs/010-client-annotations/checklists/requirements.md) and
[tasks](../specs/010-client-annotations/tasks.md).

**Progress: T001–T024 complete (24/24); Feature010 is software-complete.**
Phase1 remains incomplete. Features001–010 form the committed software baseline.
Numbering is sequential after009; Git remains main, with no branch hook configured.

Core/runtime/v3 persistence, authenticated service and thin CLI annotation are
implemented. Assertions remain exact bounded client-supplied context, explicitly
client_assertion/client_asserted. They use the existing recorder gate, host clock,
ordinary sequence, retention and active/confirmed-close terminal retrieval. The
incarnation limiter and per-run strongly owned insertion preserve existing
005 lifecycle,008 read-cleanup uncertainty and009 Monitor post-ACK timing.
V1/v2/Profile-v1 and all six prior codecs/charges remain compatible; no migration,
new backend contract/reader/store, dependency or verified-identity claim.
Exact product contracts remain in Core and the active010 spec/contract.

Completed checkpoint evidence is summarized below. Detailed RED/GREEN results,
consumer inventories, corrections, commands and limitations are preserved newest
first in [development history](development_history.md); counts are separate runs,
not cumulative and not hardware acceptance.

| Completed checkpoint | Recorded evidence |
|---|---|
| T001–T005 foundation | Pure values/codecs and explicitv3 journal/read-only terminal;592 focused/5936 full passed. |
| T006–T009 coordinator/runtime | T006 RED made GREEN at T007;1264 focused passed. T008's101 RED cases made GREEN at T009 within2720 focused tests. |
| T010–T013 delivery/US1 | T011:1820 service regressions passed. T013: all300 T012 cases GREEN, end-to-end active/terminal retrieval verified;6552 full passed. |
| T014–T016 bounds/retention | Four genuine timestamp-provenance failures corrected at T016 with one bounded v3 committed segment descriptor;51 retention/6194 compatibility passed. No unresolved defect. |
| T017–T019 lifetime/combined hardening |56 Core/44 service new cases already GREEN; no correction needed.3181 focused/6798 full passed, zero failures/errors/skips. |
| T020 guarded installed flows |529 passed (153 new annotation/376 existing CLI/evidence/Monitor process cases); non-editable wheel/sdist, both backends, IPv4/IPv6. |
| T021 complete-diff/artifact review | No production/test correction.1276 focused/44 installed passed;14 archives and four stack/two CLI-only installs reviewed; all33 product modules/locked dependencies/private-artifact exclusion verified. |
| T022 documentation/conformance | Completed evidence/progress/limits reconciled; Core16 and all seven import contracts conform. Documentation/diff/scope checks pass; no new test run or full gate claimed. |
| T023 final code Graphify | Structural/shared-interface trigger met; one code-only incremental update completed in5.853s:5436 nodes/18055 edges/246 communities, zero tokens.36 code sources stamped; pyproject.toml yields zero nodes. Built-in sequential fallback and graph-health limits recorded in history; outputs/backups/tooling ignored. |
| T024 fresh final verification |6951 passed in464.54s, zero failures/errors/skips (Core2517/service1903/CLI2531); Ruff/mypy107/seven import contracts/diff pass. Includes all529 installed-process cases.20 fresh archives and six full-stack/two CLI-only installs pass source/metadata/import/locked-dependency/privacy review. No corrective change. |

T024 is the fresh final full gate:6951 passed in464.54s, with Ruff, mypy107
files, seven import contracts and diff checks clean. Its529 installed-process
cases include153 annotation and376 existing CLI/evidence/Monitor regressions,
not an additional test run. Fresh wheel/sdist source/metadata/RECORD/import and
privacy review passed across20 archives and eight non-editable environments.
No genuine Feature010 defect or corrective change was found; no full-gate rerun
was needed while closing T024. The separately authorized staged review/commit is
recorded below. Software validation does not establish native/physical acceptance
or Phase1 completion.

**Core §16 conformance:** deterministic annotation admission/limiter/ordering and
evidence ownership stay in Device Core. Service composition owns the sole backend,
coordinator and journal; FastAPI/HTTP models and security stay in delivery. The CLI
uses one authenticated local HTTP request without Core/service imports, direct DUT
access, policy duplication or retry. Authentication/browser rejection and independent
read/Monitor ownership remain intact. No MCP/AI/external-program feature was added.
The existing Service/Core/CLI layer directions and ownership relationships are
unchanged; internal annotation module additions are documented in the active010
artifacts. Core and its architecture explanation need no update, and no design
document was created. T024 import-linter:70 modules/249 dependencies, seven kept/
zero broken.

T023 evaluated final010 module additions and shared evidence/preparation/runtime/
delivery interfaces against the tooling trigger. Graphify0.9.48 processed only37
changed code/configuration paths;18 changed documents were excluded. Its parallel
workers failed because the temporary launcher lacked a multiprocessing main guard;
the tool's built-in sequential fallback completed the same invocation. No second
update, semantic extraction, LLM, force override or direct graph.json read occurred.
Health diagnostics found392 dangling-endpoint candidates,115 exact duplicates and
690 undirected same-endpoint collapsed edges; no missing endpoints/self-loops/
unverified code nodes. These are navigation limits requiring source verification.
The >5000-node HTML uses246 community nodes;79 stale labels were renamed by hubs.
All36 selected Python sources have current AST stamps; root pyproject.toml remains
unstamped after yielding zero nodes. Generated outputs and five curated backups
remain ignored. All109 source/configuration hashes match task entry.

At the010 commit checkpoint the next action was to await human direction.
That direction now selects011; its current authorization boundary is in Resume
Here. The completed010 commit task itself authorized no next slice or hardware.

T024 task evidence remains /private/tmp/dutchmate-010-t024-96i7fh5x/.
The separately authorized pre-commit checkpoint freshly validated an exact236-blob
index export:6951 passed in471.58s, zero failures/errors/skips; Ruff/mypy107/
seven import contracts/diff clean. Includes all529 installed-process cases. Fresh
20-archive/eight-install source/metadata/RECORD/import/dependency/privacy review passes.
Final review found no genuine defect. Scope:16 production,20 test and11 spec/status/
configuration files. Eight old codec/helper and29 CLI transport definitions retain
their committed009 AST;219 prior test functions retain coverage, including one
explicitv2-to-v3 composition-test rename. No unrelated/generated/runtime/credential/
Graphify/local-tooling file is staged. Final result/commit-baseline documentation
uses consistency/diff/blob checks under AGENTS8.3; no executable/governing contract
or validation requirement changed and no extra full-gate rerun was needed.
Evidence: /private/tmp/dutchmate-010-precommit-q_r9_4w8/. No Graphify rerun, physical hardware/real-account credential
access, native acceptance, push or next slice. Acceptance limits below remain.

## Completed Feature: Receive-Only Monitor (009; Software-Complete)

Artifacts: [spec](../specs/009-receive-only-monitor/spec.md),
[plan](../specs/009-receive-only-monitor/plan.md),
[model](../specs/009-receive-only-monitor/data-model.md),
[contract](../specs/009-receive-only-monitor/contracts/monitor.md),
[research](../specs/009-receive-only-monitor/research.md),
[quickstart](../specs/009-receive-only-monitor/quickstart.md),
[quality checklist](../specs/009-receive-only-monitor/checklists/requirements.md) and
[tasks](../specs/009-receive-only-monitor/tasks.md).

The specified bounded receive-only Monitor is implemented through Core/service/CLI.
T001–T037 are complete (37/37). Feature 009 is software-complete within its
specified scope; implementation commit `:/^Implement receive-only monitor` retains
008 as its accepted parent. Phase 1 remains incomplete.
Current progress lives here; detailed RED/GREEN commands, corrections, per-file reasons
and completed-slice evidence remain in [history](development_history.md).

### Implemented scope

The application owns one finite literal-byte Monitor over the existing authoritative
acknowledged stream. Its committed start marker installs matching/deadline atomically;
the first decision freezes its record window, examined-byte count and byte endpoints.
It keeps bounded prefix state, preserves whole RX/trailing/ambient chunks and never
creates another reader, transport or journal. Host timing remains distinct from
backend observation clocks; start positions claim observation order, not causation.

Operation markers use explicit schema-v2/record-v2 through the existing journal
gate/worker/order/charge/rolling retention. Default v1 factories and old four codecs,
generic provenance-v1, Profile-v1 and 003 retrieval/cursor/snapshot/outcome semantics
remain intact. Active reads use the same journal; expected-version terminal reads
remain fresh verified read-only transactions after confirmed writer close, with
native identity/session/policy checks and permanent 008 cleanup uncertainty.

Optional prepared access preserves legacy attach-only construction. Present support
must identify the transferred recorder/coordinator/session/policy and same clock;
T033 corrected transfer validation for mismatched or stale support before backend
open. Six regression cases on both fixture shapes first failed, then passed. T005's
explicitly authorized union-compatibility narrowing and all earlier corrections
remain documented with affected files/reasons in history.

The authenticated literal POST and thin CLI command accept only the four required
inputs in the contract, project the closed 14-field report and add exactly two
evidence shapes. Condition 1..256 bytes, timeout 1..4000 ms, RX 1..1048576 bytes,
body 16384, cursor 1024 and independent HTTP/raw/CLI JSON 1048576 caps remain exact;
CLI LF is extra. Original security/media/no-store/privacy, 007 receipts/exits and
5s phase/10s overall budgets remain. All nine outcomes and both durability states
are facts; end_unconfirmed preserves a decision without inventing end acknowledgement.

One Core owner and one independent service Monitor slot remain strongly owned across
client loss. Detach/shutdown seal admission and join submitted markers before writer
closure; eight read/eight mutation jobs and existing 005/006/008 cleanup facts are
preserved. Blocked durable I/O/cleanup remains pending rather than abandoned. Backend
capability/provenance rules stay neutral; the simulated Enhanced-shaped fixture is
software evidence only, not Enhanced implementation or hardware acceptance.

Existing packages and Ports-and-Adapters boundaries suffice. Model/evidence values,
the application matcher/coordinator/runtime, infrastructure clock/versioned journal
and delivery projections follow the plan's mapping. Acquisition/backend/Profile,
server stop implementation, package declarations and lockfile are unchanged by 009;
root import contracts add Monitor coverage without weakening a boundary. No Core
architecture rule or product contract needs rewriting, and no new dependency exists.

### Progress and recorded verification

| Completed checkpoint | Recorded evidence |
|---|---|
| T001–T005 foundation | Protected 001–008 baseline; pure RED/GREEN values/matcher/marker codecs and charge preflight. T005 full gate: 4064 passed. |
| T006–T016 operational implementation | Explicit v2/read-only terminal compatibility, committed coordinator/clock/composition, runtime admission/lifetime, authenticated HTTP and thin CLI; paired RED/GREEN evidence in history. |
| T017 US1 MVP | 688 focused and 4935 full-suite cases passed. |
| T018–T025 US2 quality | Boundary/error/retention tests and cross-layer contract audit; no genuine edge defect. T025: 2402 focused/5310 full passed. |
| T026–T032 US3 ownership/installability | Lifetime/security/installed fixtures, no genuine correction in paired tasks; T032: 2723 focused/5777 full passed and artifact audit GREEN. |
| T033 complete-diff review | One preparation-contract defect corrected; six RED→GREEN, 1549 focused/5783 full passed. |
| T034 safe quickstart acceptance | 2804 focused/5783 full passed; guarded help, exact bounds/privacy, installed stories and artifact audit GREEN. |
| T035 documentation reconciliation | Implemented scope/counts/limits reconciled; documentation checks only, no suite rerun. |
| T036 final structural maintenance | Graphify 0.9.48 completed on the single explicitly authorized corrected retry: 4947 nodes/16016 edges/207 communities, zero input/output LLM tokens. |
| T037 final verification | 527 focused compatibility/5783 full passed; Ruff/mypy/seven import contracts, fresh 14-archive/four-install audit and final diff/privacy review passed; no correction. |
| Final pre-commit review | Clean software review; staged export 527 focused/5783 full passed; 14 fresh archives/four installs and final staged privacy/diff checks passed; implementation committed, nothing pushed. |

The final pre-commit staged gate: 5783 passed in 311.97s (Core 2111/service 1641/CLI 2031),
zero failures/errors/skips; Ruff, mypy 92 files and seven import contracts passed
(67 files/228 dependencies). It includes 153 Monitor/112 original 007/111 original
008 installed-process cases. Four isolated non-editable installs and 14 rebuilt
archives passed source/metadata/RECORD/entry/import checks: 30 production modules,
28 locked runtime distributions per install, no checkout/.pth or generated/runtime/
credential/Graphify inputs. These selections overlap; counts are not added together.

T035 changes documentation only. Source/tests/configuration and governing behavior/
validation requirements retain the T034 gate's baseline. No new test or full gate
was run for T035 under AGENTS §8.3; its evidence is documentation consistency, task/
baseline/hash/link/diff verification. This is not final-feature validation.

### Software readiness and remaining acceptance

The final pre-commit review found no genuine software defect. Core/009 and
completed 003/005–008 ownership, evidence, lifecycle, security and thin-client
contracts remain satisfied. V1 codecs/legacy CLI definitions and Profile/backend/
acquisition/package/lock baselines remain intact; import contracts only add Monitor
coverage. All 37 tasks and feature progress annotations agree. Governing requirements
and normative contract bodies are unchanged. The previously authorized AGENTS §8.3
validation-policy update is included in the reviewed commit.

All 50 intended files were staged and inspected. An export of all 213 index blobs
passed the fresh full gate and guarded installability audit outside the checkout;
final documentation-only recording was checked separately and leaves all executable
inputs identical. No unrelated, generated, runtime, credential or Graphify artifact
is included. See history for actual validation and implementation-commit evidence.

T036's final code-only Graphify update remains recorded: 4947 nodes/16016 edges/
207 communities, zero LLM tokens, after the explicitly authorized corrected retry.
Its known zero-node pyproject.toml, 238 dangling candidates and 381 collapsed-edge
warnings remain navigation limitations. Outputs/backups remain ignored. No Graphify
run was required or performed during T037 or pre-commit review; no code changed after T036.

Feature 009 is software-ready for its bounded receive-only Monitor scope on the
validated macOS environment. All 37 tasks are complete; there is no recorded
uncorrected software defect. The last full gate, installed software fixtures and
simulated Enhanced-shaped backend do not establish native Linux/Windows, active-DUT,
physical/electrical or Enhanced hardware acceptance. Those remain unexecuted;
actual Windows commands remain unsupported. Phase 1 and deferred workflows remain
incomplete. The authorized implementation commit is recorded above. Nothing was
pushed; no next slice or hardware access was performed or automatically authorized.
Await explicit instructions; do not push, start another slice or access physical
hardware automatically.

## Completed Feature: Bounded Evidence Retrieval (008; Software-Complete)

Artifacts: [spec](../specs/008-evidence-retrieval/spec.md),
[plan](../specs/008-evidence-retrieval/plan.md),
[contract](../specs/008-evidence-retrieval/contracts/evidence-retrieval.md),
[model](../specs/008-evidence-retrieval/data-model.md),
[research](../specs/008-evidence-retrieval/research.md),
[quickstart](../specs/008-evidence-retrieval/quickstart.md),
[quality checklist](../specs/008-evidence-retrieval/checklists/requirements.md) and
[tasks](../specs/008-evidence-retrieval/tasks.md).

Feature 008 advances Core §22.2 A/H/I/J with software evidence retrieval,
backend-neutral workflows and authenticated delivery. It does not complete these
Phase 1 requirements: real-DUT acceptance and the remaining workflows are pending.
No unresolved product/API decision or demonstrated uncorrected feature defect is
recorded. T001–T035 and the separately authorized final pre-commit review are
complete; Feature 008 is software-complete. Its implementation is the title-based
commit reference above. No native/physical or Phase 1 completion is implied.

### Implemented read and lifetime contract

Core exposes pure read ports, immutable prepared access/run-page values and
normalized read exceptions. Optional preparation fields preserve old attach-only
callers. `ObservationRuntime.read_record/read_page` guard the owning loop and pin
one known run/session/source before their first await. An admitted new attach
replaces public selection immediately; rejected attach preserves it. Already pinned
old reads may finish. Restart retains no association; there is no historical index.

Active reads reuse the existing journal instance/gate/worker alongside append and
retention. Teardown joins acquisition, seals new live reads, joins bound reads,
then closes the authoritative recorder. The association releases live recorder
references and retains only immutable private terminal target/opener facts.
Terminal access requires `owner_settled` and `recorder_close_confirmed`; physical
release uncertainty alone neither forbids retrieval nor proves successful release.
Known failed preparations can retain terminal access after confirmed cleanup;
unknown session, missing source or unconfirmed recorder close remains unavailable.

Every terminal query opens a fresh private worker/connection with SQLite
`mode=ro&cache=private`, sets and verifies `query_only`, and validates native identity,
session, exact policy and full schema-v1 inside an explicit read transaction.
It rolls back/closes before delivery, reusing unchanged 003 validators/selection.
No writable reopen, recovery, `immutable`, `nolock`, pool or client-selected path.
Native identity capture failure preserves live-only access without a path fallback.

At most eight Core leases span all source generations. The service owns eight
read jobs separately from its unchanged eight mutation jobs; registration precedes
Core admission, which alone binds a source. Strongly owned work survives cancelled
waiters/client loss and joins at shutdown before final detach. No queue, public job,
result history, retry or forced worker abandonment. Uncertain terminal/partial-open
cleanup or unexpected opener faults permanently latch read cleanup false and seal
future reads before lease release. Existing pinned work settles; capture/status/
attach facts stay unchanged. Positive service cleanup also requires that latch.

### Implemented HTTP and CLI contract

Authenticated literal POST routes `/v1/evidence/record` and `/v1/evidence/page`
retain feature 006 peer/Host/Origin/browser/Bearer/query/media gates and no-store.
Closed request bodies select an explicit session plus stable reference or bounded
half-open range/page; no run/path/database/catalogue input. Security rejection
precedes body/source work. The [contract](../specs/008-evidence-retrieval/contracts/evidence-retrieval.md#7-exact-errors-service-lifetime-and-privacy)
owns exact status/source/code pairs for all five read rejections, all 20 declared
`JournalFailure` categories and existing common service/runtime errors. Operation,
detail, paths, SQL, causes, tracebacks and credentials are never returned.

`dutchmate evidence record --session ID --sequence N` and
`dutchmate evidence page --session ID --max-records N --max-charged-bytes N`
use the existing global numeric host/required port. Page optionally accepts paired
`--start/--end` and `--cursor`; absent range/cursor become explicit JSON nulls.
No defaults for session/sequence/page budgets. Resource-free help and lexical input
validation precede credential/network access. The CLI reads the fixed per-user
credential once and makes one HTTP request with unchanged 007 transport/receipts.
It validates closed wire shapes and canonical binary/cursor representation without
importing Core/service policy, recomputing page facts or fetching another page.
Valid HTTP 200 reports exit 0 for complete/partial/expired/not_found; recognized
remote errors exit 4. Existing private local errors, interrupt and pipe behavior stay.

Exact ordered UART bytes use standard canonical padded base64; compact UTF-8 JSON
preserves every record, timestamp domain/origin, connection/segment boundary,
reported capability, opaque provenance, loss scope and retention marker. Fixed
snapshot continuation uses canonical unpadded base64url of the specified ordered
JSON value, with no signature, registry, retained resource or tail behavior.
Append never extends an existing traversal; eviction remains explicit. Direct 003
facts preserve outcome/truncation independence, MAX references and zero-record
charged-byte shortage pages with exact required charge/continuation position.

| Independent bound | Implemented limit |
|---|---|
| Actual request body | 16384 bytes; overflow detection at 16385 |
| Session | 1–256 UTF-8 bytes, no NUL; exact, unnormalized |
| Reference/range counters | Exact integers 0–9223372036854775807, not bool |
| Page request | 1–4096 records and 1–1048576 charged bytes; also subject to captured 003 policy |
| Cursor input/output | 1–1024 ASCII bytes when non-null; canonical service/response token, lexical CLI input check |
| Service response | Whole canonical UTF-8 JSON ≤1048576 bytes |
| CLI output | Canonical UTF-8 JSON ≤1048576 bytes plus one LF |
| Raw/encoded overflow accumulator | At most 1048577 bytes for detection |
| CLI HTTP delivery | Existing absolute 10s budget and 5s phases; raw uncompressed body |

Encoded report or emitted-cursor overflow rejects the whole response with
413 `evidence/delivery_too_large`. CLI malformed/encoded overflow remains private
`invalid_response`, exit 5. No record split, metadata omission, trimming, substitute
cursor or automatic retry. Explicit lower-budget continuation retains its snapshot;
a fresh initial retry captures a new snapshot. These delivery caps do not tighten
003 policy, or claim exact OS/socket/SQLite/materialization memory limits or a new
Core lifecycle deadline.

### Compatibility, review and installability

Schema-v1, Profile-v1, codecs, physical backend contract, acquisition and bootstrap/
credential ownership remain unchanged. The only 003 correction is the demonstrated
`JournalFailure` exception-transport defect: sealed read-only facts and ordinary
writable exception metadata preserve constructor/categories/message/equality/hash.
Completed 005–007 capture/lifecycle/security/old command meanings remain intact.

The T031 review checked all FR-001–032 and the intended 34 feature files:
12 production, 11 tests, eight specification artifacts, two progress documents and
one import configuration. Application read access shares the existing runtime layer;
import coverage extends to the new module with no weakened rule or exemption.
Feature 008 adds a read adapter and delivery modules within the existing modular
monolith/Ports-and-Adapters design. It changes no architecture or dependency direction;
the active model/contract already document the additions, so no architecture/Core/
old-contract rewrite is required. T034's structural assessment triggered one
code-only incremental Graphify update for the added modules/shared read interfaces
and import coverage. It selected 24 code/config inputs (23 Python plus root
pyproject.toml), preserving the existing graph without Markdown/semantic extraction.
Graphify 0.9.48 produced 3897 nodes/12448 edges/153 communities with zero LLM tokens;
23 Python inputs have current AST stamps. Read-only diagnostics found no saved-graph
missing/dangling endpoints, self-loops, duplicate or collapsed edges. The updater
completed through its internal sequential fallback after stdin-based parallel worker
startup failed; root pyproject.toml remains the known zero-node/unstamped input,
and 45 community labels were refreshed deterministically. No second update or
LLM relabel followed. Outputs and four curated backups remain ignored and untracked.
No production/test/dependency/configuration changes are part of T033–T035 or the
final pre-commit review.

T030 inspected eight wheel/sdist artifacts and two fresh installed stacks. All
15 Core/six service/five CLI Python modules and sdist pyprojects matched source;
version 0.0.0, Python ≥3.14,<3.15, declared dependencies and CLI entry metadata
matched. Locked installs are non-editable and run entries/imports outside cwd,
without repository .pth/local source dependencies, generated/private runtime files
or credential/Graphify artifacts. T032 rebuilt guarded installed tests and reconciled
that evidence. `uv.lock` and package/build/dependency declarations are unchanged.

T035 independently inspected this final run's eight rebuilt artifacts and two fresh
installed stacks. All module bytes, sdist pyprojects, Name/Version/Python/dependencies
and CLI entry metadata match; both non-editable stacks have all 28 distribution
versions pinned to uv.lock, no repository .pth and passing guarded outside-cwd
entries/imports. The final 34-file review found no genuine defect/correction or
unrelated/generated/runtime/credential/Graphify input. Fifty-six protected schema/
Profile/backend/acquisition/bootstrap/credential/package/lock/Core/old-spec files
match committed 007 HEAD exactly; 14 old evidence declarations remain unchanged
apart from the intended JournalFailure transport correction. Root configuration
changes only add the specified inward read-module coverage. No rule was weakened.

### Progress and recorded verification

- [x] T001–T005: protected baseline, exception regression/correction and pure reads.
- [x] T006–T014: live association/composition, authenticated routes/thin CLI and US1.
- [x] T015–T019: terminal read-only adapter, association/cleanup and US2.
- [x] T020–T025: 003 semantic/wire/CLI edges and US3; emitted cursor bound corrected.
- [x] T026–T030: ownership/shutdown, guarded installed tests and combined US1–US4.
- [x] T031–T032: complete diff/FR review and safe quickstart acceptance reconciliation.
- [x] T033: implemented contracts/counts/progress/limits reconciled; documentation verified.
- [x] T034: structural trigger confirmed; exactly one code-only incremental Graphify update.
- [x] T035: fresh final gate/diff/installability review passed; software-complete.

The separately authorized final pre-commit review passed without a new defect or
production/test/configuration/dependency change. Fresh full gate and installed
artifact verification confirm the reviewed implementation; commit metadata alone
is reconciled here and in spec/model/task progress and history.

| Recorded checkpoint | Actual result | Scope |
|---|---|---|
| T030 combined validation | 3223 passed; zero failures/errors/skips | Core 789/service 1107/CLI 1327; stories, lifetime, privacy/security, installed delivery |
| T031 feature review | 1699 focused/3889 full passed; zero failures/errors/skips | Complete 34-file/FR-001–032 review; no defect or correction |
| T032 safe acceptance | 1736 passed; zero failures/errors/skips | Core 531/service 542/CLI 663; includes 111 feature 008 and 112 old 007 guarded process cases |
| T032 full gate | 3889 passed; zero failures/errors/skips | Core 1455/service 1107/CLI 1327; existing 003/005–007 regressions included |
| T032 static/diff checks | Ruff clean; mypy 75 files; seven import contracts kept/zero broken; diff clean | 62 import-graph files/193 dependencies; no code/test/dependency change |
| T033 documentation reconciliation | Full 3889 passed in 163.85s; zero failures/errors/skips; Ruff/mypy 75/import 7/diff clean | Core 1455/service 1107/CLI 1327; documentation checks and unchanged-code audit passed; final T035 gate remains pending |
| T034 structural maintenance | One incremental update; 3897 nodes/12448 edges/153 communities; zero input/output LLM tokens. Full 3889 passed in 162.98s; zero failures/errors/skips; Ruff/mypy 75/import 7/diff clean | 24 code/config inputs; ignored output/backups; source/tests/contracts unchanged. This checkpoint does not execute final T035 review/readiness |
| T035 final software gate/review | 3889 passed in 167.23s; zero failures/errors/skips; Ruff clean; mypy 75 files; seven import contracts kept/zero broken; diff clean | Core 1455/service 1107/CLI 1327; includes 111 new 008/112 old 007 guarded installed cases. Final 34-file scope and eight-artifact/two-stack install review passed; no product correction |
| Final pre-commit review | 3889 passed in 162.75s; zero failures/errors/skips; Ruff clean; mypy 75 files; seven import contracts kept/zero broken; diff clean | Complete 34-file review and eight fresh artifacts/two locked installed stacks passed; schema-v1/Profile-v1 unchanged; no production correction |

These selections overlap; their counts are not added to the 3889 distinct full-suite
cases. Dated RED/GREEN, focused/full commands, corrections and earlier checkpoints
remain in [history](development_history.md), rather than a competing current chronology.

## Acceptance Limits and Deferred Work

Native software evidence is macOS/arm64 (Darwin 25.2.0), Python 3.14.3, including
actual IPv4/IPv6 authenticated loopback and installed wheel/sdist fake-DUT flows,
SIGINT/closed pipes, exact all-256-byte retrieval and terminal read-only transactions.
Independent parent/CLI/service child guards forbid physical serial/discovery and
real-account credential access. Shared Basic/Enhanced-shaped fixtures establish
backend neutrality only. Selected suites skipped zero tests; native Linux/Windows,
active-DUT/physical/electrical and Enhanced hardware acceptance were not selected
in those software gates and are not inferred from them. Separately authorized
physical Stage1/Stage2 evidence below is distinct from those guarded software tests.

Actual service/CLI commands initially support Linux/macOS POSIX. Native Linux
acceptance is outstanding; Windows commands are explicitly unsupported before
account/network work. Mocked Windows/platform checks are not native acceptance.
On2026-10-21, after the user flashed/independently observed the RP2040 fixture,
identified the FTDI adapter/port, confirmed3.3V wiring and disconnected VCC/DTR/RTS/
CTS, released the independent receiver and approved the human-owned RX-only
Profile, observation-only Stage1 ran on that exact target. No UART TX request.
The production service/API2/CLI, unchanged, made two explicit opens and passed55
checks covering idle durable RX, bounded retrieval, concurrent Follow/Monitor,
subscriber cancellation, Monitor detach settlement, physical close, explicit
fresh-origin reopen and joined service shutdown. Private evidence is at
`.dutchmate/acceptance/rpi-pico/stage1-20261021T101309Z/`; report/CLI captures and
two v4 journals (161 and53 records) remain ignored. Physical device identity,
source/Profile hashes and exact UART bytes are retained there, not in public docs.

Within-run ticks are consecutive; counter1270 falls in the unobserved interval
between closed/run1 and reopened/run2, without a continuity claim. No reset
banner was observed; firmware/banner identity was independently reported by the
user rather than recaptured by resetting the DUT. Normal private service bootstrap
was used; credential invalidation/cleanup confirmation succeeded and port ownership
was released. No unrelated account state was accessed.

After Stage1 passed, the user explicitly approved temporarily enabling TX and
exactly one bounded Interact: PING CR LF (hex50 49 4e 47 0d 0a), observing for
PONG CR LF within4000ms/4096 RX bytes. Stage2 ran on the same identified setup,
2026-10-21T10:30:09.983129Z–10:30:22.262198Z, through the unchanged authenticated
production service/API2/CLI. All76 recorded checks pass. The private evidence at
`.dutchmate/acceptance/rpi-pico/stage2-20261021T103009Z/` retains exact original/TX
Profile snapshots, one-request guard, CLI/Follow captures, raw RX and closed v4
journals (115 and53 records). Intent53 contains the exact six requested bytes;
TX settlement54 reports backend acceptance of6 bytes only. Independent RX55–60
spells PONG CR LF; Interact end61 is matched/complete with no audit failures,
window[54,61). Concurrent Monitor start35/end62 matches those same RX positions;
Follow delivers identical evidence including all three Interact kinds. These
ordered host facts do not establish wire completion, DUT-time causation or an
absence of buffering. Ambient ticks2280–2285 remain present around the response.

Follow SIGINT leaves RX active; detach confirms physical-owner/recorder settlement
and release. The exact original Profile bytes/hash are restored (TX=false) before
explicit RX-only reopen, with a fresh session/timestamp origin and ticks2287–2289.
Counter2286 is in the unobserved closed interval. Joined service stop with Follow
and RX active exits0; bootstrap cleanup is confirmed, credential invalidated and
port released without cleanup uncertainty. The terminal Follow frame honestly
leaves its final source tail unknown; closed-journal audit confirms the segment
end independently. Read-only SQLite integrity/sequence/payload/hash checks pass
for both journals. No second TX request, SILENT request, reset, flash or retry.

Safe-open DTR/RTS waveforms/glitches, measured electrical pin levels/baud accuracy,
OS/driver loss/re-enumeration, non-standard baud, RX load and in-flight physical TX
cancellation/blocked-write settlement remain unvalidated. This activity joins an
already-settled write before close; it does not force a pending-write race.
Selected Stage1/Stage2 results do not establish those claims, other OS/adapter
combinations, or full Phase1 readiness. The preceding full software gate's one
installed Monitor checkpoint failure remains a historical failed run. A subsequent
hardware-free investigation demonstrates a test-control race: a redundant normal
fault command can be acknowledged from the already-normal audit before the child
consumes it, then unlink the following emission command unread. The narrow fix in
`apps/cli/tests/test_cli_monitor_process.py` resets only the fault-injected case.
Four installed wheel/sdist, Basic/Enhanced-shaped regressions force the original
interleaving and fail at the same emission checkpoint before the fix; all pass
afterward. Focused28 cases pass; fresh full11403 pass in1032.65s, zero failures/
errors/skips, warnings as errors (Core4545/service2777/CLI4081). Ruff clean,
mypy142 and all seven import contracts kept (77 files/312 dependencies); diff
clean. No baseline test case removed. Product code, shared fixture, deadlines,
hardware/account guards, contracts, dependencies and architecture are unchanged.
Private diagnostics remain ignored under build/. This software result resolves
the checkpoint discrepancy; it establishes no additional physical acceptance.

Client annotations are accepted010 scope; Core values/v3 persistence/coordinator,
runtime admission/rate/ownership, production composition and authenticated service
delivery and thin CLI US1 MVP are implemented. Annotation bound/lifetime hardening
and the combined T019 full gate are verified, with no further correction after T016.
T020 guarded installed annotation workflow validation, T021 complete-diff/artifact
review and T022 documentation/conformance reconciliation are verified. T023 final
code-only Graphify update is complete with recorded tooling/health limits. T024
fresh final full gate, installed flows and artifact/privacy/Core/contract review
passed; Feature010 is software-complete and committed.
Follow011 has a GREEN Core/service/CLI US1 MVP and combined T019 hardening/full gate;
T020 installed Follow and T021 diff/artifact/compatibility review are verified.
T022 conformance/T023 tooling and T024 fresh full/installed/artifact/privacy
closure and final pre-commit review are verified; Feature011 is software-complete
and committed. Other explicit
deferrals beyond010 remain text/line decoding, regex and Monitor multiple conditions,
annotation editing/backdating/attachments and derived views, catalogue/discovery, restart recovery/arbitrary
historical browsing, Console, Control, reconnect/handoff, service management,
Enhanced production, MCP/AI and broader physical-hardware acceptance. Profile discovery/
defaults/writing/migration/overlays/reload, durable Profile identity, session management,
cleanup retry/operator recovery and external-program execution remain deferred.
Existing 003 process-crash recovery tests do not imply terminal-reader recovery or
arbitrary power-loss/media/lying-flush/live-copy guarantees. No Core timeout or
forced abandonment is introduced.

Phase 1 remains incomplete under
[Core §22.2](project_context_core.md#222-phase-1--basic-backend-through-cli): remaining
Follow/Interact native/physical acceptance, Console, control, handoff, reconnect
and real-DUT acceptance remain.
Feature010 annotation behavior, hardening, installed review and final T024 software
closure and the separately authorized final pre-commit review/commit are verified.
Features001–012 are committed software slices. Software tests alone do not establish
physical Monitor acceptance; only the identified Stage1/Stage2 observations above do
so within their declared scope. Feature012 current progress and authorization are
recorded in Resume Here; final review/software closure is verified and committed. Await
human review/selection; no physical hardware or another slice is automatically
authorized.

## References

Product semantics: [Core](project_context_core.md).
Non-normative reasoning: [Rationale](project_context_rationale.md).
Agent workflow/tooling: [AGENTS.md](../AGENTS.md), [agent tooling](agent_tooling.md).
Completed evidence: [development history](development_history.md).
