# DUTchMate Development Status

This is the single authority for current progress, active phase, blockers,
milestone, and next work. It is subordinate to
[Core](project_context_core.md) and active focused implementation specifications.
Completed-slice evidence is kept in [development history](development_history.md).

## Resume Here

- **Active phase**: Phase 1 — Basic backend through CLI; Phase 1 is incomplete.
- **Implementation baseline**: Features001–007 are software-complete on main.
  Feature007 is the `Implement observation CLI` commit containing this reviewed
  snapshot, identified by Git revision `:/^Implement observation CLI`.
  Its accepted parent baseline is c2c9ce3;006 implementation remains b4c5730.
- **Latest completed slice**:007-observation-cli — T001–T025 software-complete;
  separately authorized final pre-commit review passed. Phase1 remains incomplete.
- **Delivered CLI**: Installable dutchmate-cli/Typer, dutchmate attach/status/detach;
  one already-running service selected by127.0.0.1(default) or::1 and required port.
  Attach passes explicit bounded Profile/journal paths without opening either file.
- **Delivery contract**: Read the fixed passwd/effective-UID credential once; one
  authenticated HTTP request,10s total wait/5s phases, raw body<=1MiB plus detection
  byte and compact JSON<=1MiB plus LF. Valid200 exit0 means report delivery only.
  Fixed exits/diagnostics and request_outcome preserve client-delivery uncertainty.
- **Ownership**: Thin HTTP delivery only; no production Core/service imports or
  bootstrap/domain copy. Client exit/loss never retries, detaches or signals service;
  one service runtime/RX and admitted-operation ownership remain authoritative.
- **Latest software evidence**: Fresh final pre-commit full2261 passed, zero failures/errors/
  skips; Ruff clean, mypy61 files clean,7 import contracts kept/0 broken. Diff,
  final24-file review and fresh wheel/sdist installs/outside-cwd entries passed.
- **This slice**: Complete final review found no defect or source/test/config change;
  intended24-file staged audit and cached whitespace checks passed before commit.
  All25 task markers checked; final validation/commit snapshot records reconciled.
  T024's single code-only graph update remains recorded; output/backups ignored.
- **Next action**: Await explicit direction for the next Phase1 slice; do not start
  it or access physical hardware automatically. No next slice has been selected.
  Nothing pushed; this authorization ends after the feature007 commit.
- **Limits**: Native validation has been macOS only, including IPv4/IPv6 auth,
  installed SIGINT/closed pipes and scripted-loopback timing. Guarded ASGI/fake DUT
  lifecycle/loss/readback and Enhanced-shaped fixtures are software evidence only.
  Native Linux/Windows, native active-DUT lifecycle and physical/electrical acceptance
  remain unexecuted. Actual commands initially support Linux/macOS POSIX only.
- **Deferrals**: Service management, evidence delivery/follow/Monitor/TX/Control,
  handoff/reconnect, catalogue/Profile discovery, Enhanced/MCP/AI and hardware.
  Known003 JournalFailure context-manager limitation remains outside007.
- **Hardware**: No physical device or real account credential accessed.

## Repository Baseline

| Feature | Committed software scope | Implementation commit |
|---|---|---|
| [001](../specs/001-rx-continuous-evidence/spec.md) | Normalized backend, continuous exact-byte RX, evidence ordering/provenance | `a13522c` |
| [002](../specs/002-basic-serial-adapter/spec.md) | Explicit-device receive-only Basic adapter, configure-before-open, joined read/close | `e2cd2cf` |
| [003](../specs/003-durable-evidence-journal/spec.md) | SQLite schema-v1 durable append/reopen, bounded retention/references/retrieval | `15890e59` |
| [004](../specs/004-dut-profile-policy/spec.md) | Strict observation-only TOML-v1 Profile, immutable values and Basic translation | `6d10cf72014c46d7eeb5481b26857222ee40b7fd` |
| [005](../specs/005-observation-runtime/spec.md) | Backend-neutral runtime, in-memory Profile/session association, serialized lifecycle | `2824c0dc3ecc63684f573b3b0a55c621e18e069f` |
| [006](../specs/006-local-observation-service/spec.md) | Authenticated local service, persistent runtime, private bootstrap, joined shutdown | `b4c5730b2a5e593c10c06ad9e8f24c39e06f794b` |
| [007](../specs/007-observation-cli/spec.md) | Thin authenticated Typer observation CLI, bounded HTTP delivery, reported facts and private exits | `:/^Implement observation CLI` |

