# Feature Specification: Continuous RX Evidence Foundation

**Feature Branch**: `main`

**Created**: 2026-09-29

**Status**: Implemented and validated

**Input**: Establish the first Phase 1 foundation for a normalized backend
boundary, one continuous authoritative UART RX path, binary-safe evidence, and
backend-neutral timestamp and loss provenance. Prove neutrality with test-only
Basic-shaped and Enhanced-shaped backends; do not implement real hardware
backends or later-phase features.

**Governing authority**: `docs/project_context_core.md`, especially §§5.2, 11,
14.1–14.4, 15.1, 16.1, 17, 18, 22.2, and 23. This specification adds only the
concrete contracts needed by this slice. The Core document wins if a conflict
is found.

## User Scenarios & Testing

### User Story 1 - Preserve continuous authoritative UART evidence (Priority: P1)

As a Device Core consumer, I need every UART byte observed while an owned
backend is connected to enter one ordered evidence stream, including bytes
received while no workflow is active, so later work can rely on a complete and
binary-safe observation foundation.

**Why this priority**: Continuous authoritative acquisition is the foundation
on which every Phase 1 workflow and evidence feature depends.

**Independent Test**: Drive arbitrary binary payloads, idle periods, and a
disconnect through a receive-capable test backend. Verify that exactly one
acquisition path runs for the ownership interval and that concatenating the RX
evidence payloads reproduces the observed bytes exactly and in order.

**Acceptance Scenarios**:

1. **Given** Device Core owns a connected receive-capable backend, **When** the
   backend observes bytes before, during, and after periods with no workflow,
   **Then** all bytes are appended to the same authoritative evidence stream.
2. **Given** a payload containing every byte value and invalid UTF-8, **When**
   it crosses the normalized boundary, **Then** the evidence payload is
   byte-for-byte identical and remains available without decoding.
3. **Given** acquisition is already active, **When** another component attempts
   to create a second receive path for the same owned connection, **Then** the
   attempt is rejected without disturbing the authoritative path.

---

### User Story 2 - Preserve explicit timing and connection provenance (Priority: P2)

As an evidence consumer, I need each observation to identify its ordering,
connection segment, and backend-observation timestamp domain so I can reason
honestly about when and where it was observed without treating host and device
clocks as the same measurement.

**Why this priority**: Evidence without explicit provenance can create false
timing claims and cannot safely survive later backend expansion.

**Independent Test**: Feed observations with repeated timestamp values, a
timestamp-origin reset, and a disconnect. Verify that Device Core orders them
by its own evidence sequence, starts a new segment at the origin reset, and
never orders or compares distinct backend-observation timestamp domains as one
clock.

**Acceptance Scenarios**:

1. **Given** a Basic-shaped backend, **When** it reports an RX observation,
   **Then** the timestamp is labeled as a host observation of that backend
   event and is not represented as DUT emission time or as a universal clock.
2. **Given** two observations with the same timestamp value, **When** Device
   Core records them in stream order, **Then** their evidence sequence values
   provide an unambiguous order without modifying either timestamp.
3. **Given** a timestamp-origin reset or connection interruption, **When** the
   next observation is accepted, **Then** it belongs to a new segment with a
   new provenance snapshot.

---

### User Story 3 - Prove backend neutrality (Priority: P3)

As a maintainer, I need the same Device Core acquisition and recording behavior
to work against Basic-shaped and Enhanced-shaped test backends so Basic-only
assumptions are caught before a real Enhanced backend exists.

**Why this priority**: The Core requires Basic-first implementation without
allowing Basic properties to leak above the normalized boundary.

**Independent Test**: Run the same backend-independent contract and Device Core
tests against both fixtures. The Basic-shaped fixture uses host-observation
timestamps and cannot report upstream loss. The Enhanced-shaped fixture uses a
device-domain timestamp origin and emits an observer-scoped overflow report.
No shared assertion branches on backend identity.

**Acceptance Scenarios**:

1. **Given** the shared test suite, **When** it runs against both fixtures,
   **Then** exact-byte, ordering, segmentation, ownership, and continuous
   acquisition assertions pass unchanged.
2. **Given** the Enhanced-shaped fixture reports overflow, **When** Device Core
   records it, **Then** the loss amount, cause, observer scope, timestamp, and
   stream position are explicit evidence.
3. **Given** the Basic-shaped fixture reports that upstream loss is not
   observable, **When** no loss event exists, **Then** no layer describes the
   path as lossless or as having proven zero loss.

### Edge Cases

- Empty RX payload observations are invalid and are rejected at the normalized
  boundary rather than creating meaningless evidence records.
- RX event chunk boundaries have no semantic meaning above the backend
  boundary; splitting or coalescing chunks must not change the reconstructed
  byte stream.
- Repeated or decreasing timestamp values do not reorder evidence. A declared
  backend-observation timestamp-origin reset starts a new segment; an
  undeclared regression is an explicit contract failure, not silently repaired.
- A stale event from an earlier connection instance is rejected and never
  attributed to the current segment.
