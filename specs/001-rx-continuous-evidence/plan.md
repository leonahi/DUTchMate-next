# Implementation Plan: Continuous RX Evidence Foundation

**Branch**: `main` | **Date**: 2026-09-29 | **Spec**: [spec.md](spec.md)

**Input**: Focused feature specification in
`specs/001-rx-continuous-evidence/spec.md`

## Summary

Create the first `dutchmate_core` package and define the smallest normalized
backend/evidence contract that can support one continuously running,
authoritative RX path without assuming Basic serial semantics. Device Core will
assign evidence order and connection/segment identity, preserve RX payloads as
bytes, and record timestamp and loss provenance supplied through the normalized
boundary. Hardware-free Basic-shaped and Enhanced-shaped fixtures will execute
the same contract and acquisition tests. Real serial and Enhanced adapters,
workflows, persistence, service, CLI, and MCP remain outside this slice.

## Technical Context

**Language/Version**: Python 3.14 with
`requires-python = ">=3.14,<3.15"` (the declared initial repository baseline)

**Primary Dependencies**: Python standard library for runtime; uv for workspace
and dependency management; pytest and pytest-asyncio for tests; ruff, mypy, and
import-linter for the required quality and architecture gates

**Storage**: An in-memory append-only evidence recorder behind a narrow
recording port for this slice; durable bounded storage, sessions, retention, and
retrieval are explicitly deferred

**Testing**: pytest with async tests, shared backend contract tests, focused
unit tests, and hardware-free integration tests

**Target Platform**: Platform-neutral Python library; default tests must not
discover or open any physical serial device

**Project Type**: uv workspace containing one initial core library package

**Performance Goals**: No unsupported throughput target is introduced in this
foundation. The implementation must avoid per-byte decoding or semantic
processing on the authoritative path and must preserve deterministic order
under bounded test loads.

**Constraints**: Exactly one active owner and RX consumer; continuous capture
for the owned connected interval; immutable raw bytes; explicit timestamp
domain/origin; Core-assigned sequence order; no cross-domain timestamp
comparison; explicit loss observability; no backend identity branches; no real
hardware access; no later-phase functionality

**Scale/Scope**: One active backend connection, one active connection segment
at a time, one in-process evidence journal, four normalized backend event kinds,
and two test-only backend shapes

## Constitution Check

The installed `.specify/memory/constitution.md` is an unfilled template and is
not a project authority. Per `AGENTS.md` §2, this gate uses the Core document,
the focused specification, and repository engineering constraints.

### Pre-design gate

| Gate | Result | Evidence |
|---|---|---|
| Core authority preserved | PASS | The feature spec references relevant Core sections and does not restate or modify product semantics. |
| Basic-first, backend-neutral | PASS | Only test doubles are planned; shared code consumes normalized capabilities and provenance. |
| One owner and one RX path | PASS | The acquisition coordinator exclusively consumes one connection event stream. |
| Exact bytes remain authoritative | PASS | RX payloads remain immutable bytes; no decoding is on the authoritative path. |
| Timestamp domains stay explicit | PASS | Timestamp value, domain, observer, unit, and origin remain attached; evidence sequence supplies ordering. |
| Loss claims stay honest | PASS | Observer-reported loss and unobservable upstream loss are distinct. |
| Inward dependencies | PASS | Only `dutchmate_core` is created; it has no delivery, serial, HTTP, CLI, MCP, or AI dependency. |
| No speculative/later-phase work | PASS | Real adapters, protocols, workflows, persistence, service, CLI, and MCP are excluded. |
| Hardware safety | PASS | All validation is software-only and opens no physical device. |

## Project Structure

### Documentation (this feature)

```text
specs/001-rx-continuous-evidence/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── normalized-backend.md
├── checklists/
│   └── requirements.md
└── tasks.md
```

### Source Code (repository root)

```text
pyproject.toml                         # uv workspace + shared quality configuration
.python-version                       # declared Python baseline
uv.lock                               # reproducible dependency resolution
core/
├── pyproject.toml                    # dutchmate-core package metadata
├── src/dutchmate_core/
│   ├── __init__.py                   # intentionally small public surface
│   ├── model.py                      # capabilities, IDs, timestamps, events, evidence
│   ├── backend.py                    # normalized backend/connection ports
│   ├── evidence.py                   # recorder port + in-memory recorder
│   └── acquisition.py                # exclusive continuous acquisition coordinator
└── tests/
    ├── conftest.py                   # reusable fixture parameterization
    ├── fakes.py                      # Basic- and Enhanced-shaped test backends
    ├── contract/test_backend.py      # normalized backend contract tests
    ├── unit/test_model.py            # invariant/value validation
    ├── unit/test_evidence.py         # sequence and exact-byte recording
    └── integration/test_acquisition.py # continuous ownership and segmentation
```

