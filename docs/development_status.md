# DUTchMate Development Status

This is the single authority for current progress, active phase, blockers,
milestone, and next work. It is subordinate to
`docs/project_context_core.md` and active focused implementation specifications.
Completed-slice evidence is kept in [development history](development_history.md).

## Resume Here

- **Active phase**: Phase 1 — Basic backend through CLI; Phase 1 is not complete.
- **Committed software baseline**: Features 001–004 are committed and accepted.
  Feature 005 is committed as `2824c0dc3ecc63684f573b3b0a55c621e18e069f` on `main`,
  following feature-004 commit `6d10cf7`.
- **Completed slice**: `005-observation-runtime` — observation-only Device Core
  runtime for Profile activation, in-memory durable-session association, and
  attach/status/detach. Implementation and review through T025 are delivered;
  T026/T027/T028 are complete. Final pre-commit review found no new defect;
  the software-complete change set is committed under the explicit human instruction.
- **Fresh pre-commit evidence**: Ruff clean; mypy 40 files clean; all three import
  contracts kept (31 files/77 dependencies); pytest 924 passed with zero failures/
  errors/skips; diff/whitespace checks clean before and after documentation edits.
  The suite includes 349 feature cases, 565 completed regressions and ten fixtures.
- **Next action**: Await explicit selection and specification of the next coherent
  Phase 1 slice. Do not infer or start it automatically.
- **Planning progress**: All T001–T028 markers are now checked. T028 reconciles
  the previously completed T026 marker against its existing evidence, while
  preserving T026's original two-file-only execution record and all deferrals.
- **Scope guard**: One observation run, one RX path, immutable resolved Profile,
  fresh journal/session per attach, in-memory association only, unchanged schema-v1,
  ordered joined cleanup, conservative uncertainty blocking, and no auto reconnect.
  Service/CLI/Monitor/TX/Control/handoff/Enhanced/MCP/AI/hardware work stays deferred.
- **Hardware**: No physical device has been accessed, modified or validated.
  Fake/temporary-journal and Enhanced-shaped results prove software contracts only;
  opt-in platform/electrical acceptance remains separately authorized and unexecuted.
- **Open issues**: No unresolved feature-005 product decision. The existing
  feature-003 `JournalFailure` context-manager limitation remains unfixed and
  outside feature 005. No failed required check or unresolved feature-005 blocker
  remains; physical-hardware acceptance is not implied.
  Python 3.14 remains the declared baseline.

## Repository Baseline

The feature-005 commit on `main` is
`2824c0dc3ecc63684f573b3b0a55c621e18e069f` (`Implement observation runtime lifecycle`);
its parent is feature-004 commit `6d10cf72014c46d7eeb5481b26857222ee40b7fd`.
The committed baseline includes reproducible agent tooling and these software milestones:

| Feature | Committed software scope | Commit |
|---|---|---|
| [001](../specs/001-rx-continuous-evidence/spec.md) | Normalized backend boundary, authoritative continuous exact-byte RX, evidence ordering and provenance | `a13522c` |
| [002](../specs/002-basic-serial-adapter/spec.md) | Explicit-device receive-only Basic adapter, configure-before-open, joined read/close lifecycle | `e2cd2cf` |
| [003](../specs/003-durable-evidence-journal/spec.md) | SQLite schema-v1 durable append/reopen, bounded retention/references/fixed-snapshot retrieval | `15890e59` |
| [004](../specs/004-dut-profile-policy/spec.md) | Strict bounded observation-only TOML-v1 Profile resolution, immutable values and pure Basic translation | `6d10cf7` |
| [005](../specs/005-observation-runtime/spec.md) | Observation-only run ownership, in-memory Profile/session association and serialized attach/status/detach | `2824c0dc3ecc63684f573b3b0a55c621e18e069f` |

Feature 005 is software-complete and included in the commit identified above.
It adds `core/src/dutchmate_core/runtime.py` and
`core/src/dutchmate_core/adapters/observation_runtime.py`, explicitly additive
Acquisition snapshot/join support, tests/fixture gates, planning artifacts and
runtime coverage in existing import contracts.
Package exports, dependencies/lockfile, schema-v1 and existing evidence/Backend
execution contracts remain unchanged; architecture contracts were strengthened
without new exemptions. The uv workspace remains Python 3.14 with
`dutchmate-core`, pySerial 3.5 and the locked development toolchain.

