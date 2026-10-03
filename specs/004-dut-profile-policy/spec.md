# Feature Specification: Observation-Only DUT Profile and Policy

**Feature Branch**: `main`

**Created**: 2026-10-01

**Status**: Complete for software-only scope; physical hardware acceptance
remains deferred

**Input**: User description: "Define the minimum human-owned DUT Profile and
safe policy foundation for the current observation-only Basic path, without
starting lifecycle, service, workflow, or hardware behavior."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Resolve an explicit observation profile (Priority: P1)

A human developer can write one explicit DUT Profile that identifies the DUT,
selects the Basic backend, names the exact expected local serial device, and
states the UART and serial-open DTR/RTS intent. Resolving that Profile produces
one immutable configuration value without discovering, opening, or otherwise
interacting with hardware.

**Why this priority**: The completed Basic adapter already requires these
values, and every later attach/lifecycle surface needs one human-owned source
for them. Without this contract, later composition would need temporary or
duplicated configuration inputs.

**Independent Test**: Resolve a valid human-authored Profile from an explicitly
selected file and verify that every identity, backend, device, UART, and
serial-open line value is preserved exactly while hardware-access sentinels
remain untouched.

**Acceptance Scenarios**:

1. **Given** a supported Profile containing a non-empty DUT identity and name,
   explicit Basic selection, an exact local serial-device name, supported UART
   settings, and coherent DTR/RTS open intent, **When** the Profile is resolved,
   **Then** one immutable resolved Profile contains those exact values.
2. **Given** a valid Profile path, **When** resolution completes, **Then** no
   serial device is enumerated or opened, no acquisition starts, and no session
   or journal is created.
3. **Given** two resolutions separated by an edit to the source file, **When**
   the earlier resolved value is inspected, **Then** it remains unchanged and
   the later resolution reflects only the later file contents.

---

### User Story 2 - Apply safe observation-only policy and storage bounds (Priority: P2)

A human developer can state the finite evidence policy required by the durable
journal while the current observation invariants and future state-changing
permissions resolve separately. The resolved Profile requires RX and evidence
recording, while TX, semantic Control, and automatic reconnect remain denied.

**Why this priority**: Continuous evidence needs explicit finite storage limits,
and later lifecycle composition must receive policy values that cannot silently
enable state-changing behavior.

**Independent Test**: Resolve Profiles with omitted observation/policy fields
and with explicit finite persistence limits, then verify the mandatory
observation invariants, fail-closed permission defaults, and an exact one-to-one
mapping into the existing durable session-policy contract.

**Acceptance Scenarios**:

1. **Given** a valid Profile that omits optional observation/policy fields,
   **When** it is resolved, **Then** RX and evidence recording are mandatory
   enabled invariants, while TX, semantic Control, and automatic reconnect are
   denied permissions.
2. **Given** valid explicit retention, per-record, physical database, and
   retrieval-page limits, **When** the Profile is resolved for future journal
   composition, **Then** all six values map exactly to the existing immutable
   durable session policy without deriving one ceiling from another.
3. **Given** a Profile requesting TX, semantic Control, a control-role mapping,
   or reconnect behavior, **When** it is resolved in this observation-only
   feature, **Then** resolution fails explicitly and none of the request is
   silently ignored.

---

### User Story 3 - Fail closed at the Profile boundary (Priority: P3)

A human developer receives a stable, explicit Profile error when a document is
malformed, incompatible, incomplete, internally inconsistent, or requests
unsupported behavior. Unknown data is never accepted as inert configuration,
and adapter-library or filesystem exception objects do not become part of the
generic Profile contract.

**Why this priority**: A human-owned policy root is safe only if typoed or
future configuration cannot be mistaken for an applied rule.

**Independent Test**: Exercise oversized or malformed documents, unsupported
versions, unknown fields, unsupported backend selections, invalid serial
settings, incoherent line intent, invalid storage limits, and state-changing
requests; verify stable Profile-level failures and no side effects.

**Acceptance Scenarios**:

1. **Given** a Profile with an absent or unsupported format version, **When** it
   is loaded, **Then** it is rejected as incompatible without migration or
   best-effort interpretation.
2. **Given** a Profile with an unknown table/key or an invalid enumerated value,
   **When** it is resolved, **Then** it is rejected under the deterministic
   failure matrix and is not ignored or retained for later activation.
3. **Given** a Profile whose Basic values are valid, **When** the explicit Basic
   translation boundary is invoked, **Then** it produces the exact feature-002
   construction request without opening the device or leaking Basic adapter
   types into the generic resolved Profile.

### Edge Cases

