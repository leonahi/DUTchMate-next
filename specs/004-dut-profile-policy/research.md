# Research: Observation-Only DUT Profile and Policy

## Decision: Include a serialized Profile now

Include both the human-authored serialized document and the immutable resolved
domain value in this feature.

### Rationale

Core §13.2 makes the Profile the human-owned configuration root. A typed-only
model would still require later service or CLI work to invent a file format,
compatibility behavior, and failure model before a human could own the input.
Defining the smallest read-only format now prevents provisional attach inputs
and lets future lifecycle composition consume one stable resolved value.

### Alternatives considered

- **Typed/resolved model only**: smaller immediately, but defers the actual
  human boundary and makes the next lifecycle slice choose a public format.
- **Service/CLI request schema only**: violates the accepted slice and would
  make delivery transport, rather than human configuration, the source of
  truth.

## Decision: TOML version 1, read-only and strict

Use one UTF-8 TOML document parsed by Python 3.14's standard-library `tomllib`.
The root declares `profile_version = 1`. The schema is closed: unknown tables,
keys, enum values, missing version, and unsupported version are errors. There is
no writer, canonical reserialization, migration, repair, inheritance, overlay,
or preservation of unknown fields.

### Rationale

TOML is human-readable, already familiar in this uv/Python repository, supports
typed scalars and tables, rejects duplicate keys, and adds no dependency. An
explicit integer version makes compatibility fail-closed and leaves a clear
place for a later documented revision without pretending forward compatibility.

### Alternatives considered

- **JSON**: standard-library and unambiguous, but needlessly unfriendly for
  hand-authored profiles and unable to express comments.
- **YAML**: human-friendly, but adds a parser dependency and a broader type/
  alias surface not justified by the minimal schema.
- **Python module/config objects**: executable configuration conflicts with a
  deterministic, data-only human policy boundary.
- **Lenient unknown-field handling**: risks a typoed safety setting being
  accepted but unapplied.

## Decision: One explicit path and one read per resolution

The loader accepts one path supplied by its caller, reads that file once, parses
that captured content, and returns an immutable resolved value. It performs no
directory search, environment interpolation, device discovery, cache, file
watching, or automatic reload.

### Rationale

This keeps selection human-controlled, avoids search-order ambiguity, and makes
the resolved object an honest snapshot. Later lifecycle composition may decide
which path to supply, but this feature creates no path policy.

### Alternatives considered

- **Search paths/default profile directories**: introduce precedence and
  machine-local behavior before a delivery surface exists.
- **Live reload/watch**: creates active-profile lifecycle and mutation semantics
  explicitly deferred from this slice.

## Decision: Bound Profile v1 input at 65,536 serialized bytes

Resolution reads at most 65,537 bytes from the explicitly selected source. It
uses the length of those captured bytes—not filesystem metadata—as the
authoritative check and returns `input_too_large` before UTF-8/TOML parsing when
more than 65,536 bytes are captured. No parser tree or partial resolved value is
then produced. Metadata may be used only as a non-authoritative early hint.

### Rationale

The Profile schema is intentionally small. A 64 KiB ceiling is ample for a
human-authored Profile while placing a simple, testable bound on parser input.
Checking the actual capture closes the inspection/read race for mutable sources.
This ceiling protects format resolution and is unrelated to feature-003
persistence-policy limits.

### Alternatives considered

- **Filesystem-size check only**: races with replacement or mutation between
  inspection and read and is unavailable for some readable sources.
- **Unbounded `read_bytes()`**: allows a malformed human input to consume
  unbounded memory before the closed schema can reject it.
- **Reuse a persistence limit**: conflates parser resource safety with journal
  retention and database policy.

## Decision: Separate generic values, TOML loading, and Basic translation

Place generic immutable Profile values and Profile-level errors in shared Core.
Place TOML/filesystem parsing in one concrete adapter. Place conversion to the
existing `BasicSerialOpenRequest` in a separate Basic adapter-side translator.
The generic Profile contains only its own UART/open-line value types and the
existing generic `SessionPolicy`; it imports no Basic or pySerial type.

### Rationale

Filesystem syntax and Basic adapter construction are external details that
change independently. The split preserves inward dependencies without adding a
protocol, registry, factory hierarchy, or Profile manager. A small pure
translator proves that every generic value reaches feature 002 exactly.

### Alternatives considered

- **Generic Profile imports Basic request types**: leaks the first backend into
  shared Core and makes future backend-neutral lifecycle composition branch on
  adapter implementation values.
