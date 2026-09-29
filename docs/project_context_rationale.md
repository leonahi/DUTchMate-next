# DUTchMate — Project Context (Rationale)

> **Purpose:** explains *why* the rules in `project_context_core.md` exist, with examples and diagrams.
>
> This document is explanatory, not normative. It adds no requirements. If anything here seems to conflict with the core document, the core document wins. Section references such as "Core §7.1" point to the core document.

---

## 1. The Problem

UART remains one of the most common interfaces in embedded firmware development. Firmware emits boot messages, debug logs, assertions, fault information, runtime state, test progress, telemetry, shell prompts, command responses, and crash diagnostics. Many applications also expose a bidirectional UART interface: a Zephyr shell, an application CLI, diagnostic or manufacturing commands, AT-style commands, bootloader consoles, or binary management protocols.

A human developer typically works like this:

```text
build firmware
    -> flash DUT using an external tool
    -> observe UART
    -> reset or otherwise stimulate the DUT
    -> inspect boot/runtime output
    -> type a diagnostic command
    -> inspect the response
    -> modify firmware
    -> repeat
```

Coding agents can edit source, and often build and flash, but direct access to a physical DUT raises questions that a raw `/dev/ttyUSB0` or `pyserial` object doesn't answer:

- Who owns the serial port, and who keeps reading when no command is running?
- What happens to spontaneous logs between commands?
- How are TX and RX ordered, and where does a command-response window begin and end?
- What if the DUT never responds, resets, disconnects, or an adapter buffer overflows?
- What evidence existed before a failure, and who records what was transmitted?
- How are reset and boot signals controlled safely?
- How does an external flash tool temporarily take the same port?
- How does an agent avoid writing timing-sensitive polling loops itself?

DUTchMate answers these by putting physical ownership, continuous acquisition, bounded workflows, hardware control, evidence recording, and provenance behind one deterministic service boundary.

The evidence model exists so that, afterward, someone can answer: what did the DUT emit, what did DUTchMate transmit, what hardware action occurred, when did the connection change, was there a period DUTchMate didn't observe, which serial settings and timestamp source applied, was loss observable, was evidence discarded by retention, and why did an operation end?

---

## 2. Deterministic Execution Is Not a Deterministic DUT (Core §5.1)

Two runs of `sensor read` may legitimately return `temperature=23.4` and later `temperature=23.7`. DUTchMate doesn't promise identical DUT output. It promises that the workflow executes under the same defined rules and that observations are preserved accurately. That is why the boundary is stated in three parts: the client picks the operation, DUTchMate owns its execution, and the DUT owns the physical outcome.

---

## 3. Why Acquisition Is Continuous (Core §5.2)

Consider:

```text
12:00:00  DUT: READY
12:00:10  client starts Interact
12:00:10  TX: status\r\n
12:00:10  DUT: OK
12:00:11  Interact completes

           no workflow is running

12:00:41  DUT: HardFault
12:00:41  DUT: PC=0x08001234
```

If the reader only ran during workflows, the fault at 12:00:41 would be lost. Because acquisition is continuous while DUTchMate owns the backend, it's evidence like anything else.

Continuous acquisition also removes a classic race:

```text
RESET
   [first boot bytes arrive here]
MONITOR starts
```

The reader was already running before the reset, so the first boot bytes are captured.

Workflows are therefore windows over the stream rather than readers:

```text
continuous UART evidence
---------------------------------------------------------->

                 operation start cursor
                         |
                         v
... earlier RX ... | TX command | RX | RX | RX | prompt | ... later RX ...
                   ^                              ^
                   |______________________________|
                         operation evidence window
```

Because bytes are already recorded, combining operations (reset, then wait for `READY`) isn't needed to avoid missing bytes between requests. Small combined primitives can still be worthwhile, because they give one bounded intent, one result, clear timing between action and condition, and simpler clients (Core §21).

---

## 4. Monitor and Interact Flows (Core §6, §7)

Monitor:

```text
continuous RX already active
        |
mark Monitor start cursor
        |
        +---- "READY" observed ----> matched
        +---- timeout -------------> timeout
        +---- connection lost -----> disconnected / reconnecting per contract
        |
return bounded operation result + evidence reference
```

Interact:

