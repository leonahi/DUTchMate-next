# Quickstart: Receive-Only Monitor Software Validation

**Implementation state**: T001–T037 complete (37/37). The bounded Monitor is implemented and safe software acceptance passed at T034 (2804 focused/5783 full-suite cases). All 37 implementation tasks are complete; Feature 009 is software-complete; Phase 1 and native/physical acceptance remain incomplete. Nothing here authorizes physical-device access. [Contract](contracts/monitor.md) owns bounds/errors/outputs; [tasks](tasks.md) owns execution order and the Graphify deferral through T035. Detailed evidence lives in [history](../../docs/development_history.md).

## Prerequisites and safety

Use the committed001–008 uv workspace/Python version and existing physical-device/real-account guards. Tests create their own fake backends, temporary SQLite/profile/credential roots and, where needed, virtual ports. Never enumerate/select an attached port or use a developer's real service credentials. Do not run live service/attach commands against a DUT as part of this guide. Native Linux/Windows, active-DUT, physical/electrical and Enhanced hardware acceptance remain separate and unexecuted.

## Focused software checkpoints

Run through RTK and uv from repository root:

```bash
rtk proxy uv run pytest core/tests/unit/test_monitor_values.py core/tests/unit/test_monitor_matcher.py core/tests/unit/test_operation_evidence.py core/tests/unit/test_operation_codec.py
rtk proxy uv run pytest core/tests/contract/test_monitor_journal.py core/tests/contract/test_terminal_evidence_reader.py core/tests/contract/test_sqlite_evidence_journal.py
rtk proxy uv run pytest core/tests/contract/test_monitor_recording.py
rtk proxy uv run pytest core/tests/integration/test_monitor.py core/tests/unit/test_monotonic_clock.py
rtk proxy uv run pytest core/tests/contract/test_monitor_runtime.py core/tests/integration/test_monitor.py
rtk proxy uv run pytest apps/service/tests/test_monitor_http.py
rtk proxy uv run pytest apps/cli/tests/test_cli_monitor.py
rtk proxy uv run pytest apps/service/tests/test_monitor_http.py apps/service/tests/test_monitor_lifetime.py apps/cli/tests/test_cli_monitor.py
rtk proxy uv run pytest apps/cli/tests/test_cli_monitor_process.py
```

Test groups must use the same assertions across Basic/Enhanced-shaped fixtures where backend independent. The simulated fixture is software-contract evidence only. RED task runs are expected to expose missing specified behavior; do not record those as GREEN or implement in a RED-only task.

## Guarded story acceptance

1. US1: already active fake-DUT run; request binary literal split across chunks after committed operation-start. Assert one RX owner, first match/endpoints, preserved full raw chunks/provenance and both marker refs. Repeat with pre-start bytes, timeout, unavailable/terminal/different session and overlapping concurrent requests.
2. US2: injected clock with RX just before/at/after deadline; match at byte bound; observed loss resets prefix, segment/origin/connection failure terminates. Roll retention over markers/RX and continue008 fixed-snapshot pages. Confirm complete/partial/expired/not_found, zero-shortage page and unchanged cursor fields; no pinning/trimming.
3. US3: cancel waiter/HTTP client, gate start/end submission, detach and shutdown. Prove positive writes joined before writer close, first decision frozen, valid end_unconfirmed report when end fails, no invented start on failure and permanently false reader-cleanup latch prevents clean service marker.
4. Installed: build/install wheel and sdist stacks outside repository without editable/.pth dependence under existing guards; exercise actual authenticated service/CLI monitor plus active/terminal marker retrieval, SIGINT/closed pipes/private errors. Inspect module bytes/metadata/entry points against declarations and uv.lock.

## Implemented CLI/API surface (guarded stack only)

Static help is resource-free: `rtk proxy uv run dutchmate monitor --help`. In a test-created active service, the exact command grammar is:

```text
dutchmate --host 127.0.0.1 --port TEST_PORT monitor --session TEST_SESSION --condition-base64 UEFTUw== --timeout-ms 4000 --max-rx-bytes 65536
```

