# RP2040 Basic UART test DUT

This is deterministic acceptance infrastructure, not production DUTchMate firmware
or an Enhanced helper. Its governing documents are
[firmware context](../../docs/firmware_context.md) and
[test-DUT context](../docs/test_dut_context.md). Exact bytes are defined in
[protocol v1](protocol.md).

## Fixed target and electrical assumptions

| Item | Required setup |
|---|---|
| Board | Original Raspberry Pi Pico with RP2040 and 2 MiB flash; not Pico W or Pico 2 |
| Zephyr | v4.4.0; exact board target `rpi_pico/rp2040` |
| Peripheral | RP2040 hardware UART0, Zephyr node `uart0`; not PIO or USB CDC |
| Framing | 115200 baud, 8 data bits, no parity, 1 stop bit; no RTS/CTS or XON/XOFF |
| Pico TX | GP0, physical header pin 1, to external USB-UART adapter RX |
| Pico RX | GP1, physical header pin 2, from external USB-UART adapter TX |
| Ground | Pico GND, physical header pin 3, to adapter GND |
| Levels | Adapter must use compatible **3.3 V UART logic**, not 5 V or RS-232 levels |
| Unused signals | Adapter DTR, RTS, CTS and other modem-control signals disconnected; Pico RUN/reset and BOOTSEL unconnected to adapter |
| Power | Pico powered only through its micro-USB connector; adapter separately powered by its own USB connection |
| Power pins | Adapter VCC/5V/3V3 left disconnected; no adapter power connection to Pico VBUS, VSYS or 3V3 |

GP0/GP1 are the upstream board's UART0 pinctrl defaults; no overlay is needed.
The application explicitly configures 115200 8N1 without flow control before any
protocol output. Zephyr console, shell, logging and USB device stacks are disabled.
The Pico USB cable supplies power during operation; firmware exposes no USB serial
endpoint. BOOTSEL's ROM USB mass-storage mode is used only for manual flashing.

These are required setup assumptions, **not measured electrical acceptance**.
Record the actual board, adapter model/serial number, voltage selection, host,
Profile and wiring before later physical work. Disconnected DTR/RTS avoids an
intentional reset connection; it does not prove glitch-free adapter open/close.

