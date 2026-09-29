# DUTchMate Release Strategy

## Purpose

This document defines the release cadence and release-scope policy for DUTchMate.

It complements:

- `docs/project_context_core.md`, which defines durable product semantics, architecture, and development phases;
- `docs/project_context_rationale.md`, which explains the reasoning behind them (non-normative);
- `AGENTS.md`, which defines engineering constraints for coding agents;
- `docs/development_status.md`, which defines current project progress and next work.

This document does not define product architecture, implementation contracts, or current development status.

---

## 1. Release Philosophy

Prefer small, frequent public releases over large batched releases.

A release should normally contain one or a few coherent, independently useful changes that have passed the required validation gate.

Do not delay completed, validated functionality solely to accumulate more features for a larger milestone release.

Release scope should be driven by coherence, validation, compatibility, and user value rather than by release size.

---

## 2. Preferred Release Shape

Prefer releases that are:

- small enough to review and reason about;
- focused on one feature, one capability slice, or a small set of tightly related changes;
- independently testable;
- independently documentable;
- independently reversible or diagnosable if a problem is discovered;
- explicit about hardware validation and platform limitations;
- accompanied by concise release notes.

A release may include more than one change when those changes are tightly coupled and separating them would create an incomplete or misleading user experience.

---

## 3. What Not to Batch

Do not bundle unrelated completed work merely to create a larger release.

Avoid release trains that combine unrelated changes such as:

- a new Device Core capability;
- an unrelated CLI refactor;
- documentation cleanup;
- dependency upgrades;
- release automation changes;
- a separate hardware feature;

unless there is a concrete technical reason they must ship together.

Unrelated work should normally be released separately when each part is stable and validated.

---

## 4. When to Delay a Release

A small release should still be delayed when there is a concrete reason, including:

- required validation has not passed;
- real-hardware acceptance is required and has not been completed;
- a compatibility or migration problem is unresolved;
- the implementation would expose an unstable or misleading public contract;
- user-facing documentation is materially incomplete;
- a known regression remains;
- security or licensing review is incomplete;
- the release would expose the local service without caller authentication or browser-origin rejection (core §16.4);
- the release would weaken a core invariant or silently change the meaning of recorded evidence;
- the release would leave the repository or package set in an internally inconsistent state.

Release frequency must not override correctness.

---

## 5. Validation Before Release

Each public release should pass the repository's required validation gate for the affected scope.

For Python work this will normally include appropriate equivalents of:

```bash
uv run ruff check .
uv run mypy .
uv run lint-imports
uv run pytest
git diff --check
```

Additional validation should be added when required by the change, including:

- focused compatibility tests;
- package build/install checks;
- CLI smoke tests;
- service startup and local-authentication checks;
- supported-platform checks;
- real-hardware acceptance for each backend and connection topology the change affects (for example, an external USB-to-UART adapter vs. a native USB console).

Do not claim hardware support from software-only tests.

Before every publication, check distributable artifacts for sensitive data (credentials, tokens, keys, generated local service credentials, device secrets, private test data), and review repository history added since the previous publication. Before the first publication, review the full history.

The simulated Enhanced-shaped test fixture proves backend neutrality only. It does not demonstrate Enhanced hardware support.

---

## 6. Release Notes

Each public release should have concise release notes that explain:

- what changed;
- what user-visible capability was added, changed, or fixed;
- important compatibility changes;
- known limitations;
- which backends, adapters or topologies, platforms, and DUTs were validated on real hardware, if any;
- known physical or observability limits relevant to the change, such as platform-dependent DTR/RTS behavior on open, timestamp domain, or loss observability;
- any migration action required from users.

Do not list planned or incomplete functionality as released.

Do not use `AGENTS.md`, `docs/development_status.md`, or temporary plans as user-facing release notes. When releases begin, maintain a changelog and user documentation that distinguish supported, experimental, backend-specific, hardware-dependent, and physically limited behavior.

Release notes should describe the shipped behavior rather than reproduce internal implementation plans.

---

## 7. Versioning Approach

Before stable release, deliberate documented breaking changes are acceptable when required by the architecture or current specification.

Keep compatibility commitments narrow until an interface is intentionally declared stable.

Potential compatibility surfaces include:

- CLI commands and options;
- Device Core Service APIs;
- DUT Profile/configuration schemas;
- persisted evidence formats, including retention metadata and annotations;
- local service authentication mechanism;
- Debug Helper protocol contracts;
- Python APIs;
- MCP interfaces.

Recorded evidence is the product's core output. Before stable release, persisted evidence formats may change, but a release must never silently misread evidence recorded by an earlier release. It either reads that evidence correctly or rejects it explicitly, and its release notes state any format break.

Do not preserve obsolete behavior merely to avoid a version change when it conflicts with the governing architecture or specification.

When formal semantic-versioning policy is introduced, keep the version source intentional and centralized.

---

## 8. Release Automation

Introduce release automation incrementally.

Automate only what provides clear value for the current release process.

Do not build a large release pipeline before the project has stable packaging and repeatable manual release steps.

When formal releases begin, validate from a clean environment.

As the project matures, automation may cover:

- clean dependency installation;
- package build;
- package installation;
- CLI startup and packaged resources;
- test/static-analysis gates;
- artifact creation;
- version reporting and verification;
- signing and publication;
- release-note generation support;
- supported-platform smoke tests.

Release automation must not bypass normal validation or architecture rules.

---

## 9. Relationship to Development Slices and Phases

Implementation work should favor small coherent slices that can become releasable units.

A development slice does not have to become a public release immediately, but once it is:

- complete;
- independently useful;
- validated;
- documented;
- compatible with the current public surface;

there should be a concrete reason to hold it back.

This encourages early feedback and reduces the risk associated with large accumulated releases.

Releases are not tied to phase boundaries. Phase 1 (Basic backend through the CLI), Phase 2 (Enhanced backend), and Phase 3 (MCP) may each ship through several small releases. A phase does not need to be complete before validated slices within it are released, and a release does not imply that its phase is complete.

A release must not present later-phase capabilities as available:

- no Enhanced backend support before it passes real-hardware acceptance;
- no MCP tool for a workflow whose Device Core semantics have not already been defined and validated through the CLI (core §22).

---

## 10. Release Decision Rule

Default to releasing a completed change when:

1. it is coherent and independently useful;
2. its required validation has passed;
3. its user-facing behavior is documented;
4. its compatibility impact is understood;
5. no known blocker requires bundling it with later work.

If those conditions are met, prefer a small release rather than waiting for a larger milestone.
