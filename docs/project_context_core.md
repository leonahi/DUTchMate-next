# DUTchMate — Project Context (Core)

> **Purpose:** the durable, normative product context for DUTchMate.
>
> This document states what DUTchMate is, what it must and must not do, and how development is phased. The explanations, examples, and reasoning behind these rules live in the companion document, `project_context_rationale.md`. If the two documents disagree, this one is authoritative and the disagreement is a defect to fix.
>
> This document intentionally does **not** define executable API schemas, HTTP routes, MCP tool names, wire-protocol fields, storage file formats, exact timeout values, quotas, buffer sizes, or detailed acceptance procedures. Those belong in focused implementation specifications.
>
> "Must" and "must not" are requirements. "Should" is a strong default that needs a documented reason to deviate from.

---

## 1. Product Definition

DUTchMate is a deterministic interface between software clients and a physical embedded Device Under Test (DUT). It gives human developers and coding agents reliable access to the DUT's UART and to configured hardware-control interfaces during firmware development, debugging, testing, and diagnosis.

It provides three deterministic capabilities:

1. **Monitor** — bounded observation of UART evidence.
2. **Interact** — UART transmission plus bounded observation of the resulting evidence.
3. **Control** — configured, bounded hardware-control actions where the backend supports them.

A later capability adds **hardware event observation** through generic event inputs.

All of these run on one foundational rule: **while DUTchMate owns a connected backend, UART acquisition is continuous; workflows are bounded windows and actions over that continuous stream and never start or stop the authoritative reader.**

The user-facing name is **DUTchMate**. The primary command is `dutchmate`; a short alias such as `dm` may be provided.

---

## 2. Goal and Scope

### 2.1 Final goal

Let a coding agent work with physical embedded hardware as reliably as a human developer at a bench: modify firmware, build it, flash it with an external tool, then observe, interact with, and control the real DUT and inspect trustworthy evidence of what happened, without opening the serial port itself, implementing timing-sensitive polling, or making hardware decisions outside human-owned rules.

Humans, CI systems, and other tools use the same service with the same guarantees.

### 2.2 In scope

- One Device Core Service owning one active DUT connection at a time.
- Continuous UART acquisition and durable, bounded evidence recording with explicit provenance.
- Monitor, Interact, and Control workflows, plus human `follow` and `console` views.
- Explicit ownership handoff to external tools that need the same transport.
- Two backends behind one normalized contract: **Basic** (standard USB-to-UART adapter or native USB serial console) and **Enhanced** (custom RP2350/Zephyr DUTchMate Debug Helper).
- A CLI (first acceptance surface) and an MCP interface for coding agents.

---

## 3. Non-Goals

Unless introduced by a later explicit design, DUTchMate is not:

- a firmware compiler, general flashing framework, JTAG/SWD debugger, or GDB server;
- an oscilloscope or logic analyzer;
- a general-purpose workflow or scripting engine;
- a vendor-specific shell, bootloader, or MCUmgr implementation, or a replacement for specialized protocol host tools;
- a multi-DUT orchestration system;
- an autonomous AI hardware controller, or a system that gives AI unrestricted GPIO manipulation;
- a guarantee that DUT firmware behaves deterministically;
- a guarantee of lossless physical UART transport when the backend cannot observe all loss points;
- a general-purpose or remote execution service. Device Core never executes arbitrary external programs on behalf of clients.

---

## 4. Clients

All clients share one Device Core behavior. No client may define a parallel hardware model.

- **Human developer (CLI):** attach, view live output, use an interactive console, run bounded workflows, invoke control, hand off the transport, retrieve evidence, and inspect connection and operation history.
- **Coding agent (MCP):** requests bounded operations and receives structured results plus evidence references. It never opens the serial device, runs its own reader, sleeps and polls, races for ownership, reconstructs reconnect history, guesses serial settings, manipulates arbitrary GPIOs, or speaks the Enhanced helper's private protocol.
- **Other clients** (CI, HIL test programs, IDE integrations): use the same Device Core Service.

---

## 5. Execution Model

### 5.1 The deterministic boundary

```text
Client decides WHAT operation to request.
DUTchMate owns HOW the bounded operation executes.
DUT determines WHAT physically happens in response.
```

A deterministic workflow is a bounded operation whose execution semantics — input or hardware action, observation boundaries, ordering, completion conditions, timeout behavior, terminal outcome, and evidence association — are owned by DUTchMate. Determinism applies to workflow execution, not to DUT output.

### 5.2 Continuous acquisition, bounded workflows

