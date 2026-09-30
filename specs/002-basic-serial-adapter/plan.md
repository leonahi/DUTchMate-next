# Implementation Plan: Basic Serial Backend Adapter

**Branch**: `main` | **Date**: 2026-09-30 | **Spec**: [spec.md](spec.md)

**Input**: Focused feature specification in
`specs/002-basic-serial-adapter/spec.md`

## Summary

Add one real receive-only Basic adapter behind feature 001's normalized
`Backend`/`BackendConnection` protocols. The adapter will use pySerial 3.5,
require an exact platform device name, configure a closed `Serial` instance
before one open, snapshot requested/effective serial and DTR/RTS-open
provenance, and deliver sequential exact-byte reads through the existing async
event stream with host monotonic timestamps. Shared acquisition will only copy
opaque connection provenance; it will not import pySerial or branch on Basic
identity. All implementation tests in this slice are hardware-free.

## Technical Context

**Language/Version**: Python 3.14 with
`requires-python = ">=3.14,<3.15"`

**Primary Dependencies**: pySerial 3.5 as the runtime host-serial library;
Python `asyncio.to_thread` and `time.monotonic_ns` for sequential non-blocking
integration and timestamps; `types-pyserial==3.5.0.20260712` for development
typing; existing pytest, pytest-asyncio, ruff, mypy, and import-linter tooling

**Storage**: Existing in-memory evidence journal only; the adapter contributes
immutable connection/segment provenance and normalized observations. Durable
storage and retention remain deferred.

**Testing**: Test-first pytest unit, adapter-contract, and acquisition
integration tests with an injected private serial-library fake; optional
POSIX-only test-created PTY coverage; unchanged feature 001 regression suite

**Target Platform**: CPython 3.14 on Linux, macOS, and Windows, within the
behavior documented by pySerial. Hardware support claims require later opt-in
acceptance on named adapter/driver/OS combinations.

**Project Type**: Existing uv workspace and `dutchmate-core` library, with one
new infrastructure adapter subpackage

**Performance Goals**: Preserve 100% of bytes and read-return order under
bounded tests. No UART throughput or latency guarantee is invented before
hardware acceptance.

**Constraints**: Exact user-selected device; one physical owner; at most one
outstanding read and one normalized stream consumer; no adapter queue; exact
bytes; Core-assigned evidence order; host-observation timestamps with a fresh
domain/origin per open; upstream loss remains unobservable; DTR/RTS intent is
configured before open but glitch-free electrical behavior is not claimed;
default tests open no physical device

**Scale/Scope**: One serial device and one receive-only connection at a time;
six requested/effective UART setting fields; DTR/RTS open provenance; open,
read/disconnect, and close failure normalization; no TX, Control, reconnect,
profile schema, delivery surface, or persistence

## Constitution Check

The installed `.specify/memory/constitution.md` is an unfilled template and is
not a project authority. Per `AGENTS.md` §2, this gate uses the Core document,
the active specification, the feature 001 normalized contract, and repository
engineering constraints.

### Pre-design gate

| Gate | Result | Evidence |
|---|---|---|
| Core authority preserved | PASS | The specification implements Core §§9.4, 13.1, and 17.5 without changing product semantics. |
| Feature 001 contract preserved | PASS | The descriptor/provenance is extended; event, sequence, timestamp comparison, segment, ownership, and teardown rules remain unchanged. |
| Explicit device ownership | PASS | Open requires one exact device name and performs no discovery or fallback. |
| Serial-open safety is honest | PASS | DTR/RTS intent is preconfigured and both glitch and electrical-verification limits are recorded. |
| One authoritative RX path | PASS | One sequential `to_thread` read is outstanding; the existing acquisition coordinator remains the only event consumer. |
| Exact bytes and provenance | PASS | Non-empty read results cross unchanged with a host monotonic observation timestamp. |
| Backend neutrality | PASS | pySerial and Basic provenance terminate in the adapter; shared code copies the base provenance type without inspecting it. |
| Inward dependencies | PASS | The adapter depends on backend/model contracts; shared acquisition/domain modules are forbidden from importing adapters. |
| No later-phase work | PASS | TX, Control, reconnect, persistence, service, CLI, Enhanced, and MCP are excluded. |
| Hardware safety | PASS | Default validation uses fakes or test-created virtual ports only and performs no enumeration. |