- The selected Profile path is missing, unreadable, not a regular file, or
  changes while a separate resolution is attempted.
- The actual captured Profile input is exactly 65,536 bytes or exceeds 65,536
  bytes even though earlier filesystem metadata reported a smaller size.
- The serialized document is syntactically malformed, contains a duplicate
  field, lacks its format version, or declares a boolean as an integer or text.
- DUT identity or display name is empty or only whitespace.
- The device name is empty, numeric-only, `auto`, `-`, or URL-like rather than
  one exact local device name.
- Baud is non-positive; data bits, parity, or stop bits are unsupported; or
  hardware and software flow control are both enabled.
- DTR is declared driver-managed, or RTS is not driver-managed exactly when
  hardware RTS/CTS flow control is enabled.
- A persistence limit is missing, non-integer, boolean, zero, negative, or
  outside the existing signed-64-bit domain.
- Maximum single-record charge exceeds retained-byte capacity or retrieval-page
  byte capacity.
- A Profile explicitly disables RX or evidence recording, enables TX, supplies
  semantic control mappings, or requests reconnect behavior.
- The document selects an unknown backend, Enhanced, serial discovery, or an
  automatic/fallback device selector.

## Requirements *(mandatory)*

### Functional Requirements

#### Human-authored Profile and compatibility

- **FR-001**: The feature MUST include one human-editable serialized DUT Profile
  format and one typed immutable resolved Profile model. A typed-only model is
  insufficient because the Profile is the human-owned configuration root used
  by later process composition.
- **FR-002**: Profile resolution MUST require one explicit file path. It MUST NOT
  search default directories, discover profiles, select the first match, or
  infer a Profile from connected devices.
- **FR-003**: Every serialized Profile MUST declare generic Profile format
  version `1`. Missing, non-integer, or unsupported versions MUST fail
  explicitly. Version 1 MUST perform no migration, repair, or fallback parsing.
- **FR-004**: The version-1 schema MUST be closed: unknown tables and fields
  MUST fail validation rather than being ignored, preserved for future
  activation, or interpreted by a lower layer. Unsupported values for known
  fields MUST follow the deterministic failure matrix below.
- **FR-005**: Syntax, filesystem, oversized-input, incompatible-version,
  missing-field, unknown-field, invalid-value, unsupported-backend, and
  unsupported-behavior failures MUST be distinguishable at the Profile
  boundary. Raw parser, filesystem, pySerial, or operating-system exception
  objects and parser/error message text MUST NOT cross or determine behavior at
  that boundary.

The deterministic Profile failure-category matrix is:

| Condition | Category |
|---|---|
| Explicit path does not exist | `missing_file` |
| Explicit path is not a regular file | `not_a_file` |
| Source cannot otherwise be read | `unreadable` |
| Captured serialized input exceeds 65,536 bytes | `input_too_large` |
| Invalid UTF-8/TOML or duplicate TOML key | `invalid_syntax` |
| Missing, wrong-scalar-type, or unsupported `profile_version` | `incompatible_version` |
| Required non-version field/table is absent | `missing_field` |
| Unknown table or key | `unknown_field` |
| Known field has the wrong scalar type, invalid range, unsupported enum value, or inconsistent combination | `invalid_value` |
| String backend selection names a kind other than Basic | `unsupported_backend` |
| Recognized but currently unsupported TX, Control, reconnect, or reacquire configuration | `unsupported_behavior` |

#### Identity and observation-only connection configuration

- **FR-006**: A Profile MUST contain an explicit non-empty opaque DUT identity
  and a non-empty human-readable DUT name. Whitespace-only values are invalid;
  the identity is not a filesystem path or physical-device discovery rule.
- **FR-007**: A Profile MUST explicitly select the Basic serial backend. Any
  other string backend selection, including Enhanced, MUST fail as unsupported
  in this feature; a wrong scalar type remains `invalid_value`. Neither case
  creates a backend registry or plugin contract.
- **FR-008**: A Profile MUST provide one exact expected local serial-device name
  satisfying the feature-002 selector rules. Numeric-only, `auto`, `-`, URL-like,
  empty, discovery, first-device, and fallback selectors MUST be rejected.
- **FR-009**: A Profile MUST provide the complete supported UART configuration:
  positive integer baud; data bits 5, 6, 7, or 8; parity none, even, or odd;
  stop bits one or two; and explicit hardware and software flow-control flags.
  Simultaneous hardware and software flow control MUST be rejected.
- **FR-010**: A Profile MUST provide explicit DTR and RTS open intent. DTR MUST
  be asserted or deasserted. RTS MUST be driver-managed exactly when hardware
  RTS/CTS flow control is enabled and otherwise MUST be asserted or deasserted.