Feature007's accepted parent baseline is the feature006 commit-recording change
`c2c9ce3`; the service implementation remains `b4c5730`. The implementation commit
for007 is the commit titled `Implement observation CLI` containing this snapshot.
Resolve its actual full hash with `git rev-parse ':/^Implement observation CLI'`;
this title-based reference keeps the commit's own record accurate without a
self-referential hash or a second bookkeeping commit. All prior001–006 implementation
commits remain ancestors. Nothing is pushed. Earlier005/006 maintenance is in history;
feature007's T024 assessment and single code-only incremental update are complete;
generated graph/output/backups remain ignored, with no product change or commit.

## Completed Feature: Observation CLI (T001–T025 Software-Complete; Final Review Passed)

Governing artifacts: [spec](../specs/007-observation-cli/spec.md),
[plan](../specs/007-observation-cli/plan.md),
[contract](../specs/007-observation-cli/contracts/observation-cli.md),
[data model](../specs/007-observation-cli/data-model.md),
[research](../specs/007-observation-cli/research.md),
[quickstart](../specs/007-observation-cli/quickstart.md) and
[tasks](../specs/007-observation-cli/tasks.md).

The implemented surface is the three root observation commands, resource-free
help and fixed private errors. Target and attach inputs receive lexical validation
before credential/network work; the client never reads Profile/journal/DUT resources
or selects hardware. Credential access is read-only/no-follow and bounded, without
service lock/marker/PID/generation/repair/refresh logic. HTTPX delivers one literal006
request with exact Host/Bearer, no environment/proxy/redirect/retry/fallback/autostart.

Closed wire validation preserves all six runtime states, immutable Profile,
nullable IDs, ordered primary/cleanup facts, trigger/release/recorder uncertainty,
reported admissibility and opaque capability/provenance data. It does not reconstruct
Core predicates. Every valid200 exits0, including failed runtime; documented remote
errors exit4, and fixed local envelopes carry truthful delivery phase. SIGINT,
timeout and response/output failure end client delivery only; later explicit status
observes facts without recovering or attributing a lost response.

The four production files are package initializer, context.py, client.py and main.py.
Typer/context/HTTPX/filesystem/terminal concerns stay in apps/cli. Core/service code
and completed001–006 contracts, schema-v1, Profile-v1 and lifecycle/security semantics
remain unchanged. Workspace/test/mypy/import extensions cover the CLI; seven import
contracts preserve Core/service directions and forbid CLI implementation coupling.
No product exception or ignore_imports was added; fixture imports/subprocesses are
confined to guarded tests.

The Python3.14 uv package depends directly only on Typer>=0.27.3,<0.28 and
HTTPX>=0.28.1,<0.29, resolved to0.27.3/0.28.1 with HTTPcore1.0.9. All35 prior lock
package rows remain unchanged; required client/framework transitives are intentional.
Wheel/sdist installs into fresh temporary environments prove the real entry and
outside-cwd imports without mandatory editables or globally installed dependencies.