## Project Structure

### Documentation (this feature)

```text
specs/002-basic-serial-adapter/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── basic-serial-adapter.md
├── checklists/
│   └── requirements.md
└── tasks.md
```

### Source Code (repository root)

```text
pyproject.toml                              # tooling + exact adapter import rule
uv.lock                                    # reproducible pySerial/stub resolution
core/
├── pyproject.toml                         # pySerial runtime dependency
├── src/dutchmate_core/
│   ├── model.py                           # provenance base + segment snapshot field
│   ├── backend.py                         # normalized backend failure values
│   └── adapters/
│       ├── __init__.py                    # adapter package marker
│       └── basic_serial.py                # only pySerial-importing product module
└── tests/
    ├── fakes.py                           # existing backend fixtures remain neutral
    ├── unit/test_basic_serial_model.py    # request/provenance validation
    ├── contract/test_basic_serial_adapter.py # open/read/close boundary contract
    └── integration/test_basic_serial_acquisition.py # adapter through Acquisition
```

**Structure Decision**: Keep the adapter in `dutchmate_core.adapters` because
the repository's core package intentionally contains ports and infrastructure
adapters. Only `adapters/basic_serial.py` receives a narrow Ruff `serial`
import exemption. Import Linter will forbid acquisition, backend, evidence, and
model modules from importing `dutchmate_core.adapters`, turning the normalized
boundary into an enforced dependency direction. No package, factory, registry,
or composition root is added before a delivery slice needs one.

## Architectural Invariants

1. `Acquisition` continues to consume only `Backend`; it never imports or tests
   for `BasicSerialBackend` or Basic provenance.
2. The serial-library object and exceptions exist only in
   `dutchmate_core.adapters.basic_serial` and its focused tests.
3. One async generator issues one blocking `read()` via `asyncio.to_thread` at
   a time. There is no second reader or adapter buffer that can reorder/drop RX.
4. The adapter timestamps the returned bytes inside the blocking helper
   immediately after `read()` returns; evidence sequence remains authoritative.
5. Every successful open creates fresh host timestamp domain/origin identities
   and immutable serial provenance copied into every segment for that
   connection.
6. Requested/effective settings and line behavior are distinct. Library state
   is never mislabeled as electrical measurement or glitch-free proof.
7. Open/read/close behavior is classified by normalized enum/category fields,
   never by exception message text above the adapter boundary.
8. The adapter reports only `uart_receive`; open-time DTR/RTS setup is not
   semantic Control and does not report `serial_line_control`.
9. No test enumerates or opens physical serial hardware unless an explicit,
   separately authorized opt-in hardware configuration is provided.

## Implementation Steps

1. **Add and constrain the dependency boundary.** Add pySerial 3.5 and matching
   type stubs through uv, record license/provenance as required, create the
   adapter package, add the exact-file Ruff exemption, and extend architecture
   checks so shared Core cannot import adapters.
2. **Define normalized configuration and provenance values.** Add validated
   serial selector/configuration, line-intent, open-limitation, and Basic serial
   connection-provenance values, plus a backend-neutral provenance base copied
   by `ConnectionDescriptor` and `SegmentProvenance`.
3. **Define normalized failure values.** Add open/read/close operation and
   failure categories to the backend boundary without serial exception types or
   platform handles.
4. **Test and implement safe open.** First add failing tests for selector and
   configuration validation, exact pySerial mapping, configure-before-open
   order, exclusivity, effective-setting verification, DTR/RTS provenance,
   cleanup, and open-failure normalization; then implement only that behavior.
5. **Test and implement normalized RX.** First add failing tests for arbitrary
   binary reads, timestamp capture, empty reads, one outstanding read,
   sequential backpressure, classified disconnect, and unclassified read
   failure; then implement the sequential `asyncio.to_thread` event stream.
6. **Test and implement close lifecycle.** First add failing tests for
   cross-thread read cancellation, idempotent close, close failure, and primary
   failure preservation through existing acquisition teardown; then implement
   minimum close behavior.
7. **Integrate without Core branching.** Pass the real adapter connection
   through `Acquisition`, snapshot opaque provenance, retain all feature 001
   tests, and optionally add a POSIX PTY smoke test that opens only its own
   test-created device.