**Structure Decision**: Start only the shared core library. The normalized
backend is a genuine external boundary and the recorder is a genuine future
persistence boundary, so each earns a small port. No adapter/application
packages are created until a focused slice needs them. Cohesive types remain
grouped rather than using one file per class.

## Architectural Invariants

1. Device Core, not a backend timestamp, assigns the authoritative order within
   its evidence journal.
2. A connection object exposes one consumable ordered event stream; only the
   acquisition coordinator consumes it.
3. Starting or stopping any future workflow cannot own or replace that stream.
4. The backend boundary contains no serial-library or Enhanced-protocol type.
5. The normalized backend RX/loss stream has exactly one stable
   backend-observation timestamp domain and loss-observability descriptor per
   segment. This does not constrain timestamp domains for future non-backend
   evidence. Origin reset starts a new segment.
6. RX bytes are copied/preserved as immutable bytes and never decoded on the
   authoritative path.
7. Missing loss telemetry means “not observable” or “no report within a stated
   observer scope,” never “lossless.”
8. The Enhanced-shaped backend exists only under tests and predicts no helper
   protocol, firmware, timing, or hardware behavior.

## Implementation Steps

1. **Establish the Python/core baseline.** Create the uv workspace, core package,
   declared Python version, test/static-analysis tooling, and enforceable
   dependency boundaries without adding service or adapter packages.
2. **Define validated domain values.** Implement immutable capability, ID,
   backend-observation timestamp-domain/timestamp, loss-observability,
   normalized event, segment provenance, and evidence record types from the
   data model.
3. **Define the normalized backend port.** Implement the backend connection
   descriptor and single-consumer async event-stream contract, including
   explicit close/disconnect behavior and contract rejection cases.
4. **Implement ordered evidence recording.** Add the recorder boundary and an
   in-memory append-only implementation that assigns/validates sequence order,
   preserves bytes, and fails explicitly rather than silently dropping data.
5. **Implement exclusive continuous acquisition.** Add the coordinator that
   owns one connection, starts one RX task, records ambient events, rejects a
   second path, isolates stale connection events, and terminates explicitly.
6. **Implement segment transitions.** Record initial segment provenance, close
   on disconnect, and start a new segment on backend-observation
   timestamp-origin reset without comparing the old and new clocks.
7. **Build neutrality fixtures and shared tests.** Add Basic-shaped host-time/no-
   telemetry and Enhanced-shaped device-time/overflow fixtures and run identical
   contract and acquisition assertions against both.
8. **Validate and document the slice.** Run focused tests and the full software
   gate, inspect the diff for backend leakage or later-phase scope, then update
   development status/history with software-only evidence and limitations.

## Critical Tests

- Round-trip every byte value, NULs, and invalid UTF-8 through arbitrary RX
  chunking with exact reconstruction.
- Prove ambient evidence is recorded before and after an idle/no-workflow period.
- Prove a second consumer/acquisition attempt is rejected.
- Prove evidence sequence remains strictly increasing for identical timestamps.
- Prove origin reset changes segments and forbids cross-origin comparison.
- Prove stale prior-connection events do not enter the current segment.
- Prove Basic-shaped absence of telemetry never becomes a lossless claim.
- Prove Enhanced-shaped overflow records count, cause, observer scope, device
  timestamp, and correct stream position.
- Prove identical shared assertions pass for both backend shapes without
  checking backend identity.
- Prove disconnect and recorder failure terminate explicitly without a silent
  evidence gap.

## Validation Requirements

During implementation, run focused test files first. Before claiming the slice
complete, run:

```bash
uv run ruff check .
uv run mypy .
uv run lint-imports
uv run pytest
git diff --check
```

Also inspect imports and test names with `rg`, review the final diff, confirm the
default test run opens no hardware, and explicitly report that the fixtures do
not provide hardware acceptance.

## Post-design Constitution Check

PASS. The data model and internal contract keep timestamp and loss differences
as normalized provenance rather than backend branches. No Basic-specific type,
serial handle, host-clock assumption, OS chunk semantics, Enhanced protocol,
real control/event behavior, delivery API, or persistence format has entered
shared code design. All pre-design gates remain satisfied.

## Complexity Tracking

No governing-rule violation or exception is planned. The two ports correspond
to demonstrated external boundaries (physical backend and future persistence),
and the in-memory recorder is the smallest concrete implementation needed to
test the slice.
