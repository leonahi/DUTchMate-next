# Tasks: Basic Serial Backend Adapter

**Input**: Design documents from `specs/002-basic-serial-adapter/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`,
`contracts/basic-serial-adapter.md`, and the completed feature 001 contract

**Tests**: This hardware-boundary feature uses TDD. For each behavioral phase,
add the named tests first, run them, and confirm RED for the intended missing
behavior before production changes.

**Scope**: Receive-only real Basic adapter. No physical hardware, TX, semantic
Control, reconnect, profile schema, persistence, service, CLI, Enhanced, or MCP.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel only when it touches different files and has no
  dependency on incomplete tasks.
- **[US1]**, **[US2]**, and **[US3]** map to the prioritized stories in
  `spec.md`.

## Phase 1: Setup (Dependency and Adapter Boundary)

**Purpose**: Add the one runtime dependency and establish the only permitted
pySerial import location without production behavior.

- [x] T001 Add `pyserial==3.5` to `core/pyproject.toml`, add `types-pyserial==3.5.0.20260712` to the root dev dependency group using uv, update `uv.lock`, verify BSD-3-Clause/Apache-2.0 suitability, and record dependency provenance in `THIRD_PARTY_NOTICES.md` (plus `LICENSES/` only where redistribution terms require a bundled notice)
- [x] T002 Create `core/src/dutchmate_core/adapters/__init__.py` and the empty implementation target `core/src/dutchmate_core/adapters/basic_serial.py`; add an exact-file Ruff `TID251` exemption for that target and an import-linter contract in `pyproject.toml` forbidding `dutchmate_core.acquisition`, `backend`, `evidence`, and `model` from importing `dutchmate_core.adapters`

**Checkpoint**: pySerial is reproducibly installed and statically confined to
one adapter module; no open/read behavior exists.

---

## Phase 2: Foundational (Normalized Values and Provenance)

**Purpose**: Extend feature 001 with the minimum backend-neutral provenance and
failure surface needed by every story.

**⚠️ CRITICAL**: Complete this phase before adapter behavior.

- [x] T003 [P] Add failing validation tests in `core/tests/unit/test_basic_serial_model.py` for `SerialDeviceSelector.device_name` being non-empty after trimming and not numeric/`auto`/`-`/URL-like; `SerialConfiguration` allowing positive baud, data bits `5|6|7|8`, parity `none|even|odd`, stop bits `one|two`, and rejecting simultaneous hardware/software flow control; and `SerialOpenLineIntent.rts` being `driver_managed` exactly when RTS/CTS is enabled
- [x] T004 [P] Add failing feature-001 compatibility tests in `core/tests/unit/test_model.py` and `core/tests/integration/test_acquisition.py` proving `ConnectionDescriptor.connection_provenance` is immutable, is copied unchanged into `SegmentProvenance`, survives timestamp-origin reset, and is never used for backend-identity branching
- [x] T005 Implement only the validated Basic serial request/provenance values in `core/src/dutchmate_core/adapters/basic_serial.py`, the backend-neutral provenance base in `core/src/dutchmate_core/model.py`, and normalized `open|read|close` failure operation/kind values in `core/src/dutchmate_core/backend.py`; extend descriptor/segment construction in `core/src/dutchmate_core/acquisition.py` and `core/tests/fakes.py` with immutable opaque provenance until T003–T004 pass

**Checkpoint**: Existing acquisition semantics pass with opaque connection
provenance; no pySerial object or Basic branch enters shared Core.

---

## Phase 3: User Story 1 - Open an Explicit Device Safely (Priority: P1) 🎯 MVP

**Goal**: Open only one exact selected local serial device with validated
settings and honest requested/effective DTR/RTS-open provenance.

**Independent Test**: A fake serial-library object records all assignments,
then one open. Invalid input never constructs/opens it; successful provenance
matches requested/effective settings and states the glitch/electrical limits.

### Tests for User Story 1