- **FR-011**: DTR/RTS open intent MUST remain connection configuration and MUST
  NOT be represented as semantic Control, a control-role mapping, or evidence
  that any electrical pin state is safe or physically verified.

#### Policy and persistence limits

- **FR-012**: Capability reporting, human policy, and semantic DUT roles MUST
  remain separate concepts. Profile selection MUST NOT assert that a backend
  has a capability; later runtime code evaluates reported capabilities.
- **FR-013**: Omitted observation/policy fields MUST resolve to UART RX enabled,
  evidence recording enabled, UART TX disabled, semantic Control unavailable,
  and automatic reconnect disabled.
- **FR-014**: UART RX enabled and evidence recording enabled are mandatory
  current observation invariants in Profile version 1, not future switchable
  permissions. An explicit request to disable either MUST fail as
  `unsupported_behavior` rather than producing an inert Profile.
- **FR-015**: UART TX is a human-owned permission that MUST resolve as disabled
  in Profile version 1. Enabling TX
  or supplying TX transformations, line-ending behavior for transmission, or
  Interact/console policy MUST fail as `unsupported_behavior`.
- **FR-016**: Semantic Control is a human-owned permission that MUST resolve as
  disabled, and version 1 MUST expose no semantic roles or electrical action
  sequences. Enabling Control or supplying any role-to-DTR/RTS, role-to-channel,
  pulse, delay, safe-state, or action configuration MUST fail as
  `unsupported_behavior`.
- **FR-017**: Automatic reconnect is a human-owned permission that MUST resolve
  as disabled. Reconnect matching, retry, native-USB topology, disconnect
  expectation, automatic reconnect, or automatic reacquire configuration MUST
  fail as `unsupported_behavior`.
- **FR-018**: A Profile MUST provide all six explicit finite positive limits
  required by the existing durable session policy: retained records, retained
  charged bytes, single-record charged bytes, database pages, retrieval-page
  records, and retrieval-page charged bytes. No unbounded or implicit numerical
  default is permitted in this feature.
- **FR-019**: Every persistence limit MUST satisfy the existing feature-003
  signed-64-bit and cross-limit validation. In particular, one record must fit
  within both retained-byte capacity and retrieval-page byte capacity.
- **FR-020**: Mapping a resolved Profile to the existing durable session policy
  MUST preserve all six values exactly and independently. Retention capacity
  MUST NOT determine retrieval-page ceilings, and the Profile MUST store the
  configured database-page ceiling rather than a storage-engine runtime value.

#### Resolution and architectural boundaries

- **FR-021**: Successful resolution MUST produce immutable values for Profile
  format version, DUT identity/name, backend selection, expected device,
  requested UART configuration, DTR/RTS open intent, safe policy, and durable
  session policy inputs.
- **FR-022**: A resolved Profile MUST be a snapshot. Editing or replacing its
  source document later MUST NOT mutate an existing resolved value or rewrite
  configuration already supplied to later lifecycle composition.
- **FR-023**: Generic Profile contracts MUST NOT import, contain, or expose
  Basic adapter classes, pySerial types/constants, serial handles, parser
  objects, filesystem handles, or persistence-adapter objects.
- **FR-024**: Translation from a resolved Profile into the feature-002 Basic
  adapter construction request MUST exist only at the composition/adapter
  boundary. It MUST be total for valid version-1 Profiles, exact, and free of
  device enumeration, device open, reads, writes, acquisition, or lifecycle
  ownership.
- **FR-025**: Mapping from a resolved Profile into feature-003 session policy
  MUST use the existing generic durable policy value and MUST NOT import the
  SQLite adapter or expose SQLite connection/PRAGMA details.
- **FR-026**: Loading, validation, resolution, and both mappings MUST NOT open or
  enumerate hardware, start acquisition, create/open a journal, create a
  session, select a storage path, or establish Device Core/service ownership.
- **FR-027**: This feature MUST NOT introduce a backend registry, Profile
  registry/manager, discovery service, generalized configuration framework,
  lifecycle state machine, or second backend/persistence abstraction.
- **FR-028**: Architecture and default-test guards MUST prove that shared Core
  remains backend-neutral, Basic/pySerial details remain adapter-local, and no
  physical serial access occurs while resolving or mapping Profiles.
- **FR-029**: Profile format version 1 MUST have a maximum serialized size of
  65,536 bytes. Resolution MUST read at most 65,537 bytes, enforce the ceiling
  against the bytes actually captured rather than trusting filesystem metadata,
  and return `input_too_large` before UTF-8/TOML parsing when the captured input
  exceeds the ceiling. No parser tree or partial resolved Profile may result.
  This parser-resource ceiling is independent of all persistence-policy values.

