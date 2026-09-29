# Research: Continuous RX Evidence Foundation

This records decisions needed to make the implementation plan executable. It
does not introduce product semantics beyond the Core and focused specification.

## 1. Scope the slice to core contracts and software fixtures

**Decision**: Implement the normalized boundary, evidence values, in-memory
recorder, continuous acquisition coordinator, and two test-only backend shapes.
Do not implement a real Basic serial adapter in this slice.

**Rationale**: A real serial adapter requires concrete contracts for serial
configuration, DTR/RTS behavior on open, platform behavior, and hardware
acceptance. Those are outside this foundation. Core behavior can be proven
without touching hardware.

**Alternatives considered**:

- Add a pyserial adapter now: rejected because it expands the slice into
  serial-open safety and platform-specific behavior.
- Define only data classes with no acquisition loop: rejected because it would
  not prove the continuous single-RX-path invariant.

## 2. Use one single-consumer asynchronous event stream

**Decision**: An owned backend connection exposes one ordered async stream of
normalized events. The acquisition coordinator is its sole consumer.

**Rationale**: This models continuous observation without polling, lets
disconnect and loss occupy the same observation order, and makes a second
reader structurally rejectable. It exposes neither OS reads nor helper framing.

**Alternatives considered**:

- Callback registration: rejected because ownership, backpressure, teardown,
  and callback ordering are less explicit.
- Repeated `read()` calls from workflows: rejected because workflows would own
  readers and violate continuous acquisition.
- Multiple subscribers on the backend stream: rejected because subscribers
  belong above recorded evidence, not on the physical RX path.

## 3. Separate backend observations from Device Core evidence

**Decision**: Backends emit normalized observations; Device Core attaches its
own evidence sequence and connection/segment identities when recording them.

**Rationale**: Backend observation order and timestamp provenance are inputs,
but Device Core owns authoritative evidence. The split prevents a backend from
defining durable evidence identity or authoritative journal ordering.

**Alternatives considered**:

- Let backends emit final evidence records: rejected because it moves Device
  Core policy and identity into adapters.
- Derive evidence order from timestamps: rejected because timestamps can repeat,
  reset, use different origins, or come from different observers.

## 4. Use explicit timestamp domains with opaque origins

**Decision**: A timestamp is an integer value plus a referenced domain. The
domain states host/device observer, observation meaning, unit, and opaque origin
identity. Values are comparable only inside the same domain and origin.

**Rationale**: Basic host observation and Enhanced device observation can use
the same data shape without being presented as equivalent measurements. Opaque
origins avoid implying wall-clock or cross-segment continuity.

**Alternatives considered**:

- Normalize everything to host wall time: rejected because it destroys device
  provenance and implies cross-domain comparability.
- Store a bare integer timestamp: rejected because its observer, unit, and
  continuity scope would be ambiguous.
- Add clock synchronization/calibration now: rejected as a future contract.

## 5. Core assigns connection and segment identity

**Decision**: Every ownership acquisition receives a new connection-instance
ID. Device Core starts a segment with a provenance snapshot and creates another
segment after a backend-observation timestamp-origin reset. Disconnect closes
the segment.

**Rationale**: Core-owned opaque IDs isolate stale events without leaking serial
device identity. Segment identity preserves stable backend-observation
timestamp and loss provenance for the normalized RX/loss stream.

**Alternatives considered**:

- Use a device path as connection identity: rejected as Basic-specific and not
  stable across backend types.
- Treat one process lifetime as one segment: rejected because backend-observation
  timestamp origins can reset while the process remains alive.

## 6. Separate loss observability from loss reports

**Decision**: Segment provenance declares whether upstream loss is unobservable
or an identified observer reports UART loss. A loss event records observer
scope, overflow/other cause, and known positive byte count or explicit unknown.

**Rationale**: “No loss reported” has meaning only inside an observer's scope;
it is never proof of a lossless physical path. The split represents both Basic
and Enhanced-shaped behavior honestly.

**Alternatives considered**:

- Boolean `lossless`: rejected as physically misleading.
- Boolean `overflowed`: rejected because it loses amount, observer, scope, and
  the distinction between unknown and zero.
- Infer loss from time or data gaps: rejected as nondeterministic.

## 7. Begin with an in-memory recorder behind a port

**Decision**: Implement an append-only in-memory recorder for executable tests,
behind the minimal recording boundary acquisition needs.

**Rationale**: Persistence is a genuine external boundary, but choosing a file
format, quotas, retention, sessions, and retrieval would exceed this slice. The
port tests acquisition and explicit recording failures without claiming
durability.

**Alternatives considered**:

- Choose SQLite or a file format now: rejected because persistence and retention
  contracts are explicitly deferred.
- Embed a list in acquisition code: rejected because it hides the recording
  failure boundary and tangles acquisition with storage mechanics.

## 8. Start one core package with standard-library runtime types

**Decision**: Create a Python 3.14 uv workspace with
`requires-python = ">=3.14,<3.15"` and one `dutchmate-core` package. Use
standard-library async, immutable data types, enums, and protocols; add only
development dependencies required by the validation gate.

**Rationale**: The repository mandates Python/uv but has no implementation
baseline. One package is the smallest structure respecting modular-monolith
dependency direction while remaining independently testable.

**Alternatives considered**:

- Create service and CLI packages now: rejected as speculative for this slice.
- Add an async framework runtime dependency: rejected because the standard
  library is sufficient for the internal acquisition contract.