- [x] T006 [US1] Add failing configure-before-open contract tests in `core/tests/contract/test_basic_serial_adapter.py` for an exact device name, baud/data/parity/stop mapping, `rtscts`, `xonxoff`, `dsrdtr=False`, platform exclusivity, explicit DTR/static RTS or driver-managed RTS, and exactly one `open()` after all assignments
- [x] T007 [US1] Add failing open-result tests in `core/tests/contract/test_basic_serial_adapter.py` proving a successful descriptor reports exactly `uart_receive`, a fresh host/observation/nanosecond domain+origin, `UpstreamLossNotObservable`, selected/opened device names, equal requested/effective settings, preconfigured-while-closed line strategy, `not_guaranteed` transition, and `not_verified` electrical state
- [x] T008 [US1] Add failing open-failure tests in `core/tests/contract/test_basic_serial_adapter.py` for invalid input before host access, missing/permission/busy/configuration/line-state/generic-I/O categories from stable attributes, effective-setting mismatch, best-effort cleanup, primary-error preservation, and no leaked pySerial exception object

### Implementation for User Story 1

- [x] T009 [US1] Implement the private serial-construction seam, platform configuration mapping, closed-handle preconfiguration, one open, effective-state verification, immutable descriptor/provenance construction, and normalized open cleanup/failures in `core/src/dutchmate_core/adapters/basic_serial.py` until T006–T008 pass

**Checkpoint**: Safe-open behavior is independently complete; it starts no RX
until feature 001 receives the successful connection.

---

## Phase 4: User Story 2 - Deliver Exact Normalized RX (Priority: P2)

**Goal**: Feed exact serial reads into the existing single-consumer event
stream with host timestamps and normalized read/close termination.

**Independent Test**: A fake returns arbitrary bytes, empty reads, classified
loss, and failures. Events preserve bytes/order, one read is outstanding, and
close terminates without exposing library types.

### Tests for User Story 2

- [x] T010 [US2] Add failing stream tests in `core/tests/contract/test_basic_serial_adapter.py` for all byte values and invalid UTF-8, one `monotonic_ns` timestamp immediately after each non-empty read, no event for timeout/cancellation empties, read-return order, at most one outstanding read, no adapter queue, and feature-001 single-consumer rejection
- [x] T011 [US2] Add failing read-termination tests in `core/tests/contract/test_basic_serial_adapter.py` proving only stable exception attributes produce `Disconnected(reason="device_lost")`, ambiguous exceptions become normalized `read/io_failure`, message text never controls classification, and unexpected normal completion remains a feature-001 transport failure
- [x] T012 [US2] Add failing close/lifecycle tests in `core/tests/contract/test_basic_serial_adapter.py` and `core/tests/integration/test_basic_serial_acquisition.py` for cross-thread `cancel_read()`, waiting for the outstanding read, one serial close, idempotency, normalized close failure, and preservation of feature-001 STOPPING/primary-failure/restart guards

### Implementation for User Story 2

- [x] T013 [US2] Implement one sequential `asyncio.to_thread` read task, in-helper host timestamp capture, exact `RxBytesObserved` yielding, empty-read handling, stable-attribute disconnect classification, and normalized read failure in `core/src/dutchmate_core/adapters/basic_serial.py` until T010–T011 pass
- [x] T014 [US2] Implement idempotent closing, outstanding-read cancellation/join, one serial close, and normalized close failure in `core/src/dutchmate_core/adapters/basic_serial.py` until T012 passes without changing `core/src/dutchmate_core/acquisition.py` lifecycle semantics beyond T005 provenance copying

**Checkpoint**: A successful Basic connection implements the feature 001
backend contract for continuous receive-only acquisition.

---

## Phase 5: User Story 3 - Hardware-Free Contract Proof (Priority: P3)

**Goal**: Prove adapter neutrality and safe default validation without touching
or enumerating physical hardware.

**Independent Test**: The real adapter runs through acquisition using only the
injected fake; all feature 001 regressions and architecture checks pass; absent
hardware configuration cannot select a port.

### Tests and validation for User Story 3

