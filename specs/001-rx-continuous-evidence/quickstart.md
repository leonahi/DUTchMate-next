# Quickstart Validation: Continuous RX Evidence Foundation

This validates the implemented software-only continuous RX evidence foundation.
The commands remain hardware-free and make no hardware-acceptance claim.

## Prerequisites

- uv installed
- Python 3.14 available through uv
- no physical DUT or serial adapter required
- repository root as the working directory

Validation must not enumerate, open, reset, flash, or otherwise interact with
physical hardware.

## 1. Synchronize the declared environment

```bash
uv sync --all-packages --dev
```

Expected: root workspace and `dutchmate-core` test environment resolve on
Python 3.14 from `pyproject.toml` with `requires-python = ">=3.14,<3.15"` and
`uv.lock`.

## 2. Run focused model and contract tests

```bash
uv run pytest core/tests/unit/test_model.py core/tests/contract/test_backend.py
```

Expected:

- empty RX, zero loss counts, and unknown backend-observation timestamp domains
  are rejected;
- both test backends satisfy the same single-consumer stream contract;
- no serial-library or Enhanced protocol type crosses the contract.

## 3. Run evidence and acquisition tests

```bash
uv run pytest core/tests/unit/test_evidence.py core/tests/integration/test_acquisition.py
```

Expected:

- every byte value, NUL, and invalid UTF-8 round-trips exactly;
- arbitrary chunking reconstructs the same ordered bytes;
- idle periods do not stop acquisition;
- one active connection has one RX consumer;
- repeated timestamps do not affect Core sequence order;
- origin reset creates a new segment;
- missing Basic telemetry never becomes a lossless claim;
- Enhanced-shaped overflow has device-domain provenance;
- disconnect and recorder failure terminate explicitly.

## 4. Run the complete software gate

```bash
uv run ruff check .
uv run mypy .
uv run lint-imports
uv run pytest
git diff --check
```

Expected: all commands pass with no hardware attached. An absent/skipped
hardware test is not evidence of hardware support.

## 5. Review scope and neutrality

```bash
rg -n "serial|FastAPI|Typer|MCP|RP2350|Zephyr|backend.*(name|type)|isinstance" core/src core/tests
```

Review every match. Tests may mention backend shapes, but shared Device Core
code must contain no backend-identity branch, serial dependency, HTTP/CLI/MCP
framework, helper protocol, firmware behavior, or later-phase feature.

## Acceptance statement

Passing this guide proves only the software contract and neutrality fixture. It
does not prove a real Basic connection, Enhanced hardware, serial-open behavior,
timing accuracy, physical losslessness, or hardware acceptance.