T001–T025 are checked. The specified007 software slice is complete; the separately
authorized complete pre-commit review and fresh full gate passed without a new defect.
Its implementation is recorded by the title-based commit reference above.
T019 corrected T018's demonstrated EPIPE
shutdown diagnostic/exit120 defect; no remaining007 defect was demonstrated by
T020–T022. T021 aligned stale five-state text with006's existing six-state contract.
T023 removes duplicate per-task chronology and obsolete CLI deferral from current
status; dated RED/GREEN/correction evidence remains unchanged in history.
T025's final intended24-file review found no new production defect and made no
source/test/config/dependency/contract change. Two planning-only notes are now
explicitly dated as snapshots, avoiding stale unchecked-task/current-state claims.

## Recorded Validation and Acceptance Boundaries

The final pre-commit gate was executed freshly after T025. Earlier task results
retain their recorded dates/boundaries; T024 refreshed the code graph only.

| Checkpoint | Recorded result | Boundary |
|---|---|---|
| Final pre-commit review, 2026-10-10 |2261 passed, zero failures/errors/skips; Ruff clean; mypy61 files clean;7 import contracts kept/0 broken (56 files/152 dependencies); working/staged diff checks clean | Complete24-file review found no defect; source/tests/config unchanged from T025. Fresh wheel/sdist installs and outside-cwd entries passed; software evidence only. |
| T025 fresh final software gate/review, 2026-10-10 |2261 passed, zero failures/errors/skips; Ruff clean; mypy61 files clean;7 import contracts kept/0 broken (56 files/152 dependencies); diff clean before/after docs |776 CLI +561 service +924 Core; all112 installed-process cases rebuilt/reinstalled wheel/sdist. Final24-file diff/import/lock/artifact review passed; uncommitted, ready for final review/commit. |
| T021 full software/static gate, 2026-10-10 |2261 passed, zero failures/errors/skips; Ruff clean; mypy61 files clean;7 import contracts kept/0 broken (56 files/152 dependencies); diff clean |776 CLI +561 service +924 Core; hardware-free. Full intended24-file review/installability passed. |
| T022 focused quickstart, 2026-10-10 |3132 passes/2261 distinct cases, zero failures/errors/skips; both help commands0/empty stderr; four exact scope searches passed | Eight selections include repeated service/transport cases; no final full-gate block or new static run. |
| T022 CLI selections | commands127, context139, lifecycle88, transport310 (twice), process112 | Real Typer grammar/direct wrapper plus actual006 authentication; wheel/sdist entries installed in fresh isolated environments. |
| T022 completed regressions | service561 separately and service/Core1485 | Service breakdown90 bootstrap/226 HTTP/38 process/111 projection/96 runtime; Core924. |
| Native macOS evidence |10 status-auth cases (5 IPv6),20 installed-auth cases (10 IPv6),8 SIGINT,8 closed-pipe,2 default5s/10s timing cases; no platform/IPv6 skips | Native service children have one inactive runtime; signal/wait fault checkpoints use test-only controls. Timing listeners are scripted loopback HTTP. |
| Guarded software lifecycle/neutrality | Actual006 ASGI/bootstrap/lifespan, FakeSerial/temp SQLite;12 admitted attach/detach loss cases;54 shared reported-fact cases (27 per Basic/Enhanced-shaped fixture) | Idle exact binary readback, one owner/consumer and immutable reported facts; no native active-DUT or Enhanced hardware acceptance. |
| T024 structural maintenance, 2026-10-10 | One Graphify0.9.48 incremental update of12 changed code inputs:3195 nodes/9455 edges/137 communities; zero input/output LLM tokens | CLI package/modules and dependency boundaries meet the trigger.11 inputs indexed; known zero-node root pyproject.toml remains unstamped. Existing graph retained; no Markdown extraction. Outputs/backups ignored. |

Parent and independent CLI/service child tripwires block physical serial factories,
URL factories/enumeration and real account state. Tests use isolated passwd homes,
test-owned loopback, observation-only Profiles and temporary journals. Test-side
journal readback is not a CLI evidence-retrieval surface. The cooperative HTTP
budget does not claim hard bounds on account/filesystem/decoding/output/socket cleanup.