8. **Validate scope and record acceptance debt.** Run focused and full gates,
   inspect imports/diffs for Basic leakage or deferred behavior, document the
   unexecuted OS/driver/adapter hardware acceptance matrix, and update current
   status/history only after validated implementation.

## Platform-Specific Risks

- pySerial documents that some OSes/drivers assert DTR/RTS immediately on open
  and may glitch before requested values are applied. Software cannot promote
  preconfiguration into an electrical guarantee.
- POSIX pySerial may ignore `EINVAL`/`ENOTTY` while applying DTR/RTS. The
  returned property is therefore library-reported intent, not pin verification.
- Windows and POSIX expose different open/exclusive and error representations;
  failure classification must use stable attributes/errno where present and
  otherwise remain a generic transport failure.
- Non-standard baud support varies by OS, driver, and adapter. A positive value
  is requestable but never silently substituted.
- `cancel_read()` is documented for cross-thread use, but close/read races and
  platform regressions require focused fake tests plus later platform/hardware
  acceptance.
- A native USB console may disappear on DUT reset; reconnect matching and
  expected-disconnect policy are deliberately outside this slice.

## Critical Tests

- Reject absent/blank/numeric/URL/automatic selectors before serial API use.
- Validate every supported enum and reject unsupported parity, stop bits, and
  combined RTS/CTS plus XON/XOFF.
- Prove all settings and applicable DTR/RTS values are assigned before exactly
  one `open()`; prove mismatched effective settings fail and clean up.
- Prove provenance distinguishes requested, library-reported effective, and
  electrically unverified/glitch-not-guaranteed statements.
- Round-trip all byte values, NULs, and invalid UTF-8 in read-return order with
  one host timestamp per non-empty read and no empty RX event.
- Prove at most one read is outstanding and the next read waits until the prior
  event is consumed.
- Prove only stable error attributes classify `Disconnected`; all other
  exceptions become normalized read failures without leaked types.
- Prove `close()` cancels an outstanding read, is idempotent, and preserves
  feature 001 teardown/primary-failure semantics.
- Prove the adapter reports only `uart_receive` and upstream loss unobservable.
- Prove feature 001 shared acquisition behavior remains unchanged and no shared
  production module imports or branches on the Basic adapter.

## Later Real-Hardware Acceptance Criteria

These cases are defined now but are not executed in planning or default tests:

1. On each claimed Linux/macOS/Windows + driver + adapter combination, open the
   explicitly configured port and receive a known binary pattern exactly.
2. Exercise supported data bits, parity, stop bits, RTS/CTS, XON/XOFF, standard
   and selected non-standard baud values; confirm accepted/rejected effective
   settings without silent substitution.
3. Verify missing, permission-denied, and already-owned device outcomes.
4. Physically disconnect during a blocking read and confirm the honest
   normalized disconnect or transport-failure category for that platform.
5. Close and prove another owner can open the same device, then reopen through
   DUTchMate with a fresh connection and timestamp origin.
6. With DTR/RTS connected to suitable measurement equipment—not an unknown
   DUT—capture open-time transitions and steady state. Record whether the
   documented glitch limitation occurs for each combination.

## Validation Requirements

During implementation, run focused adapter unit/contract/integration tests
after each RED/GREEN group. Before completion run:

```bash
uv run --frozen ruff check .
uv run --frozen mypy .
uv run --frozen lint-imports
uv run --frozen pytest
git diff --check
```

Also run the feature quickstart groups, inspect `core/src` imports and branches,
confirm no physical enumeration/open call occurs in the default suite, and
report all real-hardware acceptance as unexecuted.

## Post-design Constitution Check

PASS. The data model and adapter contract extend feature 001 only with immutable
backend connection provenance and normalized failure categories. The chosen
module boundary contains pySerial and the one precise lint exemption; shared
Core remains capability/provenance driven. The design adds no TX, Control,
reconnect, profile delivery, persistence, service, CLI, Enhanced, MCP, or
hardware claim. All pre-design gates remain satisfied.

## Complexity Tracking

No governing-rule violation is planned. The private serial-construction seam is
the minimum test boundary for hardware-free validation, and the one adapter
module is the only justified pySerial import location.
