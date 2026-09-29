# DUTchMate Engineering Constraints

This file defines how coding agents work in this repository. Product semantics live in `docs/project_context_core.md`. Any product-rule summaries here are non-authoritative implementation reminders; the Core document remains authoritative.

---

## 1. Repository Name

The GitHub repository may temporarily be named `DUTchMate-next` while the new implementation is developed. It is expected to be renamed `DUTchMate` once it becomes canonical.

`DUTchMate-next` is a repository-management name only. The product name is **DUTchMate**. Do not use `DUTchMate-next` in product-facing identifiers, documentation, packages, CLI commands, service names, protocol names, or hardware names.

---

## 2. Authority and Source of Truth

Use this precedence for implementation decisions:

1. `docs/project_context_core.md`: product semantics, architecture, invariants, capability/evidence/safety boundaries.
2. Active implementation specification: concrete contracts, schemas, timing, persistence, concurrency, acceptance criteria.
3. Current implementation plan or task.
4. Existing tests.
5. Existing implementation.

`docs/project_context_rationale.md` explains the reasoning, examples, and trade-offs behind the core document. It is not normative and adds no requirements. Consult it when the intent of a core rule is unclear. If it appears to conflict with the core document, the core document wins; report the conflict.

`docs/development_status.md` is authoritative for current progress, active phase, blockers, milestone, and next step. It does not override the core document.

Existing code is evidence of current behavior, not automatically the intended architecture. If code or tests conflict with a governing specification, do not preserve the conflict merely for compatibility; identify it and make the smallest coherent change that restores consistency. Do not silently change a product-level invariant in code. When the product decision itself changes, change the governing documentation explicitly.

Before coding:

- read the relevant specification sections, and consult the rationale when the intent behind a relevant core rule is unclear;
- inspect `docs/development_status.md` when selecting or continuing work;
- inspect `git status`, relevant diffs, affected code, and tests;
- identify the invariants touched by the change.

---

## 3. When to Stop and Ask

Stop and ask the human before proceeding when:

- an action may change the state of physical hardware and the human has not asked for it in the current task (see §6);
- it is unclear which physical device, port, or DUT profile is intended;
- the task appears to require changing a product-level rule in `docs/project_context_core.md`. Propose the documentation change instead of coding around the rule;
- governing documents conflict and the precedence in §2 does not resolve it;
- a requirement has several viable interpretations that lead to materially different behavior or public contracts.

Otherwise, proceed, and state any assumption you made in the completion report. Do not ask for confirmation of routine, well-specified work.

---

## 4. Architecture

DUTchMate is a modular monolith using Ports-and-Adapters principles and lightweight domain modelling.

The repository may grow to include `core/` (shared domain, application, protocol, and adapter code), `apps/service/` (Device Core Service and composition root), `apps/cli/` (thin CLI delivery adapter), `apps/mcp_server/` (thin MCP delivery adapter, Phase 3), and `hardware/` (firmware, protocol schemas, schematics, and validation assets). Create structure incrementally as the active phase and specification require, never merely because it is listed here, and follow the actual structure as it evolves.

### 4.1 Dependency rules

These are enforced by architecture contracts where possible (§8.2).

- Dependencies point inward: delivery and infrastructure adapters → application → domain. Adapters depend on the application/core contract, never the reverse.
- Application and domain code must not depend on FastAPI, Typer, HTTP clients, serial libraries, filesystem details, MCP frameworks, or any adapter or framework implementation.
- Delivery applications may depend on `dutchmate_core`. `dutchmate_core` never imports from `apps/`.
- FastAPI/HTTP models and transport concerns stay outside application and domain policy.

### 4.2 Ports and abstractions

- Use ports only for genuine external boundaries, or where substitution gives concrete testing or architectural value: physical DUT backends, persistence, clocks and other nondeterministic infrastructure, and external service/client boundaries.
- Do not create ports, interfaces, repositories, factories, adapters, services, DTO layers, registries, or other abstractions merely to satisfy a pattern or for architectural symmetry. Prefer direct concrete code where no meaningful boundary exists.
- Do not introduce DDD patterns (aggregates, repositories, domain services, factories, commands, events, extra ports) unless they solve a demonstrated problem.
- Do not create speculative structure for future phases. The normalized backend contract and its minimal simulated fixture are current Phase 1 requirements, not speculative structure (§5.1).

### 4.3 Domain modelling and source structure

Prefer typed values, dataclasses or similarly explicit structures, explicit state transitions, validation near the invariant it protects, small intentional public APIs, and domain language from the specifications.