- **Move all feature-002 serial types into generic Profile**: creates an
  unnecessary compatibility move in an already completed contract.
- **Backend registry/factory**: unjustified with one production backend and
  prohibited by the accepted scope.

## Decision: Reuse `SessionPolicy` exactly

The TOML persistence table contains the six existing feature-003 fields with
the same names and integer meanings. Resolution constructs the existing
immutable `SessionPolicy` directly; no second Profile quota model and no unit
conversion exists.

### Rationale

Feature 003 already owns signed-64-bit validation, positive bounds, record-fit
cross-checks, independent retrieval ceilings, and database-page policy. Reuse
prevents drift and ensures later composition can pass the value directly to
journal creation.

### Alternatives considered

- **Profile-specific quota object plus later mapping**: duplicates invariants
  and allows two sources of truth.
- **Byte-size database limit converted to pages**: rounding and page-size
  decisions would change the accepted `max_database_pages` contract.
- **Numerical defaults**: feature 003 requires explicit finite policy, and no
  delivery UX exists yet to justify product defaults.

## Decision: Separate mandatory observation invariants from permissions

The version-1 policy table recognizes five booleans. When omitted, they resolve
to RX enabled, recording enabled, TX disabled, semantic Control disabled, and
automatic reconnect disabled. RX enabled and recording enabled are mandatory
current observation invariants, not switchable permissions. TX, semantic
Control, and automatic reconnect are actual fail-closed policy permissions;
Profile v1 permits only `false`. Explicit values are accepted only when equal to
those states. Recognized TX/Control/reconnect/reacquire configuration fails as
`unsupported_behavior`; unrelated unknown tables or keys fail as
`unknown_field`.

### Rationale

This implements Core §13.4 defaults while preventing a Profile from claiming a
permission or behavior that current production code cannot enforce. Accepting
future configuration as inert would make the human policy misleading.

### Alternatives considered

- **Omit future policy names entirely**: safe, but makes it impossible to state
  and inspect the complete observation-only policy snapshot.
- **Accept `true` but leave it inactive**: silently ignores state-changing
  human intent and is therefore unsafe.

## Decision: Normalize Profile failures with a fixed classification matrix

Expose these stable categories:

| Condition | Category |
|---|---|
| path does not exist | `missing_file` |
| path is not a regular file | `not_a_file` |
| selected file cannot be read | `unreadable` |
| captured input exceeds 65,536 bytes | `input_too_large` |
| bytes are not valid Profile TOML | `invalid_syntax` |
| Profile version is missing, wrong-type, or unsupported | `incompatible_version` |
| required non-version field is absent | `missing_field` |
| unrecognized table or key | `unknown_field` |
| known field has the wrong scalar type, invalid range, unsupported enum value, or inconsistent combination | `invalid_value` |
| string backend selection names a kind other than Basic | `unsupported_backend` |
| recognized TX/Control/reconnect/reacquire request or disabled mandatory observation invariant | `unsupported_behavior` |

Preserve optional diagnostic text only as inert context; never expose raw
parser, filesystem, pySerial, or OS exception objects. Classification is based
on the condition and schema location, never parser or exception message text.

### Rationale

Later service/CLI layers need deterministic failure semantics without parsing
messages or inheriting local exception types. The categories remain local to
Profile resolution and do not invent HTTP or CLI error schemas.

### Alternatives considered

- **Propagate `OSError`/`TOMLDecodeError`**: leaks adapter details across the
  boundary and makes behavior platform/message dependent.
- **One undifferentiated invalid-profile error**: loses the compatibility and
  unsupported-behavior distinctions needed for safe user feedback.

## Decision: Historical inputs versus future runtime policy

DUT identity/name, selected backend/device, UART settings, DTR/RTS open intent,
Profile format version, `SessionPolicy`, and the two mandatory observation
invariants are immutable inputs intended for future connection/session
provenance. The three state-changing policy booleans are also immutable in each
resolved snapshot, but they represent permissions for future runtime evaluation
rather than physical facts. Re-resolving an edited file may produce a new
snapshot for later lifecycle decisions; it never mutates an existing snapshot
or prior evidence.

### Rationale

This distinction preserves historical meaning without prematurely designing
active-profile replacement or live policy updates.

### Alternatives considered

- **Mutable Profile object**: makes it unclear which configuration governed a
  connection and conflicts with Core §13.3.
- **Runtime policy engine now**: belongs with later lifecycle and action
  arbitration, not this value-resolution slice.
