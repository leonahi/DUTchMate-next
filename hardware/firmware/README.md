# DUTchMate Firmware

This directory contains embedded firmware associated with DUTchMate.

Firmware in this repository has two fundamentally different roles:

- `test_dut/` — deterministic test and acceptance firmware used to exercise DUTchMate
  against controlled physical DUT behavior.
- `enhanced/` — production firmware for the future DUTchMate Enhanced hardware helper.

These roles are intentionally separate.

Test-DUT firmware is test infrastructure and is not part of the DUTchMate production runtime. Enhanced firmware, when implemented, will be part of DUTchMate itself.

The common firmware-domain rules are documented in:

- `docs/firmware_context.md`

Test-DUT-specific rules are documented in:

- `test_dut/docs/test_dut_context.md`

Target-specific hardware assumptions, wiring, build instructions and protocols belong
with the corresponding firmware target rather than in the common context documents.

The governing DUTchMate product invariants remain in `docs/project_context_core.md`.
Firmware documentation supplements those rules; it does not redefine them.