- While DUTchMate owns a connected backend, there is exactly one authoritative UART receive path and it runs continuously, including when no workflow is active.
- Monitor and Interact establish logical windows over this stream. They do not create readers.
- Continuous acquisition does not imply unbounded storage (§14.5).

### 5.3 Capability overview

`follow` and `console` are user-facing views over the stream and the TX path. They are not separate physical capabilities. Hardware event observation is a later Enhanced capability (§10).

---

## 6. Monitor

Monitor is a bounded observation request over the continuous stream: for example, wait for a boot banner, a prompt, or a fault marker, or capture the next N seconds or bytes.

DUTchMate owns the start cursor, completion-condition evaluation, the finite bound, termination, disconnect handling, evidence-window association, and result construction.

Monitor is **receive-only at the UART payload level**: it never intentionally transmits UART bytes or performs a control action. This does not claim that opening a serial port is electrically passive (§9.4).

---

## 7. Interact

Interact is a bounded operation in which DUTchMate performs an exact UART TX and observes the stream around it until a completion condition, bound, or terminal failure.

DUTchMate owns the TX action, start boundary, observation window, ordering, completion evaluation, timeout, terminal outcome, and evidence association. The continuous reader remains authoritative before, during, and after.

Requirements:

- Clients express an intention ("send these bytes, wait for this condition, within this bound"). They must not need send/sleep/read loops.
- Multiple explicit completion conditions (for example, `PASS` or `FAIL`) are allowed. Device Core reports which one matched; clients decide what it means.
- Interact must not delete or hide unrelated-looking output (echo, periodic logs, asynchronous warnings) to manufacture a clean response. All received bytes remain evidence.

### 7.1 Operation start boundary limitation

The operation start cursor is a position in **Device Core's observation order**, not a point in DUT time. Bytes the DUT emitted before the TX but still in transit (adapter FIFO, USB, OS buffers) can be observed after the cursor and so appear inside the operation window. Therefore:

- operation results must not claim that evidence inside the window was caused by the TX;
- backends that observe closer to the DUT (Enhanced) may narrow this ambiguity and must report the provenance of their boundary, but no backend may claim to eliminate it unless it actually can;
- clients that need an unambiguous boundary should use a DUT-level synchronization point (for example, a returned prompt or a unique marker in the command).

---

## 8. Follow and Console

**Follow** is a live, read-only human view of the stream Device Core is already recording.

- Starting or stopping `follow` does not start or stop acquisition. Ctrl-C or client disconnect ends only the subscriber.
- Multiple read-only subscribers may be supported if ordering and ownership are unaffected.

**Console** is live human TX/RX through Device Core, available only when UART TX is permitted by policy.

- The CLI must not open the serial port itself. Input passes through Device Core policy and arbitration, and every transmitted byte is recorded.

Both may remain open until the user exits, because the human directly controls their lifetime. This does not relax the bound on autonomous waits (§12). MCP must not depend on an indefinitely open terminal session.

---

## 9. Control

### 9.1 General

Clients request a **configured semantic action** (reset, boot-mode, wake, enable, a project-specific role). They do not invent electrical sequences. DUTchMate owns capability, profile, and policy validation; the allowed electrical semantics; sequence timing; finite bounds; safe-state handling; action recording; and explicit terminal outcomes (§12).

### 9.2 Basic: serial modem-control lines

On adapters, drivers, and wiring that support it, DTR/RTS may implement limited semantic control such as reset or boot-mode. This is **not** general GPIO control and must be represented as a distinct capability.

### 9.3 Enhanced: generic control channels

The Enhanced Debug Helper exposes generic outputs (`CTRL0`…`CTRL3`) with defined safe states. DUT-specific meanings are assigned by the host-side profile. The helper firmware stays generic.

### 9.4 Serial-open side effects

Opening a serial device can change DTR/RTS and therefore DUT state. The active profile must define intended DTR/RTS behavior where the platform exposes the lines. Device Core applies it and records the effective behavior as reliably as the platform permits. If a glitch-free open cannot be guaranteed, that limitation must be represented, not hidden. Intentional DTR/RTS control is a configured, recorded hardware-changing operation. DUTchMate must avoid incidental serial-open transitions where the platform permits, and must not rely on or represent an incidental serial-open transition as an intentional control action.

---

## 10. Hardware Event Observation (later)

A later Enhanced capability exposes generic event inputs (`EVENT0`…`EVENT3`). Host-side roles give them meaning (interrupt, ready, fault, wake, custom). Event evidence follows the same rules as UART evidence: one authoritative capture path, explicit timestamp provenance, ordering, explicit overflow and loss semantics, durable recording, and bounded waits when used as completion conditions.