## Active Feature: Observation Runtime

The governing artifacts are [specification](../specs/005-observation-runtime/spec.md),
[plan](../specs/005-observation-runtime/plan.md),
[internal contract](../specs/005-observation-runtime/contracts/observation-runtime.md),
[quickstart](../specs/005-observation-runtime/quickstart.md), and
[task definitions](../specs/005-observation-runtime/tasks.md).
Their completion metadata is reconciled by T028; all 28 implementation tasks
are complete. Current project progress remains recorded here.

Delivered software behavior:

- A backend-neutral, owning-loop/thread-bound runtime with serialized
  attach/status/detach and exactly one accepted observation generation.
- The Basic/SQLite edge checks context, resolves the explicit bounded Profile,
  then prepares a fresh journal and unopened backend only after runtime admission.
  Runtime busy rejection performs no preparation; an outer busy edge call may
  still read the explicit Profile as defined by the contract.
- Acquisition remains the sole backend opener/continuous RX consumer. Runtime
  projects normalized primary failure, close failure, trigger, committed
  provenance and release certainty separately, using the additive join barrier.
- One owner handles explicit stop, cancellation and autonomous termination.
  Actual Acquisition startup/consumer/close work is joined before recorder close
  and terminal settlement. Repeated cancellation cannot abandon cleanup;
  unconfirmed physical or recorder release permanently blocks that instance's reuse.
- Immediate terminal Acquisition cannot publish active capture. Observed
  disconnect wins terminal cause independently of primary/cleanup failures;
  historical status and old-generation results remain isolated from a fresh run.
- Profile/session association is in memory only. Cancelled/failed journals are
  retained; explicit subsequent attach uses a fresh destination/session. Existing
  sequence, retention, expiry, pagination and provenance-envelope semantics persist.
- Both normalized fixture shapes exercise the same shared lifecycle/readback
  assertions, including device-domain timestamps, observer-scoped loss, origin
  resets and explicit missing-RX rejection. This adds no Enhanced production support.
- T011 corrected normalized rejection transport; T024 corrected preparation
  failure transport while retaining read-only facts and validation. Full review
  found no other feature-005 scope/contract defect.

| Work | Recorded completion |
|---|---|
| T001–T005 | Foundations and additive Acquisition/runtime values |
| T006–T011 | Normal lifecycle, Basic composition, durable readback and US1 review |
| T012–T018 | Request/cancellation, preparation/failure cleanup, certainty and US2 review |
| T019–T023 | Fixture gates, autonomous termination, backend neutrality and US3 review |
| T024 | Full FR-001–030/contract/diff review and bounded preparation-error correction |
| T025 | All quickstart-focused scenarios and pre-final scope commands |
| T026 | Development status/history reconciliation; prior completion now checked in tasks |
| T027 | Trigger satisfied; one code-only incremental Graphify update completed |
| T028 | Fresh full software gate and final diff/completion review passed |

All feature-005 implementation and validation above is software-only.
The feature is software-complete and committed following final pre-commit review.
Phase 1 remains incomplete; no subsequent slice has been selected or started.
Per-task RED/GREEN evidence and earlier milestone details remain in development
history rather than a competing chronological status narrative.

## Validation Evidence

The final pre-commit gate is fresh evidence; earlier rows retain their checkpoint
meaning. No software tests were rerun during T026/T027:

