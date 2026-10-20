# Validation Guide: Bounded Interact

[Core](../../docs/project_context_core.md) and the [012 contract](contracts/interact.md)
govern behavior. [Development status](../../docs/development_status.md) records the
current checkpoint; [history](../../docs/development_history.md) holds the observed
RED/GREEN counts and exact earlier commands. This guide contains executable,
guarded validation flows, not instructions to select or open a physical target.
T030's fresh final software gate and installed/artifact/privacy/Core review pass.
Feature 012 is software-complete within the observed macOS/arm64 scope; Phase 1
remains incomplete. Subsequent authorized pre-commit review/commit is complete;
its corrected11,399-test gate and staged artifact/privacy checks pass. T029 tooling
result/limits remain historical in status/history, without a rerun.

## Preconditions

Use the repository Python3.14 and locked uv environment. The commands below reuse
the existing populated offline uv cache and environment; `--no-sync` assumes that
environment is already prepared. An empty cache cannot build/install offline.
Build/cache and numeric-loopback access may require sandbox permission. A denied
socket or unavailable build dependency is an infrastructure failure, not passed
acceptance. Do not disable authentication or the account/device/discovery guards.

All Profile2 TX authorization, serial-library handles, backend shapes, RX and
write results in these tests are temporary fixtures. The installed service uses
real Core/composition/authentication/HTTP/CLI and temporary SQLite journals; only
external backend work, clock progress and append acknowledgements are controlled.
No real Profile, physical device, discovery result or real service credential is
used. The Enhanced-shaped fixture proves normalized-boundary neutrality only.

## Installed Interact and Artifact Audit

Run the complete installed module:

```bash
rtk proxy env UV_OFFLINE=1 uv run --no-sync pytest apps/cli/tests/test_cli_interact_process.py -q -W error --tb=short --junitxml=/private/tmp/dutchmate-012-t027-installed.xml
```

The unchanged007–011 builders create fresh wheel/sdist pairs for Core, service and
CLI, install each full stack non-editably in temporary environments, and execute
outside checkout. PYTHONPATH contains only independent test guards/control
helpers. Account-state, serial-open/discovery and DNS tripwires run before product
imports; actual numeric IPv4/IPv6 authentication remains enabled.

The192 transaction cases cover24 scenarios in every wheel/sdist × IPv4/IPv6 ×
Basic/Enhanced-shaped cell:

- Exact all-byte payload, ordered literal conditions, early pre-ACK chunk-spanning
  RX, original whole chunks, timeout/byte bounds and same-ending-byte ties.
- Concurrent Monitor, Follow, annotations and active/confirmed-close readback;
  one authoritative RX path and one admitted write, with independent capacities.
- Full, prefix, zero, timeout, disconnect, I/O and malformed write results;
  ambiguous intent ACK suppressing TX, independent TX/end audit uncertainty,
  unpaired retained rows and rolling expiry without replay or pinning.
- Actual client SIGINT, finite HTTP deadline and OS EPIPE; no synthesis, retry,
  poll or implicit detach. Service slots remain owned through write/audit joins.
- Repeated service stop while write/end audit is held; synchronous seal before
  HTTP drain, write before physical close and audit before journal close/clean
  bootstrap publication.
- Default API1/Profile1/receive-only behavior, explicit API2 legacy readback and
  explicit API1 rejection against a Profile2/journal4 run without downgrade.

Five T027 audit cases additionally compare all packaged product bytes and public
sdist source/test/config bytes with the checkout. They check METADATA/PKG-INFO,
Python/dependency declarations, wheel tags and console entry point, every wheel
RECORD hash/size, both installations' RECORD entries and module hashes,
locked external versions, original archive URL, non-editable import paths
and absence of private/generated files. Public Python tests and the root public
.gitignore intentionally remain in sdists; wheels contain only product modules
and distribution metadata. No artifact contains runtime journals/credentials,
caches, local agent installations or Graphify output.

Run only those artifact audits:

```bash
rtk proxy env UV_OFFLINE=1 uv run --no-sync pytest apps/cli/tests/test_cli_interact_process.py -k t027 -q -W error --tb=short --basetemp=/private/tmp/dutchmate-012-t030-artifacts --junitxml=/private/tmp/dutchmate-012-t030-artifacts.xml
```

## Compatibility and Defect Regression

The existing installed workflows remain executable through their unchanged
builders, guards and authentication paths:

```bash
rtk proxy env UV_OFFLINE=1 uv run --no-sync pytest apps/cli/tests/test_cli_process.py apps/cli/tests/test_cli_evidence_process.py apps/cli/tests/test_cli_monitor_process.py apps/cli/tests/test_cli_annotations_process.py apps/cli/tests/test_cli_follow_process.py -q -W error --tb=short
```

T027's narrow codec regression rejects a full TX acknowledgement paired with a
`tx_failed` observation even when an external overall termination is recorded.
It verifies invalid-input/corrupt-journal mappings and append non-mutation using
both backend shapes and real temporary journals:

```bash
rtk proxy env UV_CACHE_DIR=/private/tmp/dutchmate-012-uv-cache UV_OFFLINE=1 uv run --no-sync pytest core/tests/contract/test_interact_journal.py -k t027 -q -W error --tb=short --junitxml=/private/tmp/dutchmate-012-t027-green.xml
```