---

## 11. UART Data and Transmission

- UART bytes are the authoritative evidence. Decoded text, reconstructed lines, pattern matches, and summaries are derived views.
- Invalid UTF-8 or binary content never removes access to the raw bytes, even when the display is lossy.
- Device Core transmits bytes. Text conveniences (line endings: none, LF, CR, CRLF) are allowed, but the exact transmitted bytes must always be knowable. No silent line endings or invisible transformations.
- Binary TX must remain possible at the Device Core level, even if early CLI commands optimize for text.

---

## 12. Completion Conditions and Bounds

- Patterns are deterministic observation tools, not AI interpretation. They operate on explicitly defined derived representations (complete lines, bounded text or byte windows) and never replace raw evidence.
- Only evidence observed at or after an operation's start cursor can satisfy that operation's completion condition.
- Every autonomous wait for the DUT must have a finite timeout or other explicit finite bound.
- Timeout is a normal workflow outcome, not an internal error. Operation results must distinguish applicable terminal outcomes explicitly, including success or condition matched, timeout, disconnect, rejection (policy or capability), and transport failure.
- The exact matching model (encoding, line reconstruction, regex support, limits, overlap, incomplete lines, matches spanning chunk boundaries) belongs in the implementation specification.

---

## 13. Configuration and Policy

### 13.1 Serial configuration

The profile defines intended serial configuration, and each connection segment records the effective settings: baud, data bits, parity, stop bits, hardware and software flow control, and DTR/RTS behavior where relevant, plus backend-specific parameters that affect interpretation. Recording a setting does not claim it is correct for the DUT. Bytes received at the wrong baud are still observed bytes, with provenance that shows the configuration.

### 13.2 DUT Profile

The DUT Profile is the human-owned configuration root for one DUT. It covers identity and name; backend selection and expected device identity; UART configuration; DTR/RTS behavior; policy; semantic control mappings (role → DTR/RTS or `CTRLn`); control electrical semantics; reconnect and topology information (including whether reset is expected to cause a transport disconnect); retention settings; and human convenience defaults such as the default line ending. The schema belongs in the implementation specification.

### 13.3 Configuration snapshots

When a connection segment begins, the effective configuration is snapshotted into its provenance. Later profile changes never rewrite the meaning of earlier evidence.

### 13.4 Policy

Policy is human-owned configuration that decides which state-changing operations clients may request. It is never chosen by an LLM, and no client surface bypasses it. Defaults for a new or incomplete profile:

| Capability | Default |
|---|---|
| UART RX / continuous acquisition | enabled when connected |
| UART evidence recording | enabled |
| UART TX | disabled until explicitly allowed |
| DTR/RTS semantic control | unavailable until explicitly configured |
| Enhanced `CTRLn` semantic control | unavailable until explicitly configured |
| Arbitrary public GPIO manipulation | unavailable |

### 13.5 Policy is not electrical safety

Policy governs what DUTchMate may request. It does not make a cable, adapter, voltage level, or circuit safe. For example, TX being disabled in software does not mean the adapter's TX pin is high-impedance.

---

## 14. Evidence

### 14.1 Evidence vs. interpretation

Evidence includes exact RX bytes; TX actions; timestamps and their provenance; serial configuration provenance; derived text, lines, and pattern matches (marked as derived); control and DTR/RTS actions; connection, disconnection, release, and reacquire events; segment boundaries; ownership gaps; loss and overflow telemetry where observable; retention markers; client annotations (marked as client claims); future event-input records; and operation start and end markers with terminal outcomes.

Device Core owns evidence. Interpretation ("the firmware probably dereferenced an invalid pointer") belongs to humans, agents, or optional analysis, and must never replace or overwrite raw evidence.

### 14.2 Structure

- **Evidence stream:** the ordered history Device Core observes while it owns the backend, including ambient output between operations.
- **Operation:** a bounded logical action or observation (Monitor, Interact, a control action). It references evidence and never owns a reader.
- **Connection segment:** an uninterrupted physical observation context with stable effective provenance. A new segment starts on disconnect/reconnect, release/reacquire, transport identity change, timestamp-origin reset, configuration change requiring reconnection, or another implementation-defined provenance boundary.
- **Session:** a durable, bounded container for a development run: ambient evidence, operations, segments, control actions, boundaries, results, annotations, and derived observations.

Bytes observed between operations must never be discarded merely because no operation was active. Session lifecycle, file format, and cursor details belong in the implementation specification.

