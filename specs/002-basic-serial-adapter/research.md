# Research: Basic Serial Backend Adapter

## Decision 1: Use pySerial 3.5 directly

**Decision**: Use the stable `pyserial==3.5` runtime package, resolved through
uv, and `types-pyserial==3.5.0.20260712` for development typing.

**Rationale**: pySerial is the established cross-platform Python serial layer
for POSIX and Windows, exposes closed-object configuration, explicit `open()`,
blocking byte reads, DTR/RTS properties, exclusive-open behavior, and
cross-thread `cancel_read()`. It is pure Python and BSD-3-Clause licensed. Its
stable release metadata predates Python 3.14 classifiers, so implementation
must verify it on the repository's Python 3.14 baseline rather than infer
compatibility. Upstream main now declares Python 3.14, but an unreleased branch
is not a better reproducibility choice than the stable package.

**Alternatives considered**:

- `pyserial-asyncio`: rejected because it adds another dependency and event-loop
  transport behavior without improving the normalized boundary, while platform
  support and lifecycle behavior require separate validation.
- Native `termios` and Win32 implementations: rejected because they duplicate
  mature platform code, expand the slice substantially, and still cannot
  provide a universal glitch-free DTR/RTS open.
- An unreleased pySerial Git commit: rejected because stable 3.5 can be locked
  and tested directly; a VCS dependency would increase supply/reproducibility
  risk without a demonstrated required fix.

**Sources**:

- <https://pypi.org/project/pyserial/>
- <https://pyserial.readthedocs.io/en/latest/pyserial_api.html>
- <https://github.com/pyserial/pyserial>
- <https://pypi.org/project/types-pyserial/>

## Decision 2: Configure a closed handle before open

**Decision**: Construct `serial.Serial(port=None)`, assign the explicit device,
UART settings, flow control, DTR/RTS intent, and exclusivity while closed, then
call `open()` once. Do not use `serial_for_url` or any discovery API.

**Rationale**: pySerial documents that the port opens immediately when a port
is passed to construction, while a `None` port permits configuration before an
explicit `open()`. It also permits DTR/RTS assignment before open. This is the
only generic-library mechanism that can avoid an avoidable post-open corrective
transition. The exact device name prevents silent selection of an unrelated
connected adapter.

**Alternatives considered**:

- Construct with the device name and correct lines afterward: rejected because
  it guarantees a window using library defaults.
- Discover by VID/PID or choose the first port: rejected because identity and
  reconnect matching need a separate specification and automatic choice is
  unsafe.
- Serial URL handlers: rejected because remote/synthetic transports and URL
  parsing are outside the real local Basic-device slice.

## Decision 3: Record, but do not overstate, DTR/RTS safety

**Decision**: Require explicit DTR intent and either explicit RTS intent or
`driver_managed` RTS under RTS/CTS. Record preconfiguration strategy,
library-reported post-open state, and fixed limitations stating that a
glitch-free transition and electrical pin state are not verified.

**Rationale**: pySerial explicitly warns that OSes/drivers can assert RTS/DTR
as soon as the port opens and can glitch when the requested state differs from
the default. It also documents that POSIX can silently ignore some failures
while applying these lines. The adapter can reduce avoidable changes and report
intent, but cannot honestly claim what occurred electrically without external
measurement.

**Alternatives considered**:

- Refuse every open without a glitch-free guarantee: rejected because generic
  Basic serial would become unusable on the very platforms the Core supports,
  while explicit profile intent and limitation provenance preserve honesty.
- Treat opening as receive-only/passive: rejected because it conflicts with
  Core §9.4 and known driver behavior.
- Record open-time changes as semantic Control: rejected because incidental or
  setup behavior is not an intentional configured reset/boot action.

## Decision 4: Support a conservative portable configuration subset

**Decision**: Support positive baud values; 5/6/7/8 data bits; none/even/odd
parity; 1/2 stop bits; RTS/CTS; and XON/XOFF. Reject mark/space parity, 1.5 stop
bits, DSR/DTR flow control, and simultaneous RTS/CTS plus XON/XOFF in this
slice.

**Rationale**: pySerial exposes broader values but notes that non-standard baud
and combined flow-control support vary. The selected subset covers ordinary
embedded UARTs while keeping the first contract portable and testable. A
positive non-standard baud may be attempted and must fail explicitly if the
platform rejects it.

**Alternatives considered**:

- Expose every pySerial constant: rejected because that would imply portable
  support that the library and drivers do not guarantee.
- Restrict baud to a fixed table: rejected because useful embedded rates can be
  platform-supported and explicit rejection at open is more honest than an
  arbitrary product list.

## Decision 5: Use sequential `asyncio.to_thread` reads

**Decision**: The async event generator will call one synchronous helper via
`asyncio.to_thread`; that helper performs one blocking `read()` and captures
`time.monotonic_ns()` immediately after return. The next read starts only after
the preceding event is yielded.

**Rationale**: This uses the standard library, keeps at most one read
outstanding, requires no adapter queue or second ordering channel, and naturally
applies backpressure. pySerial documents `cancel_read()` as callable from
another thread on POSIX and Windows, allowing `close()` to unblock a pending
read.

**Alternatives considered**:

- A permanent reader thread plus cross-thread queue: rejected because it adds
  buffer sizing, queue saturation, shutdown, and another ordering surface with
  no requirement for read-ahead.
- Polling non-blocking reads in the event loop: rejected because it can busy
  poll and couples correctness to an arbitrary sleep interval.
- Run blocking reads on the event-loop thread: rejected because it would block
  acquisition teardown and other Core work.

## Decision 6: Normalize failures conservatively

**Decision**: Translate open, read, and close failures into normalized
operation/kind values. Emit `Disconnected(device_lost)` only when stable
exception attributes or documented platform signals positively identify
disappearance. Otherwise report a transport/read failure. Error strings may be
diagnostic detail but never drive classification.

**Rationale**: pySerial and OSes do not expose one portable disconnect signal;
some common disconnect paths provide only ambiguous I/O failure. Calling every
read error a disconnect would invent knowledge, while allowing serial exception
types across the boundary would break feature 001.

**Alternatives considered**:

- Parse pySerial exception messages: rejected because messages are not a stable
  contract and differ by version/platform.
- Map every read error to disconnect: rejected because access, driver, and
  programming failures are not necessarily physical disappearance.
- Expose original exceptions: rejected because backend-specific types must
  terminate at the normalized boundary.

## Decision 7: Extend provenance opaquely

**Decision**: Add a backend-neutral immutable `BackendConnectionProvenance`
base value to `ConnectionDescriptor` and `SegmentProvenance`; implement one
`BasicSerialConnectionProvenance` subtype. Acquisition copies it unchanged and
never dispatches on its subtype.

**Rationale**: Core requires effective serial configuration and line behavior
per segment, while Core §17.2 explicitly allows real provenance differences in
normalized data. An opaque typed base preserves those facts without making
shared behavior Basic-specific or inventing an Enhanced provenance schema.

**Alternatives considered**:

- Generic string-key metadata: rejected because it weakens validation and
  creates an undocumented extensibility format.
- Put Basic fields directly on every descriptor: rejected because it makes
  Basic configuration universal.
- Store provenance only inside the adapter: rejected because segment evidence
  would then omit required effective configuration.