### Key Entities

- **DUT Profile Document**: Human-authored, explicitly selected, versioned
  serialized configuration for one DUT; strict and fail-closed in version 1.
- **Resolved DUT Profile**: Immutable in-memory snapshot of validated identity,
  observation configuration, policy, and persistence inputs, containing no
  adapter implementation object.
- **DUT Identity**: Opaque non-empty identifier plus a human-readable name;
  distinct from a host serial-device selector.
- **Backend Selection**: Explicit choice of the Basic serial mechanism for this
  feature; it is not a capability claim or registry key.
- **UART Configuration**: Backend-neutral requested serial parameters whose
  supported value set aligns with the current feature-002 Basic contract.
- **Serial-Open Line Intent**: Explicit DTR/RTS behavior requested during open;
  distinct from semantic Control roles/actions.
- **Observation Policy**: One immutable snapshot containing the mandatory
  current RX/recording invariants separately from the denied TX, Control, and
  reconnect permissions.
- **Profile Persistence Limits**: The six explicit finite values that map
  one-to-one into the existing immutable durable `SessionPolicy`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For every supported UART, flow-control, and line-intent
  combination in the Profile contract suite, resolution preserves 100% of
  declared values and Basic-boundary translation produces the exact equivalent
  feature-002 construction request.
- **SC-002**: For every valid persistence-policy case in the contract suite,
  all six limits map exactly to the durable session policy, and every existing
  feature-003 cross-limit or signed-64-bit violation is rejected.
- **SC-003**: Every tested omission of optional observation/policy fields
  resolves to mandatory RX/recording invariants enabled and TX, Control, and
  reconnect permissions disabled; 100% of tested attempts to change those
  invariants or enable unsupported state-changing behavior fail before any
  mapping or side effect.
- **SC-004**: All malformed, incompatible-version, unknown-field,
  unsupported-backend, oversized-input, and internally inconsistent Profile
  cases fail with the matrix-defined Profile-level category and produce no
  parser tree or partially resolved Profile.
- **SC-005**: Tests detect zero serial enumeration/open calls, acquisition
  starts, journal/session creations, or other physical effects across all
  Profile load, validation, and mapping scenarios.
- **SC-006**: Static architecture checks find no Basic adapter or pySerial type
  in generic Profile contracts, no adapter import from shared domain/application
  code, and no new backend registry or generalized Profile manager.
- **SC-007**: All completed feature-001/002/003 tests and repository validation
  gates remain green without weakening their capability, evidence, persistence,
  or hardware-access boundaries.

## Assumptions

- A serialized Profile format is included now because a typed-only model would
  not yet provide the human-owned configuration root required by later attach
  and service composition. The planning phase selects the concrete format.
- The source Profile path is supplied explicitly by a later composition root.
  This feature neither chooses profile locations nor defines CLI/HTTP input.
- Version 1 requires all six numerical persistence limits explicitly. Product
  convenience defaults can be considered later at a delivery boundary without
  weakening the durable journal's explicit-policy contract.
- Resolved identity, backend/device selection, UART/open-line intent, mandatory
  observation invariants, and persistence limits are immutable historical
  inputs for later connection and session provenance. TX, Control, and
  reconnect permissions are also snapshotted at resolution; future features
  may define how a newly resolved Profile changes those permissions for later
  operations, never retroactively.
- Feature-002 and feature-003 validation semantics remain authoritative for
  adapter construction and durable session policy respectively.
- All validation is software-only. It does not establish electrical safety,
  physical identity, line-state behavior, baud accuracy, or real-device
  compatibility.

## Explicit Exclusions and Deferred Behavior

- Ownership/lifecycle states, attach/detach orchestration, active-profile
  replacement, session creation/naming/listing/sealing, and storage path policy.
- Service/HTTP, local authentication, browser-origin rejection, CLI, and any
  user-facing command or response schema.
- Monitor, follow, derived text/lines/patterns, operation records, annotations,
  and live subscription behavior.
- UART TX, Interact, console, transmission line-ending behavior, output
  flushing, and TX arbitration.
- Semantic Control roles, DTR/RTS action sequences, capability execution,
  safe-state execution, and any hardware-changing operation.
- Reconnect, native-USB topology, release/reacquire, handoff, external-command
  execution, and ownership-gap evidence.
- Automatic profile discovery, directory search, inheritance, overlays,
  environment interpolation, secret handling, registries, managers, plugins,
  and generalized configuration frameworks.
- Enhanced backend/protocol/firmware, MCP, AI behavior, and all physical
  hardware access or acceptance.
