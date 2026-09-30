# Internal Contract: Basic Serial Backend Adapter

This contract extends
`specs/001-rx-continuous-evidence/contracts/normalized-backend.md`. It is not a
DUT Profile, HTTP, CLI, persistence, reconnect, or Control contract.

## 1. Construction boundary

Conceptual interface:

```text
BasicSerialBackend(
  selector: SerialDeviceSelector,
  configuration: SerialConfiguration,
  line_intent: SerialOpenLineIntent,
)
```

- All values are validated before any serial-library construction/open call.
- The selector is exact and mandatory; no discovery or fallback exists.
- A private serial-construction callable may be injected for tests. It is not a
  backend registry or public adapter plugin API.

## 2. Open boundary

`BasicSerialBackend.open()` implements feature 001 `Backend.open()`:

1. Create a closed pySerial object (`port=None`).
2. Assign the exact device, supported configuration, `dsrdtr=False`, platform
   exclusivity, and DTR/static RTS state while closed.
3. For RTS/CTS, leave RTS driver-managed and do not claim a static state.
4. Call `open()` once.
5. Read back library-reported device/settings/line state.
6. If required settings differ, best-effort close and raise a normalized open
   failure, preserving the primary failure.
7. Return a connection descriptor with only `uart_receive`, host nanosecond
   observation provenance, unobservable upstream loss, and immutable Basic
   serial connection provenance.

No `ConnectionInstanceId`, `SegmentId`, evidence record, or read task is created
inside the adapter or on failed open. Those remain feature 001 acquisition
responsibilities.

## 3. DTR/RTS boundary

- The adapter reduces avoidable transitions by configuring the closed object.
- It does not guarantee a glitch-free open because the OS/driver may assert
  defaults before applying requested values.
- It does not verify electrical pin state. Post-open properties are
  library-reported state only.
- It emits no semantic Control action and reports no `serial_line_control`
  capability.
- It performs no reset, boot-mode sequence, pulse, delay, or post-open line
  correction.

## 4. Event stream boundary

Conceptual read loop:

```text
while open and not closing:
  payload, observed_at = await asyncio.to_thread(read_and_timestamp_once)
  if payload:
    yield RxBytesObserved(payload, observed_at)
```

Rules:

1. Feature 001 single-consumer enforcement still applies to `events()`.
2. At most one pySerial `read()` is outstanding.
3. The blocking helper captures `monotonic_ns()` immediately after a non-empty
   or empty read returns; empty-read timestamps are discarded with the empty
   result.
4. A yielded payload is immutable exact bytes. No decoding, line processing,
   buffering queue, coalescing, splitting, or normalization occurs.
5. The next read begins only after the preceding normalized event has been
   accepted back from the async generator yield.
6. Empty timeout/cancellation results emit nothing.
7. The adapter never emits `ObserverLossObserved`; descriptor provenance says
   upstream loss is not observable.

Read size and finite library timeout are private tuning values. They do not
create message, line, evidence-order, or public timing contracts.

## 5. Timestamp contract

Each successful physical open creates a fresh
`BackendObservationTimestampDomain`:

```text
observer = host
meaning = observation
unit = nanosecond
domain_id = fresh opaque value
origin_id = fresh opaque value
```

`observed_at.value` comes from host monotonic time in the blocking helper after
the read returns. The timestamp applies to the returned chunk, not each byte,
and does not claim DUT emission time, wall-clock time, USB arrival time, or
cross-connection comparability.

## 6. Normalized failure contract

- Request validation raises a normalized open/invalid-request failure before
  host access.
- Open exceptions are categorized from stable attributes into not-found,
  permission, busy, configuration, line-state, or generic I/O failure.
- Read disappearance becomes `Disconnected(device_lost)` only when stable
  attributes positively identify it. Otherwise the stream raises a normalized
  read/I/O failure.
- No behavior depends on parsing exception text.
- Close exceptions become normalized close/I/O failures.
- Optional diagnostic text may be retained without the original exception
  object and is never used by shared Core behavior.

Feature 001 maps stream/close failures to its existing transport-failure
termination and preserves earlier primary failures.

## 7. Close contract

`close()` is idempotent:

1. Mark closing so no new read begins.
2. If a read is outstanding, call pySerial `cancel_read()` from the closing
   thread and await the `to_thread` call's completion.
3. Close the serial object once.
4. Surface a normalized close failure if cancellation/close fails; always leave
   the connection terminal.

Normal completion caused by owner close does not invent a `Disconnected`
event. Unexpected completion while not closing remains feature 001 transport
failure.

## 8. Boundary enforcement

- Only `dutchmate_core.adapters.basic_serial` imports `serial`.
- Acquisition, backend, evidence, and model modules must not import adapters.
- Shared code may store/copy `BackendConnectionProvenance` but must not use a
  Basic subtype check to choose acquisition, evidence, ordering, timestamp, or
  loss behavior.
- Existing Basic-shaped and Enhanced-shaped fixtures retain identical shared
  assertions; only the newly required opaque provenance constructor input may
  change.
