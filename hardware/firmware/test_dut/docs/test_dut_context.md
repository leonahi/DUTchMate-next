# Test-DUT Firmware Context

## 1. Purpose

Test-DUT firmware provides deterministic physical DUT behavior for DUTchMate development
and acceptance.

A test DUT exists to make the behavior on the far side of a DUTchMate transport known
and reproducible.

It allows DUTchMate behavior to be validated without depending on unknown or
application-specific DUT firmware.

Test-DUT firmware is test infrastructure and is not part of DUTchMate production
behavior.

---

## 2. Design Principle

A test DUT should be simpler than the system being tested.

Prefer:

- fixed behavior;
- explicit byte sequences;
- bounded state;
- deterministic responses;
- easily observable execution.

Avoid:

- general-purpose shells;
- dynamic command registration;
- scripting engines;
- complex configuration;
- unnecessary persistence;
- generic protocol frameworks;
- behavior unrelated to the current acceptance requirement.

Complex test firmware makes failures harder to attribute.

---

## 3. Deterministic Behavior

Externally visible behavior must be documented precisely enough that an acceptance test
can distinguish:

- expected DUT output;
- expected DUT response;
- intentional silence;
- DUT reset/restart;
- unexpected output.

Where practical, protocols should be defined in exact bytes rather than terminal-level
or textual assumptions.

Line endings must be explicit.

For example, a protocol should specify:

`PING\r\n`

rather than merely stating that the DUT accepts a `PING` command.

---

## 4. Firmware and Protocol Identity

Every test-DUT target must expose an observable firmware/protocol identity.

The identity should allow acceptance evidence to establish which DUT behavior was under
test.

At minimum, the target documentation must define:

- firmware fixture name;
- protocol version;
- board target;
- source-identification mechanism.

Each physical acceptance record must capture the actual source revision used.

A boot banner is preferred when the tested transport permits it.

Firmware implementation version and protocol version should remain conceptually
separate when they can change independently.

---

## 5. UART Fixtures

When validating DUTchMate's Basic external USB-UART path, the test DUT must use a
hardware UART connected to the external USB-UART adapter.

Do not substitute RP2040 USB CDC or another native USB serial implementation for the
Basic UART acceptance path.

The target documentation must explicitly identify:

- UART peripheral;
- TX pin;
- RX pin;
- baud rate;
- data bits;
- parity;
- stop bits;
- flow-control use;
- signal voltage assumptions;
- common-ground requirement.

The initial Basic reference fixture must not require hardware flow control.

DTR, RTS and CTS must remain disconnected unless a specific acceptance activity
explicitly scopes and documents their use.

---

## 6. Additional Serial Signals

DTR, RTS, CTS and similar signals must not have undocumented effects.

If they are unused, target documentation should state that they are not connected.

If a future acceptance activity connects one of these signals to reset, boot or another
DUT function, that relationship must be explicitly documented before the test.

Opening a serial port must not be assumed electrically harmless without evidence.

---

## 7. Boot Behavior

Boot behavior must be deterministic and documented.

If the DUT emits a boot banner, its exact bytes should be defined by the target protocol.

Unexpected reset or boot output during an acceptance activity should be treated as an
observable event rather than silently ignored.

---

## 8. Asynchronous Output

A fixture may generate periodic or asynchronous UART output when required to test
continuous observation.

Such output should:

- be deterministic in format;
- use bounded records;
- contain an observable sequence or counter when useful;
- avoid excessive rates that turn the fixture into a stress test unless stress behavior
  is explicitly being tested.

Exact host-level scheduling or inter-byte timing should not be promised unless the
specific acceptance requirement depends on it.

---

## 9. Request/Response Behavior

Commands should use exact, documented byte sequences.

The initial Basic UART fixture should provide only the minimum behavior needed for
acceptance, including:

1. a deterministic benign request that produces a deterministic response;
2. a request that intentionally produces no response, allowing bounded timeout behavior
   to be tested.

Additional commands should be introduced only when required by a specific acceptance
activity.

---

## 10. TX Acknowledgement Versus DUT Observation

The test DUT must not be used to collapse distinct DUTchMate evidence semantics.

A DUTchMate backend write acknowledgement establishes only that the backend accepted the
write according to its contract.

It does not itself prove:

- electrical UART transmission;
- exact bytes on the wire;
- DUT reception;
- DUT processing.

A DUT response received through the authoritative RX path is independent evidence.

Test-DUT protocols should make that distinction easy to observe.

---

## 11. Failure Attribution

The test fixture should be independently validated before it is used to draw conclusions
about DUTchMate.

The recommended sequence is:

1. build the firmware;
2. flash the target;
3. independently verify the documented UART behavior;
4. record the firmware/protocol identity;
5. run DUTchMate acceptance.

If the fixture does not behave according to its documented protocol, stop DUTchMate
acceptance and resolve the fixture first.

Do not modify DUTchMate production code merely to accommodate an unexplained fixture
failure.

---

## 12. Fixture Evolution

Changes to test-DUT firmware should be tied to concrete acceptance requirements.

When adding behavior:

- state which DUTchMate capability requires it;
- keep existing protocol behavior stable where practical;
- version externally incompatible protocol changes;
- avoid adding unrelated future commands;
- update the target protocol documentation together with implementation.

Do not turn the test DUT into a general embedded demonstration application.

---

## 13. Relationship to Enhanced Firmware

Test-DUT firmware and Enhanced DUTchMate firmware may use similar MCUs, Zephyr APIs or
peripherals, but they represent opposite sides of the system boundary.

The test DUT behaves as the device being observed or controlled.

The Enhanced helper is part of DUTchMate and performs transport, observation and control
functions on behalf of the host.

Do not share protocols, state machines or abstractions between these roles merely
because their implementation technologies are similar.

Any genuine shared component should be justified independently.

---

## 14. Initial RP2040 Reference DUT

The first planned test-DUT fixture is:

`hardware/firmware/test_dut/rpi_pico/`

Its initial purpose is to support identified-DUT acceptance of the Basic external
USB-UART backend.

The initial fixture is expected to provide:

- a fixed firmware/protocol boot banner;
- deterministic periodic UART output;
- one harmless deterministic request/response;
- one intentional no-response request.

Board-specific UART selection, pins, wiring, build commands, flashing procedure and
exact protocol bytes belong in the target's own README and protocol documentation.

Those details are not defined by this context document.
