# Quickstart Validation: Observation CLI

Staged validation guide: T010 US1/native status and installed help validated.
T020 validates all US3/software checks:transport310/process112/completed1485 and
full2261 passed, zero failures/errors/skips. Static/import/installability/privacy/
guard checks passed; no code/test changes. Native IPv4/IPv6 authentication and SIGINT
were tested on macOS; guarded ASGI loss cases remain software fixture evidence.
T021 full intended diff/FR-001–030 review is complete; no production defect and no
code/test changes. Three stale state references now match006's six-state contract.
Fresh full2261/static/import/installability/scope checks passed, zero failures/errors/
skips. T022 executed every focused selection and exact scope search:3132 passes/
2261 distinct cases, zero failures/errors/skips; both help commands exit0/empty
stderr and fresh wheel/sdist installs verified. No demonstrated007 failure or code/
test change. T023 reconciles status/history and progress metadata only; no new
software/static run or acceptance. Feature007 remains uncommitted at c2c9ce3.
T024's structural trigger was met: one code-only incremental Graphify0.9.48 update
succeeded (3195 nodes/9455 edges/137 communities, zero LLM tokens); generated outputs/
backups stay ignored. Known zero-node root pyproject.toml remains; no product change
or new software/static run/acceptance in T024. T025 freshly executed the final gate:
2261 tests passed, zero failures/errors/skips; Ruff clean, mypy61 files clean,7 import
contracts kept/0 broken, diff checks clean before/after docs. Final24-file diff,
fresh wheel/sdist installs/outside-cwd entries and all25 task markers verified.
No new production defect or source/test/config/dependency/contract change. Software
scope completed in T025. Separately authorized final pre-commit review freshly reran
the full gate:2261 passed, zero failures/errors/skips; static/import/staged checks
clean, complete24-file/installability review passed without a new defect. This
snapshot belongs to `Implement observation CLI` (`:/^Implement observation CLI`),
accepted parent c2c9ce3. No push, next slice or hardware action.
Linux/Windows, native active-DUT lifecycle and physical hardware acceptance remain
unexecuted. Do not run
product attach against a physical Profile. Every scenario below is implemented
with test-owned temporary account state, numeric loopback and hardware tripwires.
[CLI contract](contracts/observation-cli.md) is the source for grammar/output/exits;
[006 contract](../006-local-observation-service/contracts/local-observation-service.md)
continues governing the server. See [tasks](tasks.md) for staged execution.

## Prerequisites and safety

Python3.14 uv workspace; committed baseline c2c9ce3/006 b4c5730. Add dependencies
only during T002 through uv. Linux/macOS are initial native platforms. Native Linux/
Windows and all physical/electrical acceptance remain unexecuted after T005.
Tests isolate passwd home and forbid real serial/serial_for_url/enumeration in
parent and each helper child, plus real account bootstrap. Do not reuse a running
personal service. Native socket permission may require the environment's approval;
never weaken tests or count a skip as passed.

## First implementation group: T001–T005

Baseline006 before any new production behavior:
```bash
rtk proxy uv run pytest apps/service/tests --tb=short
```
Expected committed baseline561 passes (90 bootstrap/226 HTTP/38 process/111 projection/
96 runtime), no hardware. Counts are prior evidence until actually run.

T003 RED context/credential contracts then T004 GREEN:
```bash
rtk proxy uv run pytest apps/cli/tests/test_cli_context.py --tb=short
```
Verify targets, fixed credential reading, no-follow/file mode/UID/links/66-byte bound,
ignored environments, no marker/lock/file repair, context failures without input echo.
Package import through uv works after T002; no console script/HTTP/commands yet.
T005 runs required gate below with only implemented test paths and records actual
counts. Stop T001–T005 before T006.

## US1: Typer help, authenticated status and wire bounds

```bash
rtk proxy uv run pytest apps/cli/tests/test_cli_commands.py --tb=short
rtk proxy uv run pytest apps/cli/tests/test_cli_transport.py --tb=short
```