Upstream references: [Zephyr Pico board documentation](https://docs.zephyrproject.org/latest/boards/raspberrypi/rpi_pico/doc/index.html)
and [Raspberry Pi Pico pinout](https://datasheets.raspberrypi.com/pico/Pico-R3-A4-Pinout.pdf).
The tested checkout's `boards/raspberrypi/rpi_pico/{board.yml,rpi_pico-common.dtsi}`
and `boards/raspberrypi/common/rpi_pico-pinctrl-common.dtsi` define the selected
target and routing; the moving online documentation is not a build-version pin.

## Build without hardware

Use the existing external Zephyr workspace and its Python environment, west,
CMake, Ninja and Zephyr SDK. No DUTchMate Python dependency or lockfile changes
are needed. From the DUTchMate repository root, with paths adjusted to your local
Zephyr installation:

```sh
source "$HOME/zephyrproject/.venv/bin/activate"
export ZEPHYR_BASE="$HOME/zephyrproject/zephyr"
export ZEPHYR_SDK_INSTALL_DIR="$HOME/zephyr-sdk-1.0.1"
export ZEPHYR_TOOLCHAIN_VARIANT=zephyr
export CCACHE_DIR="$PWD/build/ccache"
fixture="$PWD/hardware/firmware/test_dut/rpi_pico"
west build -p always -b rpi_pico/rp2040 \
  -d "$PWD/build/test-dut-rpi-pico" "$fixture" -- \
  -DPython3_EXECUTABLE="$(command -v python)" \
  -DUSER_CACHE_DIR="$PWD/build/zephyr-cache"
```

Use a v4.4.0 Zephyr checkout with the matching modules from its `west.yml` and
SDK 1.0.1. Do not update another workspace merely to build this target. Outputs
are `build/test-dut-rpi-pico/zephyr/zephyr.{elf,bin,uf2}`. Root `build/` is ignored;
never put generated output into source or host packages. `west build` only builds;
do not invoke `west flash`, debug runners or serial tools in software validation.

Hardware-free protocol checks compile the **actual `src/main.c`** against small
test-only UART/clock/device substitutes and execute it on the host:

```sh
cmake -S "$fixture/tests" -B build/test-dut-rpi-pico-host -G Ninja
cmake --build build/test-dut-rpi-pico-host
ctest --test-dir build/test-dut-rpi-pico-host --output-on-failure
```

These checks cover exact output, framing, partial/malformed/overlong requests,
counter formatting, periodic progress under input and startup failure. They do
not simulate RP2040 registers, UART wiring or real scheduling. The cross build
checks actual Zephyr APIs, target configuration and linkability.

On the validated macOS/Clang host, also check memory and undefined behavior:

```sh
cmake -S "$fixture/tests" -B build/test-dut-rpi-pico-sanitized -G Ninja \
  -DCMAKE_C_FLAGS='-fsanitize=address,undefined -fno-omit-frame-pointer' \
  -DCMAKE_EXE_LINKER_FLAGS='-fsanitize=address,undefined'
cmake --build build/test-dut-rpi-pico-sanitized
ctest --test-dir build/test-dut-rpi-pico-sanitized --output-on-failure
```

## Firmware and source identity

The immutable protocol-v1 banner identifies fixture `rpi_pico`, firmware `1.0.0`
and protocol `1`. Firmware version and protocol version are separate: a source
fix may preserve protocol v1. A banner alone cannot identify the exact binary.

For each build retained for later acceptance, capture the Git revision, local
changes, exact source hashes, Zephyr/module revisions and artifact hash:

```sh
git rev-parse HEAD > build/test-dut-rpi-pico/source-revision.txt
git status --porcelain --untracked-files=all -- hardware/firmware/test_dut/rpi_pico \
  > build/test-dut-rpi-pico/source-worktree.txt
shasum -a 256 "$fixture/CMakeLists.txt" "$fixture/prj.conf" \
  "$fixture/src/main.c" "$fixture/protocol.md" "$fixture/README.md" \
  > build/test-dut-rpi-pico/source.sha256
west manifest --resolve > build/test-dut-rpi-pico/west-resolved.yml
for module in zephyr hal_rpi_pico cmsis_6; do
  if test "$module" = zephyr; then
    module_dir="$ZEPHYR_BASE"
  else
    module_dir="$(west list "$module" -f '{abspath}')"
  fi
  git -C "$module_dir" rev-parse HEAD > "build/test-dut-rpi-pico/$module.revision"
  git -C "$module_dir" status --porcelain --untracked-files=all \
    > "build/test-dut-rpi-pico/$module.worktree"
done
shasum -a 256 build/test-dut-rpi-pico/zephyr/zephyr.uf2 \
  > build/test-dut-rpi-pico/firmware.sha256
```

Retain these records with the observed banner and tool versions. A revision with
dirty/untracked fixture files is **not** an exact source identity without their
hashes/content. Do not embed a changing repository hash in this README or infer
that a flashed image matches the source solely from its banner.

The resolved manifest records declared module revisions; the separate revision/
worktree files record the actual Zephyr, RP2040 HAL and CMSIS-6 sources used.
Require those worktrees to be clean and module revisions to match the manifest.
Keep the generated `.config`, `zephyr.dts` and `build_info.yml` with the record.
A whole-workspace `west manifest --freeze` requires every unrelated project to
be cloned; this fixture does not require fetching those projects to record its
build inputs.

## Later manual flashing and wiring (not executed by the build)

Only perform these steps during a separately authorized hardware activity:

1. Identify the original Pico/RP2040 board and the intended USB-UART adapter.
   Confirm 3.3 V signal compatibility and the wiring/power assumptions above.
   Stop any owner of the adapter port. Leave the adapter disconnected from the
   Pico while flashing; do not use its DTR/RTS to enter boot mode.
2. Disconnect Pico power. Hold its BOOTSEL button, connect its micro-USB cable
   to the host, then release BOOTSEL. Identify **that board's** `RPI-RP2` volume;
   do not copy to an arbitrary mounted volume.
3. Copy the recorded `build/test-dut-rpi-pico/zephyr/zephyr.uf2` to that volume
   using Finder. The ROM loader writes flash and restarts the board. This is a
   manual flash/power transition, not a DUTchMate operation.
4. Disconnect both Pico and adapter USB power before wiring. Connect GP0/pin 1
   to adapter RX, GP1/pin 2 to adapter TX, and GND/pin 3 to adapter GND. Leave
   adapter VCC, DTR, RTS and CTS disconnected, together with Pico RUN/reset.
   Verify the wiring before power.
5. Power the Pico through micro-USB and the adapter through its USB connection.
   Independently verify protocol v1 with suitable UART equipment before using
   it to judge DUTchMate. The banner occurs once on startup and is not replayed
   when a host opens the adapter; periodic ticks remain available afterward.
   Capturing startup may require an already-running independent receiver.
6. Close the independent receiver before DUTchMate owns the adapter. Identify its
   exact macOS device path and human-owned Profile. Begin DUTchMate acceptance
   observation-only; request explicit approval for the exact benign TX payload
   before any Interact. Do not infer DUT receipt from backend acknowledgement.

No reset automation, Control, reconnect behavior or host acceptance is supplied
by this fixture. Safe-open DTR/RTS transitions, actual voltage/pin state, UART
accuracy/loss, hardware timing and DUTchMate physical integration remain unproven
until separately measured. Power/restart resets the tick counter; host attach,
detach or request traffic does not intentionally reset it.
