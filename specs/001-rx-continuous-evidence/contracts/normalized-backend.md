# Internal Contract: Normalized Backend and Acquisition Boundary

This is an internal Device Core contract, not an HTTP, CLI, MCP, persistence, or
Enhanced wire contract. Names are descriptive; field and behavior semantics are
the compatibility surface for this slice.

## 1. Backend owner boundary

Conceptual interface:

```text
Backend.open() -> BackendConnection
```

- `open` is called only by the Device Core ownership/acquisition component.
- Success creates one fresh Core `ConnectionInstanceId` and returns a connection
  descriptor plus an unopened single-consumer event stream.
- A descriptor lacking `uart_receive` is rejected before acquisition starts.
- Failure is explicit and creates neither a segment nor an RX task.
- Serial settings, discovery, DTR/RTS, reconnect, and physical identity are not
  part of this slice's `open` contract.

## 2. Owned connection boundary

Conceptual interface:

```text
BackendConnection.descriptor -> ConnectionDescriptor
BackendConnection.events() -> async ordered stream[BackendEvent]
BackendConnection.close() -> completion
```

Rules:

1. `events()` may be consumed exactly once.
2. The acquisition coordinator is the only consumer.
3. Events are yielded in backend observation order; no second ordering channel
   exists.
4. `Disconnected` terminates the stream. Normal completion without disconnect
   or explicit close is a transport contract failure.
5. `close()` is idempotent and terminates the stream. It does not invent a
   successful disconnect observation.
6. Backpressure may delay consumption, but must not silently discard events.
   Unavoidable observable loss is an explicit loss event; otherwise failure is
   explicit.
7. No native handle, serial type, OS read chunk, helper frame, or backend
   discriminator crosses this boundary.

## 3. Backend event union

```text
RxBytesObserved(payload, observed_at)
ObserverLossObserved(observer_id, scope, cause, lost_bytes?, observed_at)
TimestampOriginReset(new_backend_observation_timestamp_domain)
Disconnected(reason)
```

Validation and fields are defined in [data-model.md](../data-model.md).

- RX chunk boundaries are transport-delivery artifacts only.
- Loss evidence is scoped to its observer, not the whole physical path.
- Origin reset is a provenance boundary, not a request to rewrite timestamps.
- Adapter exceptions stay behind the boundary; disconnect reasons are normalized.

## 4. Acquisition coordinator contract

Conceptual operations:

```text
Acquisition.start(backend) -> connection_id
Acquisition.stop() -> terminal result
Acquisition.state -> idle | starting | acquiring | stopping | stopped | failed
```

Rules:

1. At most one `start` may own a live connection. A concurrent or repeated
   attempt is explicitly rejected.
2. `start` opens the backend, validates `uart_receive`, creates connection and
   segment identity, appends `SegmentStartedEvidence`, then starts the sole event
   consumer.
3. Acquisition continues independently of workflows, subscribers, or client
   calls until a terminal condition.
4. Each RX/loss event is validated against current provenance and appended
   before any future derived consumer can observe it.
5. Origin reset appends the old segment end, creates a new segment, appends its
   start, then accepts events in the new domain.
6. Disconnect appends a segment end where recording remains available and
   terminates acquisition. This slice does not reconnect.
7. Events from an expired connection are stale and are never retagged to the
   active connection.
8. Recorder or stream contract failure moves acquisition to `failed`, closes
   the connection, and reports the reason. It does not claim continued capture.
9. `stop` is bounded and idempotent. It closes the connection and waits for the
   sole consumer task to terminate. Exact internal teardown timing remains an
   implementation/test detail, not a DUT wait contract.

## 5. Evidence recorder contract

Conceptual interface:

```text
EvidenceRecorder.append(record_without_sequence) -> recorded record
EvidenceRecorder.snapshot() -> immutable finite sequence[EvidenceRecord]
```

Rules:

1. `append` atomically assigns the next consecutive `EvidenceSequence` and
   returns the accepted immutable record.
2. Records are never reordered or decoded.
3. Append failure is explicit and adds no partially accepted record.
4. The in-memory implementation is finite test infrastructure, not durable
   storage and not retention.
5. `snapshot` exists only for deterministic tests. It is not the future bounded
   retrieval API and creates no cursor/pagination contract.

## 6. Capability and provenance behavior

- Shared code asks the reported set whether `uart_receive` exists.
- Shared code never asks whether a backend is Basic or Enhanced.
- RX/loss timestamp behavior comes from
  `BackendObservationTimestampDomain`, not backend identity. This field is
  scoped to the normalized backend-observation stream and does not constrain
  timestamp domains for future non-backend evidence in the segment.
- Loss behavior comes from `LossObservability` and explicit loss events, not
  backend identity.
- Capability names not acted on remain inert; they create no placeholder method
  or emulated behavior.

## 7. Required contract fixtures

### Basic-shaped fixture

- reports only `uart_receive` unless a rejection test says otherwise;
- declares host observer, observation meaning, unit, and opaque host origin;
- declares `upstream_loss_not_observable`;
- can emit arbitrary binary RX, origin reset, and normalized disconnect;
- contains no real serial or OS handle.

### Enhanced-shaped fixture

- reports `uart_receive` without implementing a real Enhanced backend;
- declares device observer, observation meaning, unit, and distinct device
  origin;
- declares one observer-reported UART-loss scope;
- can emit arbitrary binary RX and counted overflow in one ordered stream;
- emits a normalized non-serial disconnect signal;
- contains no helper framing, USB behavior, firmware simulation, GPIO/control,
  event-input behavior, or realistic timing model.

The same parameterized contract and acquisition tests run against both.
Fixture-specific construction is allowed; behavior assertions must not branch
on fixture/backend identity.