### 14.3 Evidence quality and loss

DUTchMate must distinguish at least: loss observed by an available observer; no loss reported within that observer's scope; upstream loss not observable; local evidence discarded by retention (§14.5); transport interruption; ownership gap while released; and incomplete derived-line processing. "No loss reported" must never be presented as proof of a lossless physical path.

### 14.4 Timestamp provenance

Each timestamp records its domain: for example, host observation of a received chunk (Basic) or observation by the helper's device timer (Enhanced). Different domains must not be presented as equivalent measurements. Timestamps across segment boundaries or origin resets must not be compared as one continuous clock unless a future contract explicitly establishes that relationship.

### 14.5 Retention and quotas

- Storage is bounded by explicit quotas and retention rules.
- The **default retention strategy is rolling**: when a quota is reached, the oldest evidence is discarded first.
- Every discarded range is recorded by an explicit **retention marker** (sequence and time span, and amount). Silent loss is never acceptable.
- Retention metadata may be compacted or coalesced as long as discarded ranges remain explicitly distinguishable from evidence that never existed, the required discard provenance remains available, and storage remains bounded. The exact representation belongs in the implementation specification.
- References to discarded evidence remain valid identifiers. Retrieving discarded evidence returns an explicit "expired" outcome, never silently partial data. A partially expired range is reported as partial.
- A profile may explicitly choose a different retention strategy. Unbounded retention is never a default. Exact quotas belong in the implementation specification.

### 14.6 Retrieval

All evidence retrieval is bounded, for every client:

- every retrieval request has a maximum size;
- when more evidence exists, the response includes a continuation cursor and an explicit truncation indicator;
- operation results return evidence references and may include a bounded excerpt. They never inline unbounded evidence;
- clients can select a range (by operation, segment, session, or sequence or time span) and a representation (raw bytes, decoded text, lines).

### 14.7 Client annotations

Clients may insert an **annotation**: a short client-supplied record placed in the evidence stream at the point Device Core receives it. Annotations:

- are attributed to the originating client surface;
- are recorded as **client assertions**, never as DUT observations or DUTchMate actions;
- do not change DUT state and do not require TX permission;
- carry a host-domain timestamp;
- are bounded in size and rate.

Typical uses are recording external actions DUTchMate cannot observe (a flash over SWD, a probe-driven reset), build identifiers, and test-step names.

---

## 15. Ownership and Connection Lifecycle

### 15.1 Single physical owner

Exactly one component owns the active backend at any instant. CLI, MCP, and other clients never open the serial device or Debug Helper while Device Core owns it. The service owns backend open/close, the authoritative reader, continuous acquisition, TX and control serialization, reconnect behavior, and evidence recording. Single ownership is not permanent ownership.

### 15.2 Release and reacquire

When an external tool needs the same transport (for example, `esptool`, a serial bootloader, or a vendor recovery tool):

- **Release** closes the current segment and records a release boundary. The released interval is recorded as unobserved. DUTchMate never claims knowledge of UART activity during it.
- **Reacquire** reopens the backend, applies the effective profile, starts a new segment, and resumes continuous capture.
- **Reacquire is explicit by default.** DUTchMate must not reacquire merely because the device reappeared, since external tools often reset and reopen the port during their run. A profile may opt in to automatic reacquire only when tied to a signal that the external tool has finished.
- The CLI should provide a **handoff wrapper**: release, run the user-supplied external command as a local child process of the CLI, and reacquire when it exits, recording the command's exit status as an annotation. The wrapper runs in the client. Device Core never executes arbitrary external programs on behalf of clients.
- Release and reacquire are available to all client surfaces, including MCP.

### 15.3 Independent flash transports

If flashing uses an independent interface (for example, SWD/JTAG while DUTchMate owns a separate UART adapter), DUTchMate should stay connected so that reset and earliest boot output are captured without a gap. Release is required only when the tool needs the same physical resource.

### 15.4 Lifecycle states

The service distinguishes states equivalent to: detached; attaching; connected with continuous acquisition; reconnecting after transient disconnect; released; and back to detached on stop. Every return to connected starts a new segment. Physical ownership, observation gaps, and connection boundaries are always explicit. Exact state names belong in the implementation specification.

### 15.5 Reconnects and native USB consoles

- With an external USB-to-UART adapter, DUT reset normally leaves the host device present, so earliest boot output is capturable.
- With a native USB serial console, reset makes the host device disappear and re-enumerate. This must be recorded as a segment boundary. When the profile declares this topology, a reset workflow may treat the disconnect as expected rather than as a failure.
- Output produced before the DUT reinitializes its native USB interface is physically unobservable through that interface, and DUTchMate must say so rather than imply continuity.
- Reconnect matching rules belong in the implementation specification.

