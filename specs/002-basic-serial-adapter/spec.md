# Feature Specification: Basic Serial Backend Adapter

**Feature Branch**: `main`

**Created**: 2026-09-30

**Status**: Complete for software-only scope; physical hardware acceptance
remains deferred

**Input**: Connect one explicitly user-selected host serial device to the
normalized backend contract established by feature 001, with safe and honest
serial-open, configuration, timestamp, RX, and failure provenance.

**Governing authority**: `docs/project_context_core.md`, especially §§5.2,
9.2, 9.4, 11, 13.1–13.5, 14.2–14.4, 15.1, 17, 18, 19, 22.2, and 23; and
`specs/001-rx-continuous-evidence/contracts/normalized-backend.md`. The Core
document wins if a conflict is found. This specification extends the feature
001 descriptor and segment provenance without changing its acquisition,
ordering, timestamp-comparison, or evidence semantics.

## User Scenarios & Testing

### User Story 1 - Open an explicitly selected serial device safely (Priority: P1)

As a Device Core owner, I need the Basic backend to open only the exact host
serial device and configuration supplied by human-owned configuration, while
making DTR/RTS open behavior and its limitations explicit, so observation
cannot silently target an arbitrary device or pretend that opening is
electrically passive.

**Why this priority**: Device selection and serial-open line behavior are the
first physical safety boundary. No RX claim is valid until they are explicit.

**Independent Test**: Supply a fake serial-library boundary with one exact
device selector, serial settings, and DTR/RTS intent. Verify that the adapter
configures a closed handle before one open attempt, never enumerates or chooses
a device, and returns normalized immutable requested/effective provenance with
the open-transition limitation.

**Acceptance Scenarios**:

1. **Given** no explicit non-empty platform serial-device name, **When** open
   is requested, **Then** validation fails before any host serial API is
   called.
2. **Given** an explicit device name and valid settings, **When** open
   succeeds, **Then** the descriptor identifies the selected and
   library-reported device, requested and effective settings, requested and
   library-reported line behavior, and the limit of what was actually verified.
3. **Given** requested DTR/RTS behavior, **When** the serial handle is prepared,
   **Then** the intent is assigned while the handle is closed and open occurs
   only afterward.
4. **Given** the OS or driver cannot guarantee that it avoided an intermediate
   DTR/RTS state, **When** open succeeds, **Then** provenance explicitly states
   that a glitch-free open and electrical pin state were not verified.

---

### User Story 2 - Deliver exact RX through the normalized boundary (Priority: P2)

As Device Core, I need one real Basic connection to produce exact byte
observations with host-observation timestamps and normalized terminal failures,
so the feature 001 acquisition path can record real serial input without
learning about pySerial, OS handles, or Basic identity.

**Why this priority**: This is the minimum useful physical adapter behavior and
must preserve the already accepted authoritative RX contract.

**Independent Test**: Drive arbitrary binary reads, empty timeout reads, a
classified device disappearance, an unclassified read failure, and close
through a hardware-free serial-library fake. Verify one sequential blocking-read
path, one event consumer, exact payloads, host monotonic observation provenance,
normalized termination, and no serial-library type outside the adapter.

**Acceptance Scenarios**:

1. **Given** a successfully opened Basic connection, **When** a non-empty read
   returns, **Then** exactly those bytes are emitted once as `RxBytesObserved`
   with a timestamp captured immediately after the read returns.
2. **Given** a timeout or stop-cancellation read returns no bytes, **When** the
   reader continues or closes, **Then** no empty RX event and no invented loss
   event is emitted.
3. **Given** the adapter can positively classify a device disappearance,
   **When** the read fails, **Then** it emits one normalized `Disconnected`
   event and terminates the stream.
4. **Given** an open, read, or close error that is not an observed disconnect,
   **When** it crosses the adapter boundary, **Then** it is represented by the
   corresponding normalized backend failure and exposes no pySerial exception
   or OS handle.

---

### User Story 3 - Prove the adapter contract without hardware (Priority: P3)

As a maintainer, I need deterministic tests for configuration mapping,
line-state ordering, RX delivery, provenance, and failures on every supported
host platform, plus a separate opt-in hardware acceptance definition, so the
default suite remains safe while real support claims require real evidence.

**Why this priority**: Software doubles can prove the boundary and lifecycle,
but cannot prove driver behavior or electrical line safety.

