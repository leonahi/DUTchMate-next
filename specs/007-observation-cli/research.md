# Research: Observation CLI

Planning checkpoint (2026-10-08): all design decisions are settled. Source
verification is read-only; version metadata is not execution/compatibility acceptance.
No packages installed or lock changed during planning. Implementation T002 must
resolve/verify actual versions through uv.
These are planning-time decisions; current progress/evidence lives in tasks.md and
docs/development_status.md, with completed runs in docs/development_history.md.

## Framework and package boundary

Decision: user-mandated Typer, narrow typer>=0.27.3,<0.28; new dutchmate-cli
workspace on existing Python>=3.14,<3.15, console dutchmate. No direct Click dependency.
Typer0.27.3 declares Python>=3.10 and3.14 support classifier, MIT; it vendors Click
since0.26 and provides public TyperException from0.27.2. Existing locked Click8.5.0
remains unchanged for its current consumers. Required Rich/shellingham/annotated-doc
transitives are legitimate framework dependencies, not product formatting features.
T002 must verify current resolution and existing35 locked package versions.

Rationale: preserve requested delivery framework and public privacy/error API;
avoid private vendored imports or unsafe dependency on external Click classes.
Alternatives: argparse violates request; old Typer/external Click coupling loses
current public error handling; new general client/framework abstraction adds no value.