---

## 16. Architecture

### 16.1 Device Core

Device Core is the deterministic library at the center. It handles profile application, backend lifecycle, ownership, release/reacquire, continuous acquisition, capability validation, serial configuration, TX, Monitor, Interact, Control, backend event normalization, ordering, bounded waits, pattern detection, segments, evidence recording, retention, retrieval, annotations, reconnect semantics, and explicit result and failure models.

It must not depend on a CLI framework, HTTP framework semantics, MCP, an LLM provider, or coding-agent behavior.

### 16.2 Device Core Service

The service provides process-level ownership around Device Core. It owns at most one active DUT/backend, keeps the connection alive independently of short CLI invocations, arbitrates TX and control, serves live subscribers, exposes bounded workflows, maintains evidence and session state, applies reconnect rules, exposes release/reacquire, and provides one common API for all clients. It embeds no AI reasoning.

### 16.3 Local service transport

The Phase 1 service delivers its API over local HTTP using FastAPI, bound to loopback by default. FastAPI and HTTP belong only to the delivery layer. Device Core must be testable and reusable without them. The CLI and the later MCP server are thin clients of this API. Routes, schemas, streaming mechanisms, status codes, transport timeouts, and versioning belong in implementation specifications.

### 16.4 Local access control

The local HTTP service must authenticate callers using a per-user local credential or another explicitly specified local authentication mechanism.

It must also reject browser-originated access, including unsuitable `Host` and `Origin` values.

Authentication does not exempt a caller from DUT policy, ownership, bounds, or evidence rules. Remote or shared deployment requires a separate authentication and authorization design.

The exact authentication mechanism belongs in the implementation specification.

### 16.5 CLI

The CLI is the first acceptance surface: every workflow is invocable and inspectable by a human before it is exposed to agents. It covers attach with a profile, status and capabilities, `follow`, `console`, Monitor, Interact, Control, evidence and session retrieval, annotations, release, reacquire, and clear presentation of disconnect, reconnect, release, and retention boundaries. The CLI should also provide the handoff wrapper (§15.2). Command names are implementation details.

### 16.6 MCP

The MCP server is a thin machine-facing client of the service. It exposes bounded tools for: capability and status inspection; bounded Monitor; bounded Interact; allowed Control; release and reacquire; bounded evidence retrieval; annotations; and operation and session inspection.

It must not own the serial port, create a reader, implement a separate hardware model, broaden policy, bypass ownership rules, invoke an LLM to execute deterministic operations, replace evidence with interpretation, or execute arbitrary external programs on behalf of clients. It uses bounded operations, not an open-ended terminal abstraction.

---

## 17. Backends

### 17.1 One backend per connection

A DUT connection uses exactly one physical backend. DUTchMate must not silently combine UART from one device with control from another. That requires a future synchronization design. Unsupported operations fail explicitly through capability checks.

### 17.2 Normalized backend boundary

Backends deliver normalized events and capability descriptions to Device Core. Backend-specific details (serial-library types, adapter vendor quirks, Enhanced framing and message types) terminate at the boundary. Shared behavior (recording, raw-byte preservation, text projection, pattern detection, Monitor, Interact, retrieval, API, CLI, MCP) must not branch on backend identity. Real capability and provenance differences are carried explicitly in the normalized data.

### 17.3 Capabilities vs. roles

**Capabilities** describe what a backend can physically do (`uart_receive`, `uart_send`, `serial_line_control`, `gpio_control`, `gpio_events`). **Roles** describe what a configured channel means for a particular DUT (reset, boot, wake, power_enable, interrupt, ready, custom). The profile maps roles to mechanisms (for example, `reset → CTRL0 (RESET_N)` or `reset → DTR`). Device Core resolves roles against the backend's reported capabilities.

### 17.4 Backend neutrality: design for Enhanced, build Basic first

Basic is implemented first, but Device Core and the normalized contract are designed for both backends from the start, so that adding Enhanced should not require Basic-specific redesign above the backend boundary.

- **Do not build Enhanced early.** Phase 1 must not implement helper wire protocols, framing, firmware behavior, or other speculative Enhanced mechanics.
- **Do not hardcode Basic.** Code above the backend boundary must not assume that:
  - every timestamp is a host-observation timestamp;
  - loss is always "not observable" or that no observer can report overflow;
  - control is always DTR/RTS or limited to reset and boot;
  - a serial-library handle or type represents the connection;
  - disconnect means only "OS serial device disappeared";
  - received data arrives with OS read-chunk granularity or with any backend-specific framing;
  - the capability set is fixed rather than reported by the backend;
  - there are no defined safe states for control outputs.
