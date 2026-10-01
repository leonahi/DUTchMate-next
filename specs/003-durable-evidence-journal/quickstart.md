# Quickstart: Validate Durable Evidence Journal

This quickstart is the required software-only validation shape after
implementation. It creates journals only under pytest temporary directories and
must not enumerate or open a serial device.

## 1. Model and codec foundation

```bash
uv run --frozen pytest \
  core/tests/unit/test_evidence_journal_model.py \
  core/tests/unit/test_sqlite_evidence_codec.py
```

Proves validated bounded policies, references/cursors, normalized provenance
envelopes with opaque backend kind/version, signed-64-bit durable integer
bounds, independent retrieval ceilings, strict schema-version-1 encoding,
every current evidence variant, and exact all-byte RX round trips.

## 2. Durable append and process recovery

```bash
uv run --frozen pytest \
  core/tests/contract/test_sqlite_evidence_journal.py \
  core/tests/integration/test_sqlite_recovery.py \
  -k 'append or reopen or recovery or interrupted or ambiguous or cancellation or exhausted or thread'
```

Proves commit-before-acknowledgment behavior observable through reopen, durable
sequence continuation, abrupt process-exit recovery, all-or-nothing interrupted
transactions, one-thread SQLite connection ownership, cancellation-safe gate
and close ordering, explicit sequence/counter exhaustion, and the documented
commit-before-cancellation/return ambiguity. It does not claim arbitrary
power-loss acceptance.

## 3. Retention, references, and bounded retrieval

```bash
uv run --frozen pytest \
  core/tests/contract/test_sqlite_evidence_journal.py \
  -k 'retention or expired or partial or reference or page or cursor or bound or ceiling or empty_range'
```

Proves count/byte rolling retention, minimum-prefix deletion, persisted physical
page policy reapplied and verified on writable connections, oversized-record
no-op, constant-size coalesced marker with discarded RX byte counts, stable
expired/partial/not-found and empty-range outcomes, independent bounded page
ceilings, and fixed-snapshot keyset pagination.

## 4. Compatibility, corruption, and capacity failures

```bash
uv run --frozen pytest \
  core/tests/contract/test_sqlite_evidence_journal.py \
  core/tests/integration/test_sqlite_recovery.py \
  -k 'version or envelope or opaque_provenance or application or corrupt or malformed or locked or capacity or read_only'
```

Proves fail-closed open/append behavior, normalized failures, and preservation
of the source journal. Unsupported generic provenance envelopes fail while
unknown conforming backend kind/schema versions round-trip opaquely. Raw
SQLite/OS exceptions are not accepted results.

## 5. Acquisition integration and prior-feature regressions

```bash
uv run --frozen pytest \
  core/tests/integration/test_durable_acquisition.py \
  core/tests/integration/test_acquisition.py \
  core/tests/integration/test_basic_serial_acquisition.py \
  core/tests/contract/test_backend.py \
  core/tests/contract/test_basic_serial_adapter.py
```

Proves one unchanged acquisition path can record into the durable journal,
exact bytes and provenance survive, recording failures terminate explicitly,
and no Basic-specific branch enters shared Core.

## 6. Full repository gate

```bash
uv run --frozen ruff check .
uv run --frozen mypy .
uv run --frozen lint-imports
uv run --frozen pytest
git diff --check
```

The default suite must retain its fail-closed physical-serial guard. No result
from this quickstart is hardware acceptance or arbitrary power-loss
certification.