```text
continuous RX already active
        |
mark operation start cursor
        |
record and perform exact TX
        |
continue observing the same RX stream
        |
        +---- completion condition matched --> matched
        +---- timeout ------------------------> timeout
        +---- unrecoverable disconnect ------> disconnected
        |
return terminal outcome + evidence reference
```

### 4.1 Why send() and read() aren't enough

Without an Interact primitive, a coding agent ends up writing:

```text
send command
sleep
read
if incomplete: sleep again, read again, repeat
```

That moves timing-sensitive hardware behavior into the agent and makes results depend on how each client happens to be written. Interact lets the client state an intention instead: send these bytes, wait for this condition, within this bound.

### 4.2 Why asynchronous output isn't filtered out

A real window often looks like:

```text
periodic log
shell prompt
TX command
command echo
command output
asynchronous warning
shell prompt
```

Every line is real UART evidence. Silently dropping the periodic log or the warning to present a "clean" response would falsify the record, and the warning may be the most important line in it.

---

## 5. Why the Start Cursor Can't Be Perfect (Core §7.1)

On a Basic adapter, bytes travel through the DUT's UART, the adapter FIFO, USB, and OS buffers before Device Core sees them. Suppose the DUT prints a periodic log line a few milliseconds before DUTchMate transmits a command. That line may still be in transit when the cursor is placed, so it arrives *after* the cursor and sits inside the Interact window, looking like part of the response.

Device Core can't generally tell these apart, so the honest product rule is: the cursor marks Device Core's observation order, results don't claim causation, and clients that need a clean boundary use a DUT-level synchronization point, such as waiting for the prompt or including a unique marker in the command. The Enhanced helper observes much closer to the DUT and can narrow the ambiguity, but it should report what its boundary means rather than claim perfection.

The related rule that only evidence at or after the cursor can satisfy a completion condition (Core §12) prevents a stale `OK` from before the command counting as the command's success.

---

## 6. Follow and Console (Core §8)

```text
DUT -> backend -> Device Core continuous capture
                         |
                         +--> durable evidence
                         |
                         +--> live CLI follow subscriber
```

```text
human keyboard -> CLI console -> Device Core TX -> DUT
DUT -> Device Core continuous RX -> CLI console display
                      |
                      +-> durable evidence
```

Without `follow` and `console`, developers would stop DUTchMate and open `minicom`, `screen`, or `picocom` to watch logs or type commands. The moment they do, the evidence trail breaks and ownership becomes ambiguous. Providing these views inside DUTchMate keeps humans on the same path as every other client. Their lifetime is open-ended only because the human is directly in control. That's why this doesn't conflict with the rule that autonomous waits must be bounded.

---

## 7. Serial-Open Side Effects and DTR/RTS (Core §9.2, §9.4)

Many OS serial APIs and USB-UART drivers toggle DTR or RTS when a port opens. On common development boards (for example, ESP32 auto-reset circuits), those lines are wired to reset or boot-mode pins. A "receive-only" connection can therefore reset the DUT or put it in the bootloader. This is why DUTchMate separates UART payload direction (RX/TX) from adapter control lines (DTR/RTS), requires the profile to state intended line behavior, and treats deliberate DTR/RTS use as recorded control rather than a side effect.

It's also why DTR/RTS control is kept distinct from dedicated GPIO. Only two lines are available, their behavior depends on the driver, and their timing is often imprecise, so presenting them as general-purpose control would overpromise.

---

## 8. Evidence vs. Interpretation (Core §14.1)

```text
Evidence:        UART emitted "HardFault"
Interpretation:  firmware probably dereferenced an invalid pointer
```

Device Core owns the first. Humans, agents, or analysis tools produce the second. Keeping them separate means a wrong diagnosis never contaminates the record, and anyone can go back to the raw bytes and reach a different conclusion.

---

## 9. Timestamps and Loss (Core §14.3, §14.4)

Backends observe at different points:

```text
Basic:     DUT -> UART adapter -> USB -> OS -> Device Core observation
Enhanced:  DUT -> RP2350 UART -> helper timestamp -> USB -> Device Core
```

A Basic timestamp records when the host received a chunk, which can be milliseconds after the bytes left the DUT and is shared by the whole chunk. An Enhanced timestamp records when the helper saw the bytes, using its own clock. These aren't the same measurement, and presenting them as equivalent would mislead anyone reasoning about timing.