**Independent Test**: Run the existing feature 001 suite unchanged and the new
adapter contract suite without enumerating or opening a physical device. Verify
that real-hardware tests remain opt-in and require an explicit configured
target.

**Acceptance Scenarios**:

1. **Given** the default test command on Linux, macOS, or Windows with no DUT,
   **When** the suite runs, **Then** it neither enumerates nor opens a physical
   serial device.
2. **Given** the Basic adapter descriptor, **When** it enters the existing
   acquisition coordinator, **Then** feature 001 exact-byte, sequence,
   provenance, ownership, and teardown behavior passes without a Basic branch
   in shared Device Core.
3. **Given** no explicit hardware-test target, **When** real-hardware tests are
   selected, **Then** they skip clearly rather than selecting any available
   serial device.

### Edge Cases

- A blank device name, numeric port index, URL-style pySerial handler, or
  sentinel such as `auto` is invalid; this slice accepts only an explicit
  platform serial-device name.
- A positive non-standard baud value may pass model validation but still be
  rejected explicitly at open when the platform or driver cannot apply it.
- Simultaneous RTS/CTS and XON/XOFF is rejected before open because portable
  support is not guaranteed.
- When RTS/CTS is enabled, RTS is driver-managed rather than a requested static
  line state. DTR remains explicitly requested. This does not create semantic
  Control behavior.
- pySerial may report requested line state in software even when a POSIX driver
  ignored the operation. Such state is recorded as library-reported and not as
  verified electrical state.
- An empty read caused by timeout or cancellation carries no data and is not a
  disconnect by itself.
- If a failure cannot be classified as physical disappearance without parsing
  unstable error text, it remains a normalized transport/read failure rather
  than a false disconnect claim.
- Close remains idempotent. A close failure is explicit and must not strand the
  feature 001 acquisition coordinator in `stopping` or replace an established
  primary failure.
- RX delivery backpressure must not silently discard bytes. Queue saturation
  or worker/bridge failure is a terminal transport failure, not inferred loss.

## Requirements

### Functional Requirements

#### Device selection and supported serial configuration

- **FR-001**: The adapter MUST require one explicit non-empty platform serial
  device name for every open attempt. It MUST NOT enumerate devices, use a
  default, interpret `auto`, or select the first available device.
- **FR-002**: The adapter MUST use pySerial 3.5's local `Serial` implementation,
  not URL handlers or `pyserial-asyncio`. pySerial objects, constants,
  exceptions, and OS handles MUST terminate inside the adapter module.
- **FR-003**: Requested configuration MUST contain: positive integer baud rate;
  data bits of 5, 6, 7, or 8; parity of none, even, or odd; stop bits of 1 or 2;
  a hardware RTS/CTS flow-control flag; and a software XON/XOFF flow-control
  flag.
- **FR-004**: Unsupported values, including mark/space parity, 1.5 stop bits,
  and simultaneous hardware and software flow control, MUST fail validation
  before the host device is opened. Support can be expanded only by a later
  contract revision with platform tests.
- **FR-005**: A non-standard positive baud rate MAY be requested. If the host
  platform or driver rejects it, open MUST fail explicitly; the adapter MUST
  NOT silently substitute another baud rate.
- **FR-006**: DSR/DTR flow control MUST be disabled. When RTS/CTS is disabled,
  requested DTR and RTS asserted/deasserted states are both required. When
  RTS/CTS is enabled, DTR state remains required and RTS MUST be represented as
  driver-managed rather than static.

#### Serial-open behavior and provenance

- **FR-007**: The adapter MUST create a closed serial object, assign the exact
  selected device, supported serial settings, disabled DSR/DTR flow control,
  exclusive-open intent, and applicable DTR/RTS state while closed, and only
  then call `open()` once.
- **FR-008**: On POSIX, the adapter MUST request pySerial exclusive access. On
  Windows, it MUST rely on pySerial's exclusive `CreateFile` open. Any platform
  limitation in exclusivity MUST stay adapter-local and be represented in
  provenance when the library cannot confirm it.
- **FR-009**: A successful connection descriptor MUST carry immutable Basic
  serial connection provenance containing the selected device name, the
  library-reported opened name, requested settings, library-reported effective
  settings, serial-open DTR/RTS behavior, exclusivity status, and explicit
  verification/limitation markers.