Organize modules by cohesive responsibility and reason to change, and split when responsibilities change independently. File count and length are signals, not goals. Do not default to one class per file, prefer private helpers, and remove obsolete compatibility layers after consumers migrate.

---

## 5. Implementing Product Boundaries

Read the relevant core sections before changing code in these areas:

| Area | Core sections |
|---|---|
| Backends, capabilities vs. roles, backend neutrality | §17 |
| Control, DTR/RTS, serial-open side effects | §9 |
| UART data, TX transformations | §11 |
| Completion conditions, bounds, terminal outcomes | §7, §12 |
| DUT Profile, policy, defaults | §13 |
| Evidence, provenance, retention, retrieval, annotations | §14 |
| Ownership, release/reacquire, reconnects, native USB | §15 |
| Service, CLI, MCP, local access control | §16 |
| Concurrency and serialization | §18 |
| Hardware safety | §19 |
| AI boundary, external tools, scope | §3, §20, §21 |

This section summarizes relevant Core constraints only where needed to guide implementation and adds repository-level implementation guidance. The Core document remains authoritative.

### 5.1 Backends

- Prefer capability-driven behavior over backend-name checks.
- Phase 1 implements only the Basic backend. Do not implement Enhanced helper protocol, framing, firmware behavior, or other Enhanced mechanics before Phase 2. `EVENTn` comes later still.
- Do not hardcode Basic properties above the backend boundary. Core §17.4 lists the forbidden assumptions.
- Prove neutrality with the simulated Enhanced-shaped test fixture (core §17.4): the smallest test double that exercises the current contract, extended only when the contract changes. It is test code and does not demonstrate Enhanced hardware support.
- Run shared backend-independent workflow tests identically against both backends. Test capability-dependent behavior against each backend's reported capabilities, including explicit rejection. Never emulate capabilities to create artificial symmetry.
- If Enhanced work requires changing Device Core or the normalized contract, document it as a contract revision. It indicates a Phase 1 gap only when it removes a Basic-specific assumption.

### 5.2 Serial open and DTR/RTS

Avoid incidental DTR/RTS transitions on open where the platform permits. Use only platform/library mechanisms whose behavior is understood and validated for the active implementation. Never rely on or record an incidental open transition as an intentional control action.

### 5.3 Evidence

Retention metadata may be compacted or coalesced when the conditions in core §14.5 hold. Do not implement retention markers as an unbounded list of tombstones.

### 5.4 Ownership and concurrency

- Do not solve concurrency by creating more physical readers.
- If the CLI provides the handoff wrapper, the user-supplied external program runs as a local child of the CLI process. Device Core, Device Core Service, and MCP never execute arbitrary external programs on behalf of clients.

### 5.5 Service and clients

- In Phase 1, Device Core Service uses FastAPI over local HTTP as its delivery boundary, and the CLI is a thin HTTP client of it.
- The local HTTP service authenticates callers and rejects browser-originated access (core §16.4). Do not disable or bypass this for convenience, including in development defaults. Tests use the same authentication path or a mechanism the implementation specification explicitly defines for testing.
- The CLI must not open the DUT transport, create its own UART reader, implement a separate reconnect model, reproduce Device Core transaction timing, or bypass profile or policy checks.
- MCP is Phase 3, after the Enhanced backend (Phase 2). Do not implement it before `docs/development_status.md` shows that phase as active, and do not expose a workflow through MCP before its Device Core semantics are defined and validated through the CLI.

### 5.6 AI and Device Core scope

- Do not add LLM calls to UART acquisition, transport ownership, TX/control execution, completion matching, reconnect handling, or evidence recording.
- Do not add build logic, source modification, project-specific orchestration, or general scripting primitives to Device Core merely for one client.

---

## 6. Working with Real Hardware

Treat every connected device as someone's working hardware, even if it looks like a spare.

Unless the human explicitly asks for it in the current task, do not:

- open, reset, flash, or otherwise interact with a connected physical device, whether through DUTchMate, another tool, or by running real-hardware tests;
- enable UART TX or any control mapping in a DUT profile used with real hardware;
- run repeated automated reset, boot-mode, power, or flash loops;
- change serial settings or DTR/RTS behavior on a real device.

When the human does ask:

- use the device and profile they identified; never pick one because it happens to be connected;
- use the least-invasive profile that achieves the task. Enable TX or control only when the task is about them;
- stop and ask if the electrical setup matters and is unknown (voltage levels, wiring, what a control line is connected to).

Profiles written for tests, examples, or documentation default to observation only (TX disabled, no control mappings), matching core §13.4.

Report every real-hardware action in the completion report.

---

