# Implementation Plan: Observation-Only DUT Profile and Policy

**Branch**: `004-dut-profile-policy` | **Date**: 2026-10-01 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from
`/specs/004-dut-profile-policy/spec.md`

## Summary

Add one strict, versioned, human-editable TOML Profile format and one immutable
backend-neutral resolved Profile model to `dutchmate-core`. A concrete TOML
loader reads only an explicitly supplied path, normalizes failures, validates a
closed schema within a 65,536-byte serialized-input ceiling, and returns
observation-only values. The resolved Profile holds
the existing generic feature-003 `SessionPolicy`; a separate Basic adapter-side
translator converts generic UART/open-line values into the existing
feature-002 construction request without opening hardware. No lifecycle,
session creation, service, workflow, registry, or physical behavior is added.

## Technical Context

**Language/Version**: Python `>=3.14,<3.15`

**Primary Dependencies**: Python standard library (`dataclasses`, `enum`,
`pathlib`, `tomllib`); existing project dependencies unchanged

**Storage**: One read-only human-authored TOML Profile document selected by an
explicit path and limited to 65,536 serialized bytes; no Profile discovery,
writer, mutation, migration, secret store, journal creation, or Profile registry

**Testing**: pytest 9.1; temporary Profile files; unit tests for immutable
values; contract tests for strict parsing, errors, Basic translation, and
`SessionPolicy` mapping; existing Ruff, mypy, Import Linter, and fail-closed
serial-hardware guards

**Target Platform**: Local Linux, macOS, and Windows filesystems supported by
Python 3.14; device-name text remains platform-supplied and exact

**Project Type**: Existing uv Python workspace and `dutchmate-core` library

**Performance Goals**: Resolve one finite local Profile by reading at most
65,537 bytes and rejecting an oversized capture before TOML parsing; no device
scan, directory walk, network access, background work, cache, or retained parser
state

**Constraints**: Strict format version 1; closed schema; no implicit numerical
persistence defaults; no Basic or pySerial implementation type in generic
Profile values; no raw parser/filesystem exception at the Profile boundary; no
classification from exception-message text; no hardware, acquisition, journal,
session, or lifecycle side effect

**Scale/Scope**: One Profile document for one DUT, one supported Basic backend
selection, current feature-002 UART/open-line value set, two mandatory
observation invariants, three fail-closed state-changing permissions, and the
six existing feature-003 session-policy limits

## Constitution Check

The repository constitution template is not populated, so the governing gates
come from `AGENTS.md`, the Core document, and the active specification.

- **Authority**: Pass. The plan implements Core §§9.4 and 13 and preserves the
  completed feature-002/003 contracts.
- **Human ownership and safety**: Pass. The Profile is an explicit human-authored
  input; RX and evidence recording are mandatory current observation invariants;
  TX, Control, and reconnect are disabled permissions and cannot be activated by
  ignored fields.
- **Dependency direction**: Pass. Generic Profile values depend only on existing
  Core values. TOML/filesystem handling and Basic translation depend inward from
  adapters. Shared Core never imports adapters.
- **Backend neutrality**: Pass. Generic values contain a backend selection and
  UART semantics, not a `BasicSerialBackend`, pySerial value, handle, or identity
  branch for shared runtime behavior.
- **Capabilities, policy, and roles**: Pass. The Profile does not claim runtime
  capabilities, safe policy is distinct, and semantic roles are absent/rejected.
- **Concrete boundary only**: Pass. There is one TOML loader and one Basic
  translator; no registry, manager, factory hierarchy, plugin system, or generic
  configuration framework is introduced.
- **Persistence boundedness**: Pass. All six `SessionPolicy` values remain
  required, positive, signed-64-bit, and independent where feature 003 requires.
- **Evidence integrity**: Pass. Resolution creates no evidence or session and
  cannot rewrite prior configuration/provenance.
- **Hardware safety**: Pass. Loader and translators have no backend-open or
  serial enumeration path; default tests keep the physical-serial sentinel.
- **Phase discipline**: Pass. No lifecycle, service, CLI, Monitor/follow,
  TX/Interact/console, Control, reconnect, handoff, Enhanced, or MCP behavior is
  introduced.

Post-design re-check: `research.md`, `data-model.md`, and the Profile v1 contract
retain every gate. No complexity waiver is required.

## Project Structure

### Documentation (this feature)

```text
specs/004-dut-profile-policy/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── dut-profile-v1.md
├── checklists/
│   └── requirements.md
└── tasks.md
```

### Source Code (repository root)

```text
core/
├── src/dutchmate_core/
│   ├── model.py                         # existing SessionPolicy/value bounds
│   ├── profile.py                       # generic immutable Profile values/errors
│   └── adapters/
│       ├── toml_profile.py              # concrete Profile v1 loader/resolver
│       ├── basic_profile.py             # side-effect-free Basic request mapping
│       └── basic_serial.py              # existing Basic construction values
└── tests/
    ├── unit/
    │   └── test_profile_model.py
    └── contract/
        ├── test_toml_profile.py
        └── test_basic_profile_mapping.py
```