- **Prove neutrality in Phase 1** with a **simulated Enhanced-shaped backend** used only in tests. It implements the normalized contract with device-domain timestamps, observer-reported overflow, dedicated control channels with safe states, and its own disconnect semantics. It is a test fixture, not a product feature.
- The fixture should be the smallest test double necessary to exercise the normalized contract. It must not simulate helper protocol, firmware behavior, USB framing, timing characteristics, or hardware that the current contract does not require. It emits timestamp values labeled with the device domain, for example, but does not model realistic device timing. It grows only when the contract does.
- If implementing the real Enhanced backend requires changing Device Core or the normalized contract, that change is a documented contract revision. It indicates a Phase 1 gap only when it removes a Basic-specific assumption. Revisions for capabilities that are genuinely new in Enhanced are expected.

### 17.5 Basic backend

A user-selected host serial device: a TTL-level USB-to-UART adapter or a native USB console presented as a serial port. Vendor-independent.

| Capability | Basic |
|---|---|
| UART RX, continuous acquisition | Yes |
| UART TX | Optional, per policy |
| Deterministic Interact | Yes, when TX is allowed |
| Timestamps | Host observation |
| Overflow telemetry | Usually not available |
| DTR/RTS observation and control | Optional, adapter/driver dependent |
| Semantic reset/boot via DTR/RTS | Optional, profile-configured |
| General GPIO control, GPIO events | No |

The user is responsible for correct electrical connection: compatible voltage levels, common ground, correct TX/RX wiring, any level translation, and never connecting true RS-232 levels to logic-level DUT pins.

### 17.6 Enhanced backend

A dedicated **RP2350-based DUTchMate Debug Helper** with **Zephyr** firmware, based on an existing KiCad design that includes circuitry for generic control outputs and event inputs. Expected capabilities: UART RX/TX, continuous acquisition, device-side timestamps, explicit receive-buffer overflow telemetry, `CTRL0`…`CTRL3` with defined safe states, and later `EVENT0`…`EVENT3`.

The helper implements generic mechanisms, timestamps, buffering, and safe states. It never encodes DUT-specific meanings. RP2350 and Zephyr are durable implementation constraints for this backend, but none of their concepts enter Device Core. USB framing, firmware structure, pin assignments, timestamp encoding, buffer sizing, and event filtering belong in Enhanced implementation specifications.

---

## 18. Concurrency and Serialization

- One authoritative RX path, running continuously while connected.
- TX and action workflows are serialized according to explicit rules. Two transactions must never transmit into the same DUT interface ambiguously.
- Control actions are serialized where necessary.
- Read-only evidence retrieval and live `follow` subscribers may run concurrently without becoming hardware owners.
- Console input passes through Device Core arbitration.
- Bounded workflows receive stable start cursors even while ambient output continues.

The precise locking model belongs in the implementation specification.

---

## 19. Hardware Safety

Validate backend capability and the active profile before acting; apply human-owned policy; keep state-changing operations bounded and recorded; define safe control states; treat intentional DTR/RTS changes as control; never expose unrestricted GPIO manipulation merely because a backend can toggle pins; distinguish software permission from electrical safety; keep AI out of the physical-control path.

Power switching, voltage changes, repeated automated reset loops, and similar disruptive actions require explicit design. They are not automatic generalizations of existing Control semantics.

---

## 20. AI Boundary

Device Core is not an AI system. The deterministic path is: requested operation → validated Device Core workflow → physical interaction or observation → recorded evidence. AI reasoning happens above it: evidence → analysis → hypothesis, source change, or next requested operation. An AI may request operations, but Device Core validates and executes them under the same policy and contract as for a human. AI output never overwrites or replaces evidence.

---

## 21. External Tools

DUTchMate integrates with the embedded toolchain rather than replacing it. Compilation, flashing, JTAG/SWD, GDB, vendor core-dump decoding, logic analysis, oscilloscope measurement, protocol-specific host tools, and complex test orchestration stay external. Complex loops, build logic, test plans, and multi-step strategies stay above Device Core, unless a small bounded primitive (for example, reset-then-wait) proves broadly useful.

---

## 22. Phases and Success Criteria

### 22.1 Strategy

Deterministic physical behavior is defined and proven through Device Core and the CLI, independently of AI, before it is exposed to agents:

```text
product semantics → Device Core + normalized backend contract
  → Phase 1: Basic backend + service + CLI on real hardware
  → Phase 2: Enhanced backend on the same contract
  → Phase 3: MCP exposure
  → later: optional AI analysis, advanced hardware evidence
```

### 22.2 Phase 1 — Basic backend through CLI

DUTchMate becomes independently useful to a human developer using a Basic backend, with Device Core proven backend-neutral.

- **A. Continuous evidence.** With a real DUT connected, UART is continuously acquired and recorded for each connected segment. Output while no workflow is active remains available, subject only to explicit retention. A crash after a command completes is not lost because the client was idle.
- **B. Live follow.** A user can follow the stream Device Core is already recording. Starting or stopping `follow` does not affect acquisition, and the evidence is retrievable later.
- **C. Bounded Monitor.** Results are explicit (matched, timeout, connection-related termination), reference authoritative evidence, and communicate timing, provenance, and evidence-quality limits.
- **D. Interact.** A user sends an exact payload and observes the evidence until a completion condition or timeout, with no client sleep/read loop. The result shows the exact TX bytes, relevant RX evidence, operation boundaries and their limitations (§7.1), the match if any, the terminal outcome, timestamp and configuration provenance, and an evidence reference.
- **E. Console.** When TX is permitted, a human uses DUTchMate as an interactive console without opening the port elsewhere. Input goes through policy and arbitration and is recorded.
- **F. Basic control.** Where adapter, driver, wiring, and profile support it, DTR/RTS-based semantic control (reset, boot-mode) produces explicit, auditable results. Unsupported control fails explicitly.
- **G. Ownership handoff.** A user can release, run an external tool on the same port, and explicitly reacquire. If the handoff wrapper is provided, it performs the same ownership lifecycle automatically. The released interval is recorded as unobserved, and nothing reacquires the port while the external tool is running.
- **H. Backend neutrality.** Shared backend-independent Device Core workflows pass the same behavioral tests against the Basic backend and the simulated Enhanced-shaped backend (§17.4). Capability-dependent behavior is tested against each backend's reported capabilities, including explicit rejection where a capability is absent. No Basic-specific type or assumption exists above the backend boundary.
- **I. Evidence lifecycle.** Rolling retention writes explicit markers, retrieval of discarded evidence reports "expired", all retrieval is bounded with continuation cursors, and annotations are recorded as attributed client assertions.
- **J. Local access control.** The service authenticates callers and rejects browser-originated access (§16.4).
- **K. Reconnects.** Segments preserve reconnect boundaries, and native-USB reset/re-enumeration is represented honestly where applicable.

### 22.3 Phase 2 — Enhanced backend

The RP2350/Zephyr Debug Helper joins through the same normalized contract.

- **A. Drop-in backend.** The Enhanced backend implements the Phase 1 contract. Changes are confined to the backend, unless a documented contract revision is required (§17.4).
- **B. Device timestamps.** Evidence carries device-domain timestamps with explicit provenance, never conflated with host timestamps.
- **C. Loss telemetry.** Helper overflow and dropped-byte counters appear as observer-reported evidence quality within the helper's scope.
- **D. Dedicated control.** `CTRLn` semantic control works with defined safe states and is capability-, profile-, and policy-gated, bounded, and auditable.
- **E. Common semantics.** Monitor, Interact, Control, follow, console, handoff, retention, and retrieval keep the same client-level meaning across Basic and Enhanced where the required physical capabilities exist. Capabilities are never emulated to create artificial symmetry. Differences (timestamp domain, telemetry, control mechanism) remain explicit rather than leaking private protocol details.
- **F. Simulation alignment.** The simulated Enhanced-shaped backend is reconciled with real helper behavior, and remaining differences are documented.

### 22.4 Phase 3 — MCP for coding agents

A coding agent performs the deterministic interactions already proven through the CLI, on either backend, without operating a serial terminal. It can:

1. inspect backend, profile, and capabilities;
2. run bounded Monitor;
3. retrieve authoritative evidence in bounded pages;
4. send UART data and wait for explicit conditions and timeouts;
5. invoke allowed Control;
6. release and reacquire the transport around its own use of external tools, and record annotations for actions DUTchMate cannot observe;
7. distinguish connection, reconnect, release, and retention boundaries;
8. understand evidence-quality and provenance information;
9. operate entirely through Device Core semantics, with no privileged bypass of policy, ownership, bounds, safety, or evidence rules.

### 22.5 Later