The same applies to loss. A generic adapter usually can't report whether bytes were dropped inside it or in the USB stack. The helper can report its own ring-buffer overflows, but only within its own scope. "No loss reported" is therefore a statement about one observer, never proof that the whole path was lossless.

---

## 10. Why Rolling Retention by Default (Core §14.5)

Continuous acquisition on a chatty DUT eventually fills any quota. The two basic choices are to stop recording new evidence or to discard the oldest. Stopping preserves the start of a session but loses exactly what usually matters most, the latest events leading up to a crash. Rolling retention matches how developers debug, since the recent past is the most valuable, and it keeps the continuous-acquisition promise intact. The retention marker and the explicit "expired" result keep the loss honest. A reference that quietly returned partial data would be worse than one that says the evidence is gone.

The core document deliberately leaves the representation of retention metadata open, so that markers don't have to accumulate as an ever-growing list of tombstones. One candidate optimization for the persistence specification: while retention only ever discards a prefix of a stream, a per-stream low-water sequence mark can answer "expired or never existed?" cheaply. On its own, though, it does not preserve the discarded time span and amount, and it does not work for non-prefix retention strategies. So it would have to be combined with coalesced discard provenance, not used as a replacement for it.

---

## 11. Why Retrieval Is Always Bounded (Core §14.6)

A DUT logging at high rate can produce megabytes per minute. An unbounded "give me the evidence for this session" response can overwhelm a terminal, and it will overflow a coding agent's context window and derail its reasoning. Bounded pages with continuation cursors and explicit truncation let every client fetch exactly what it needs and always know whether it saw everything.

---

## 12. Why Client Annotations (Core §14.7)

The one-backend rule (Core §17.1) and the external-tools boundary (Core §21) mean some important actions are invisible to DUTchMate: a flash over SWD, a reset driven by a debug probe, a test harness moving to its next step. Without annotations, those appear in the evidence only as unexplained boot output. An annotation such as "flashed build abc123 via SWD" lets a human or agent tie evidence to the exact build and action that preceded it. Recording annotations as *client assertions* keeps the evidence model honest: DUTchMate attests that a client made the claim at a given time, not that the claim is true.

---

## 13. Ownership Handoff (Core §15.2, §15.3)

```text
DUTchMate owns backend -> continuous capture
       |
explicit RELEASE  -> segment closes, release boundary recorded
       |
external tool owns port   (DUTchMate cannot observe this interval)
       |
explicit REACQUIRE -> backend reopened, profile applied, new segment
       |
continuous capture resumes
```

**Why reacquire is explicit by default.** Tools like `esptool` often reset the DUT and reopen the port during a run, so the device can briefly disappear and reappear. If DUTchMate reacquired as soon as the device reappeared, it could grab the port mid-flash and break it. Tying reacquire to an explicit request, or to the handoff wrapper seeing the tool exit, avoids that race.

**Why the wrapper runs in the CLI, not in Device Core.** Running external programs from Device Core would turn it into a remote execution service. That's a major security surface, especially once agents can call it, and it conflicts with the non-goal of becoming an orchestration engine. The CLI already runs as the user, so the wrapper adds no new privilege. Agents achieve the same thing with their own shell plus release and reacquire tools.

**Why independent transports avoid release.** If flashing uses SWD while DUTchMate holds a separate UART adapter, staying connected captures the reset and the earliest boot output with no gap. That's one of the most valuable things DUTchMate can record.

---

## 14. Native USB Consoles (Core §15.5)

With an external adapter, the host serial device survives a DUT reset. With a native USB console, it doesn't:

```text
reset -> USB serial device disappears -> Device Core sees disconnect
      -> DUT boots -> USB firmware initializes -> device re-enumerates
      -> Device Core reconnects
```

For such DUTs, reset and reconnect are inherently coupled, and anything the firmware prints before USB comes back up can't be seen through that interface at all. Treating this as an expected, declared topology avoids false failures. Recording the segment boundary and the unobservable interval avoids implying continuity that didn't exist.

---

## 15. Architecture Choices

**Single DUT per service (Core §16.2).** Keeping one active DUT per service keeps ownership, concurrency, sessions, reconnects, and MCP tool semantics tractable. Running separate service instances for separate DUTs may work operationally, but orchestrating them is a separate design.

