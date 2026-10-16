# DUTchMate Development Status

This is the single authority for current progress, active phase, blockers,
milestone, and next work. It is subordinate to
[Core](project_context_core.md) and active focused implementation specifications.
Completed-slice evidence is kept in [development history](development_history.md).

## Resume Here

- **Active phase**: Phase 1 — Basic backend through CLI; Phase 1 remains incomplete.
- **Committed baseline**: Features001–010 are software-complete on main.
  Feature010: `:/^Implement client annotations` (`Implement client annotations`),
  accepted parent `2fdebaf4aa3df815be9f2ce223c832e70c739569` (Feature009).
- **Current checkpoint**: Feature010 T001–T024 complete,24/24, with separately
  authorized final pre-commit review and implementation commit complete.
  No next implementation slice is selected or authorized.
- **Implemented010**: Exact bounded attributed client assertions through Core,
  authenticated service and thin CLI; explicitv3 and ordinary evidence retrieval.
- **Preserved**: Strictv1/v2/Profile-v1 and oldsix codecs/charges; sole RX/journal/
  coordinator/clock,005 lifecycle/008 cleanup/009 Monitor timing and security.
- **Fresh staged gate**:6951 passed in471.58s, zero failures/errors/skips;
  Ruff/mypy107/seven import contracts, working/staged diff checks clean.
- **Installed evidence**:529 process cases within that run:153 annotation and376
  CLI/evidence/Monitor; wheel/sdist, both backend shapes and IPv4/IPv6.
- **Staged artifact review**:20 archives, six full-stack/two CLI-only installs;
  all33 module bytes/imports/locked dependencies/metadata/private exclusions pass.
- **Review/scope**: No defect or product correction;47 intended files only.
  All236 index blobs exported/checked; executable and governing inputs unchanged
  during final documentation result recording. No extra full-gate rerun.
- **Graphify**: T023's one code-only update/recorded warnings remain; no rerun.
  Generated output/backups/local tooling stay ignored and outside the commit.
- **Next action**: Await human direction for the next Phase1 slice. Do not start
  implementation or native/physical acceptance automatically.
- **Stop boundary**: Commit only completed; nothing pushed, no next slice/hardware.
- **Acceptance limits**: macOS/arm64 Python3.14.3 software evidence only. Native
  Linux/Windows, active-DUT, physical/electrical/safe-open and Enhanced hardware
  acceptance remain unexecuted; actual Windows commands remain unsupported.
- **Deferrals**: Follow, TX/Interact/console, Control, handoff/reconnect, text/regex,
  annotation editing/backdating/attachments, catalogue/history/restart/service
  management, verified identity, Enhanced production/MCP/AI.

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

**Next action: Await human direction for the next Phase1 slice. Do not start
implementation or native/physical acceptance automatically.**
No next slice, push or hardware action was authorized by the completed commit task.

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
active-DUT/physical/electrical and Enhanced hardware acceptance were not selected or
executed, and are not reported as passed.

Actual service/CLI commands initially support Linux/macOS POSIX. Native Linux
acceptance is outstanding; Windows commands are explicitly unsupported before
account/network work. Mocked Windows/platform checks are not native acceptance.
No physical device has been accessed. Safe-open DTR/RTS/glitches, OS/driver
loss/re-enumeration, non-standard baud, RX load and physical cancellation/close
require separately authorized acceptance with an identified device/Profile/setup.

Client annotations are accepted010 scope; Core values/v3 persistence/coordinator,
runtime admission/rate/ownership, production composition and authenticated service
delivery and thin CLI US1 MVP are implemented. Annotation bound/lifetime hardening
and the combined T019 full gate are verified, with no further correction after T016.
T020 guarded installed annotation workflow validation, T021 complete-diff/artifact
review and T022 documentation/conformance reconciliation are verified. T023 final
code-only Graphify update is complete with recorded tooling/health limits. T024
fresh final full gate, installed flows and artifact/privacy/Core/contract review
passed; Feature010 is software-complete and committed.
Explicit deferrals beyond010 remain streaming/follow, text/line decoding, regex/multiple conditions,
annotation editing/backdating/attachments and derived views, catalogue/discovery, restart recovery/arbitrary
historical browsing, TX/Interact/console, Control, reconnect/handoff, service management,
Enhanced production, MCP/AI and physical-hardware acceptance. Profile discovery/
defaults/writing/migration/overlays/reload, durable Profile identity, session management,
cleanup retry/operator recovery and external-program execution remain deferred.
Existing 003 process-crash recovery tests do not imply terminal-reader recovery or
arbitrary power-loss/media/lying-flush/live-copy guarantees. No Core timeout or
forced abandonment is introduced.

Phase 1 remains incomplete under
[Core §22.2](project_context_core.md#222-phase-1--basic-backend-through-cli): follow,
Interact, console, control, handoff, reconnect and real-DUT acceptance remain.
Feature010 annotation behavior, hardening, installed review and final T024 software
closure and the separately authorized final pre-commit review/commit are verified.
Features001–010 are committed software slices. Software-complete009 does not establish
physical Monitor acceptance. Await human direction for the next Phase1 slice;
do not access physical hardware or start another slice automatically.

## References

Product semantics: [Core](project_context_core.md).
Non-normative reasoning: [Rationale](project_context_rationale.md).
Agent workflow/tooling: [AGENTS.md](../AGENTS.md), [agent tooling](agent_tooling.md).
Completed evidence: [development history](development_history.md).
