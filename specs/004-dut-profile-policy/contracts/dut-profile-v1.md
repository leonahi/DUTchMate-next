# Internal Contract: DUT Profile Format and Resolution Version 1

This is an internal human-configuration, Core-value, and adapter-translation
contract. It is not a lifecycle, service/HTTP, CLI, session manager, serial
open, Monitor, TX, Control, reconnect, or Enhanced contract.

## 1. Serialized format boundary

One Profile is one UTF-8 TOML file selected by an explicit caller-supplied path.
Profile version 1 has a maximum serialized size of `65,536` bytes. This is a
format/parser resource ceiling, not a persistence-policy value or default.

The version-1 shape is:

```toml
profile_version = 1

[dut]
id = "board-a"
name = "Board A"

[backend]
kind = "basic_serial"
expected_device = "/dev/ttyUSB0"

[uart]
baud_rate = 115200
data_bits = 8
parity = "none"
stop_bits = 1
hardware_flow_control = false
software_flow_control = false

[uart.open_lines]
dtr = "deasserted"
rts = "deasserted"

[policy]
# All five keys are optional; these are the only accepted resolved values.
uart_rx_enabled = true
evidence_recording_enabled = true
uart_tx_enabled = false
semantic_control_enabled = false
automatic_reconnect_enabled = false

[persistence]
max_retained_records = 10000
max_retained_charged_bytes = 8388608
max_record_charged_bytes = 65536
max_database_pages = 4096
max_retrieval_page_records = 256
max_retrieval_page_charged_bytes = 262144
```

The example numbers demonstrate syntax only; they are not product defaults.
Every persistence key is required in each Profile.

Allowed root keys are exactly `profile_version`, `dut`, `backend`, `uart`,
`policy`, and `persistence`. The `policy` table itself may be omitted because all
five resolved values are defined. Every other required table must exist.
Unrecognized tables or keys at any nesting level fail as `unknown_field`.
Specifically recognized but currently unsupported TX, Control, reconnect, and
reacquire tables/keys fail as `unsupported_behavior` instead; they are not
accepted members of the version-1 schema.

TOML native types are exact. Boolean is not accepted for integer fields; string
or integer substitutes are not accepted for booleans or enum strings. Duplicate
TOML keys fail syntax parsing. No environment expansion, include, inheritance,
overlay, interpolation, or path-relative reference exists.

## 2. Compatibility boundary

- `profile_version` is required and must be TOML integer `1`.
- Missing, boolean, string, negative, zero, or otherwise unsupported versions
  fail as `incompatible_version`.
- Unknown fields never imply forward compatibility and are not retained.
- Version 1 performs no migration, repair, downgrade, or fallback parsing.
- A future version requires an explicit contract revision. This feature does
  not promise that a version-1 loader can interpret it.
- The Profile format version is independent of durable journal schema version,
  generic provenance envelope version, and opaque backend provenance versions.

## 3. Load and resolution boundary

Conceptual operation:

```text
resolve_profile(explicit_path) -> ResolvedDutProfile
```

Rules:

1. Accept exactly one caller-supplied local path.
2. Do not search directories, consult environment variables, enumerate devices,
   follow a Profile registry, or choose a default Profile.
3. Reject a missing source as `missing_file` and a non-regular source as
   `not_a_file`.
4. Read at most `65,537` bytes into one captured byte string. Filesystem size
   metadata may short-circuit an obviously oversized source but is never the
   authority; the captured byte count is always checked because the source may
   change between inspection and read.
5. If the captured byte count exceeds `65,536`, return `input_too_large` before
   UTF-8/TOML parsing. Create no parser tree or partial resolved Profile.
6. Otherwise parse the captured bytes as UTF-8 TOML and validate the complete
   closed schema before returning.
7. Normalize parser/filesystem/value failures into `ProfileFailure`; raw source
   exceptions and parser objects do not cross the boundary, and parser or
   operating-system message text never determines a category.
8. Return no partial resolved Profile on failure.
9. Perform no serial construction/open/enumeration, acquisition, evidence
   append, journal/session creation, storage-path selection, or lifecycle work.

## 4. Deterministic failure categories

| Condition | Category |
|---|---|
| Explicit path does not exist | `missing_file` |
| Explicit path is not a regular file | `not_a_file` |
| Source cannot otherwise be read | `unreadable` |
| Captured serialized input exceeds 65,536 bytes | `input_too_large` |
| Invalid UTF-8/TOML or duplicate TOML key | `invalid_syntax` |
| Missing, wrong-scalar-type, or unsupported `profile_version` | `incompatible_version` |
| Required non-version field/table is absent | `missing_field` |
| Unrecognized table or key | `unknown_field` |
| Known field has the wrong scalar type, invalid range, unsupported enum value, or inconsistent combination | `invalid_value` |
| String backend selection names a kind other than `basic_serial` | `unsupported_backend` |
| Recognized but currently unsupported TX, Control, reconnect, or reacquire configuration, including disabling a mandatory observation invariant | `unsupported_behavior` |

