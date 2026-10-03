# Quickstart: Validate Observation-Only DUT Profile and Policy

This quickstart is the required software-only validation shape after
implementation. It reads only pytest-created temporary Profile files. It must
not enumerate or open a serial device, start acquisition, or create a journal.

## 1. Generic Profile values and safe policy

```bash
uv run --frozen pytest core/tests/unit/test_profile_model.py
```

Proves immutable identity, backend-selection, UART/open-line, observation-policy,
and resolved-Profile values; RX/recording as mandatory current observation
invariants; TX/Control/reconnect as fail-closed permissions; safe defaults;
explicit rejection of state-changing policy; and reuse of the existing
signed-64-bit `SessionPolicy` validation.

## 2. Strict TOML Profile v1 resolution

```bash
uv run --frozen pytest core/tests/contract/test_toml_profile.py
```

Proves explicit-path-only loading, one immutable snapshot, exact supported
values, closed schema, and the fixed failure-category matrix. It also proves an
exactly 65,536-byte captured input reaches parsing while a 65,537-byte capture
returns `input_too_large` before parsing, without relying on filesystem metadata
and without a parser tree or partial result.

The tests must install the repository's fail-closed serial guard and assert
that Profile resolution performs no device enumeration/open, acquisition,
journal open/create, or session creation.

## 3. Basic adapter and durable-policy mappings

```bash
uv run --frozen pytest \
  core/tests/contract/test_basic_profile_mapping.py \
  core/tests/contract/test_basic_serial_adapter.py \
  core/tests/unit/test_evidence_journal_model.py
```

Proves exact field-for-field conversion into the existing feature-002
`BasicSerialOpenRequest`, no Basic type in the generic Profile model, no serial
construction/open during translation, and exact one-to-one reuse of all six
feature-003 `SessionPolicy` values.

## 4. Prior-feature regressions

```bash
uv run --frozen pytest \
  core/tests/unit/test_model.py \
  core/tests/unit/test_evidence.py \
  core/tests/unit/test_basic_serial_model.py \
  core/tests/unit/test_evidence_journal_model.py \
  core/tests/unit/test_sqlite_evidence_codec.py \
  core/tests/contract/test_backend.py \
  core/tests/contract/test_basic_serial_adapter.py \
  core/tests/contract/test_sqlite_evidence_journal.py \
  core/tests/integration/test_acquisition.py \
  core/tests/integration/test_basic_serial_acquisition.py \
  core/tests/integration/test_durable_acquisition.py \
  core/tests/integration/test_sqlite_recovery.py
```

Proves the completed continuous-acquisition, Basic adapter, and durable journal
contracts remain unchanged and backend-neutral.

## 5. Architecture and scope searches

```bash
rg -n "import serial|from serial" core/src/dutchmate_core \
  -g '*.py' \
  -g '!**/adapters/basic_serial.py'
rg -n "BasicSerial|pyserial|serial\.Serial" \
  core/src/dutchmate_core/profile.py
rg -n "registry|manager|discover|enumerat|open\(|Acquisition|SqliteEvidenceJournal" \
  core/src/dutchmate_core/profile.py \
  core/src/dutchmate_core/adapters/toml_profile.py \
  core/src/dutchmate_core/adapters/basic_profile.py
```

Review results semantically. Expected contract/type names in tests or comments
may be benign; product code must contain no serial import outside the existing
Basic adapter, no Basic implementation type in the generic Profile module, and
no discovery, hardware open, lifecycle, session, registry, or manager behavior.

## 6. Full repository gate

```bash
uv run --frozen ruff check .
uv run --frozen mypy .
uv run --frozen lint-imports
uv run --frozen pytest
git diff --check
```

The default suite must retain its fail-closed physical-serial guard. No result
from this quickstart is physical-hardware, electrical, lifecycle, service, or
workflow acceptance.
