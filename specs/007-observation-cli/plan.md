# Implementation Plan: Observation CLI

**Branch**: main | **Date**: 2026-10-08 | **Spec**: [spec.md](spec.md)
**Feature directory**:007-observation-cli, assigned by sequential repository workflow.
Setup scripts report the feature context as BRANCH; Git remains main.
**Status**: T001–T025 and final pre-commit review complete; fresh2261 passed, zero
failures/errors/skips; Ruff/mypy61 files/7 import contracts/diff clean. Complete
staged24-file/installability review passed, no defect or source/test/config change.
This snapshot belongs to `Implement observation CLI` (`:/^Implement observation CLI`),
accepted parent c2c9ce3; Linux/Windows/native active-DUT/hardware acceptance unrun.

## Summary

Add a small installable Typer CLI with attach/status/detach, fixed private credential
read and one finite HTTP exchange to already-running006. JSON-only reports preserve
existing statuses, including HTTP200 failed runtime. Local delivery failures carry
fixed categories and not_submitted/unknown/report_received; no service cancellation,
automatic retries/detach or second execution stack.

## Technical Context

**Language/Version**: Existing Python>=3.14,<3.15, uv workspace.
**Primary Dependencies**: typer>=0.27.3,<0.28 (mandatory framework), httpx>=0.28.1,<0.29
(no extras), standard os/pwd/stat/json/asyncio. Verify httpcore>=1.0.9,<2 transitive
resolution; preserve all35 pre-existing locked versions, including Click8.5.0.
No production Core/service dependency. No dependency install during planning.
**Storage**: Read existing credential only; no client persistent state or journals.
**Testing**: pytest/asyncio, typer.testing.CliRunner plus entry-wrapper and installed
console-process tests, actual006 guarded app/loopback, Core fake/fixture/temp journals.
**Target Platform**: Linux/macOS POSIX actual commands; resource-free help/import
may run elsewhere. Native Linux/Windows and hardware acceptance remain unexecuted.
**Project Type**: Modular-monolith thin delivery application apps/cli.
**Performance Goals**: One request/invocation;10s total HTTP wait with5s phase limits;
retained body<=1MiB plus detection byte; encoded output<=1MiB plus LF.
**Constraints**: No Core/service production imports; Typer only CLI layer; no proxy/
redirect/env/URL/credential overrides, retries, discoveries, resource ownership or
client reproduction of domain predicates.
**Scale/Scope**: One selected local service per invocation, three root commands,
one private token read, no streaming/concurrent client jobs/session catalogue.
**Research**: [Decisions/sources](research.md); declared metadata compatibility,
implementation-time uv/import/behavior verification still required.

## Constitution Check

Constitution remains an unpopulated scaffold, not another source of authority.
Core/AGENTS/006 and completed contracts govern before and after design.

| Gate | Design assessment |
|---|---|
| Core/006 authority | No execution/auth/ownership/API/schema revision |
| Thin client | HTTP only; no Core/service product imports or policy/runtime replicas |
| Typer scope | User-mandated framework solely in new CLI delivery |
| Security | Fixed credential hygiene, exact numeric Host, no logs/input/token echo |
| Ownership/RX | Client process ends without stopping admitted work/capture |
| Bounds | Absolute HTTP wait plus finite phase/body/output limits |
| Facts | Existing primary/cleanup/trigger/nullable/provenance fields preserved |
| Neutrality | Generic wire views, same fixture assertions, no identity branches |
| Simplicity | Three cohesive modules plus package initializer; no client/plugin/DTO framework |
| Hardware | Parent/child physical guards, isolated account and loopback only |

No exemption/ignore_imports or weakened boundary proposed. These are design checks,
not assertions that unimplemented code already passes.

## Project Structure

```text
specs/007-observation-cli/
  spec.md
  plan.md
  research.md
  data-model.md
  contracts/observation-cli.md
  quickstart.md
  tasks.md
  checklists/requirements.md
apps/cli/
  pyproject.toml
  ruff.toml
  src/dutchmate_cli/
    __init__.py
    context.py   # Typed target/options, read-only credential hygiene, fixed local failures
    client.py    # One concrete async HTTP exchange, deadline/bounds/wire validation
    main.py      # Pure Typer grammar, entry wrapper, output/exits/interrupt boundary
  tests/
    conftest.py
    test_cli_context.py
    test_cli_commands.py
    test_cli_transport.py
    test_cli_lifecycle.py
    test_cli_process.py
pyproject.toml   # workspace/test/mypy/import-contract coverage
uv.lock          # intentional CLI dependencies during T002 only
docs/development_status.md
docs/development_history.md
```

No new generic client port/registry/job/serialization layer. HTTPX's concrete transport
is an actual external boundary; tests may substitute it privately without a public
production bypass. Test-only service/Core imports do not become CLI dependencies.

## Consumer/configuration inventory