Sources: [version metadata](https://pypi.org/pypi/typer/0.27.3/json),
[Click migration](https://typer.tiangolo.com/tutorial/click/),
[release notes](https://typer.tiangolo.com/release-notes/#0273-2026-10-06),
[public exports](https://raw.githubusercontent.com/fastapi/typer/0.27.3/typer/__init__.py).

## Grammar/help/privacy boundary

Decision: one root app and three commands, global target options before command,
optional parser port required only in actual command. Callback only stores values.
add_completion=False, suggest_commands=False, rich_markup_mode=None,
pretty_exceptions_enable=False, pretty_exceptions_show_locals=False.
No-argument invocation explicitly reaches safe --help; no-command callback is pure.
Console wrapper invokes app with standalone_mode=False and fixed prog_name.

Catch public TyperException without accessing input-bearing text: usage exit_code2
maps to invalid_arguments; other unexpected framework failures map internal_failure.
Handle public Abort/outer KeyboardInterrupt and returned interrupt exit130; suppress
default diagnostic printing. Public command exits go through explicit envelope/
rendering path. No private typer._click imports.
CliRunner tests app grammar/help but bypass console wrapper, so direct wrapper and
installed-process tests separately prove privacy/exits/SIGINT.

Sources: [Typer reference](https://typer.tiangolo.com/reference/typer/),
[callback ordering](https://typer.tiangolo.com/tutorial/commands/callback/),
[tagged invocation handling](https://raw.githubusercontent.com/fastapi/typer/0.27.3/typer/core.py),
[testing](https://typer.tiangolo.com/tutorial/testing/),
[console packaging](https://typer.tiangolo.com/tutorial/package/).

## Endpoint and existing credential

Decision: host exact127.0.0.1/default or::1, required port, no arbitrary URL/proxy/
discovery/autostart. Explicit Host always includes port, including80. Fixed passwd-
derived credential read once with bounded no-follow read-only access and file
ownership/mode/type/link validation. No service module imports, lock/marker logic,
token generation/repair or401 reread/replay.

Rationale: reuse006 local HTTP/security contract; client safety checks are private
file-reading hygiene, never a second bootstrap/authentication-policy owner.
Alternative configurable credential/URL/environment model broadens scope/security.
Server identity/discovery/TLS is not added to006's already accepted local model.

Source: [completed006 contract](../006-local-observation-service/contracts/local-observation-service.md).

## Concrete asynchronous HTTP transport

Decision: httpx>=0.28.1,<0.29 without extras, production dependency only in CLI.
Verify resolution includes httpcore>=1.0.9,<2 and existing AnyIO4.15.1/h11 remain
compatible and unchanged; no unrelated dependency upgrade. HTTPX BSD-3-Clause,
HTTPcore BSD-3-Clause; HTTPX adds HTTPcore/certifi, with certifi MPL-2.0.
AsyncClient within synchronous Typer command's asyncio.run; explicit transport/client
trust_env=False, retries0, HTTP/1 only, no redirects, one connection/no kept pool.

Rationale: standard-library urllib installs proxy/redirect defaults; lower-level
blocking http.client needs additional socket/signal machinery for slow total waits
and Ctrl-C. Existing async HTTP framing/cancellation provides concrete boundary value,
without a custom parser or blocking worker left running on cancellation.

Numeric targets are handled before DNS by current AnyIO/asyncio IP branches; test
both accepted families with resolver tripwires, not a custom backend stack.
Metadata compatibility is declared, not demonstrated; T002 verifies Python3.14 imports.

Sources: [HTTPX metadata](https://pypi.org/project/httpx/),
[HTTPcore changelog](https://pypi.org/project/httpcore/),
[HTTPX transport](https://raw.githubusercontent.com/encode/httpx/0.28.1/httpx/_transports/default.py),
[HTTPcore AnyIO backend](https://raw.githubusercontent.com/encode/httpcore/1.0.9/httpcore/_backends/anyio.py),
[AnyIO numeric-address branch](https://raw.githubusercontent.com/agronholm/anyio/4.15.1/src/anyio/_core/_sockets.py),
[urllib defaults](https://docs.python.org/3.14/library/urllib.request.html),
[http.client](https://docs.python.org/3.14/library/http.client.html),
[certifi license](https://pypi.org/project/certifi/).

## Deadline, retained bytes and JSON

Decision: absolute asyncio.timeout_at(loop.time()+10.0) for HTTP waiting, finite5.0s
phase limits; no synchronous HTTP offloading. Stream aiter_raw with identity request
encoding; cap retained body at1048576 plus detection byte, validate strict JSON/
closed006 wire schema and output bound before writing. No exact socket-read cap:
transport may already buffer chunks before client slicing/closing.
Wire validation is delivery shape/type checking, not Core predicates/objects.

Rationale: phase/inactivity timeouts alone permit indefinite trickling; total budget
must remain fixed. Strict decoding prevents duplicate/nonfinite ambiguity; rejecting
compression avoids expansion. No pagination, evidence bytes or text derivation added.

Sources: [HTTPX timeouts](https://www.python-httpx.org/advanced/timeouts/),
[absolute asyncio timeout](https://docs.python.org/3.14/library/asyncio-task.html#asyncio.timeout_at),
[raw streaming](https://www.python-httpx.org/async/#streaming-responses),
[HTTPcore read chunks](https://raw.githubusercontent.com/encode/httpcore/1.0.9/httpcore/_async/http11.py),
[JSON decoding controls](https://docs.python.org/3.14/library/json.html).

## Output and cancellation semantics

Decision: JSON-only report/error delivery, help text only exception. Exit0 for all
valid200 reports including failed runtime; HTTP rejection4; usage2; local credential/
platform3; transport/protocol5; interrupt130; internal/output1. Local envelopes add
request_outcome not_submitted/unknown/report_received describing client delivery.
No reinterpretation of runtime attach/detach outcome, especially uncertain cleanup.

First Ctrl-C cancels client main task under asyncio.run; close client delivery and
normalize at outer entry. Timeout/loss must not signal service, detach or replay.
Explicit later status cannot identify/recover the lost call. Disable HTTPX/httpcore
logs/propagation and framework input-bearing diagnostics. No logging/telemetry feature.

Sources: [006 ownership contract](../006-local-observation-service/contracts/local-observation-service.md),
[asyncio SIGINT](https://docs.python.org/3.14/library/asyncio-runner.html#handling-keyboard-interruption),
[HTTPX logging](https://www.python-httpx.org/logging/).

## Tooling and acceptance

Decision: extend actual workspace/static/test paths and import/Ruff contracts after
CLI package exists; strengthen inward direction without exemptions. Tests can use
actual006 guarded app/loopback/fakes and existing Enhanced-shaped fixture; CLI
production imports no Core/service implementation. Final software gate has explicit
platform/hardware limits. Graphify assessment only near implementation completion,
with exactly one code-only update if structural trigger applies, not during planning.
CLI/Core/service import separation stays transitive; a separate direct-only external
ban (allow_indirect_imports=true, documented as in006) permits required framework
internals without allowing product serial/sqlite/server/MCP/subprocess imports.

Alternative new shared DTO/client framework, extraction of service bootstrap or Core
logic, and full Superpowers pipeline rejected: no demonstrated need in this slice.
No unresolved decision remains; no runnable CLI/service behavior is claimed here.
