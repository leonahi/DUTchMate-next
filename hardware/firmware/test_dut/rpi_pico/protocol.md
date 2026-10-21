# RP2040 test-DUT UART protocol v1

Fixture: `rpi_pico`; firmware: `1.0.0`; protocol: `1`. This is a test-DUT
protocol, not an Enhanced transport or a DUTchMate product interface.

Transport is hardware UART0, GP0 TX / GP1 RX, 115200 8N1, no flow control.
All quoted strings below denote exact ASCII bytes. `\r` is `0d`, `\n` is `0a`;
quotes and C terminating NULs are never transmitted. No echo, prompts, shell,
USB CDC, line-ending translation, case folding or whitespace trimming exists.

## DUT output

After successful UART initialization, emit exactly once:

```text
DUTCHMATE-TEST-DUT rpi_pico fw=1.0.0 protocol=1\r\n
```

Suppress Zephyr's boot banner, console and logging. No other boot text is part
of this protocol. Failure to initialize/configure UART emits no protocol output.
The fixed banner is not replayed on adapter open or in response to requests.
Exact source/binary identification is recorded as described in [README](README.md#firmware-and-source-identity).

Nominally 1000 ms after the banner's UART API calls return, then nominally once
per 1000 ms, emit a tick. API return does not establish physical wire completion:

```text
TICK 0000000000\r\n
TICK 0000000001\r\n
```

Every tick is 17 bytes: `TICK `, ten zero-padded decimal digits, CR LF. The
unsigned 32-bit counter starts at zero, increments once per emitted tick and
wraps from `4294967295` to `0000000000`. Only a firmware restart resets it.
Late scheduling emits one tick and schedules the next relative to the current
uptime; no catch-up burst is generated. This is a continuity indicator, not a
precision clock or a promise about host arrival/inter-byte timing or losslessness.

## Requests and responses

| Exact request | Request hex | Exact response | Response hex |
|---|---|---|---|
| `PING\r\n` (6 bytes) | `50 49 4e 47 0d 0a` | `PONG\r\n` (6 bytes) | `50 4f 4e 47 0d 0a` |
| `SILENT\r\n` (8 bytes) | `53 49 4c 45 4e 54 0d 0a` | No request response | No bytes |

`PING` has no side effect beyond its one fixed response; `SILENT` has no side
effect. **Periodic ticks continue for both requests.** Intentional silence
means no response to that request, not an idle TX wire. To exercise an Interact
timeout later, wait for an absent response such as `PONG\r\n`, not any RX byte.
This document specifies bytes; it does not authorize host TX during acceptance.

Framing and bounded behavior:

- LF terminates a request record; CR is an ordinary byte that must appear in
  precisely the documented position for a request to match.
- Accumulate at most eight bytes **including** the terminating LF. Accept exact
  records only. Unknown records, empty records, bare LF variants, additional
  whitespace, lowercase and embedded NUL/non-ASCII bytes yield no response.
- If a record exceeds eight bytes, discard the entire record through its next
  LF. No valid-looking suffix inside an overlong record is executed. The next
  record starts fresh. A partial record waits without an inter-byte timeout;
  memory stays bounded and ticks continue.
- Requests may arrive in fragments. Consecutive valid records each produce
  their documented result, in reception order. There is no retry, echo, error
  response, request identifier, negotiated mode or dynamic command registry.
- One application loop owns UART output. A banner, tick or PONG is emitted
  completely before another output record starts, so record bytes never
  interleave. At each loop iteration, service at most eight available input
  bytes, then check tick eligibility, then sleep nominally 1 ms. If a request
  completes in that batch, its response precedes the tick checked afterward.
- There is no hard response deadline, arbitrary streaming-input support or
  overflow telemetry. Initial acceptance uses one short request at a time at
  low rate. Excess input may overflow the hardware FIFO; it is not a stress
  fixture. XON/XOFF bytes are ordinary unmatched input, not flow control.

## Interpretation limits

A received PONG is independently observed DUT output under this fixture's
documented behavior. It does not turn a DUTchMate backend ACK into proof of
wire transmission, DUT receipt or causation for arbitrary buffered output.
Ticks are asynchronous evidence and must not be removed to manufacture a clean
transaction. Exact host chunk boundaries are unrelated to these records.

The fixture must be independently validated after manual flashing before
DUTchMate physical acceptance. A software build or host protocol test establishes
neither physical UART/electrical behavior nor hardware acceptance.