- An observer-loss report must identify a positive amount when the observer can
  count it. Unknown amounts remain explicit rather than being represented as
  zero.
- Disconnect ends the current connected segment. This slice does not reconnect
  or reacquire automatically.
- Evidence recording failure is terminal and explicit; the acquisition path
  must not continue while silently dropping authoritative observations.

## Requirements

### Functional Requirements

#### Normalized backend boundary

- **FR-001**: A backend MUST expose one normalized connection contract that
  reports its physical capabilities and yields an ordered stream of normalized
  observations while that connection is owned.
- **FR-002**: Capabilities MUST be an immutable reported set of named physical
  abilities, separate from DUT-specific semantic roles. This slice recognizes
  the Core capability names `uart_receive`, `uart_send`,
  `serial_line_control`, `gpio_control`, and `gpio_events`; it requires only
  `uart_receive` for acquisition and implements no operation for the others.
- **FR-003**: Acquisition MUST reject a connected backend that does not report
  `uart_receive`; unsupported abilities MUST NOT be emulated.
- **FR-004**: Code above the backend boundary MUST consume only normalized
  capabilities, observations, and provenance. It MUST NOT inspect backend
  identity, serial-library objects, OS read framing, Enhanced message types, or
  private backend metadata to choose shared behavior.
- **FR-005**: One successful ownership acquisition MUST create a distinct
  connection instance. Observations from another or expired connection
  instance MUST NOT enter its evidence stream.

#### Normalized observations and evidence

- **FR-006**: The normalized observation stream for this slice MUST represent:
  non-empty RX byte payloads, observer-reported UART byte loss, timestamp-origin
  reset, and disconnect. Connection start is represented by the successful
  acquisition result and its provenance snapshot.
- **FR-007**: Every RX observation MUST carry an immutable byte payload and one
  observation timestamp. The payload MUST be preserved exactly; decoding,
  newline normalization, replacement characters, and other transformations are
  prohibited on the authoritative path.
- **FR-008**: Every observer-loss observation MUST carry the reporting observer
  and scope, an explicit cause, a timestamp, and either a positive lost-byte
  count or an explicit unknown amount. Zero MUST NOT mean unknown.
- **FR-009**: Device Core MUST transform accepted normalized observations into
  typed evidence records. Each record MUST include a strictly increasing
  evidence sequence, connection-instance identity, segment identity, event
  kind and payload, and the observation timestamp where the source event has
  one.
- **FR-010**: Evidence sequence assigned in Device Core acceptance order is the
  minimum authoritative ordering mechanism. Timestamp value, RX chunk size,
  backend framing, and backend identity MUST NOT determine stream order.
- **FR-011**: Byte order inside each RX payload and observation order between
  payloads MUST be preserved. RX payload boundaries MUST NOT be treated as line,
  message, transaction, or causation boundaries.
- **FR-012**: Ambient RX observations MUST be recorded whenever a connected
  backend is owned, regardless of whether any workflow or subscriber exists.

#### Backend-observation timestamp domains and segment provenance

- **FR-013**: A backend RX/loss observation timestamp MUST be a non-negative
  integer value paired with a backend-observation timestamp-domain identifier.
  Its domain descriptor MUST state whether the observer is the host or a
  backend device, that the value denotes backend observation rather than DUT
  emission, the value unit, and an opaque origin identity defining the only
  clock continuity scope this slice recognizes.
- **FR-014**: Backend-observation timestamp values MAY be compared only when
  their domain and origin identities match. Device Core MUST NOT convert,
  align, or present different origins or domains as one continuous clock in
  this slice.
- **FR-015**: A Basic host-observation timestamp MUST describe when the host
  backend observed the RX event presented at the boundary. One timestamp MAY
  apply to every byte in that event. It MUST NOT claim per-byte timing, DUT
  emission timing, or universal wall-clock meaning.
- **FR-016**: Each connected segment MUST reference an immutable provenance
  snapshot containing the connection-instance identity, segment identity,
  reported capabilities, backend-observation timestamp-domain descriptor, and
  loss-observability descriptor in effect for the normalized RX/loss stream.
  This requirement does not require future non-backend evidence in the same
  segment to use that timestamp domain.
- **FR-017**: A new segment MUST begin for a new connection instance or a
  backend-observation timestamp-origin reset. Disconnect MUST explicitly close
  the current segment. Automatic reconnect, release, and reacquire are deferred.
- **FR-018**: The loss-observability descriptor MUST distinguish at least
  `upstream_loss_not_observable` from `observer_reports_uart_loss`, and MUST
  identify the observer scope for the latter. Absence of a loss record MUST
  never be presented as proof of an end-to-end lossless path.

#### Ownership and continuous acquisition

- **FR-019**: Device Core MUST allow exactly one active owner and one consumer
  of the normalized observation stream for the current connection instance.
- **FR-020**: Successful connection ownership MUST start the authoritative RX
  acquisition path. That path MUST remain active until disconnect, explicit
  stop, or an explicit terminal recording/transport failure.