- [x] T015 [US3] Add adapter-through-acquisition tests in `core/tests/integration/test_basic_serial_acquisition.py` for descriptor provenance in segment evidence, ambient exact RX, host timestamp provenance, explicit disconnect/transport failure, stop/close ordering, and a second-owner rejection without any Basic identity assertion in shared behavior
- [x] T016 [US3] Add a hardware-safety guard test in `core/tests/contract/test_basic_serial_adapter.py` proving the default factory path is never invoked by tests without an explicit selector and that production code imports neither `serial.tools.list_ports` nor `serial_for_url`; do not add or run real-hardware tests in this slice
- [x] T017 [US3] Run the focused quickstart commands from `specs/002-basic-serial-adapter/quickstart.md`, then rerun the complete existing feature 001 test groups to confirm exact-byte, ordering, timestamp, loss, ownership, and lifecycle behavior is unchanged

**Checkpoint**: Software contract proof is complete; all electrical/platform
hardware acceptance remains explicitly unexecuted.

---

## Phase 6: Completion and Scope Validation

**Purpose**: Validate the planned feature without expanding it.

- [x] T018 From repository root using `pyproject.toml`, run `uv run --frozen ruff check .`, `uv run --frozen mypy .`, `uv run --frozen lint-imports`, `uv run --frozen pytest`, and `git diff --check`; record exact pass/fail/skip counts and do not describe skipped or absent hardware cases as passed
- [x] T019 Review the final diff and `rg` results for pySerial imports outside `core/src/dutchmate_core/adapters/basic_serial.py`, Basic identity branches in shared Core, serial discovery, TX/Control/reconnect/profile/service/CLI/Enhanced/MCP code, raw library exceptions, and accidental physical-device access
- [x] T020 Update `docs/development_status.md` with actual implementation/validation state and exact next slice, and prepend the completed record to `docs/development_history.md`; update Graphify only if the implemented structural changes meet `docs/agent_tooling.md` criteria

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (T001–T002)**: Starts from the committed feature 001 baseline.
- **Foundational (T003–T005)**: Depends on Setup and blocks adapter behavior.
- **US1 (T006–T009)**: Depends on T005 and produces the safe-open MVP.
- **US2 (T010–T014)**: Depends on US1's opened connection.
- **US3 (T015–T017)**: Depends on US1 and US2.
- **Completion (T018–T020)**: Depends on all implementation stories.

### User Story Dependencies

- **US1**: Independently validates exact selection and safe open after the
  foundational values exist.
- **US2**: Requires US1's opened connection but remains independently testable
  with the serial fake.
- **US3**: Integrates both behaviors with feature 001 and proves default safety.

### Parallel Opportunities

- T003 and T004 can be written in parallel because they target separate test
  files; T005 follows both.
- Within US1, T006–T008 can be written in parallel before the shared T009
  implementation, provided RED results are captured separately.
- Within US2, T010–T012 can be written in parallel before T013–T014, but T013
  and T014 both edit `basic_serial.py` and should be serialized.
- Documentation/scope review in T019 must wait for implementation and tests;
  do not parallelize it with behavior changes.

## Parallel Example: User Story 1

```text
Task T006: configure-before-open tests
Task T007: successful descriptor/provenance tests
Task T008: open failure and cleanup tests
Then T009: minimum implementation satisfying all three RED groups
```

## Implementation Strategy

### First implementation task group: T001–T005

1. Add and lock pySerial/stub dependencies and provenance.
2. Establish the adapter package and exact architecture exemption/guard.
3. Add RED serial value/provenance tests.
4. Add RED feature-001 descriptor/segment propagation tests.
5. Implement only normalized values, failures, and opaque provenance copying.
6. Stop and validate the foundational group before beginning physical-open
   behavior in T006.

### Incremental delivery

1. T001–T005: normalized foundation, no hardware behavior.
2. T006–T009: safe-open MVP using only a fake library boundary.
3. T010–T014: continuous exact RX and close lifecycle.
4. T015–T017: integration/neutrality/default-safety proof.
5. T018–T020: full gate, scope review, and status/history.

## Notes

- Tests precede production behavior in every story and must fail for the
  intended missing contract before implementation.
- Physical hardware is forbidden for all tasks in this feature unless a later
  user request explicitly authorizes a named target and electrical setup.
- Do not weaken architecture checks to accommodate pySerial. The one exact-file
  exemption and inward dependency contract are part of the boundary design.
- The real-hardware acceptance cases are specified in `plan.md`; they are not
  completion criteria for this software-only implementation slice.
