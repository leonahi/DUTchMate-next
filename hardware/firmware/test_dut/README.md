# Test-DUT Firmware

This directory contains deterministic DUT firmware used to validate DUTchMate against
controlled physical devices.

Test-DUT firmware is acceptance infrastructure. It is not production DUTchMate firmware.

The governing rules for test-DUT fixtures are defined in:

`docs/test_dut_context.md`

Each target should contain its own documentation describing:

- hardware;
- supported Zephyr board target;
- wiring;
- voltage assumptions;
- build and flash procedure;
- firmware identity;
- externally observable protocol.

Current targets:

- `rpi_pico/` — RP2040-based UART reference DUT for Basic external USB-UART acceptance.

Future test-DUT targets may be added when a specific acceptance requirement justifies
them.

Do not place Enhanced DUTchMate helper firmware in this hierarchy. Production Enhanced
firmware belongs under:

`hardware/firmware/enhanced/`
