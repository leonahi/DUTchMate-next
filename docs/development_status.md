# DUTchMate Development Status

This is the single authority for current progress, active phase, blockers,
milestone, and next work. It is subordinate to
[Core](project_context_core.md) and active focused implementation specifications.
Completed-slice evidence is kept in [development history](development_history.md).

## Resume Here

- **Active phase**: Phase 1 — Basic backend through CLI; Phase 1 is incomplete.
- **Committed baseline**: Features 001–006 are committed on `main`.
  Feature 006: `b4c5730b2a5e593c10c06ad9e8f24c39e06f794b`
  (`Implement local observation service`), after clean final review/software gate.
  Features 001–005 remain accepted.
  Feature 005: `2824c0dc3ecc63684f573b3b0a55c621e18e069f`
  (`Implement observation runtime lifecycle`).
  The prior baseline was `ed11051015a4e56f81a4737bc55dad322f82f622`.
- **Latest completed slice**: `006-local-observation-service` — authenticated local
  FastAPI service for observation-only attach/status/detach. All T001–T030 are
  checked. Feature 006 is software-complete and committed after final review.
  Feature 005 remains complete; no next slice has been selected or started.
- **Delivered software**: Installable service package, private bootstrap/auth,
  exact security gate, persistent runtime, owned HTTP mutations, controlled
  IPv4/IPv6 listener/signals and joined startup/shutdown.
- **Final pre-commit gate**: 1485 passed, zero failures/errors/skips; Ruff clean;
  mypy 51 files clean; five import contracts kept/zero broken (49 files/125
  dependencies); diff checks clean before/after docs. Final diff review found no
  new defect; staged diff/stat and cached whitespace checks clean. T030's earlier
  sandbox socket denials were resolved by a permitted guarded rerun.
- **T028**: Current scope, baseline, evidence and limits reconciled in status/history.
  Documentation checks only; no software tests or Graphify update rerun.
- **T029**: Structural trigger met; exactly one code-only incremental Graphify
  update succeeded: 2,891 nodes/8,348 edges/123 communities; zero LLM tokens.
  Generated output remains ignored; source/configuration unchanged.
- **Next action**: Await explicit instruction to determine the next coherent Phase 1
  slice from the governing documents and completed features 001–006. Do not run
  Spec Kit or implement the next slice automatically.
- **Invariants**: One runtime/run/RX path; immutable resolved Profile; fresh journal/
  session per attach; in-memory association; unchanged schema-v1; joined cleanup;
  conservative uncertainty blocking; no automatic reconnect/discovery/fallback.
- **Limits**: No unresolved feature-006 product decision. Initial service support
  is Linux/macOS POSIX; native validation ran on macOS only. Windows service support
  is deferred; Linux/Windows native and physical-hardware acceptance are unexecuted.
  The existing feature-003 JournalFailure context-manager limitation remains outside
  features 005/006. CLI and all broader workflows remain deferred.
- **Hardware**: No physical device has been accessed, modified or validated.
  Simulated Enhanced-shaped results establish software neutrality only.

## Repository Baseline

| Feature | Committed software scope | Commit |
|---|---|---|
| [001](../specs/001-rx-continuous-evidence/spec.md) | Normalized backend boundary, continuous exact-byte RX, evidence ordering/provenance | `a13522c` |
| [002](../specs/002-basic-serial-adapter/spec.md) | Explicit-device receive-only Basic adapter, configure-before-open, joined read/close | `e2cd2cf` |
| [003](../specs/003-durable-evidence-journal/spec.md) | SQLite schema-v1 durable append/reopen, bounded retention/references/retrieval | `15890e59` |
| [004](../specs/004-dut-profile-policy/spec.md) | Strict bounded observation-only TOML-v1 Profile resolution, immutable values and Basic translation | `6d10cf72014c46d7eeb5481b26857222ee40b7fd` |
| [005](../specs/005-observation-runtime/spec.md) | Backend-neutral observation runtime, in-memory Profile/session association, serialized attach/status/detach | `2824c0dc3ecc63684f573b3b0a55c621e18e069f` |
| [006](../specs/006-local-observation-service/spec.md) | Authenticated local observation service, persistent runtime, private per-UID bootstrap and joined shutdown | `b4c5730b2a5e593c10c06ad9e8f24c39e06f794b` |

Feature 005 is software-complete and committed after final pre-commit review.
Its hardware-free baseline gate recorded 924 passes and three kept import
contracts. Its runtime/composition, additive Acquisition snapshot/join and existing
evidence/Profile/backend contracts remain unchanged by feature 006. Feature-005
Graphify maintenance completed in its own T027; feature-006 T029 has now completed
its separate structural assessment and single code-only incremental update.