- **FR-010**: "Effective" serial settings in this slice MUST mean values
  accepted and reported by pySerial after open. They MUST NOT claim measured
  baud accuracy, electrical voltage, pin state, or correctness for the DUT.
- **FR-011**: If library-reported effective settings differ from requested
  settings, the adapter MUST best-effort close the handle and fail open. It MUST
  NOT start an RX worker or return a descriptor with silently changed settings.
- **FR-012**: The DTR/RTS open strategy MUST be recorded as preconfigured on a
  closed handle before open. The provenance MUST also record that generic
  pySerial/OS/driver behavior cannot guarantee absence of an intermediate line
  transition and cannot verify the electrical state at the adapter pins.
- **FR-013**: Failure while applying or opening with the requested settings MUST
  create no successful connection descriptor, connection/segment identity,
  evidence, or RX worker. Best-effort cleanup MUST preserve the primary open
  failure.
- **FR-014**: Serial-open line-state handling MUST remain connection setup
  provenance. It MUST NOT be recorded as an intentional semantic Control
  action, expose reset/boot roles, or imply `serial_line_control` capability.

#### Normalized descriptor, timestamp, RX, and failures

- **FR-015**: For this slice, the real Basic adapter MUST report exactly
  `uart_receive`. It MUST NOT report `uart_send`, `serial_line_control`, GPIO,
  or event capabilities until those operations are implemented and validated.
- **FR-016**: The connection descriptor MUST declare host observation,
  observation meaning, nanosecond unit, a fresh opaque domain identifier, and
  a fresh opaque origin identifier for each successful physical open. It MUST
  declare upstream UART loss not observable.
- **FR-017**: One sequential read loop MUST be the only caller of pySerial
  `read()` for an owned connection. Each blocking read MUST run off the event
  loop through `asyncio.to_thread`, with at most one read outstanding, and feed
  the single-consumer async event stream established by feature 001; no second
  RX path or subscriber read is permitted.
- **FR-018**: For each non-empty read result, the adapter MUST capture a host
  monotonic timestamp immediately after `read()` returns and emit one
  `RxBytesObserved` containing the exact returned bytes and that timestamp.
  The timestamp applies to the returned chunk and claims neither per-byte nor
  DUT-emission timing.
- **FR-019**: Empty timeout or cancellation results MUST emit no RX event. The
  adapter MUST NOT synthesize loss events because the Basic observer cannot
  observe upstream loss.
- **FR-020**: Sequential read delivery MUST preserve read-return order and
  apply backpressure by not starting another read until the prior observation
  has been yielded. The adapter MUST contain no second queue that can silently
  discard or reorder bytes.
- **FR-021**: A positively classified physical device disappearance MUST emit
  one `Disconnected` event with a stable normalized reason and then end the
  stream. Classification MUST use stable exception attributes or documented
  platform signals, not message-string matching.
- **FR-022**: Other read failures MUST terminate by raising a normalized
  backend read/transport failure. Unexpected normal worker or stream completion
  MUST continue to be treated by feature 001 as transport failure.
- **FR-023**: Open, read, and close failures MUST expose normalized operation
  and failure categories without exposing pySerial exception objects, error
  text relied on for behavior, OS handles, or platform-specific exception
  types above the adapter boundary.
- **FR-024**: `close()` MUST be idempotent, request cancellation of an
  outstanding read using pySerial's cross-thread `cancel_read()`, wait for that
  read call to finish, and close the handle. Close failure MUST remain explicit
  and obey feature 001's primary-failure and teardown semantics.
- **FR-025**: The feature 001 `ConnectionDescriptor` and `SegmentProvenance`
  MUST be extended with one immutable backend connection-provenance value.
  Shared acquisition MUST copy that value unchanged and MUST NOT inspect its
  Basic serial subtype to choose behavior.

#### Tests and hardware acceptance definition

- **FR-026**: Hardware-free tests MUST use a private serial-library seam or
  fake and MUST verify validation, exact library mapping, configure-before-open
  ordering, one open, at most one outstanding read, timestamp placement, exact
  bytes, sequential backpressure/failure behavior, idempotent close, and
  normalized failures.
- **FR-027**: The existing feature 001 contract and acquisition tests MUST pass
  unchanged except for constructing the newly required opaque connection
  provenance value. Shared behavior assertions MUST remain backend-neutral.
- **FR-028**: The default suite MUST not enumerate or open physical serial
  devices. Optional virtual-port tests MAY use test-created PTYs and MUST be
  platform-marked; they are software integration evidence, not hardware
  acceptance.
