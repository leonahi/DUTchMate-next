# Firmware Context

## 1. Purpose

This document defines the repository-level boundaries and engineering rules for embedded
firmware maintained as part of the DUTchMate project.

It applies to firmware-specific organization and implementation decisions where the
project-wide DUTchMate Core does not already define the behavior.

The governing DUTchMate architecture and product invariants remain in
`docs/project_context_core.md`.

This document must not duplicate or weaken those rules.

---

## 2. Authority

When documents overlap, authority narrows in this order:

1. `docs/project_context_core.md` — DUTchMate product invariants.
2. `hardware/firmware/docs/firmware_context.md` — firmware-domain rules.
3. role-specific context such as `test_dut_context.md`.
4. target-specific README and protocol documentation.

A narrower document may specialize its parent context but must not contradict it.

---

## 3. Firmware Roles

DUTchMate maintains two distinct firmware classes.

### 3.1 Test-DUT Firmware

Firmware under:

`hardware/firmware/test_dut/`

is deterministic test and acceptance infrastructure.

Its purpose is to provide controlled physical DUT behavior so that DUTchMate host
software and hardware interfaces can be tested against a known endpoint.

Test-DUT firmware:

- is not part of the DUTchMate production runtime;
- does not define DUTchMate product behavior;
- may be deliberately changed to expose specific deterministic acceptance scenarios;
- should remain small, explicit and independently understandable;
- must not become a dependency of production DUTchMate behavior.

Additional rules are defined in:

`hardware/firmware/test_dut/docs/test_dut_context.md`.

### 3.2 Enhanced Firmware

Firmware under:

`hardware/firmware/enhanced/`

is reserved for DUTchMate Enhanced helper firmware. When implemented, that firmware
is production DUTchMate firmware rather than test infrastructure.

It may eventually provide capabilities such as UART transport, buffering, timestamps,
control outputs, event inputs and other explicitly designed Enhanced-backend functions.

Enhanced behavior must be defined by its own product contracts and implementation work.
Test-DUT behavior must not be treated as an Enhanced protocol or implementation
requirement.

---

## 4. Architectural Separation

Test-DUT and Enhanced firmware have different responsibilities and must remain
architecturally separate.

The fact that both may use Zephyr, similar boards or similar peripheral drivers does not
by itself justify shared application abstractions.

Do not introduce shared firmware frameworks merely to remove small amounts of
duplication.

Shared code should be introduced only when:

1. at least two concrete consumers exist;
2. the behavior is genuinely identical;
3. the abstraction does not couple test infrastructure to production behavior; and
4. the resulting dependency direction remains clear.

Test-DUT protocols and Enhanced DUTchMate protocols are independent unless an explicit
future design establishes otherwise.

---

## 5. Relationship to Host DUTchMate

Firmware must not duplicate responsibilities already owned by the DUTchMate host.

In particular, firmware-specific implementation must not silently redefine:

- evidence semantics;
- Profile policy;
- host-side ownership;
- authentication;
- service or CLI behavior;
- persistence semantics;
- backend-neutral Core contracts.

Host-visible behavior that becomes part of a production interface must be specified
through the appropriate DUTchMate design process rather than being established
implicitly by firmware implementation.

---

## 6. Hardware Assumptions

Every firmware target must document the hardware assumptions required to reproduce its
behavior.

At minimum, target documentation should identify when applicable:

- board and MCU;
- Zephyr board target;
- firmware version or build identity;
- UART instance;
- UART TX/RX pins;
- baud rate and framing;
- I/O voltage assumptions;
- common-ground requirement;
- DUT or helper power source;
- reset and boot behavior;
- DTR/RTS/CTS connections;
- flashing/debug interface;
- external hardware dependencies.

Unknown electrical or wiring assumptions must remain explicitly unknown rather than
being inferred.

---

## 7. Reproducibility

Firmware used for DUTchMate development or acceptance should be reproducible from the
repository.

Target documentation must define how a build is identified and reproduced.

It should provide enough information to determine:

- supported board target;
- build configuration;
- build command;
- flash procedure;
- observable firmware identity.

The target documentation should describe the source-identification mechanism rather
than embedding a changing repository revision as target documentation.

Each physical acceptance record should capture the actual source revision used together
with the observable firmware and protocol identity.

---

## 8. Generated Build Artifacts

Generated firmware build outputs are not source.

Zephyr build directories and generated binaries, maps, intermediate files and tooling
artifacts must remain ignored unless a separately defined release process explicitly
publishes a particular artifact.

Generated firmware artifacts must not enter DUTchMate host wheel or sdist packages.

---

## 9. Observable Protocols

Externally observable firmware protocols must be explicitly documented.

Protocol documentation should define byte-level behavior where practical, including:

- exact requests;
- exact responses;
- framing;
- line endings;
- binary payloads;
- intentional silence;
- asynchronous output;
- version identification.

Do not depend on undocumented shell behavior, terminal interpretation or implementation
details.

---

## 10. Hardware Acceptance

Software tests and physical hardware acceptance are separate evidence.

A successful firmware build does not establish physical UART, electrical, timing,
driver or DUTchMate integration behavior.

Likewise, a DUTchMate acceptance failure must not automatically be attributed to
DUTchMate if the firmware fixture or physical setup has not first been independently
validated.

Physical acceptance should record the exact:

- firmware;
- board;
- wiring;
- adapter;
- host;
- Profile;
- test procedure.

---

## 11. Change Discipline

Firmware changes should remain scoped to the behavior currently being implemented or
validated.

Avoid speculative support for future:

- Enhanced capabilities;
- Control operations;
- reconnect behavior;
- reset automation;
- generic command frameworks;
- protocol extensibility;
- hardware variants.

Introduce those capabilities only when their corresponding DUTchMate work is explicitly
scoped.

---

## 12. Documentation Ownership

Use the narrowest appropriate document.

- `docs/project_context_core.md`
  - product-wide DUTchMate invariants.

- `hardware/firmware/docs/firmware_context.md`
  - rules shared across firmware classes.

- `hardware/firmware/test_dut/docs/test_dut_context.md`
  - rules applying to all test-DUT fixtures.

- target `README.md`
  - board, build, flash, wiring and target-specific operation.

- target protocol document
  - exact externally observable byte-level behavior.

Do not turn a target README or the Core document into a competing architecture document.