One POST `/v1/observation/monitor` with the four closed required fields; no query/path/database selector. Normal report on stdout compact JSON+LF, exit0 for any outcome/durability. Inspect provenance, timing origin, window/match refs and independent end durability. Explicit evidence retrieval can inspect those refs/window; Monitor never auto-fetches them. Authentication/browser/media failures precede body/journal work.

Check decoded condition1/256/257 bytes, timeout1/4000/4001, RX bound1/1048576/1048577, body16384/16385, canonical JSON1048576/1048577, CLI LF excluded and008 cursor1024/1025. Whole413 returns no partial report/record/cursor. Original007 receipt/timeouts/interrupt/exits and008 snapshot/error behavior stay exact. Oversized result can follow a settled operation;4s observation is not a guarantee for blocked journal or HTTP delivery.

## T034 observed software acceptance

On macOS/arm64 with Python 3.14.3, the safe checkpoints above pass: 2804 focused
cases and the required full gate's 5783 cases, zero failures/errors/skips. Existing
guards isolate accounts, prohibit physical-device access and restrict live flows
to test-created services/fake DUTs. This records observed results; the
[contract](contracts/monitor.md) remains normative.

| Surface | Observed result |
|---|---|
| Commands and route | Root/Monitor/evidence record/page help exits0 without account/credential/network work. Required Monitor options and one literal authenticated POST match the grammar above; aliases/extra selectors reject. |
| Input limits | Exact condition1/256 bytes, timeout1/4000 ms and RX bound1/1048576 accept; condition257, timeout4001 and RX1048577 reject. Canonical base64/pad bits and session1..256 UTF-8 bytes remain strict. |
| Observation | Deadline equality times out; a match on the final permitted byte wins. Full raw chunks and trailing/ambient bytes remain evidence. The4000 ms observation ceiling does not replace5s HTTP phases/10s overall or bound journal/cleanup latency. |
| Body | Actual UTF-8/chunked16384 bytes accept;16385 returns whole413 request/payload_too_large independently of Content-Length, without Core admission. |
| Delivery | Service Monitor/evidence canonical JSON1048576 accepts;1048577 returns whole413 with its existing monitor/evidence delivery_too_large category. CLI raw/canonical caps are independent; oversized replies are invalid_response5. JSON limit excludes the extra LF. |
| Cursors and retrieval |008 token1024 accepts;1025 input rejects before Core/credentials. Oversized emitted cursors reject wholly. Fixed snapshots, expired/partial/not_found and zero-shortage pages remain intact; no trimming, pinning or automatic fetch. |
| Reports and privacy | Closed14-field reports, both marker shapes, all nine outcomes/both durability states and20 journal categories pass. Valid reports exit0; existing private error/receipt/interrupt/pipe behavior remains intact. Security/readiness/media failures precede body/marker work; responses retain no-store. |
| Ownership and shutdown | Independent8-read/8-mutation/1-Monitor jobs, cancellation, submitted marker joins and permanent reader-cleanup uncertainty pass; ambiguous end ACKs remain end_unconfirmed. |
| Installed artifacts |153 installed Monitor and223 existing007/008 process cases pass across wheel/sdist, numeric IPv4/IPv6 and both backend-shaped fixtures where applicable. Four isolated non-editable installs and14 fresh archives pass module/metadata/entry/lock/exclusion inspection. |

No source/test/dependency correction was needed. Detailed commands and evidence are
in [development history](../../docs/development_history.md). Native Linux/Windows,
active-DUT, physical/electrical and Enhanced hardware acceptance remain unexecuted;
actual Windows commands remain unsupported. Software fixtures do not establish
hardware acceptance. T001–T037 are complete and Feature 009 is software-complete; Phase 1 and native/physical acceptance remain pending.

## Required full software gate

```bash
rtk proxy uv run ruff check .
rtk proxy uv run mypy .
rtk proxy uv run lint-imports
rtk proxy uv run pytest
rtk proxy git diff --check
```

Review complete feature diff and install metadata/artifact membership; no generated/runtime/credential/Graphify files. Verify old v1 factories/codecs and Profile-v1 byte/behavior compatibility, explicit v2 version/read-only validation and unchanged backend contract. Record actual counts/platform and all skipped/unexecuted acceptance honestly. Rerun full gate after corrective changes. Update current status/history only for completed tasks; planning alone marks none complete. No commit/push/next slice is implied by this guide.
