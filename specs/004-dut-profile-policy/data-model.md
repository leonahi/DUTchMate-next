# Data Model: Observation-Only DUT Profile and Policy

These are logical contract values. Exact Python names may vary, but validation,
immutability, and dependency semantics are normative for this feature. Existing
feature-002 adapter values and feature-003 `SessionPolicy` retain their accepted
meanings.

## ProfileFormatVersion

Positive integer discriminator for the serialized Profile schema. This feature
supports exactly `1`. It is generic Profile compatibility state, not a backend,
adapter, persistence, or application version.

## ProfileV1InputCeiling

Profile format version 1 permits at most `65,536` serialized bytes. Resolution
captures at most `65,537` bytes and checks the captured length before UTF-8 or
TOML parsing. Filesystem metadata may be used only as an early hint and is never
the authority because the source can change between inspection and read.

The ceiling bounds parser resources. It is not a `SessionPolicy` value, a
retention quota, a product persistence default, or a limit derived from any of
those values.

## DutIdentity

| Field | Type | Rules |
|---|---|---|
| `id` | string | Non-empty and not whitespace-only; opaque; not a path, serial selector, or discovery key. |
| `name` | string | Non-empty and not whitespace-only; human-readable display value. |

The values are immutable historical inputs. This feature does not create a DUT
registry, uniqueness lookup, rename operation, or filesystem naming rule.

## ProfileBackendSelection

| Field | Type | Rules |
|---|---|---|
| `kind` | string enum | Exactly `basic_serial` in Profile format version 1. |
| `expected_device` | string | Exact local serial-device name satisfying the feature-002 selector contract. |

Selection chooses later composition input. It does not report a runtime
capability, construct an adapter, establish stable physical identity, discover a
device, or create a registry entry.

## ProfileUartConfiguration

| Field | Type | Rules |
|---|---|---|
| `baud_rate` | integer | Positive; boolean is not an integer. |
| `data_bits` | integer enum | `5`, `6`, `7`, or `8`. |
| `parity` | string enum | `none`, `even`, or `odd`. |
| `stop_bits` | integer enum | `1` or `2`. |
| `hardware_flow_control` | boolean | Later maps to RTS/CTS. |
| `software_flow_control` | boolean | Later maps to XON/XOFF. |

The two flow-control flags cannot both be true. These values describe requested
UART configuration, not measured/effective settings. Later feature-002 open
provenance records the library-reported effective configuration.

## ProfileSerialOpenLineIntent

| Field | Type | Rules |
|---|---|---|
| `dtr` | string enum | `asserted` or `deasserted`; never driver-managed. |
| `rts` | string enum | `driver_managed` exactly when hardware flow control is true; otherwise `asserted` or `deasserted`. |

These values are immutable requested connection inputs. They do not define
semantic reset/boot roles, intentional Control actions, electrical voltage,
glitch-free behavior, or physical verification.

## ObservationPolicy

| Field | Meaning | Type | Omitted default | Version-1 accepted value |
|---|---|---|---|---|
| `uart_rx_enabled` | Mandatory current observation invariant | boolean | `true` | `true` only |
| `evidence_recording_enabled` | Mandatory current observation invariant | boolean | `true` | `true` only |
| `uart_tx_enabled` | Future runtime permission | boolean | `false` | `false` only |
| `semantic_control_enabled` | Future runtime permission | boolean | `false` | `false` only |
| `automatic_reconnect_enabled` | Future runtime permission | boolean | `false` | `false` only |

The five-field value is immutable in one resolved snapshot. RX and evidence
recording are mandatory invariants of the current continuous observation path,
not switchable permissions. TX, Control, and reconnect are future runtime
permissions held at their fail-closed values. No semantic roles or capability
set is embedded in policy.

## SessionPolicy

Reuse the existing feature-003 immutable Core value directly:

| Serialized field | Existing field | Rules |
|---|---|---|
| `max_retained_records` | `max_retained_records` | Positive signed-64-bit integer. |
| `max_retained_charged_bytes` | `max_retained_charged_bytes` | Positive signed-64-bit integer. |
| `max_record_charged_bytes` | `max_record_charged_bytes` | Positive; no greater than retained or retrieval-page byte ceilings. |
| `max_database_pages` | `max_database_pages` | Positive signed-64-bit integer; policy value, not runtime `max_page_count`. |
| `max_retrieval_page_records` | `max_retrieval_page_records` | Positive signed-64-bit integer independent of retained records. |
| `max_retrieval_page_charged_bytes` | `max_retrieval_page_charged_bytes` | Positive signed-64-bit integer independent of retained bytes. |