Feature 006 is committed as `b4c5730b2a5e593c10c06ad9e8f24c39e06f794b`
(`Implement local observation service`). Its complete 25-file set includes
`apps/service/`, feature artifacts, root `pyproject.toml`/`uv.lock` and status/history.
Final review and fresh software gate passed; staged output contained no unrelated,
generated, runtime, credential or Graphify files. This documentation reconciliation
records the actual implementation hash after commit. Nothing was pushed, and no
subsequent Phase 1 slice or hardware acceptance was started.

## Completed Feature: Local Observation Service

Governing artifacts:
[specification](../specs/006-local-observation-service/spec.md),
[plan](../specs/006-local-observation-service/plan.md),
[contract](../specs/006-local-observation-service/contracts/local-observation-service.md),
[data model](../specs/006-local-observation-service/data-model.md),
[research](../specs/006-local-observation-service/research.md),
[quickstart](../specs/006-local-observation-service/quickstart.md) and
[tasks](../specs/006-local-observation-service/tasks.md).

### Delivered scope

- Installable `dutchmate-service` uv workspace package on Python >=3.14,<3.15.
  FastAPI 0.142.2/Uvicorn 0.54.0 and required transitives are locked. T026 removed
  unused test-only httpx/httpcore/certifi; all 22 pre-existing locked versions remain
  unchanged. Five import contracts preserve the three Core boundaries and add two
  service boundaries, with no weakened Core contract or new exemption.
- Controlled synchronous `run_service(ServiceConfig(port, host="127.0.0.1"))`,
  one process/worker, no reload/proxy overrides/import-time resources. One selected
  numeric loopback socket: default IPv4 or explicit `::1` with IPV6_V6ONLY.
  No DNS, wildcard binding, alternate port/family fallback or device discovery.
- Fixed effective-UID/passwd-home private bootstrap directory, descriptor-relative
  no-follow ownership/link/mode checks, stable nonblocking per-UID flock independent
  of port, bounded cleanup marker and 256-bit process-lifetime Bearer credential.
  The whole incarnation stays dirty until cleanup is confirmed. Stale false/
  malformed/incompatible state blocks restart; no PID stealing or automatic recovery.
- Exactly `POST /v1/observation/attach`, `GET /v1/observation/status` and
  `POST /v1/observation/detach`. Attach requires explicit absolute bounded Profile
  and fresh journal paths. Closed bounded JSON projects actual runtime facts without
  task/resource handles, backend-identity branches or evidence delivery.
- Security precedes body/Profile/resource work: selected-family loopback peer,
  exact single Host authority, rejection of every Origin/Sec-Fetch header, exact
  single Bearer authorization, then query/upgrade/path/method/body validation.
  Credentials are header-only; no URL/cookie/body/environment transport or dev bypass.
  Docs/redirects/debug/input diagnostics and native framework telemetry are disabled.
  h11 may reject malformed HTTP before ASGI with fixed input-free text/plain 400.
- One persistent runtime is constructed in async lifespan on its owning loop/thread.
  Basic/SQLite remain at the existing Core composition edge. A busy edge call may
  resolve its bounded explicit Profile before runtime admission, but cannot prepare
  a journal/backend. Schema-v1, immutable Profile/run values, sequence/retention/
  retrieval and primary/cleanup/trigger/provenance/certainty distinctions persist.
- At most eight strongly owned pending mutation tasks, registered before yielding.
  Observed pre-admission cancellation/disconnection submits nothing; after admission,
  delivery loss does not cancel the owned operation or synthesize runtime cancellation.
  Completed results/errors are consumed and removed, with no queue/history/replay.
- Startup stop is latched; repeated signals/cancellation never force abandonment.
  Shutdown closes admission, drains HTTP, joins registered operations, detaches/joins
  runtime, captures final immutable status on its loop, checks ownership/physical/
  recorder cleanup, invalidates credential/closes socket, publishes a truthful marker
  and releases the guard. Partial startup unwinds acquired resources only. Pending
  work retains loop/guard; settled uncertainty retains false and blocks restart.
  Publication failure reports teardown_incomplete without a rollback/durability claim.

### Progress and validation evidence