| Checkpoint | Recorded result | Evidence boundary |
|---|---|---|
| T024 focused/full software validation | 349 feature cases; 924 default-suite cases; zero failures/errors/skips | Most recent full software gate; does not complete T028 |
| T024 correction regressions | Six RED failures/eight passes became 14 GREEN; existing normalization case also passed | Preparation exception transport and read-only facts |
| T025 focused scenarios | All 21 pytest commands passed; canonical groups 105/214/30; feature focus 349, completed regressions 565 and T019 fixtures ten | Selected software-only runs; no unrestricted full-suite invocation |
| T025 architecture/scope | Five commands passed; Ruff clean, mypy 40 files clean, three import contracts kept (31 files/77 dependencies), schema-v1 and empty SQLite/model/Backend diff | Pre-final architecture/scope checks; final-gate block deliberately omitted |
| T026 documentation | Verified branch/HEAD/commit references, two-file scope, links, whitespace and Resume Here length | No software tests, Graphify update or hardware validation rerun |
| T027 Graphify | Version 0.9.48; one changed-code-only incremental update; 2,435 nodes, 6,370 edges, 117 communities; zero input/output LLM tokens | 38 code sources; no semantic extraction; generated outputs/backups ignored |
| T028 final gate | Ruff clean; mypy 40 files clean; three import contracts kept (31 files/77 dependencies); 924 passed, zero failures/errors/skips; clean diff checks before/after docs | Fresh hardware-free default-suite run; 349 feature cases, 565 completed regressions and ten fixture cases |
| Final pre-commit review/gate | No new defect; Ruff clean; mypy 40 files clean; three import contracts kept (31 files/77 dependencies); 924 passed, zero failures/errors/skips; unstaged/staged whitespace checks clean | Full feature review and fresh hardware-free gate before the explicitly authorized commit; generated output excluded |

No physical-hardware test was executed or passed. Hardware cases remain unexecuted,
not counted as successful software validation. T028 makes a software-only
readiness claim, not an electrical/platform, Enhanced-hardware or complete Phase 1 claim.

## Blockers, Limitations and Deferred Work

- There is no unresolved product decision for the accepted feature-005 scope.
  All 28 tasks, final pre-commit review and the required software gate are complete.
  The feature is committed; selection/specification of the next slice requires
  explicit human instruction.
- The existing frozen/slotted feature-003 `JournalFailure` can be masked by
  `TypeError` when a generator context manager restores `__traceback__` on
  Python 3.14. It was reproduced during T010 and remains outside the feature-005
  correction. The distinct feature-005 preparation-error defect is fixed by T024.
- Runtime activation and observation policy enforcement now exist. Profile
  discovery/default paths, writing, migration, overlay/reload and numerical
  persistence defaults remain deferred; inputs and destinations stay explicit.
  Serial hardware discovery, automatic device selection and fallback remain absent.
- Service/HTTP/authentication/browser-origin rejection, CLI, process-wide
  ownership/deployment, Monitor/follow, TX/Interact/console, semantic Control,
  annotations/derived views and broader retrieval workflows are not implemented.
- Automatic reconnect, native-USB topology, release/reacquire/handoff,
  external-program execution, durable full-Profile identity, session catalogue/
  naming/sealing/resumption/rotation/deletion and cleanup retry attestations remain
  deferred. No lifecycle timeout or forced worker abandonment is introduced;
  pending status remains inspectable, and uncertain cleanup blocks reuse.
- Enhanced production protocol/firmware/USB/framing/GPIO/event behavior, MCP
  and AI integration remain deferred. The Enhanced-shaped fixture is a software
  neutrality test, not a hardware or Profile-selection implementation.
- Safe-open DTR/RTS electrical state/glitch behavior, OS/driver disconnect
  classification, non-standard baud, RX load and physical cancellation/close
  behavior remain separately authorized hardware acceptance cases.
- SQLite rollback-journal process-crash recovery is software-tested. Arbitrary
  power loss, lying flush hardware, media/filesystem recovery and live-file copying
  remain outside accepted guarantees.

## Planning and Evidence References

Product semantics remain in [Core](project_context_core.md); reasoning is in
[Rationale](project_context_rationale.md). Agent workflow and tooling remain in
[AGENTS.md](../AGENTS.md) and [agent tooling](agent_tooling.md). Completed feature specifications
are linked in the baseline table. Detailed completed-slice evidence, including
earlier Graphify runs, remains in [development history](development_history.md).
T027's assessment found the two new runtime/composition modules, additive
Acquisition snapshot/join interfaces and expanded dependency-contract coverage
satisfy the structural trigger. Exactly one incremental update used Graphify's
existing updater with the changed code paths only; the CLI default's full-corpus
rescan was not used. Existing documentation graph content was preserved without
semantic refresh. Graphify reported one zero-node source (`pyproject.toml`) and
deterministically renamed 34 community labels by their hubs; no retry or LLM
labeling was run. Graphify explain verified runtime, composition, snapshot and
join symbols; `.gitignore` keeps all outputs/backups ignored and no graph file is
tracked. Detailed command/results remain in development history.
