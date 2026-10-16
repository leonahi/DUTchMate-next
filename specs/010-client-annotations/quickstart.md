# Quickstart Validation: Client Annotations

Run from the repository root with the declared Python and locked uv environment.
The commands below execute guarded software fixtures. They do not launch an
observation service against a connected device or read real account credentials.
[The contract](contracts/annotations.md) defines behavior; current progress belongs
in [development status](../../docs/development_status.md), with completed results in
[history](../../docs/development_history.md).

## Preconditions and safety boundary

- Use test-owned temporary Profile/journal/account roots and both existing backend
  fixture shapes. Profiles remain TX-disabled with no control mappings.
- Keep parent and child physical-open/discovery and real-account tripwires active.
  The installed fixtures substitute the DUT boundary, use isolated credentials and
  bind only their own numeric loopback listeners.
- Installed checks need a populated uv cache for the locked dependencies and build
  backend. The verified installed run used `UV_OFFLINE=1`; an empty-cache build
  failure establishes no product acceptance. No dependency update is required.
- Linux/macOS POSIX delivery is the current contract. These runs provide
  macOS/arm64 software evidence; actual Windows commands remain unsupported.

## Focused values, persistence, admission and delivery

```bash
rtk proxy uv run --locked --no-sync pytest \
  core/tests/unit/test_annotation_values.py \
  core/tests/unit/test_annotation_codec.py \
  core/tests/unit/test_evidence.py \
  core/tests/unit/test_sqlite_evidence_codec.py \
  core/tests/unit/test_operation_codec.py \
  core/tests/contract/test_annotation_journal.py \
  core/tests/contract/test_sqlite_evidence_journal.py \
  core/tests/contract/test_monitor_journal.py \
  core/tests/contract/test_terminal_evidence_reader.py \
  core/tests/contract/test_annotation_recording.py \
  core/tests/contract/test_annotation_runtime.py \
  core/tests/contract/test_annotation_retention.py \
  core/tests/contract/test_annotation_lifetime.py \
  core/tests/integration/test_annotations.py \
  apps/service/tests/test_annotation_http.py \
  apps/service/tests/test_annotation_lifetime.py \
  apps/cli/tests/test_cli_annotations.py -q
```

Expected: strict old codecs/factories and explicit v3; exact attributed assertions
at the shared insertion gate; bounded rate/charge/retention and honest expiry;
same-journal reads; owned cancellation/stop joins; unchanged Monitor post-ACK
timing; authenticated closed HTTP/CLI projections and private errors. The
`test_t013_authenticated_annotation_active_and_closed_v3_retrieval` cases exercise
the real v3 journal through Core, authenticated ASGI and thin CLI on both backend
shapes and IPv4/IPv6. No manual device or service command is needed.

## Non-editable installed annotation workflow

```bash
rtk proxy env UV_OFFLINE=1 uv run --locked --no-sync pytest \
  apps/cli/tests/test_cli_process.py::test_t018_built_artifacts_declare_modules_dependencies_and_real_installed_entry \
  apps/cli/tests/test_cli_evidence_process.py::test_t028_artifacts_include_evidence_and_all_installed_product_modules \
  apps/cli/tests/test_cli_annotations_process.py::test_t020_installed_help_and_invalid_annotation_do_no_io \
  apps/cli/tests/test_cli_annotations_process.py::test_t020_installed_exact_annotations_and_ambient_rx_active_terminal -q
```

The fixtures build and install wheel and sdist stacks without editable/source
imports. Service and CLI children run outside the checkout. They verify static
help/local validation, one authenticated annotation request, exact Unicode and
client-asserted attribution/host-time/reference receipt, active and confirmed-close
terminal retrieval, explicit rolling expiry, exact ambient binary RX and read-only
terminal access. The Enhanced-shaped fixture proves neutrality only.

T021 freshly ran the focused selection above (**1276 passed**) and this installed
selection (**44 passed**), with zero failures/errors/skips. Its artifact review also
checked all three packages' source bytes/metadata/entry points, non-editable
outside-cwd imports, locked dependencies and private/runtime/generated-artifact
exclusion. No production or test correction was needed.

The broader installed selection, already verified at T020, is:

```bash
rtk proxy env UV_OFFLINE=1 uv run --locked --no-sync pytest \
  apps/cli/tests/test_cli_annotations_process.py \
  apps/cli/tests/test_cli_process.py \
  apps/cli/tests/test_cli_evidence_process.py \
  apps/cli/tests/test_cli_monitor_process.py -q
```

It additionally covers deterministic rate/error boundaries, ambiguous ACKs,
malformed/oversized replies, SIGINT, closed stdout, response loss without retry and
joined service shutdown. T020's result was **529 passed**, not an additional T021
full-suite run. Exact commands, counts and evidence are recorded in history.

## Required coherent full gates

Full gates are T005, T013, T019 and fresh final T024; focused checks above do not
replace them. T024 completed its fresh final task gate:6951 passed in464.54s, zero
failures/errors/skips; Ruff/mypy107/seven import contracts/diff clean.

```bash
rtk proxy uv run --locked --no-sync ruff check .
rtk proxy uv run --locked --no-sync mypy .
rtk proxy uv run --locked --no-sync lint-imports
rtk proxy uv run --locked --no-sync pytest
rtk proxy git diff --check
```

T021's fresh Ruff/mypy/seven import contracts and diff checks pass. No corrective
executable or governing-contract change required a full-gate rerun during T021.
T024 freshly verified all529 guarded installed-process cases within the full6951
run (153 annotation/376 prior CLI/evidence/Monitor), not an additional test run.
Its20 fresh wheel/sdist archives and six full-stack/two CLI-only non-editable
installs passed exact source/metadata/entry/import/locked-dependency/privacy review.
Final Core/contract review found no defect; no corrective change or full-gate rerun.

T022 reconciled completed evidence/progress and Core16 conformance. T023 completed
one final code-only incremental Graphify update with recorded tooling/health limits;
T024 fresh final verification is complete:24/24 tasks. No product tests were rerun
for T022 documentation, T023 tooling/documentation or post-gate evidence recording.

Feature010 is software-complete; implementation commit is recorded in development_status.md; Phase1 remains incomplete.
The separately authorized final pre-commit review/commit is recorded in development_status.md. Native Linux/Windows, active-DUT,
physical/electrical/safe-open and Enhanced hardware acceptance remain unexecuted.
Follow, TX/Interact/console, Control, handoff/reconnect and the other contract
deferrals remain outside this slice. No Graphify, commit/push or hardware action is
authorized by this quickstart.

The separately authorized pre-commit gate freshly passed6951 tests in471.58s
from the staged export, with Ruff/mypy107/seven import contracts and staged diff
checks clean;20 fresh archives/eight non-editable installs pass privacy/import
review. No product correction, Graphify rerun, push or hardware action. Commit
baseline and the next authorization boundary are in development_status.md.