T025 executed its own fresh full gate and inspected the final intended diff and
fresh package artifacts. Source/test/config/lock hashes match the T021-reviewed
implementation, all35 old lock rows remain unchanged and completed001–006 sources/
contracts are intact. No generated/runtime/credential/Graphify files enter the
intended24-file set. Documentation links/task markers/whitespace were rechecked.
Detailed commands, XML/count evidence, RED/GREEN history and
prior platform/Graphify limits live in [development history](development_history.md).

## Completed Feature: Local Observation Service

Feature006 is software-complete and committed as `b4c5730`. Its
[contract](../specs/006-local-observation-service/contracts/local-observation-service.md)
still governs bootstrap/authentication, three HTTP routes, one persistent runtime,
at most eight strongly owned admitted mutations and joined shutdown. Client loss
never cancels service-owned operations. Basic/SQLite remain at the Core composition
edge; no service evidence delivery, automatic reconnect or recovery override exists.

Its final recorded full gate was1485 passes (Core924/service561), Ruff clean, mypy51
files clean and five import contracts kept/0 broken (49 files/125 dependencies).
Native macOS IPv4/IPv6 and temporary wheel/sdist imports passed; these are software
results. Feature006's separate code-only Graphify update completed before commit;
its detailed checkpoints are preserved in history. Feature007's seven current import
contracts and client dependencies extend the workspace without changing006 semantics.

## Blockers, Limitations and Deferred Work

- No unresolved007 product decision or remaining demonstrated007 software defect is
  recorded. T001–T025 and final pre-commit review are complete; implementation is
  recorded by `:/^Implement observation CLI`. No next slice is active. Phase1 remains
  incomplete under [Core §22.2](project_context_core.md#222-phase-1--basic-backend-through-cli).
- Initial service/CLI actual-command support is Linux/macOS POSIX. Native Linux
  acceptance has not run; Windows actual commands are explicitly unsupported before
  account/network work. Windows implementation/native validation are deferred;
  resource-free help on unsupported platforms is tested with substituted platform
  checks, not claimed native Windows acceptance. Portable Core is unchanged.
- Native active-DUT lifecycle/installed-process capture and all physical/electrical
  cases remain unexecuted. Safe-open DTR/RTS/glitches, OS/driver disconnect handling,
  non-standard baud, RX load and physical read cancellation/close need separately
  authorized acceptance against an explicitly identified device/Profile/setup.
  No physical device has been accessed or validated.
- Existing003 frozen/slotted JournalFailure can be masked by TypeError when a
  generator context manager restores __traceback__ on Python3.14. Reproduced in005
  T010; outside007, with no new Core exception change in this slice.
- Remaining client/service workflows: evidence retrieval/streaming/formatting,
  follow, Monitor, Interact/TX/console, semantic Control, annotations/derived views,
  release/reacquire/handoff, reconnect/native-USB matching and service process
  management. Core journal retrieval remains available internally.
- Profile discovery/defaults/writing/migration/overlays/reload and durable Profile
  identity; session catalogue/naming/sealing/resumption/rotation/deletion; cleanup
  retry/operator recovery tooling and external-program execution remain deferred.
  No Core lifecycle timeout or forced abandonment is introduced.
- Enhanced production protocol/firmware/USB/framing/GPIO/events, MCP and AI remain
  deferred. Existing Enhanced-shaped fixtures prove software neutrality only.
- SQLite rollback-journal process-crash recovery is software-tested. Arbitrary
  power loss, lying flush hardware, media/filesystem recovery and live-file copying
  remain outside accepted guarantees.

## References

Product semantics: [Core](project_context_core.md).
Non-normative reasoning: [Rationale](project_context_rationale.md).
Agent workflow/tooling: [AGENTS.md](../AGENTS.md), [agent tooling](agent_tooling.md).
Completed evidence: [development history](development_history.md).