- **Optional AI analysis:** advisory functions over bounded evidence (session summaries, failure classification, baseline comparison, correlating source with logs, suggesting next operations). It preserves provenance, uncertainty, the evidence/inference distinction, and the Device Core boundary.
- **Advanced hardware evidence (Enhanced):** GPIO/event edge capture and event roles (§10), synchronized UART/event evidence within documented limits, additional UART channels, power control, power/current/voltage measurement, and other target observation. Each candidate is evaluated on whether it materially improves debugging or control, can be bounded, has representable provenance, can be exposed safely to humans and agents, and belongs in Device Core rather than an external tool.
- **Multi-DUT orchestration:** a separate future design.

---

## 23. Engineering Invariants

A one-line checklist of the rules above. Section references point to the full requirement.

1. Device Core is deterministic and AI-independent. (§5, §20)
2. Workflows are proven through the CLI before MCP exposes them, and MCP defines no parallel model. (§16.6, §22)
3. One service instance owns at most one active DUT/backend until a multi-DUT design exists. (§16.2)
4. There is exactly one physical owner at any instant. Clients never open the backend themselves. (§15.1)
5. Release is explicit, reacquire is explicit by default, and the released interval is recorded as unobserved. (§15.2)
6. UART acquisition is continuous while a connected backend is owned. Workflows never start or stop the reader. (§5.2)
7. Workflows are bounded windows and actions over the stream and reference evidence rather than creating RX paths. (§5.2)
8. Ambient output between operations is evidence. (§14.2)
9. UART bytes are authoritative. Text, lines, patterns, summaries, and AI output are derived. (§11)
10. UART is binary-safe, in both RX and TX. (§11)
11. Every autonomous wait is finitely bounded. (§12)
12. DUTchMate owns timing-sensitive transaction mechanics, so clients need no sleep/poll loops. (§7)
13. Asynchronous output is never deleted to fabricate a clean response. (§7)
14. Operation start cursors are positions in observation order, not DUT time, and results do not claim causation. (§7.1)
15. Only evidence at or after an operation's start cursor can satisfy its completion condition. (§12)
16. TX is explicit. The exact transmitted bytes are always knowable. (§11)
17. Effective serial configuration and control-line behavior are recorded per segment. (§13.1)
18. The DUT Profile is the human-owned configuration root. (§13.2)
19. Evidence snapshots effective configuration, and later profile edits do not rewrite history. (§13.3)
20. UART TX is disabled by default, and observation is the safe default. (§13.4)
21. Opening a port is not assumed electrically passive, and DTR/RTS behavior is explicit. (§9.4)
22. DTR/RTS control is limited, explicit, and not general GPIO. (§9.2)
23. Enhanced control is semantic, configured, capability-gated, bounded, and auditable. No unrestricted pin control. (§9.3, §19)
24. Physical capabilities and semantic roles are separate, and helper firmware encodes no DUT meaning. (§17.3, §17.6)
25. One physical backend per connection. (§17.1)
26. Backend-specific details terminate at the normalized boundary. (§17.2)
27. Device Core is designed for both backends, is built Basic-first, and hardcodes no Basic assumption. (§17.4)
28. Evidence quality is explicit, and unknown loss is never reported as losslessness. (§14.3)
29. Timestamp domains are explicit and never conflated. (§14.4)
30. Reconnects and origin resets create explicit segment boundaries. (§14.2, §15.5)
31. Native-USB disconnect on reset is legitimate, and pre-enumeration output is acknowledged as unobservable. (§15.5)
32. Retention is bounded and rolling by default, every discard is marked, and expired evidence is reported, never silently partial. (§14.5)
33. All evidence retrieval is bounded and paginated with explicit truncation. (§14.6)
34. Annotations are attributed client assertions, never observations. (§14.7)
35. Hardware-changing operations are recorded and distinguishable from DUT output. (§9, §14.1)
36. Human live views go through Device Core, and stopping them does not stop acquisition. (§8)
37. Local callers are authenticated and browser-originated access is rejected. Authentication never exempts a caller from policy. (§16.4)
38. AI interpretation never replaces evidence. (§14.1, §20)
39. DUT behavior is not claimed to be deterministic. Workflow execution is. (§5.1)
40. Complex orchestration stays above Device Core. DUTchMate is not a scripting language or a general-purpose or remote execution service, and Device Core never executes arbitrary external programs on behalf of clients. (§3, §15.2, §21)
41. External specialist tools stay external without a clear product reason to do otherwise. (§21)
42. Unsupported operations fail explicitly. Nothing is silently emulated or weakened. (§12, §17.1)
43. Implementation contracts may evolve without changing these product boundaries. (header)