Classification follows stable exception types/attributes, captured byte count,
and schema facts. It never parses exception text. `profile_version` and a
well-typed non-Basic backend selection intentionally use their dedicated
categories rather than the generic missing-field/invalid-value rules; a
wrong-type `backend.kind` is `invalid_value`.

## 5. Identity and backend boundary

- `dut.id` and `dut.name` are required TOML strings, non-empty after whitespace
  validation. Their exact text is preserved; they create no registry or path.
- `backend.kind` is required and exactly `basic_serial`.
- Any other string kind, including Enhanced, is `unsupported_backend`; a
  wrong-scalar-type kind is `invalid_value`. There is no registry lookup or
  adapter plugin selection.
- `backend.expected_device` is validated by the feature-002 exact-selector
  semantics: non-empty, not numeric-only, not `auto`, not `-`, and not URL-like.
- Expected device text is not proof of stable physical identity and creates no
  discovery or reconnect matching behavior.

## 6. UART and serial-open line boundary

`uart` contains exactly the six required fields defined in the example.
Supported values match the feature-002 construction contract. Both flow-control
flags cannot be true.

`uart.open_lines` is required. `dtr` is `asserted` or `deasserted`. `rts` is
`driver_managed` exactly when `hardware_flow_control` is true; otherwise it is
`asserted` or `deasserted`.

These values express connection-open intent. They do not define semantic roles,
an intentional DTR/RTS action, electrical levels, safe wiring, or a guarantee
that the OS/driver avoids intermediate transitions.

## 7. Observation policy boundary

The `policy` table recognizes exactly five optional boolean keys:

| Key | Meaning | Omitted value | Only accepted explicit value |
|---|---|---|---|
| `uart_rx_enabled` | Mandatory current observation invariant | `true` | `true` |
| `evidence_recording_enabled` | Mandatory current observation invariant | `true` | `true` |
| `uart_tx_enabled` | Future runtime permission | `false` | `false` |
| `semantic_control_enabled` | Future runtime permission | `false` | `false` |
| `automatic_reconnect_enabled` | Future runtime permission | `false` | `false` |

RX and evidence recording are mandatory invariants of the current observation
path, not permissions. TX, semantic Control, and automatic reconnect are the
three fail-closed permissions. A recognized key with the opposite value fails
as `unsupported_behavior`.

Recognized TX settings/line endings/Interact/console policy, control roles/
mappings/sequences/safe states, reconnect topology/matching/retries, and
automatic reacquire configuration also fail as `unsupported_behavior`. An
unrecognized table/key fails as `unknown_field`. Neither category is accepted
and ignored.

Policy is not a capability report. Later runtime composition must still consult
the opened backend's normalized capabilities. No semantic role exists in this
version-1 Profile.

## 8. Durable session-policy boundary

The `persistence` table requires exactly the six fields shown in the example.
Resolution passes the TOML integers directly to the existing feature-003
`SessionPolicy`. Its current validation remains authoritative:

- each value is a positive signed-64-bit integer;
- `max_record_charged_bytes <= max_retained_charged_bytes`;
- `max_record_charged_bytes <= max_retrieval_page_charged_bytes`;
- retrieval page limits remain independent of retained limits.

No value is defaulted, converted, rounded, inferred, or derived. In particular,
`max_database_pages` remains persisted DUTchMate policy and is not a Profile
representation of SQLite `max_page_count` or a byte-count conversion. The
generic Profile contract imports no SQLite adapter.

## 9. Basic translation boundary

Conceptual operation, implemented at the adapter/composition edge:

```text
to_basic_serial_open_request(resolved_profile) -> BasicSerialOpenRequest
```

The translator:

1. verifies the already-resolved selection is `basic_serial`;
2. maps `expected_device` to the existing `SerialDeviceSelector`;
3. maps every UART field to the corresponding existing
   `SerialConfiguration` value without defaults or coercion;
4. maps DTR/RTS intent to the existing `SerialOpenLineIntent`;
5. returns the existing `BasicSerialOpenRequest`.

It does not import pySerial directly, instantiate `BasicSerialBackend` or
`serial.Serial`, enumerate or open a port, create a descriptor, start
acquisition, or claim that the device exists. Generic `profile.py` does not
import this translator or any Basic adapter type.

## 10. Snapshot and ownership boundary

The resolved value is immutable. A source edit after resolution affects only a
later explicit resolution. This feature does not decide when a new snapshot
becomes active, how an active connection responds, or how a session/segment
stores it. It only makes the complete value suitable for later composition.

No Profile manager, active-profile singleton, backend factory, session manager,
watcher, reload service, or lifecycle state is created.

## 11. Explicitly absent

Lifecycle/ownership, attach/detach, session orchestration, service/HTTP,
authentication, CLI, Monitor/follow, annotations, TX/Interact/console, semantic
Control, reconnect, release/reacquire/handoff, Enhanced, MCP, AI, hardware
access, and physical/electrical acceptance are outside this contract.