**Local HTTP, Device Core independent of it (Core §16.1, §16.3).**

```text
CLI -------------------+
                       | HTTP
MCP Server [later] ----+
                       v
             Device Core Service (FastAPI)
                       |
               Device Core library
```

HTTP gives both the CLI and MCP a simple, well-understood common boundary, and the service keeps the connection alive between short CLI invocations. Keeping Device Core free of HTTP means its deterministic behavior can be tested directly.

**Why loopback isn't enough (Core §16.4).** A loopback-only port is reachable by every process on the machine, and by web pages: through cross-site requests to `localhost`, or through DNS rebinding, where a hostile domain resolves to `127.0.0.1`. Without local access control, any of these could transmit to the DUT or trigger a reset within whatever policy allows. Authenticating local callers and rejecting browser-originated access closes these paths cheaply. It doesn't sandbox an agent that already runs as the developer, which is why DUT policy still applies to every caller regardless of how it connects.

**CLI before MCP (Core §16.5, §22).** A human can see, question, and debug every workflow directly. If a behavior is wrong, it's far easier to find through the CLI than through an agent's tool calls, and MCP then exposes behavior that is already trusted.

---

## 16. Backend Design (Core §17)

**One backend per connection.** Taking UART from one adapter and control from a separate helper creates two timestamp domains, two owners, ambiguous ordering between a reset and the bytes that follow it, and two independent reconnect behaviors. Until a synchronization design exists, one backend keeps provenance coherent.

**Normalized boundary.**

```text
Basic serial implementation -----+
                                 v
                           normalized events  ---> shared Device Core behavior
                                 ^
Enhanced helper protocol --------+
```

**Capabilities vs. roles.** Keeping "what the hardware can do" (`CTRL0` can drive a line) separate from "what it means here" (`CTRL0` is `RESET_N` on this board) means the helper firmware stays generic across every DUT, and one board can serve many projects by changing only the profile.

**Design for Enhanced, build Basic first (Core §17.4).** Basic is the right first implementation: cheap hardware, and it exercises the whole service. The danger is that an implementation written only against Basic quietly bakes Basic's properties into Device Core, such as "timestamps are host time", "loss is unknowable", or "control means DTR/RTS". When the helper arrives, those assumptions would have to be torn out of shared code. The opposite danger is building speculative helper protocol code before the helper exists. The core rule avoids both: design the contract for both, implement only Basic, and prove neutrality with a simulated Enhanced-shaped backend in tests. The simulated backend models only properties the core document already states. It therefore tests the abstraction without inventing a wire protocol, and Phase 2 reconciles it against real hardware. It is deliberately the smallest test double that exercises the contract: its job is to catch Basic assumptions leaking into Device Core, not to predict how the real helper will behave, so anything beyond that would be speculative Enhanced work by another name.

**Why the phase order is Basic, Enhanced, MCP.** Agents get the most value from a complete, stable contract. Exposing MCP only after both backends exist means agent-facing tools are designed once, against the full capability and provenance model, rather than revised when device timestamps, overflow telemetry, and `CTRLn` control appear.

---

## 17. Product Summary

```text
one Device Core Service
        |
one active DUT Profile
        |
one owned backend (Basic or Enhanced)
        |
continuous UART acquisition
        |
authoritative evidence stream
```

```text
MONITOR    bounded observation over the continuous stream
INTERACT   bounded TX + observation over the same stream
FOLLOW     live read-only human view of the stream
CONSOLE    live human TX/RX through Device Core, when policy allows
CONTROL    configured semantic action -> DTR/RTS (Basic) or CTRLn (Enhanced)
EVENTS     [later] DUT -> EVENTn -> Debug Helper -> Device Core -> client
```

The two defining sentences:

> **Connection and evidence lifetime is continuous while DUTchMate owns the connected backend. Workflow lifetime is bounded.**

> **The client chooses the operation. DUTchMate executes it deterministically and preserves the evidence.**

Phase 1 proves this through the CLI on a Basic backend, with Device Core shown to be backend-neutral. Phase 2 adds the Enhanced Debug Helper on the same contract. Phase 3 lets coding agents use the proven behavior through MCP, without operating a serial terminal or writing timing-sensitive serial code. AI may help with debugging above this boundary, but it never replaces Device Core, controls hardware directly, or stands in for recorded evidence.
