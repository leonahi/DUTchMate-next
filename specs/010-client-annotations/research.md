# Research: Bounded Attributed Client Annotations

**Date**: 2026-10-15 | **Feature**: 010-client-annotations | Planning research snapshot; current implementation progress is in [development status](../../docs/development_status.md).

Research used governing Core, then-current status and committed001–009 source/contracts. No external dependency, web research, production implementation or physical experiment was needed for that planning research. Two read-only research agents inspected persistence and lifetime/delivery dependencies as requested by the plan skill; findings were checked against source. The scaffold constitution is unpopulated and supplies no additional rule. No unresolved design decision remains.

## 1. Explicit schema3, preserving six old variants

**Decision**: New explicit create_v3/open_v3, strict v3 terminal target, annotation record_version3. Original acquisition kinds keep1 and operation markers keep2, byte-identical. Production preparation selects v3, while old default-v1/explicit-v2 entry points remain exact. No migration or auto-detection.

**Rationale**: Existing003/009 contracts make explicit schema selection and closed kind/version pairs intentional compatibility surfaces. A new evidence variant must not silently redefine a v2 artifact. Same journal tables, worker, limits and retention remain sufficient.

**Alternatives**: Extending v2 in place violates its closed variant contract; silently migrating legacy files adds recovery/ownership risk; separate annotation storage loses authoritative order/retention and is unnecessary. A generic version registry is unjustified for three explicit formats.

**Source findings at the committed001–009 planning baseline**: sqlite_evidence.py contains many v1-else-v2 branches; every affected worker/validator must select1/2/3 explicitly. `_validate_operation_pair` decodes intervening match records using v2, and `_timestamp_endpoint_for_candidate` skips only operation markers. Required regressions are mixed RX→annotation→RX matches, subsequent timestamped RX, append/reopen/read-only terminal validation and rolling eviction.

## 2. Bounded plain text and honest attribution

**Decision**: Exact 1..1024 UTF-8 bytes, no NUL/surrogates, no normalization. Closed declared surfaces cli/http/core, HTTP permits cli/http, CLI fixes cli. Fixed assertion_class=client_assertion and attribution_basis=client_asserted. Text in exact UTF-8 BLOB; canonical fixed metadata.

**Rationale**: Core14.7 requires short attributed assertions, not arbitrary metadata or verified identity. The existing shared Bearer token cannot authenticate an executable/process surface. A byte bound handles multibyte text consistently and fits16384 request bytes even at worst-case JSON escaping with the session limit.

**Alternatives**: Verified per-client identity requires unrelated credential infrastructure. Silently trusting cli over HTTP overstates provenance. Forcing all origins to http loses the explicitly declared CLI origin. Structured annotations, attachments and binary input expand the slice. A larger text limit would needlessly pressure quotas/body limits.

## 3. Host receipt time distinct from admission and commit

**Decision**: Existing clock boundary/origin, sampled for the recorded timestamp only while holding the sole coordinator append gate immediately before submission. Ordinary sequence defines order. Admission limiter uses a separate earlier sample. Fresh post-ACK sampling remains necessary for Monitor publication.

**Rationale**: This places the assertion at Core's serialized insertion point without caller backdating or conflating host time with backend observation/DUT action. A delayed journal append cannot turn its pre-append timestamp into a late Monitor publication time.

**Alternatives**: Caller time/backdating invents unverifiable event order; wall-clock time adds an unnecessary nondeterministic boundary; backend timestamps misrepresent provenance; a separate annotation writer breaks serialization. No new clock port is needed: observation_runtime already reuses MonotonicMonitorClock per runtime via `_clocks` across attaches.

## 4. One owner and a shared rolling budget

**Decision**: One pending owned annotation per run and ten admitted attempts per rolling second per runtime incarnation. Samples retained in a deque of at most ten plus last valid sample/origin. No queue/delay; admitted failures/cancellation consume budget, pre-admission rejection does not. Bind origin at first actual admission; reject later changed/backward/invalid clock without resetting budget.

**Rationale**: Fixed small state enforces Core size/rate bounds independently of delivery and prevents clients/reattach from resetting per-client counters. A pending disk write is protected by ownership, never by a fabricated wall-clock I/O deadline.

**Alternatives**: Per-HTTP-only/per-client limits are bypassable by direct Core or changing client labels. Per-session reset permits reattach to reset the limit. Persistent limiter storage, token-bucket bursts and rate configuration add unnecessary policy. Checking only successful commits permits unbounded failing submissions.

## 5. Optional preparation capability and existing job ownership

**Decision**: Optional annotation access reuses the transferred coordinator/session/policy/clock and supplies a pure max-width codec-charge callback. Reuse eight existing service mutation jobs; one Core annotation owner. Keep eight reads and independent Monitor job. Add synchronous service-stop annotation sealing before snapshots and join admitted insertion before writer close.

**Rationale**: Existing lifecycle/cleanup infrastructure already provides ownership. Admitted session-level assertions may settle after SegmentEnded and do not need Monitor's later ACTIVE/segment revalidation. No new attach rejection for callers omitting support; no capture-fact reinterpretation after marker-only failure.

**Alternatives**: A new service pool/queue/general job registry is needless. Holding the lifecycle lock across durable work risks deadlock; cancelling on disconnect or reopening a writer violates005/008/009. Revalidating an admitted request after detach can silently discard its bound intent.

## 6. Ordinary charge, retention and retrieval

**Decision**: Existing exact charge formula; max-width receipt timestamp preflight against record/retained/page maxima before admission. Zero RX bytes and NULL backend timestamp endpoints. Existing record/page routes/commands gain one closed variant, with unchanged snapshots/cursors/expiry/413 and terminal read-only semantics.

**Rationale**: Annotation is ordinary evidence, not retained metadata exempt from quota. Client context can expire and must not be pinned. Existing receipt/reference patterns suffice; acknowledgement is not a retention or exactly-once promise.

**Alternatives**: Reserving or pinning context changes rolling retention; trimming text changes the assertion; a separate annotation catalogue or historical insertion is outside scope; returning only an unacknowledged reference falsely claims durability.

## 7. Exact additive delivery

**Decision**: POST /v1/observation/annotations; strict closed session_id/text/client_surface body, existing16384 cap/security-before-body/no-store. One thin annotate command with required --session/--text. Existing transport/response budgets/exits retained; new429 annotation/rate_limited is a fixed recognized remote error, never auto-retried.

**Rationale**: Authenticated bounded delivery patterns already exist in006–009. The security raw-route allowlist and readiness-before-body special path both need the new literal route. CLI cannot enforce authoritative rate, timing, lifecycle or persistence policy.

**Alternatives**: Unauthenticated debug insertion, CLI journal access, client sleep/retry, arbitrary sender fields and additional read endpoints each violate scope or existing boundaries.