| Feature-006 checkpoint | Recorded result | Evidence boundary |
|---|---|---|
| T001–T025 | Bootstrap, US1 security/status, US2 lifecycle/request ownership and US3 process/shutdown delivered; detailed RED/GREEN records in history | Fake backends, temporary journals/state and native loopback software tests |
| T026, 2026-10-07 | Full gate: 1485 passed, zero failures/errors/skips; Ruff clean, mypy 51 files clean, five import contracts kept/zero broken (49 files/125 dependencies), diff clean; wheel/sdist build and outside-cwd imports successful | Full contract/diff review corrected ambient telemetry leakage with RED → GREEN regression and removed unused test dependencies |
| T027, 2026-10-08 | All 14 unique focused quickstart commands passed, zero failures/errors/skips; union 1485 distinct cases; scope/targeted Ruff/mypy/import/diff checks clean | Overlapping selections; final full-gate block not executed; all 56 source/config hashes unchanged |
| T028, 2026-10-08 | Status/history, baseline, limits and task bookkeeping reconciled; documentation/baseline/link/whitespace checks recorded in history | Documentation only; no fresh software gate, Graphify or hardware acceptance |
| T029, 2026-10-08 | Graphify 0.9.48 structural trigger met; one incremental update of 13 changed code sources succeeded: 2,891 nodes/8,348 edges/123 communities; zero LLM tokens | Existing documentation graph preserved; outputs/backups ignored; no source/test/config change or software gate rerun |
| T030, 2026-10-08 | Fresh full gate: 1485 passed, zero failures/errors/skips; Ruff clean; mypy 51 files clean; five import contracts kept/zero broken (49 files/125 dependencies); whitespace checks clean before/after docs; final intended diff review found no new defect | Initial sandbox run had 34 loopback permission failures/1451 passes; permitted hardware-guarded rerun passed all cases, including native macOS IPv4/IPv6; no source/test/config correction |
| Final pre-commit review, 2026-10-08 | No new defect; fresh 1485 passes, zero failures/errors/skips; Ruff clean; mypy 51 files clean; five import contracts kept/zero broken (49 files/125 dependencies); diff checks clean | Complete intended feature review; source/test/config unchanged from T030; native macOS software validation only |

The fresh T030 full-suite breakdown is 924 Core, 90 bootstrap, 226 HTTP, 38 process,
111 projection and 96 runtime cases. Native macOS IPv4/IPv6 process tests ran
without platform/IPv6 skips. Counts do not establish other-platform or hardware
acceptance. T001–T030 and structural maintenance are complete. Feature 006 is
software-complete and committed following the separately authorized final review.
Its implementation baseline is the actual feature-006 commit in the table above.

## Blockers, Limitations and Deferred Work

- No unresolved feature-006 product decision or newly demonstrated software defect
  remains. Final software validation/review passed and feature 006 is committed.
  Phase 1 and platform/physical-hardware acceptance remain incomplete.
- Linux/macOS POSIX is the initial service contract. Native Linux acceptance has
  not run; Windows service startup is explicitly unsupported before bootstrap.
  Windows service implementation is deferred; native Windows validation and all
  physical-hardware cases remain unexecuted. Portable Core support is unchanged.
- The existing frozen/slotted feature-003 `JournalFailure` can be masked by
  `TypeError` when a generator context manager restores `__traceback__` on
  Python 3.14. Reproduced during feature-005 T010; outside features 005/006.
- HTTP evidence retrieval/streaming, CLI, Monitor/follow, TX/Interact/console,
  semantic Control, annotations/derived views and broader retrieval workflows
  remain deferred. Existing Core journal retrieval is available internally.
- Profile discovery/default paths, writing/migration/overlay/reload; durable Profile
  identity/schema changes; session catalogue/naming/sealing/resumption/rotation/
  deletion; reconnect/native-USB matching; release/reacquire/handoff; cleanup retry/
  operator recovery tooling; external-program execution remain deferred.
  No lifecycle timeout or forced abandonment is introduced.
- Enhanced production protocol/firmware/USB/framing/GPIO/events, MCP and AI remain
  deferred. The Enhanced-shaped fixture proves software contract neutrality only.
- Safe-open DTR/RTS electrical/glitch behavior, OS/driver disconnect classification,
  non-standard baud, RX load and physical cancellation/close behavior need separately
  authorized hardware acceptance. No physical hardware was accessed or validated.
- SQLite rollback-journal process-crash recovery is software-tested. Arbitrary
  power loss, lying flush hardware, media/filesystem recovery and live-file copying
  remain outside accepted guarantees.

## References

Product semantics: [Core](project_context_core.md).
Non-normative reasoning: [Rationale](project_context_rationale.md).
Agent workflow/tooling: [AGENTS.md](../AGENTS.md), [agent tooling](agent_tooling.md).
Detailed per-task validation and prior Graphify evidence:
[development history](development_history.md).