-006's three endpoints, StatusEnvelope/ErrorEnvelope and private credential protocol
remain unchanged. Client checks closed wire shapes/types, not semantic invariants.
-005 runtime API/binding/cancellation/cleanup,004 Profile and003 evidence codecs/
retention/retrieval remain unchanged. CLI passes paths and never touches those files.
-The current workspace members core/apps/service gain apps/cli during T002.
Create minimal __init__ first, then add deps via uv --package dutchmate-cli.
Declare dutchmate console entry only when main.py exists (T009).
-Extend root pytest/mypy paths and import root_packages after package exists.
Core forbidden-delivery contract includes dutchmate_cli; service forbidden direct
imports include dutchmate_cli. Preserve all existing Core transitive boundaries.
Add a transitive CLI-forbidden Core/service contract and a separate direct-only
CLI-forbidden serial/sqlite3/fastapi/uvicorn/mcp/subprocess contract
(allow_indirect_imports=true for the external ban only, as in006). This permits
legitimate framework internals while forbidding those imports in product modules;
Core/service direction remains transitive and strict. No ignore_imports or product exemption.
-New CLI Ruff config allows Typer/HTTPX but bans Core/service/serial/sqlite3/server/
MCP/subprocess APIs in production. Tests only may import fixtures/spawn guarded
temporary helpers; no future handoff exemption until an actual handoff module exists.
-Unique test_cli_* files avoid package collisions; no second tests package.
Parent/child sentinels forbid serial factories/URL factories/enumeration and real
account bootstrap. Native clients use actual authentication, not a patched allow gate.
-Actual dependency resolution includes Typer's legitimate transitives and HTTPX's
HTTPcore/certifi; old service test-only removal does not prohibit this new production
client dependency. Never add Typer/httpx to service/Core or upgrade unrelated lock rows.

## Settled execution/composition

1. Entry wrapper recognizes safe help; pure root callback stores host/port only.
2. Actual command validates required target and attach lexical inputs before I/O.
3. Read credential once with no-follow descriptors; no Profile/journal/marker/lock I/O.
4. Set local request_outcome unknown immediately before one request attempt; create
   short-lived AsyncClient/transport with explicit security settings and absolute deadline.
5. Stream raw bounded body; validate media/JSON/006 wire shape; mark report_received
   only after a valid complete report, then close client delivery.
6. Output compact bounded JSON;0 for any200 report,4 for remote error. Fixed local
   envelope/exits handle parse/setup/transport/protocol/interrupt/output failures.
7. HTTP loss never translates to005 cancellation or006 service stop/detach/retry.
   Output/noresponse uncertainty and server cleanup uncertainty remain different facts.

HTTP waiting deadline excludes credential filesystem calls and final decoding/output/
socket cleanup hard-real-time claims. Pure standard-library clock/async timeout suffices;
no test clock port or process-wide signal manager is introduced.

## Implementation Sequence

1. Verify committed baseline, existing guards/contracts and focused006 regressions.
2. Add installable CLI workspace/deps/static boundaries without commands/resources.
3. RED/GREEN endpoint/credential/failure primitives; validate first group and stop.
4. RED grammar/transport/status then implement one bounded client and pure Typer entry.
5. RED normal attach/detach then wire exact006 requests and validate real idle capture.
6. Exercise failure/uncertainty/provenance and client-loss/deadline/interrupt/privacy;
   correct only demonstrated new CLI defects.
7. Verify installed console/outside-cwd imports and actual authenticated loopback;
   use identical reported-fact checks on existing normalized fixture shapes.
8. Review full diff/scope, execute focused quickstart, reconcile status/history and
   assess actual Graphify structural trigger (one code-only update if warranted).
9. Fresh full gates/installability/final diff evidence; stop without automatic commit,
   push/new slice or hardware. Complete CLI acceptance needs all stories, not status only.

## Critical Regression Matrix

| Area | Required evidence |
|---|---|
| Help/grammar | Root/subcommand help0, wrong placement/inputs2, no credential/network preparation, no argv echo |
| Credential | Fixed passwd path, ignored environment, symlink/UID/type/mode/link/size/rotation-race safety; no lock/marker/write |
| HTTP | Numeric families/Host80, no resolver/proxy/redirect/retry, one request, bounded strict raw JSON |
| Outcomes | All200 reports0 including failed; remote error4; local fixed categories/phases/exits |
| Lifetime | Idle capture/client exit, lost response, total-vs-trickle deadline, Ctrl-C never detach/replay/signal |
| Neutrality | Full opaque reported domains/loss/capabilities/nullable/failure facts on both fixture shapes |
| Installation | Console script/entry wrapper, real process stdout/stderr/exits, imports outside repo cwd |
| Compatibility |001–006/core/schema/profile/ownership unchanged; import contracts strengthened |
| Acceptance limits | Native tests/IPv6 skips reported honestly; no hardware/Windows/Linux claim from macOS or mocks |

## Explicit Deferrals

Use [contract §8](contracts/observation-cli.md#8-composition-and-compatibility).
In particular no service autostart/process manager, evidence/Monitor/follow/TX/
Control/handoff/reconnect/session/Profile discovery or Enhanced/MCP/AI behavior.
No unresolved product decision. Implementation dependency/SDK/platform validation
is required work, not claimed completed by planning.