Use CliRunner for pure grammar/help, direct main(args) for actual wrapper diagnostics.
Help before target/credential exists must exit0/no file/network calls. Unknown/value-
bearing arguments exit2 with fixed JSON; no Rich/suggestion/traceback/input echo.
Target IPv4/default and explicit IPv6, port80 Host inclusion, exact Bearer/header
shape, no Origin/proxy/env/retry/redirect/DNS/fallback. Strict JSON/media/encoding/
byte/output overflow rejects before report output. Status preserves all six006 runtime states (including terminated);
valid200 failed remains report0. Real006 gate/lifespan/credential path used for
authenticated acceptance; client mock transport alone does not prove that integration.

After T009, safe installed command grammar (help only):
```bash
rtk proxy uv run dutchmate --help
rtk proxy uv run dutchmate status --help
```

## US2: Existing attach/status/detach over HTTP only

```bash
rtk proxy uv run pytest apps/cli/tests/test_cli_lifecycle.py --tb=short
rtk proxy uv run pytest apps/service/tests core/tests --tb=short
```

Use test-owned observation-only TOML and fresh temporary journal; service injects
existing strict fake Basic. Assert client never reads either file or constructs
Core/service resources. CLI emits exact bounded reports/errors/exits from contract.
Idle client process termination does not stop capture; explicit detach then
temporary journal readback proves exact ambient binary data/order/provenance.
Use identical report assertions for existing Basic/Enhanced-shaped fixtures;
no production Enhanced selection. Busy may perform server-side bounded Profile
read per005/006 but creates no run resources; CLI does not recreate that admission logic.
No retrieval is offered by CLI; journal readback occurs in tests only.

## US3: Deadline, delivery loss, console SIGINT and privacy

```bash
rtk proxy uv run pytest apps/cli/tests/test_cli_transport.py --tb=short
rtk proxy uv run pytest apps/cli/tests/test_cli_process.py --tb=short
```

Gate actual006 operation after admission, expire/interupt client delivery, verify
service work continues to authoritative settlement and no retry/detach/status probe/
signal is sent. Local request_outcome remains not_submitted/unknown/report_received,
never a fabricated service result. A new explicit status observes current state only.
Slow header/body and continually progressing chunks prove the total10s deadline,
not just5s inactivity limits. Deterministic tests can monkeypatch private timing
constants/fixtures; installed/native scenarios must prove public defaults remain fixed.
Record which tests are mocked vs native, and unsupported-platform/IPv6 skips accurately.

Installed process tests verify malformed arguments/private sentinels, Ctrl-C through
the entry wrapper, closed output pipe, zero tracebacks/log leakage, and imports/console
launch outside repository cwd. Build wheel/sdist to a temporary destination through
uv build --package dutchmate-cli; verify dependencies/entry/data without requiring
globally installed packages or mandatory editable paths. No test process may access
physical serial resources or execute user-supplied programs.

## Scope and architecture searches

```bash
rtk proxy rg -n 'typer|dutchmate_cli' core/src apps/service/src
rtk proxy rg -n 'dutchmate_core|dutchmate_service|serial|sqlite3|subprocess|fastapi|uvicorn|mcp' apps/cli/src
rtk proxy git diff c2c9ce3 -- core apps/service specs/001-rx-continuous-evidence specs/002-basic-serial-adapter specs/003-durable-evidence-journal specs/004-dut-profile-policy specs/005-observation-runtime specs/006-local-observation-service
rtk proxy git ls-files graphify-out
```
First searches expected no imports/behavioral hits; inspect words in explanatory
module docstrings separately. Completed code/contracts and tracked Graphify output
must remain empty. Review root/package configs/lock for intentional changes only.
No Core/006 relaxation, HTTP routes, Profile/schema revision or test authentication bypass.

## Final implementation gate (T025)

Run only near implementation completion, never during this planning turn:
```bash
rtk proxy uv run ruff check .
rtk proxy uv run mypy .
rtk proxy uv run lint-imports
rtk proxy uv run pytest
rtk proxy git diff --check
```

Inspect tracked/untracked intended files, entry script/installability, all task markers
and updated status/history after recording actual counts. Rerun diff checks after docs.
Graphify maintenance is T024 conditional on actual code structure, not planning.
Stop without automatic commit/push/next slice/hardware. Software tests do not prove
physical acceptance, real Enhanced behavior or unexecuted OS acceptance.