- **FR-021**: Starting, ending, or omitting a workflow or subscriber MUST NOT
  start, stop, replace, or duplicate the authoritative RX path.
- **FR-022**: Device Core MUST record an accepted observation before making any
  later derived use of it. A recording failure MUST surface as an explicit
  terminal acquisition failure rather than silent loss.

#### Backend-neutral proof fixtures

- **FR-023**: Tests MUST provide the smallest Basic-shaped fixture needed by
  this contract: it reports `uart_receive`, uses a host-observation timestamp
  domain, and declares upstream loss unobservable.
- **FR-024**: Tests MUST provide the smallest Enhanced-shaped fixture needed by
  this contract: it reports `uart_receive`, uses a distinct device-observation
  timestamp domain and origin, can emit observer-scoped UART overflow with a
  lost-byte count, and has a disconnect signal that is not represented by an OS
  serial-library type.
- **FR-025**: Both fixtures MUST run through the same backend contract and
  Device Core behavior tests. Fixture-specific setup MAY differ; shared
  assertions MUST NOT branch on backend identity.
- **FR-026**: The Enhanced-shaped fixture MUST NOT implement or simulate helper
  wire framing, USB protocol, firmware, realistic device timing, GPIO/event
  behavior, or any real Enhanced backend mechanism.

### Key Entities

- **Backend Capability Set**: Immutable physical abilities reported for one
  connection; distinct from semantic DUT roles.
- **Connection Instance**: One exclusive interval in which Device Core owns an
  opened backend connection and its single normalized observation stream.
- **Connection Segment**: An uninterrupted observation context whose normalized
  backend RX/loss stream has one stable backend-observation timestamp origin
  and immutable provenance snapshot.
- **Backend Observation Timestamp Domain**: The observer, observation semantics,
  unit, and clock origin that give a backend RX/loss timestamp value meaning
  and define its comparison scope.
- **Normalized Observation**: A backend-neutral RX, loss, origin-reset, or
  disconnect event delivered in backend observation order.
- **Evidence Record**: A Device Core-owned record authoritatively ordered within
  its evidence journal that preserves authoritative bytes or explicit
  quality/lifecycle evidence and references its connection and segment
  provenance.
- **Loss Observability**: A statement of what a particular observer can report;
  it never claims physical end-to-end losslessness.

## Success Criteria

### Measurable Outcomes

- **SC-001**: For test streams containing all 256 byte values, embedded NULs,
  invalid UTF-8, and arbitrary chunking, reconstructing RX evidence produces
  exactly 100% of input bytes in input order.
- **SC-002**: Across the full owned-and-connected test interval, 100% of
  accepted normalized observations receive unique, strictly increasing
  evidence sequence values and the correct connection and segment identities.
- **SC-003**: The same backend-independent acquisition and evidence behavior
  suite passes without identity-based branches against both the Basic-shaped
  and Enhanced-shaped fixtures.
- **SC-004**: Tests demonstrate exactly one active normalized observation
  consumer per owned connection and demonstrate that idle/no-workflow periods
  do not stop acquisition.
- **SC-005**: Every recorded RX and loss observation can be traced to one
  explicit backend-observation timestamp domain and origin, and tests reject
  cross-domain clock comparison as unsupported.
- **SC-006**: Static inspection and architecture checks find no dependency from
  domain/application code to serial, HTTP, CLI, MCP, or Enhanced protocol
  implementations.

## Assumptions

- The first production implementation language is Python, managed as a uv
  workspace as required by `AGENTS.md`; exact module placement and dependencies
  are implementation-plan concerns.
- This slice establishes in-process contracts and behavior. A later focused
  slice will select a durable bounded persistence format and retention model;
  nothing here claims crash durability.
- Evidence sequence is scoped to the active in-process journal in this slice.
  Durable session and cursor scope will be specified with persistence and
  retrieval.
- The test fixtures are deterministic software doubles and provide no
  real-hardware acceptance evidence.

## Explicit Exclusions and Deferred Behavior

- Real Basic serial-device discovery/opening, DTR/RTS open behavior, serial
  configuration, platform reconnect matching, and real-hardware validation.
- The real Enhanced backend, helper wire protocol or framing, RP2350 firmware,
  Zephyr behavior, USB details, realistic helper timing, and Enhanced hardware
  acceptance.
- Durable persistence/file formats, sessions, quotas, rolling retention,
  retention markers, retrieval cursors, pagination, and annotations.
- Monitor, Interact, Control, follow, console, TX, pattern matching, derived
  text/lines, and operation start/end models.
- Release/reacquire, automatic reconnect, native-USB topology behavior, and
  complete lifecycle state naming.
- HTTP routes or schemas, FastAPI service behavior, authentication, browser
  origin rejection, CLI commands, MCP tools, and any AI behavior.
- GPIO control, safe-state execution, GPIO event capture, semantic role mapping,
  and all later-phase functionality. Capability names remain representable so
  shared code does not assume a fixed Basic-only set; this slice does not claim
  or implement those capabilities.