## 7. Scope Discipline and Contracts

Implement the smallest coherent change that satisfies the current specification, using the simplest implementation that preserves the required architecture. A simple concrete implementation behind a meaningful port is preferable to a generalized framework designed for hypothetical requirements.

- Do not introduce extensibility points, plugin systems, registries, factories, generic frameworks, compatibility layers, or future-capability abstractions without a demonstrated requirement in the current specification. The normalized backend contract (core §17.2, §17.4) is such a requirement: designing it for both backends is not speculative abstraction, but implementing Enhanced-specific behavior before Phase 2 is.
- Do not perform unrelated refactors, implement later-phase features merely because they are mentioned, or create public contracts the task does not require.
- Distinguish current requirements, deferred behavior, and future ideas.

### 7.1 Refactoring

- Structural refactors preserve externally observable behavior unless the governing specification or task changes it.
- Before moving or deleting code, map callers, imports, exports, persistence formats, compatibility paths, and affected tests.
- Refactor one subsystem at a time and keep each slice independently testable. Do not combine architectural restructuring with unrelated feature work.
- Preserve compatibility only when the current contract still requires it. Do not retain obsolete behavior that conflicts with current specifications, and do not maintain two competing architectures.

### 7.2 Do not invent contracts

The core document deliberately leaves concrete implementation contracts to focused specifications. Do not invent undocumented public contracts for HTTP routes, MCP tool names, JSON schemas, wire-protocol framing, exact timeout defaults, storage formats, buffer sizes, retention limits, retention-metadata representation, regex semantics, cursor representations, evidence-retrieval page sizes and cursor encodings, reconnect matching, locking mechanisms, annotation schemas and limits, terminal-outcome encodings, local authentication mechanisms, or handoff-wrapper command syntax.

Follow the active implementation specification. If it does not define a contract, avoid creating one unless the task genuinely requires it.

---

## 8. Tests and Validation

Tests verify documented behavior, not accidental implementation details. Add or update focused tests where relevant for: changed behavior, ordering, failure and timeout paths, capability/policy rejection, evidence and provenance, disconnect/reconnect, release/reacquire, retention markers and expired-evidence results, bounded retrieval and truncation, annotations, local caller authentication and browser-origin rejection, backend neutrality against the simulated Enhanced-shaped fixture, and compatibility guarantees.

Mocks and simulators verify software contracts; they do not prove real-hardware acceptance. The simulated Enhanced-shaped fixture proves backend neutrality only, not Enhanced hardware behavior. Never claim hardware acceptance without testing the required hardware.

### 8.1 Hardware tests

- The default test run (`uv run pytest`) must pass with no hardware attached and must not open any physical serial device. Virtual serial ports that a test creates for itself (such as pty pairs) are allowed.
- Real-hardware tests are explicitly marked and opt-in. They are excluded from the default run and execute only when explicitly selected.
- A hardware test identifies its target device from explicit configuration. It never selects whichever serial port happens to be connected. If the target is not configured, the test skips with a clear reason rather than falling back to another device.
- Hardware tests use the least-invasive profile that exercises the behavior under test, and enable TX or control only when the test is about them.
- Report skipped hardware tests as skipped, never as passed.

### 8.2 Architecture contracts

Architecture boundaries are enforced with import-linter (`uv run lint-imports`, contracts in `pyproject.toml`) and ruff banned-API rules. Both are part of the validation gate.

- A contract violation means the code is wrong or the architecture must change. Fix the code. Never delete or weaken a contract, add `ignore_imports`, or add a new exemption merely to make the check pass. Exemptions and scope exclusions explicitly documented here are permitted: for the `subprocess` banned-API rule, the handoff wrapper module is an exemption within product code, and tests and development tooling are outside its scope. If the architecture genuinely needs to change, stop and ask (§3).
- When you create a package that falls under an existing boundary, add or extend its contract in the same change. Contracts may only name modules that exist.
- The ruff banned-API rule for `subprocess` applies to product code. Within product code, its one intended exemption is the CLI module that implements the handoff wrapper (§5.4). Tests and development tooling are outside its scope. Any spawned process that may interact with real hardware remains subject to §6 and, for tests, §8.1.

### 8.3 Validation gate

During implementation, run focused tests and targeted static analysis, search, or diagnostics, and resolve failures before broadening validation.

Before completing a slice, run the repository's required validation gate, normally including appropriate equivalents of:

```bash
uv run ruff check .
uv run mypy .
uv run lint-imports
uv run pytest
git diff --check
```

Also review the final diff, remove stale references when relevant, update architecture docs only when architecture changed, and update development status/history and Graphify when required.

