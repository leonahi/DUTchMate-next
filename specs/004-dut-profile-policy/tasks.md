# Tasks: Observation-Only DUT Profile and Policy

**Input**: Design documents from `/specs/004-dut-profile-policy/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`,
`contracts/dut-profile-v1.md`, `quickstart.md`

**Tests**: This feature creates a human-owned safety/configuration boundary and
a versioned serialized format. Every behavioral group follows RED/GREEN TDD;
confirm each RED failure is caused by the intentionally missing feature-004
contract before production behavior is added.

**Organization**: T001 establishes the narrow source/test boundary. User-story
phases then deliver valid Profile resolution, observation invariants and
permission/persistence hardening, and fail-closed bounded compatibility plus
Basic translation. No task authorizes physical hardware access.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel because it changes different files and has no
  dependency on another incomplete task in the same group
- **[US1]**, **[US2]**, **[US3]**: Maps the task to the specification user story
- Every task names its expected files

## Phase 1: Profile Boundary Setup

**Purpose**: Establish only the module/test locations and baseline guards needed
for TDD; add no Profile resolution behavior.

- [x] T001 Create skeletons for
  `core/src/dutchmate_core/profile.py`,
  `core/src/dutchmate_core/adapters/toml_profile.py`,
  `core/src/dutchmate_core/adapters/basic_profile.py`,
  `core/tests/unit/test_profile_model.py`,
  `core/tests/contract/test_toml_profile.py`, and
  `core/tests/contract/test_basic_profile_mapping.py`; record the pre-feature
  focused/full regression baseline, retain the default physical-serial
  sentinel in `core/tests/conftest.py`, and add no runtime dependency or
  production behavior.

**Checkpoint**: The files exist, prior features remain green, and no Profile
behavior has been implemented.

---

## Phase 2: User Story 1 - Resolve an explicit observation profile (Priority: P1) 🎯 MVP

**Goal**: Resolve one explicit Profile into immutable identity, Basic selection,
UART/open-line, safe explicit policy, and session-policy values without any
hardware or lifecycle side effect.

**Independent Test**: Resolve a valid Profile from a pytest temporary file,
assert every exact value and snapshot immutability, edit the source and resolve
again, and prove the serial/acquisition/journal sentinels remain untouched.

### RED tests for User Story 1

- [x] T002 [US1] Add RED immutable-model tests in
  `core/tests/unit/test_profile_model.py` for `ProfileFormatVersion(1)`,
  non-empty/non-whitespace `DutIdentity.id` and `.name`, exact
  `ProfileBackendSelection(kind="basic_serial", expected_device=...)`,
  `ProfileUartConfiguration` with `baud_rate > 0`, `data_bits` in
  `{5,6,7,8}`, `parity` in `{none,even,odd}`, `stop_bits` in `{1,2}`, mutually
  exclusive hardware/software flow control, and
  `ProfileSerialOpenLineIntent` with DTR static and RTS driver-managed exactly
  when hardware flow control is true, plus one explicitly safe immutable
  `ObservationPolicy` whose RX/recording fields are mandatory observation
  invariants and whose TX/Control/reconnect fields are state-changing
  permissions; confirm RED is caused by missing feature-004 values.
- [x] T003 [US1] Implement only the T002 immutable generic values, including the
  explicitly safe `ObservationPolicy`, and
  `ResolvedDutProfile` composition in `core/src/dutchmate_core/profile.py`,
  reusing the existing `core/src/dutchmate_core/model.py::SessionPolicy` and
  importing no adapter, filesystem, TOML, Basic, or pySerial type.
- [x] T004 [US1] Add RED valid-resolution contract tests in
  `core/tests/contract/test_toml_profile.py` for the exact
  `contracts/dut-profile-v1.md` tables/types, one explicit caller path, one
  immutable read snapshot, later-source-edit isolation, exact identity/backend/
  UART/open-line values, all five policy fields explicitly set to their safe
  values, six valid explicit persistence integers producing the existing
  `SessionPolicy`, and zero device enumeration/open, acquisition, journal, or
  session side effects. Do not test omitted policy fields or invalid input here.