There is no Profile-specific quota object, default, unit conversion, or derived
ceiling. The resolved Profile contains the existing value for direct use by
future lifecycle composition.

## ResolvedDutProfile

| Field | Type | Rules |
|---|---|---|
| `format_version` | `ProfileFormatVersion` | Exactly version 1. |
| `dut` | `DutIdentity` | Immutable identity/name snapshot. |
| `backend` | `ProfileBackendSelection` | Explicit Basic selection and exact device. |
| `uart` | `ProfileUartConfiguration` | Complete validated requested UART settings. |
| `open_lines` | `ProfileSerialOpenLineIntent` | Coherent with hardware-flow-control state. |
| `policy` | `ObservationPolicy` | Safe version-1 policy snapshot. |
| `session_policy` | existing `SessionPolicy` | Exact six persisted limits. |

The value contains no source path, live file reference, parser document, Basic
adapter request, backend instance, serial handle, journal, session, or lifecycle
state. Re-resolving the same path produces a new snapshot and cannot mutate an
older value.

## ProfileFailure

Normalized Profile-boundary failure:

| Field | Type | Rules |
|---|---|---|
| `kind` | enum | Stable category below. |
| `detail` | optional string | Diagnostic only; never used for control flow. |

Kinds and deterministic conditions:

| Condition | Kind |
|---|---|
| Explicit source does not exist | `missing_file` |
| Explicit source is not a regular file | `not_a_file` |
| Source cannot otherwise be read | `unreadable` |
| Captured serialized input exceeds 65,536 bytes | `input_too_large` |
| Bytes are invalid UTF-8/TOML or contain a duplicate TOML key | `invalid_syntax` |
| `profile_version` is absent, has the wrong scalar type, or is not exactly 1 | `incompatible_version` |
| A required non-version field/table is absent | `missing_field` |
| A table or key is unknown | `unknown_field` |
| A known field has the wrong scalar type, invalid range, unsupported enum value, or inconsistent combination | `invalid_value` |
| String backend selection names a kind other than `basic_serial` | `unsupported_backend` |
| Recognized TX, Control, reconnect, or reacquire configuration is requested, or a mandatory observation invariant is disabled | `unsupported_behavior` |

No failure contains the original `OSError`, `TOMLDecodeError`, pySerial
exception, OS handle, file object, or parser tree. Classification uses stable
exception/type/schema facts, never parser or operating-system message text.

## Basic Adapter Translation

The adapter-side translator consumes `ResolvedDutProfile` and returns the
existing feature-002 `BasicSerialOpenRequest`:

```text
backend.expected_device      -> SerialDeviceSelector.device_name
uart.baud_rate               -> SerialConfiguration.baud_rate
uart.data_bits               -> SerialConfiguration.data_bits
uart.parity                  -> SerialConfiguration.parity
uart.stop_bits               -> SerialConfiguration.stop_bits
uart.hardware_flow_control   -> SerialConfiguration.hardware_flow_control
uart.software_flow_control   -> SerialConfiguration.software_flow_control
open_lines.dtr               -> SerialOpenLineIntent.dtr
open_lines.rts               -> SerialOpenLineIntent.rts
```

The function creates values only. It does not construct `serial.Serial`, create
`BasicSerialBackend`, open a device, enumerate ports, or start acquisition.

## Resolution Transition

```text
EXPLICIT PATH
  -> read at most 65,537 bytes once
  -> reject captured length above 65,536 before parsing
  -> parse TOML
  -> validate version and closed schema
  -> validate identity/backend/UART/open lines
  -> apply and validate safe policy defaults
  -> construct existing SessionPolicy
  -> return immutable ResolvedDutProfile
```

Oversized input returns `input_too_large` without TOML parsing, parser tree, or
partial result. Any failure before the final step returns one normalized failure
and no partial resolved Profile. There is no loaded/active state machine, cache,
watcher, reload, lifecycle owner, session, or hardware transition.

## Historical Inputs and Future Policy

- **Historical inputs for later provenance**: format version, DUT identity/name,
  backend/device selection, UART settings, DTR/RTS open intent, mandatory RX/
  recording invariants, and immutable session policy.
- **Future runtime permissions**: TX, semantic Control, and automatic reconnect,
  snapshotted immutably as disabled but not enforced by any runtime operation in
  this feature.

Later Profile edits may govern later connection/operation decisions after an
explicit new resolution. They never rewrite prior segment/session provenance or
mutate an already resolved value.
