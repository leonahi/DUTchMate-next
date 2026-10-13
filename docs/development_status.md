# DUTchMate Development Status

This is the single authority for current progress, active phase, blockers,
milestone, and next work. It is subordinate to
[Core](project_context_core.md) and active focused implementation specifications.
Completed-slice evidence is kept in [development history](development_history.md).

## Resume Here

- **Active phase**: Phase 1 — Basic backend through CLI; Phase 1 is incomplete.
- **Committed baseline**: Features 001–008 are software-complete on `main`.
  Feature 008 is the `Implement evidence retrieval` commit containing this reviewed
  snapshot, identified by Git revision `:/^Implement evidence retrieval`.
  Accepted parent: `a14d1727`; service 006 implementation remains `b4c5730`.
- **Latest completed feature**: `008-evidence-retrieval`, bounded binary-safe
  evidence retrieval through the authenticated service and thin CLI.
- **Progress**: T001–T035 complete; US1–US4 software criteria and final gate passed.
  Separately authorized final pre-commit review passed; Phase 1 remains incomplete.
- **Delivered surface**: `dutchmate attach/status/detach` and `evidence record/page`;
  one already-running service, numeric loopback host and required port.
  Retrieval requires an explicit known session, with no client database/path access.
- **Read model**: One current/last run per service incarnation. Live reads use the
  existing capture journal; terminal reads require confirmed writer closure and
  open/validate/close a fresh read-only reader per request. One RX path remains.
- **Delivery**: Exact UART bytes as padded base64; unchanged 003 page facts and
  fixed snapshots. Independent service/CLI JSON caps are 1048576 bytes, CLI LF
  excluded. Whole overflow rejects; no trimming, refetch or automatic pagination.
- **Ownership/security**: Separate eight service reads/eight mutations and eight
  Core read leases; owned work joins after client loss and at shutdown. Uncertain
  reader cleanup permanently seals reads and prevents a clean service marker.
  Existing 006 auth/browser gates and 007 receipts/exits/10s HTTP budget remain.
- **Recorded evidence**: Fresh pre-commit full 3889 passed, zero failures/errors/skips;
  Ruff/mypy 75/import 7/diff clean. Final 34-file review and eight fresh artifacts/
  two installed stacks passed. T034's one graph update remains recorded/ignored.
- **Next action**: Await explicit direction to select the next coherent Phase 1
  slice. Do not start it or perform native/physical acceptance automatically.
  Nothing pushed; this authorization ends after the Feature 008 commit.
- **Acceptance limits**: Native macOS/arm64, Darwin 25.2.0, Python 3.14.3;
  guarded IPv4/IPv6 fake-DUT installed flows. Native Linux/Windows, active-DUT,
  physical/electrical and Enhanced hardware acceptance remain unexecuted.
  Actual commands initially support Linux/macOS POSIX; Windows unsupported.
- **Scope**: Schema-v1/Profile-v1 and existing 003/005–007 semantics preserved.
  Streaming/text/Monitor/TX/Control/handoff/reconnect/discovery/service management,
  Enhanced production and MCP/AI remain deferred. No hardware or real credential
  access; no push or next Phase 1 slice in this authorization.

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
| [008](../specs/008-evidence-retrieval/spec.md) | Bounded authenticated active/terminal evidence retrieval, exact binary pages and read-cleanup ownership | `:/^Implement evidence retrieval` |

All prior implementation commits remain ancestors of feature 007. Its accepted
parent `c2c9ce3` records feature 006; `b4c5730` is the service implementation.
The separately authorized feature 007 pre-commit review passed on 2026-10-10:
2261 tests (Core 924/service 561/CLI 776), zero failures/errors/skips; Ruff,
mypy 61 files, seven import contracts and working/staged diff checks passed.
Wheel/sdist installs and outside-cwd entry/import checks passed. Features 006/007
completed their code-only Graphify updates before commit; generated output and
backups remain ignored. Detailed earlier checkpoints belong in history.

Feature 008 is the commit titled `Implement evidence retrieval` containing this
reviewed snapshot. Resolve its full hash with
`git rev-parse ':/^Implement evidence retrieval'`; the title-based reference avoids
a self-referential hash or second bookkeeping commit. Its accepted parent is
`a14d1727f5a9a2dd1cab59ac2b662f47919bbe9d`. All prior implementation commits remain
ancestors. Nothing was pushed. T034's single code-only Graphify update remains
recorded; outputs/backups are ignored and excluded from the commit.

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

Explicit deferrals remain streaming/follow, text/line decoding, regex/pattern matching,
Monitor, annotations/derived views, catalogue/discovery, restart recovery/arbitrary
historical browsing, TX/Interact/console, Control, reconnect/handoff, service management,
Enhanced production, MCP/AI and physical-hardware acceptance. Profile discovery/
defaults/writing/migration/overlays/reload, durable Profile identity, session management,
cleanup retry/operator recovery and external-program execution remain deferred.
Existing 003 process-crash recovery tests do not imply terminal-reader recovery or
arbitrary power-loss/media/lying-flush/live-copy guarantees. No Core timeout or
forced abandonment is introduced.

Phase 1 remains incomplete under
[Core §22.2](project_context_core.md#222-phase-1--basic-backend-through-cli): follow,
Monitor, Interact, console, control, handoff, annotations, reconnect and real-DUT
acceptance remain. Features 001–008 are committed software slices; 008's final
review found no new software defect. Nothing was pushed. Do not start another
slice or access physical hardware automatically.

## References

Product semantics: [Core](project_context_core.md).
Non-normative reasoning: [Rationale](project_context_rationale.md).
Agent workflow/tooling: [AGENTS.md](../AGENTS.md), [agent tooling](agent_tooling.md).
Completed evidence: [development history](development_history.md).