- [x] T005 [US1] Implement the minimum valid version-1 TOML read/parse/resolve
  path in `core/src/dutchmate_core/adapters/toml_profile.py` using only the
  standard library; support only the T004 happy path, including explicitly safe
  policy values and direct construction of a valid existing `SessionPolicy`;
  return `ResolvedDutProfile`, retain no file/parser state, perform no path
  search, and make T002–T004 GREEN without implementing omitted policy defaults,
  opposite/state-changing rejection, invalid persistence hardening, the input
  byte ceiling, or generalized loading/configuration abstractions.
- [x] T006 [US1] Run the focused US1 tests, targeted Ruff/mypy, Import Linter,
  the feature-001/002/003 smoke regressions, and `git diff --check`; record exact
  RED/GREEN results and confirm no physical serial access before starting safe
  policy hardening.

**Checkpoint**: One explicitly selected valid observation-only Profile resolves
to an immutable generic snapshot; unsupported/failure completeness is not yet
claimed beyond the paths covered by US1.

---

## Phase 3: User Story 2 - Safe policy and persistence bounds (Priority: P2)

**Goal**: Apply the mandatory observation invariants and safe permission
defaults, reject opposite/state-changing values, and harden all six durable
`SessionPolicy` inputs exactly.

**Independent Test**: Resolve omitted and explicitly safe policy fields plus
boundary persistence values; verify RX/recording true, TX/Control/reconnect
false, exact `SessionPolicy`, and explicit no-result failures for every unsafe
or invalid variant.

### RED tests for User Story 2

- [x] T007 [US2] Add RED policy tests in
  `core/tests/unit/test_profile_model.py` and
  `core/tests/contract/test_toml_profile.py` for `ObservationPolicy` omitted
  defaults (`uart_rx_enabled=true`, `evidence_recording_enabled=true`,
  `uart_tx_enabled=false`, `semantic_control_enabled=false`,
  `automatic_reconnect_enabled=false`), rejection of RX/recording false and
  TX/Control/reconnect true as
  `unsupported_behavior`, and rejection of TX line endings, control mappings/
  sequences/safe states, reconnect topology/matching/retry, and automatic
  reacquire fields as `unsupported_behavior` rather than silent ignore; treat
  the first two fields as mandatory current invariants and the last three as
  fail-closed permissions, without adding runtime behavior.
- [x] T008 [US2] Add RED durable-policy tests in
  `core/tests/contract/test_toml_profile.py` for all six required positive
  signed-64-bit integers, missing values, wrong scalar types,
  boolean-not-integer validation,
  `max_record_charged_bytes` fitting both retained and retrieval byte ceilings,
  independent retention/retrieval limits, exact `max_database_pages`, and
  equality with the existing feature-003 `SessionPolicy` without defaults,
  conversion, rounding, or SQLite adapter/PRAGMA exposure; require
  `missing_field` for absent persistence keys and `invalid_value` for every
  wrong-type, out-of-range, or cross-limit-invalid known value.

### Implementation for User Story 2

- [x] T009 [US2] Implement only the omitted safe policy defaults and
  `unsupported_behavior` rejection required by T007 in
  `core/src/dutchmate_core/profile.py` and
  `core/src/dutchmate_core/adapters/toml_profile.py`, extending rather than
  recreating the `ObservationPolicy` type defined by T003; own RX/recording
  false and recognized
  TX/Control/reconnect/reacquire configuration here, and do not add TX, Control,
  reconnect, role, capability, or runtime-policy execution.
- [x] T010 [US2] Harden only persistence-input validation and Profile-level
  error normalization in `core/src/dutchmate_core/adapters/toml_profile.py` for
  missing values, wrong scalar types, boolean-as-integer values, signed-64-bit/
  positive bounds, and cross-limit-invalid combinations. Continue constructing
  the existing `SessionPolicy` directly as T005 already does on the valid path;
  map absent keys to `missing_field` and all other listed known-field failures to
  `invalid_value`, and add no duplicate quota model or numerical defaults.
- [x] T011 [US2] Run the focused US2 tests plus all feature-003 model/journal
  policy regressions, targeted static/architecture checks, and
  `git diff --check`; record exact results and confirm retention capacity and
  retrieval ceilings remain independent.

**Checkpoint**: Resolved Profiles are safely observation-only and carry one
exact existing durable session policy; no runtime operation consumes them yet.