Do not claim completion when required validation was not run or failures remain. If hardware or infrastructure prevents validation, state that explicitly.

---

## 9. Python and Agent Tooling

### 9.1 uv

DUTchMate uses **uv** as the Python package, environment, and workspace manager. `pyproject.toml` and `uv.lock` are authoritative for Python dependency configuration.

- Use uv (`uv add`, `uv add --dev`, `uv remove`, `uv lock`, `uv sync`, with workspace/package targeting when needed), and run Python tools through `uv run` unless repository-specific commands say otherwise.
- Do not introduce Poetry, Pipenv, Conda, or another Python package manager. Do not use `pip install` directly for normal development, and do not create `requirements.txt` unless an explicit external integration requires it.
- Do not edit `uv.lock` manually or upgrade unrelated dependencies. Dependency-resolution changes include the corresponding `uv.lock` update; avoid unrelated lockfile churn.
- Use the repository-declared Python version.
- Before adding a dependency, check the standard library and existing dependencies, and add one only when it provides concrete value. Consider its license suitability.

### 9.2 RTK

When RTK (`rtk`) is available, prefer it for supported commands with potentially large output (for example `rtk git status`, `rtk git diff`, `rtk git log`, `rtk pytest`, `rtk rg <pattern>`) when it reduces output without changing semantics.

Use raw commands when exact output is needed, and rerun without RTK if necessary information was omitted. Never change command semantics or hide errors for token savings; correctness takes priority. RTK is only an output-reduction wrapper: uv remains authoritative for Python execution, so do not bypass the intended uv environment merely to use an RTK shorthand.

### 9.3 Spec Kit, Graphify, and Superpowers

Read the tool's section in `docs/agent_tooling.md` before using it.

- **Spec Kit** is optional: only for substantial features where a focused specification, plan, and task breakdown materially reduce ambiguity or coordination risk (such as a new subsystem, protocol, evidence-model or persistence foundation, ownership or lifecycle behavior, or the normalized backend contract). Never for localized changes, known-cause bug fixes, mechanical refactors, or documentation-only work. Its artifacts stay subordinate to §2.
- **Graphify** is optional: for architectural navigation and cross-module impact analysis. Use source inspection and `rg` for routine navigation. Never read `graphify-out/graph.json` directly.
- **Superpowers** is used selectively, never as the full end-to-end workflow. Only `systematic-debugging`, `test-driven-development`, `verification-before-completion`, and `brainstorming` are in scope. Where Superpowers is available, use `verification-before-completion` before declaring a slice complete; the §8 validation requirements apply either way.

---

## 10. Workflow, Planning, and Documentation

### 10.1 Development status

- Read `docs/development_status.md` before selecting work. It is the only source for current progress, active phase, blockers, milestone, and next step.
- Keep its `Resume Here` section to about 40 lines or fewer. Update status, checklist, and validation information when project status changes, and reconcile code-baseline references after commits.
- Append completed-slice records to `docs/development_history.md`, newest first. It must not contain a competing current-status or next-step section.

### 10.2 Workflow and planning

- Match planning effort to change risk. For localized, well-specified work: inspect code, spec, and tests; skip separate design documents and large plans; state a short approach when useful; implement in small coherent changes; run focused tests, then final validation.
- Use a more structured workflow for changes affecting architecture, concurrency, ownership, lifecycle, reconnect, evidence, persistence/schema compatibility, protocols, public interfaces, hardware safety, or multiple subsystems. A written plan for such a change has about 5–10 meaningful steps; identifies likely components and files, invariants and compatibility constraints, and critical tests and acceptance criteria; and references specifications. It avoids large anticipated code blocks and minute-by-minute decomposition. For migrations and cleanup, prefer an affected-consumer inventory.
- Do not redesign established architecture unless the task requires it or a concrete correctness problem invalidates it.
- Before proposing new architecture or design documents, check existing product, spec, protocol, and status documents. Reference normative documents rather than restating them, and do not create another design document when behavior is already specified.
- Working plans are temporary. Durable decisions belong in specifications, current status in `development_status.md`, and completed evidence in `development_history.md`. Do not let temporary plans become competing long-term specifications.

### 10.3 Documentation

- Update documentation when a documented contract changes. Do not rewrite architecture documentation merely to match accidental implementation; a changed product decision is an explicit architecture decision.
- Keep the layers distinct: `AGENTS.md` and `docs/agent_tooling.md` (how coding agents work), `docs/project_context_core.md` (durable product semantics, normative), `docs/project_context_rationale.md` (reasoning and examples, non-normative), implementation specifications (executable contracts), implementation (code), and tests (verification).
- When a core rule changes, update the rationale if its explanation is affected. The rationale must never introduce requirements absent from the core.
- Do not document planned features as implemented.

