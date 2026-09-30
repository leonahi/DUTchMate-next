# Quickstart Validation: Basic Serial Backend Adapter

This guide validates the planned receive-only Basic serial adapter without
enumerating, opening, or changing any physical hardware. Commands become
executable after the implementation tasks are complete.

## Prerequisites

- uv and the repository-declared Python 3.14
- no physical DUT or serial adapter required
- repository root as working directory
- no environment variable or test default naming a physical serial device

## 1. Validate serial request/provenance values

```bash
uv run --frozen pytest core/tests/unit/test_basic_serial_model.py
```

Expected:

- explicit selectors and the supported configuration subset validate;
- automatic/URL/numeric selectors and unsupported combinations fail before
  host access;
- requested, effective, and open-line limitation provenance remain distinct.

## 2. Validate the adapter boundary with a fake serial library

```bash
uv run --frozen pytest core/tests/contract/test_basic_serial_adapter.py
```

Expected:

- a closed fake is fully configured before exactly one open;
- DTR/RTS intent, exclusivity, and effective settings are recorded honestly;
- binary reads and host timestamps are normalized in read-return order;
- at most one read is outstanding and no adapter queue exists;
- disconnect and open/read/close errors use normalized values;
- no test enumerates or opens a physical device.

## 3. Validate integration with feature 001 acquisition

```bash
uv run --frozen pytest \
  core/tests/integration/test_basic_serial_acquisition.py \
  core/tests/integration/test_acquisition.py
```

Expected:

- shared acquisition records exact bytes and opaque serial provenance;
- Core sequence, segment, timestamp, ownership, and teardown semantics remain
  unchanged;
- no shared behavior branches on Basic identity.

## 4. Run the complete software gate

```bash
uv run --frozen ruff check .
uv run --frozen mypy .
uv run --frozen lint-imports
uv run --frozen pytest
git diff --check
```

Expected: all checks pass with no physical serial discovery or open.

## 5. Inspect scope and dependency direction

```bash
rg -n "import serial|from serial|BasicSerial|isinstance" core/src
rg -n "FastAPI|Typer|MCP|RP2350|Zephyr|serial_for_url|list_ports" core/src
```

Expected:

- pySerial imports occur only in `adapters/basic_serial.py`;
- shared Core contains no Basic identity branch;
- no discovery, delivery framework, Enhanced implementation, or later-phase
  feature appears.

## Deferred real-hardware acceptance

Do not run these cases without separate explicit authorization, an exact target
device, and a declared electrical setup. Later acceptance must cover exact RX,
supported settings, missing/busy/permission failures, physical disconnect,
close/reopen ownership, and externally measured DTR/RTS open behavior for each
claimed OS/driver/adapter combination. A missing configuration skips; it never
falls back to another port.

## Acceptance statement

Passing this guide proves the adapter's software boundary, mapping, lifecycle,
and backend neutrality. It does not prove a real adapter, DUT compatibility,
electrical safety, baud accuracy, losslessness, a glitch-free open, or physical
DTR/RTS state.