---

## Phase 4: User Story 3 - Fail closed and translate at the Basic boundary (Priority: P3)

**Goal**: Complete strict Profile v1 compatibility/failure behavior and prove
side-effect-free exact translation into the existing Basic construction request.

**Independent Test**: Run the complete invalid-input matrix and every supported
UART/open-line mapping; receive stable Profile failures or the exact existing
Basic request with no raw exception, ignored field, device construction/open,
or shared-Core adapter dependency.

### RED tests for User Story 3

- [x] T012 [US3] Add RED failure/compatibility tests in
  `core/tests/contract/test_toml_profile.py` for missing/non-regular/unreadable
  sources; an exactly 65,536-byte valid capture and a 65,537-byte capture that
  returns `input_too_large` before TOML parsing based on bytes actually read,
  without trusting filesystem metadata or producing a parser tree/partial
  result; invalid UTF-8/TOML and duplicate keys; missing/wrong-type/unsupported
  `profile_version`; missing required tables/fields; unknown root/nested keys;
  unsupported enum values; whitespace identity/name; unsupported backend
  including Enhanced; feature-002-invalid exact device selectors; invalid
  UART/open-line combinations; optional inert diagnostics; no raw
  `OSError`/parser exception; and no side effects. Assert the fixed categories:
  unknown table/key → `unknown_field`; known-field wrong scalar type, invalid
  range, unsupported enum, or inconsistent combination → `invalid_value`;
  well-typed non-Basic backend selection → `unsupported_backend`; recognized
  unsupported TX/Control/reconnect/reacquire configuration →
  `unsupported_behavior`;
  missing/wrong-type/unsupported version → `incompatible_version`; preserve
  `missing_file`, `not_a_file`, `unreadable`, `input_too_large`,
  `invalid_syntax`, and `missing_field`; never classify from parser/error
  message text.
- [x] T013 [P] [US3] Add RED field-for-field Basic translation tests in
  `core/tests/contract/test_basic_profile_mapping.py` across data bits, parity,
  stop bits, flow-control, static RTS, and driver-managed RTS combinations;
  assert exact `SerialDeviceSelector`, `SerialConfiguration`,
  `SerialOpenLineIntent`, and `BasicSerialOpenRequest`, defensive non-Basic
  rejection, and zero `serial.Serial` construction/open/enumeration.

### Implementation for User Story 3

- [x] T014 [US3] Implement the closed-schema validator and normalized
  `ProfileFailure` behavior required by T012 in
  `core/src/dutchmate_core/profile.py` and
  `core/src/dutchmate_core/adapters/toml_profile.py`; cap the read at 65,537
  bytes and reject a captured length above the 65,536-byte Profile-v1 ceiling
  before UTF-8/TOML parsing, using metadata only as a non-authoritative hint;
  support only format version 1, classify by schema condition rather than
  message text, extend the T005/T009/T010 paths without reimplementing them, and
  add no migration, repair, unknown-field preservation, overlay, environment
  expansion, watcher, cache, or writer.
- [x] T015 [US3] Implement the pure adapter-side conversion required by T013 in
  `core/src/dutchmate_core/adapters/basic_profile.py`, reusing existing
  feature-002 request values and neither importing pySerial directly nor
  constructing `BasicSerialBackend`/hardware.
- [x] T016 [US3] Export only the intentional generic and adapter-facing symbols
  from `core/src/dutchmate_core/__init__.py` and
  `core/src/dutchmate_core/adapters/__init__.py`; extend the Import Linter
  contracts in `pyproject.toml` so `dutchmate_core.profile` cannot import
  adapters, then run focused US3 tests, Ruff, mypy, Import Linter, and
  `git diff --check`.

**Checkpoint**: All three user stories are independently testable; Profile v1
is strict, side-effect-free, backend-neutral in shared Core, and exactly
translatable at the Basic adapter boundary.

---

## Phase 5: Scope Review and Completion

**Purpose**: Verify all prior contracts remain intact, exclude deferred behavior,
and reconcile project status only after implementation is actually complete.

- [x] T017 Run every command in
  `specs/004-dut-profile-policy/quickstart.md`, including complete
  feature-001/002/003 regressions, and confirm the fail-closed serial guard
  prevents physical hardware access.