- **FR-029**: Real-hardware tests MUST be opt-in, require an explicit target and
  declared electrical setup, and skip clearly when absent. They MUST never fall
  back to an enumerated port.
- **FR-030**: Hardware acceptance MUST eventually cover at least: exact RX on a
  named device; each supported configuration class; unsupported configuration;
  busy/permission/missing-device open failures; physical disconnect; close and
  reopen ownership; and observed DTR/RTS behavior during open on each claimed
  OS/driver/adapter combination using suitable external measurement.

### Key Entities

- **Basic Serial Open Request**: Exact platform device name, supported serial
  settings, flow-control choice, and DTR/RTS open intent supplied by human-owned
  configuration.
- **Serial Configuration**: Baud, data bits, parity, stop bits, RTS/CTS, and
  XON/XOFF values in either requested or library-reported effective form.
- **Serial Open Line Provenance**: Requested/managed DTR/RTS behavior,
  configure-before-open strategy, library-reported state, and the explicit
  limits on transition and electrical verification.
- **Basic Serial Connection Provenance**: Immutable normalized snapshot of
  selected/opened identity, requested/effective configuration, line behavior,
  exclusivity, and limitations. Device Core stores it without branching on it.
- **Normalized Backend Failure**: Adapter-independent failure category and
  operation for open, read/transport, or close; it contains no pySerial object.

## Success Criteria

### Measurable Outcomes

- **SC-001**: In hardware-free tests, 100% of invalid selectors and unsupported
  configuration combinations fail before the fake serial object records an
  open call.
- **SC-002**: For all supported configuration combinations exercised by the
  contract suite, the fake records requested settings and line intent before
  exactly one open call, and provenance reproduces requested and effective
  values without omission.
- **SC-003**: For arbitrary chunks containing every byte value, reconstructing
  adapter RX events yields exactly 100% of bytes in read-return order with one
  host-domain timestamp per non-empty read.
- **SC-004**: Tests demonstrate exactly one outstanding pySerial read and one
  normalized event consumer per owned connection, with no adapter queue, loss,
  or reordering under the bounded test load.
- **SC-005**: Every tested open, read, disconnect, and close failure crosses the
  normalized boundary without a pySerial exception type, serial object, OS
  handle, or error-string-dependent behavioral assertion.
- **SC-006**: The full feature 001 suite and repository architecture gates pass
  with no backend-identity branch in acquisition, evidence, or model behavior.
- **SC-007**: The default full test run completes with zero physical serial
  enumeration/open attempts; real-hardware acceptance remains separately
  opt-in and is not claimed by this feature's software tests.

## Assumptions

- The host platforms targeted by the first implementation are POSIX (Linux and
  macOS) and Windows as supported by pySerial. Platform claims remain limited
  to what hardware-free tests and later explicit hardware acceptance establish.
- pySerial 3.5 is the current stable runtime release and is pure Python. The
  implementation will verify it under the repository's Python 3.14 baseline;
  the uv lockfile will make the resolved dependency reproducible.
- The exact serial device name and open configuration will later come from a
  DUT Profile, but the complete profile schema and client-facing input surface
  are outside this slice. This slice accepts a typed adapter construction value.
- Host monotonic time is suitable for ordering checks within the fresh
  connection domain/origin only. Device Core evidence sequence remains the
  authoritative evidence order.

## Explicit Exclusions and Deferred Behavior

- Automatic discovery, selection by VID/PID or USB serial number, reconnect
  matching, and any fallback to an available port.
- UART TX, Interact, console, TX policy, write timeouts, and output flushing.
- Intentional semantic DTR/RTS Control, reset/boot sequences, DUT roles,
  profiles beyond the minimal adapter construction values, and
  `serial_line_control` capability.
- Automatic reconnect, release/reacquire, and native-USB reset topology.
- Persistence, retention, sessions, retrieval, Monitor, follow, service/HTTP,
  authentication, CLI, Enhanced backend/protocol/firmware, MCP, and AI.
- Mark/space parity, 1.5 stop bits, DSR/DTR flow control, RS-485 mode, serial
  URL handlers, remote serial transports, and custom platform-native drivers.
- Any claim that software-only tests prove electrical safety, glitch-free
  DTR/RTS transitions, physical pin state, baud accuracy, losslessness, or
  real-device compatibility.