Legacy Profile constructors/defaults, codecs/charges/factories, Monitor clocks,
security and finite thin-client delivery remain governed by001–011. Explicit
Profile2 selects journal4 and optional Basic TX capability independently of its
TX permission; Interact requires that permission and explicit API2. No-flag CLI
and Profile1 keep API1/journal3/RX behavior. The complete focused selections and
observed results are recorded in history, rather than duplicated here.

## Observed T027 Checkpoint

Four reproduced codec regressions are GREEN;1507 focused Core/2350 delivery tests
and five fresh artifact audits pass. The required correction-triggered full gate
passes11393 tests (1017.80s), including197 installed Interact/artifact cases and625
legacy CLI process cases. Zero failures/errors/skips, warnings as errors; Ruff,
mypy142/seven import contracts and scope/docs/diff checks pass. Only the five-line
shared v4 consistency check changed production at T027. These 197 final module
passes are contained in /private/tmp/dutchmate-012-t027-full.xml. The earlier
standalone /private/tmp/dutchmate-012-t027-installed.xml contains three intermediate
authoring/stale-artifact failures, recorded in history; it is not final GREEN
evidence. T028 documentation and T029 tooling add no test execution at those
checkpoints; the separate fresh T030 result follows.

## Observed T030 Final Software Checkpoint

The full gate passes 11,393 tests in1020.29s (JUnit1020.164s), zero failures/errors/
skips, warnings as errors: Core4539/service2777/CLI4077. It includes all197 installed
Interact/artifact cases (192 transaction scenarios plus five artifact audits) and
625 legacy process cases: observation112/evidence111/Monitor153/annotations153/
Follow96. Five fresh artifact audits also pass separately in5.76s. No production,
test, package, dependency or contract correction is needed. Full XML is
/private/tmp/dutchmate-012-t030-full-green.xml; separate artifact XML is
/private/tmp/dutchmate-012-t030-artifacts.xml.

The initial run remains recorded as failed: an incomplete selected
offline cache lacked Hatchling, giving10,576 passes/817 packaging setup errors.
Using the existing populated cache restores builds without a dependency/source
change or network download. The initial XML is /private/tmp/dutchmate-012-t030-full.xml,
not final acceptance evidence. All149 software-input hashes remain unchanged.
See history for exact commands and the full artifact/compatibility/privacy review.

## Observed Final Pre-Commit Review

Review found one journal-v4 invariant defect after T030: an unpaired retained end
could carry TX settlement before its own observation start. Both times remain in
the end, so eviction does not justify skipping that check. Remove only the retained-
start guard in sqlite_evidence.py. Six literal/real-journal cases fail then pass;
780 focused persistence/retention/audit/terminal tests pass. Writer and read-only
terminal reopen preserve the existing invariant error and cleanup categories.

Fresh full gate:11,399 passes in1021.96s (JUnit1021.782s), zero failures/errors/skips,
warnings as errors; Core4545/service2777/CLI4077. It includes197 Interact/artifact
and625 legacy process cases. Five artifact audits pass again from an independent
287-blob Git-index export, building/installing wheel/sdist outside checkout/export.
These overlapping selections are not added to the full total. Superseded baseline
run/intermediate authoring diagnostics remain distinguished in history.

```bash
rtk proxy env UV_OFFLINE=1 uv run --no-sync pytest -q -W error --tb=short -rN --basetemp=/private/tmp/dutchmate-012-precommit-green-full --junitxml=/private/tmp/dutchmate-012-precommit-green-full.xml
```

Only the validator and journal regression file change software inputs at this
checkpoint. Legacy codecs/charges/Profile1/API1 and ownership/clocks remain intact.
All task definitions/normative contracts remain unchanged. Implementation committed
as `Implement bounded interact`; no push, Graphify, hardware/accounts or next slice.

## Required Gates and Limits

Full checkpoints are T005/T019/T025/T030; T027's demonstrated persisted-fact
correction additionally required and passed a complete AGENTS8.3 gate. The
commands below reproduce the successful T030 final full gate using the existing
populated offline cache:

```bash
rtk proxy env UV_OFFLINE=1 uv run --no-sync ruff check .
rtk proxy env UV_OFFLINE=1 uv run --no-sync mypy .
rtk proxy env UV_OFFLINE=1 uv run --no-sync lint-imports
rtk proxy env UV_OFFLINE=1 uv run --no-sync pytest -q -W error --tb=short -rN --basetemp=/private/tmp/dutchmate-012-t030-full-green --junitxml=/private/tmp/dutchmate-012-t030-full-green.xml
rtk proxy git diff --check
```

A backend ACK proves backend acceptance only, never physical wire transmission
or DUT receipt. The observation cursor establishes Core order, not DUT causation
or an empty hardware/USB/OS buffer. A delivered valid report exits0 even for a
failed outcome. Unknown counts/ACKs remain unknown. Observation and library write
bounds do not impose a hard limit on OS work, journal latency or joined cleanup.

Observed native acceptance is macOS/arm64 Python3.14.3 software-only. Native
Linux/Windows driver/serial behavior, electrical pin state, physical UART/DUT
receipt and Enhanced hardware/protocol acceptance remain unvalidated and require
separate authorization. Windows CLI support is not added. No Console, arbitrary
streaming TX, Control, handoff/reconnect, text/line/regex conveniences, generic
command framework, MCP or AI behavior is supplied by these flows. Safe-open
DTR/RTS transitions/glitches and physical voltage/wiring remain unvalidated.
T030 stopped before the separately authorized pre-commit review/commit. Feature012
is software-complete and committed; Phase1 remains incomplete. No Graphify rerun,
hardware/accounts, push or next slice is authorized by these validation recipes.