---

## 11. Release Readiness

DUTchMate is intended to become a distributable public project. `docs/release_strategy.md` defines release cadence, scope, notes, versioning, and automation (in short: prefer small, independently validated releases). This section covers what everyday development must preserve so releases remain possible, without adding premature release machinery.

- Keep public surfaces small, and do not create compatibility commitments before an interface is declared stable. The compatibility surfaces are listed in `docs/release_strategy.md` §7.
- When breaking an established contract: identify affected consumers, decide whether migration or compatibility handling is needed, update the governing specification, tests, and docs, and record the externally relevant change. Before stable release, deliberate documented breaking changes are acceptable when the architecture requires them.
- Python packages remain installable and reproducible through uv, `pyproject.toml`, `uv.lock`, and the declared Python version. Avoid working-directory assumptions, undeclared local import paths, mandatory editable installs, undeclared package data, hard-coded developer-machine paths, and reliance on globally installed Python packages.
- Do not scatter version strings. Use one intentional version source when formal versioning is introduced.
- Never commit credentials, tokens, private keys, generated local service credentials, personal machine configuration, device secrets, private test data, or sensitive generated artifacts.
- Do not copy third-party source, assets, or documentation without verifying redistribution rights and required notices.

---

## 12. Coding Style and Communication

Follow repository conventions. Prefer clear domain language, explicit types and failure models, small cohesive units, capability-driven behavior, deterministic state transitions, and testable boundaries. Avoid abstractions that obscure ownership, ordering, provenance, physical effects, or failure modes.

Keep progress and final responses concise and information-dense. Report important decisions, assumptions, failures, trade-offs, and exact commands, paths, and errors when relevant. Do not narrate trivial steps or sacrifice correctness for brevity.

---

## 13. Before Finishing a Task

Verify every item the change could affect. This list doubles as the quick reference for product invariants; the complete set is core §23, which is authoritative.

**Conformance:** conforms to the core document and the active specification; no undocumented public contract; no deferred functionality implemented by accident.

**Ownership and acquisition**

- Device Core Service remains the single physical owner, with one authoritative RX path and continuous acquisition while a connected backend is owned. No client opens the DUT transport.
- Monitor and Interact remain bounded windows over the stream, not readers, and timing-sensitive transaction mechanics stay in Device Core.
- Reacquire remains explicit by default, never triggered merely by a device reappearing. Device Core, the service, and MCP run no external programs.

**Evidence**

- Exact UART bytes remain authoritative and binary-safe; text, lines, patterns, summaries, and AI output remain derived. Output between operations remains evidence, and asynchronous output is never removed to manufacture a clean response.
- TX transformations (such as LF/CR/CRLF) and hardware actions remain explicit and auditable.
- Connection, reconnect, release/reacquire, timestamp-origin, and observation-gap boundaries, and evidence provenance, remain explicit and honest.
- Retention remains bounded, rolling by default, and marked; expired evidence is reported as expired, never silently partial. Retrieval remains bounded and paginated with explicit truncation. Annotations remain attributed client assertions.

**Execution**

- Autonomous waits are bounded, and results report applicable terminal outcomes explicitly.
- Start cursors remain positions in observation order: results claim no causation, and only evidence at or after the cursor can satisfy a completion condition.

**Boundaries**

- Backend details stay behind the normalized boundary, capabilities stay separate from semantic roles, no Basic-specific assumption sits above the boundary, and no Enhanced behavior was built ahead of its phase.
- Architecture contracts pass and were not weakened or exempted.
- AI stays above the deterministic path and never replaces evidence.

**Safety and security**

- Capability, policy, and DUT Profile checks remain intact, and unsupported capabilities fail explicitly.
- Local caller authentication and browser-origin rejection remain intact.
- No real hardware was touched without an explicit request, and the default test run remains hardware-free.

**Process:** tooling stays consistent with uv; required validation was actually run; Spec Kit was used only where justified; a reasonable path to packaging and release is preserved.

Resolve uncertainty before declaring completion.

---

## 14. Agent Completion Report

At completion, report concisely: what changed and why; important architectural decisions; materially changed files; tests and validation executed; tests not executed and why; remaining limitations; real-hardware actions performed, including which devices were touched; hardware validation still required; and documentation or status updates performed.

Do not describe unexecuted validation as successful, claim hardware behavior from software-only tests, or claim project completion because one development slice is complete.