- [x] T018 Review the complete feature-004 diff and focused `rg` matches for
  Basic/pySerial leakage into `core/src/dutchmate_core/profile.py`, capability/
  policy/role conflation, ignored unknown or unsafe fields, implicit numerical
  defaults, serial/Profile discovery, backend/Profile registries or managers,
  generalized configuration frameworks, lifecycle/session/service/CLI/workflow/
  TX/Control/reconnect/handoff/Enhanced/MCP leakage, and accidental physical
  access; correct only genuine feature-004 defects with RED/GREEN coverage.
- [x] T019 Update `docs/development_status.md` and prepend
  `docs/development_history.md` only after implementation is complete, recording
  the exact Profile format/version, observation-only policy, software validation,
  deferred runtime behavior, and absence of physical-hardware validation;
  preserve the committed feature-003 baseline history.
- [x] T020 Evaluate the Graphify structural-change criteria in
  `docs/agent_tooling.md`; because this plan adds a shared Profile module and two
  adapter modules, run one code-only incremental update near completion unless
  the implemented structure materially differs, and keep generated output
  ignored.
- [x] T021 Use `verification-before-completion` and run
  `uv run --frozen ruff check .`, `uv run --frozen mypy .`,
  `uv run --frozen lint-imports`, `uv run --frozen pytest`, and
  `git diff --check`; report exact pass/skip/fail counts, validation not run,
  unresolved limitations, and that no physical hardware was accessed.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (T001)**: Starts immediately and changes no behavior.
- **US1 (T002–T006)**: Depends on T001 and supplies the generic resolved model
  and valid TOML resolution used by later stories.
- **US2 (T007–T011)**: Depends on US1 because safe policy and durable limits are
  fields of the resolved Profile.
- **US3 (T012–T016)**: Depends on US1 and US2 for the complete valid model;
  failure hardening and Basic mapping touch separate adapters where marked.
- **Completion (T017–T021)**: Depends on all user stories.

### Within Each Behavioral Group

- Add the specified RED tests and observe the intended failure before production
  changes.
- Implement only the active task behavior; do not pre-implement later tasks.
- Run the focused GREEN selection before broadening validation.
- Do not weaken feature-001/002/003 assertions, architecture contracts, or the
  default hardware fail-closed guard.

### Parallel Opportunities

- T013 Basic mapping tests can be authored in parallel with T012 because they
  touch a separate test module after the resolved model is established.
- Research/design artifacts are complete; no implementation task needs a new
  framework or dependency investigation.
- Production edits to `profile.py` and `toml_profile.py` remain serialized
  within their RED/GREEN groups to keep error and schema behavior coherent.

## Parallel Example: User Story 3

```text
Task T012: strict TOML failure/compatibility contract tests
Task T013: exact Basic adapter-boundary translation contract tests
```

The two test tasks use different files and can proceed together after T011.
T014 and T015 then implement only their respective RED contracts.

## Implementation Strategy

### First implementation group: T001–T006

1. Create only the narrow modules/tests and capture a green pre-feature baseline.
2. RED-test the immutable generic identity/backend/UART/open-line model.
3. Implement those values without adapter/filesystem imports.
4. RED-test one complete valid TOML Profile with explicitly safe policy values,
   valid direct `SessionPolicy` construction, snapshot isolation, and zero side
   effects.
5. Implement only that valid version-1 resolution path.
6. Run focused GREEN/static checks and prior-feature smoke regressions, then stop
   before safe-policy failure hardening in T007.

### Incremental delivery

1. T001–T006: valid immutable Profile resolution MVP.
2. T007–T011: observation invariants, permission defaults/rejections, and
   strict durable-policy input hardening.
3. T012–T016: bounded strict compatibility/failures and Basic boundary
   translation.
4. T017–T021: quickstart, scope review, docs/Graphify, and final gate.

## Notes

- Every Profile test uses local temporary files and software fakes/sentinels.
- No task authorizes opening, enumerating, resetting, flashing, or otherwise
  interacting with physical hardware.
- A skipped hardware case is not a pass; this feature defines no hardware case.
- The TOML example values are syntax examples, not product defaults.
- Do not commit, push, or start the next Phase 1 slice as part of these tasks.
