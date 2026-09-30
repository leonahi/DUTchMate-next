# Data Model: Basic Serial Backend Adapter

These are logical contract types. Exact Python names may vary, but validation
and provenance semantics are normative for this slice. Existing feature 001
values retain their meanings unless explicitly extended below.

## SerialDeviceSelector

| Field | Type | Rules |
|---|---|---|
| `device_name` | string | Non-empty after trimming; exact platform name such as `/dev/ttyUSB0`, `/dev/cu.usbserial-...`, or `COM3`; not numeric, `auto`, `-`, or URL-like. |

The selector is used verbatim for one open attempt. It does not assert stable
physical identity and creates no discovery or reconnect rule.

## SerialConfiguration

| Field | Type | Rules |
|---|---|---|
| `baud_rate` | integer | Positive; platform may reject a non-standard value at open. |
| `data_bits` | enum | `5`, `6`, `7`, or `8`. |
| `parity` | enum | `none`, `even`, or `odd`. |
| `stop_bits` | enum | `one` or `two`. |
| `hardware_flow_control` | boolean | Maps to RTS/CTS. |
| `software_flow_control` | boolean | Maps to XON/XOFF. |

Both flow-control booleans cannot be true. DSR/DTR flow control is always false
and is not a configurable field in this slice.

The same value type represents requested and library-reported effective
settings. Equality is exact across all six fields.

## SerialOpenLineIntent

| Field | Type | Rules |
|---|---|---|
| `dtr` | `asserted` or `deasserted` | Always explicit. |
| `rts` | `asserted`, `deasserted`, or `driver_managed` | Must be `driver_managed` exactly when RTS/CTS is enabled; otherwise must be static. |

Asserted/deasserted describe modem-control semantics, not electrical voltage.
They are connection-open intent and not semantic DUT Control roles.

## SerialOpenLineProvenance

| Field | Type | Rules |
|---|---|---|
| `requested` | `SerialOpenLineIntent` | Exact validated intent. |
| `apply_strategy` | enum | `preconfigured_while_closed`; no post-open corrective sequence is planned. |
| `library_reported_dtr` | asserted/deasserted | Read from library state after open. |
| `library_reported_rts` | asserted/deasserted/driver-managed | Static library state or driver-managed marker. |
| `transition_guarantee` | enum | Always `not_guaranteed` for this generic adapter. |
| `electrical_verification` | enum | Always `not_verified`; no pin measurement occurs. |

Library-reported state is not evidence that a driver applied it or that the pin
held that state throughout open.

## SerialExclusivityProvenance

| Field | Type | Rules |
|---|---|---|
| `requested` | boolean | Always true. |
| `mechanism` | enum | `posix_pyserial_exclusive` or `windows_exclusive_handle`. |
| `result` | enum | `open_succeeded_with_requested_mechanism`; no stronger inter-process guarantee is inferred. |

## BackendConnectionProvenance

Immutable backend-neutral marker/base value. Shared Device Core stores and
copies it but defines no subtype-based behavior.

## BasicSerialConnectionProvenance

Subtype of `BackendConnectionProvenance`.

| Field | Type | Rules |
|---|---|---|
| `selected_device_name` | string | Exact validated selector. |
| `opened_device_name` | string | Non-empty name reported by pySerial after open. |
| `requested_configuration` | `SerialConfiguration` | Immutable requested values. |
| `effective_configuration` | `SerialConfiguration` | pySerial-reported post-open values; must equal requested values. |
| `open_line_provenance` | `SerialOpenLineProvenance` | Explicit intent, report, and limitations. |
| `exclusivity` | `SerialExclusivityProvenance` | Platform mechanism used for the successful open. |
| `stable_physical_identity` | absent | Explicitly not established by this selector-only slice. |

## ConnectionDescriptor (extension)

Feature 001 fields remain unchanged. Add:

| Field | Type | Rules |
|---|---|---|
| `connection_provenance` | `BackendConnectionProvenance` | Immutable snapshot returned by the opened backend. |

For the Basic adapter:

- capabilities contain exactly `uart_receive`;
- timestamp domain is host/observation/nanosecond with fresh non-empty domain
  and origin identifiers for each successful open;
- loss observability is `UpstreamLossNotObservable`;
- connection provenance is `BasicSerialConnectionProvenance`.

## SegmentProvenance (extension)

Add the same `connection_provenance` value from the descriptor. It remains
stable across timestamp-origin-reset segments within one physical connection.
Acquisition copies it and does not inspect the subtype.

## NormalizedBackendFailure

Base failure crossing the adapter boundary.

| Field | Type | Rules |
|---|---|---|
| `operation` | `open`, `read`, or `close` | Operation that failed. |
| `kind` | enum below | Stable behavioral category. |
| `detail` | optional string | Diagnostic only; never used for classification or control flow above the adapter. |

Failure kinds:

- `invalid_request` — validation failed before OS open;
- `device_not_found` — stable platform attributes identify absence;
- `permission_denied` — stable platform attributes identify access denial;
- `device_busy` — stable platform attributes identify ownership conflict;
- `configuration_rejected` — library/driver rejected or changed settings;
- `line_state_setup_failed` — explicit line-state setup raised;
- `io_failure` — other open/read/close transport failure;
- `internal_contract_failure` — adapter worker/stream invariant failed.

The adapter may expose operation-specific subclasses for typing, but no class
contains a pySerial exception or OS handle.

## Disconnect Event

Reuse feature 001 `Disconnected` with stable reason `device_lost` only after
positive classification from stable attributes/signals. Ambiguous failures use
`NormalizedBackendFailure(operation=read, kind=io_failure)` instead.

## Open State Transition

```text
VALIDATE REQUEST
  -> construct closed Serial
  -> assign device/settings/flow/exclusivity/line intent
  -> open once
  -> read library-reported effective state
  -> mismatch: best-effort close -> normalized open failure
  -> match: build immutable descriptor -> OPEN
```

No connection or segment identity, evidence, or read call exists before the
descriptor is successfully returned to feature 001 acquisition.

## Connection Read/Close Transition

```text
OPEN
  -> events() claimed once
READING
  -> non-empty read: timestamp -> yield RxBytesObserved -> next read
  -> empty timeout read: next read
  -> close cancellation + empty read: finish teardown
  -> positively classified loss: yield Disconnected -> terminal
  -> other read failure: raise normalized read failure -> terminal
CLOSING
  -> cancel outstanding read -> await return -> close serial handle
  -> success: CLOSED
  -> failure: normalized close failure, still terminal
```

Feature 001 remains responsible for evidence sequence, segment end reason,
primary-failure preservation, and terminal acquisition state.