**Structure Decision**: Keep immutable generic Profile semantics in a shared
Core module with no filesystem or adapter import. Treat file parsing and Basic
translation as two small concrete adapters because they change for different
reasons. Reuse the existing `SessionPolicy` directly and the existing Basic
construction request at the translation output; do not add a Profile port,
registry, manager, backend factory, or persistence abstraction.

## Implementation Steps

1. **Add RED contract tests for Profile values.** Cover immutability, identity,
   UART/open-line validation, the two mandatory observation invariants, the
   three state-changing permission fields, normalized error categories, and
   direct reuse of `SessionPolicy`.
2. **Implement the generic resolved model.** Add only the immutable values,
   enums, and normalized error categories needed by the contract. Reuse
   feature-003 counter validation and `SessionPolicy` rather than duplicating
   durable limits.
3. **Add RED Profile v1 happy-path tests and loader.** Exercise and implement
   only a valid document whose policy fields are explicitly safe and whose six
   persistence values construct the existing `SessionPolicy` directly.
4. **Add RED safe-default and unsupported-behavior tests, then implement them.**
   Own omitted policy defaults here, together with rejection of RX/recording
   false and all recognized TX/Control/reconnect/reacquire requests.
5. **Add RED persistence-hardening tests, then implement them.** Normalize
   missing, wrong-type, boolean-as-integer, signed-64-bit, and cross-limit-invalid
   persistence inputs while continuing to construct `SessionPolicy` directly;
   do not reimplement the valid path from step 3.
6. **Add RED bounded/strict failure tests, then implement them.** Enforce the
   65,536-byte ceiling against captured bytes before parsing, cover normalized
   filesystem and syntax failures, and apply the deterministic failure matrix.
7. **Add RED Basic translation tests.** Prove field-for-field conversion across
   every supported UART/line combination and demonstrate that translation does
   not construct/open a serial handle.
8. **Implement the Basic adapter-side translator.** Convert generic resolved
   values into the existing `BasicSerialOpenRequest`; reject non-Basic input
   defensively; keep pySerial and Basic types out of `profile.py`.
9. **Harden architecture and regression coverage.** Extend Import Linter to
   cover the shared Profile module, preserve the serial banned-import boundary,
   run all feature-001/002/003 regressions, and confirm hardware guards remain
   fail-closed.
10. **Validate and reconcile documentation.** Run the quickstart and full gate,
   review for deferred-feature leakage and unknown-field acceptance, then update
   development status/history only after implementation is actually complete.

## Architectural Invariants

- The Profile is human-authored and explicitly selected; no device or Profile
  discovery supplies policy.
- A resolved Profile is immutable and contains no parser, file, adapter,
  pySerial, SQLite, connection, or lifecycle object.
- Backend selection is not a runtime capability claim; policy is not a semantic
  role; DTR/RTS open intent is not Control.
- Shared Core never imports adapters. TOML and Basic translation remain adapter
  concerns.
- Basic translation is a pure value conversion into the existing feature-002
  request and has no hardware seam.
- Profile persistence limits are exactly the existing feature-003
  `SessionPolicy`; no duplicate quota model or default is introduced.
- Profile v1 is at most 65,536 serialized bytes. Resolution checks the bytes
  actually captured by a read capped at 65,537 bytes before TOML parsing;
  filesystem metadata is never the authoritative size check.
- Format version 1 is strict and closed. Unknown or unsupported configuration
  fails before a resolved Profile exists.
- RX and recording being true are mandatory current observation invariants.
  TX, Control, and automatic reconnect being false are fail-closed permissions.
  No unsupported request is accepted as inert.
- Resolution does not choose a journal path, create a session, start
  acquisition, or own an active Profile.

## Critical Tests and Validation

- Every valid identity, UART, flow-control, line-intent, safe-policy, and
  persistence-limit combination round-trips from Profile document to resolved
  values without coercion.
- A document of exactly 65,536 bytes may parse; 65,537 captured bytes produces
  `input_too_large` before TOML parsing, regardless of filesystem metadata, and
  produces no parser tree or partial result.
- Failures use the fixed matrix: unknown table/key → `unknown_field`; known-field
  wrong type/range/enum/combination → `invalid_value`; well-typed non-Basic
  backend selection → `unsupported_backend`; recognized
  TX/Control/reconnect/reacquire request →
  `unsupported_behavior`; missing/wrong-type/unsupported version →
  `incompatible_version`; explicit filesystem and syntax categories remain
  distinct. Classification never depends on parser/error message text.
- Numeric booleans are never accepted as integers; all persistence values reuse
  signed-64-bit and cross-limit validation.
- Exact feature-002 selector/configuration/line mapping across static RTS and
  driver-managed RTS cases, with no serial construction or open.
- Explicit rejection of RX/recording false, TX true, Control mappings/actions,
  reconnect/topology, line-ending/TX configuration, Enhanced, discovery, and
  fallback selectors.
- Architecture searches and Import Linter prove no adapter import in shared
  Profile/Core code and no new registry/manager/generalized framework.
- Focused Profile unit/contract tests, complete feature-001/002/003 regression,
  Ruff, mypy, Import Linter, full pytest, and `git diff --check`.

## Complexity Tracking

No constitutional violation or complexity exception is required.
