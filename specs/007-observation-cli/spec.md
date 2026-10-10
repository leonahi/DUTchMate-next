# Feature Specification: Observation CLI

**Feature Directory**: `007-observation-cli`
**Feature Branch**: `main` (sequential feature directories do not create branches)
**Created**: 2026-10-08
**Status**: T001–T025 software-complete; separately authorized final pre-commit review and fresh2261 tests passed, zero failures/errors/skips, Ruff/mypy61 files/7 import contracts/diff checks clean. Complete24-file staged/installability review passed; no new defect or code/test/config/dependency/contract change. This snapshot belongs to `Implement observation CLI` (Git revision `:/^Implement observation CLI`), accepted parent c2c9ce3. Native evidence remains macOS only; Linux/Windows, native active-DUT lifecycle and physical/electrical acceptance remain unexecuted.
**Input**: Minimal authenticated observation-only CLI for feature006 attach/status/detach; Typer is mandatory and belongs only in CLI delivery.

Core governs, especially §§5.2,13,14,15.1,16.3–16.5,17.4,18,19,22.2 A/H/J.
[Feature006](../006-local-observation-service/contracts/local-observation-service.md)
defines authoritative HTTP, authentication and admitted-request lifetime semantics.
Features001–005 retain their execution/Profile/evidence contracts. Exact CLI
grammar, output, exit codes and bounds belong in
[the CLI contract](contracts/observation-cli.md). No service/Core contract revision.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Inspect one authenticated local service (Priority: P1)

A developer uses help without needing a running service, then selects an already-
running numeric loopback listener and inspects its actual observation status.

**Why this priority**: Establish the human acceptance/client boundary on existing behavior.
**Independent Test**: Installed help and status with isolated credentials, actual006
security/lifespan paths and hardware tripwires; malformed arguments perform no I/O.

**Acceptance Scenarios**:
1. **Given** no command or a supported help invocation, **When** CLI runs, **Then**
   static help exits0 without account lookup, credential access, network or device work.
2. **Given** explicit listener port and safe current credential, **When** status runs,
   **Then** one authenticated HTTP request returns the complete bounded report.
3. **Given** a bad target, unsafe/missing credential or rejected authentication,
   **When** CLI runs, **Then** a fixed categorized error appears without input/token echo.
4. **Given** attaching/active/detaching/inactive/terminated/failed status, **When** inspected,
   **Then** the existing facts remain intact, including absent values and cleanup uncertainty.

### User Story 2 - Request observation attach and detach (Priority: P2)

A developer requests attach with an explicit Profile and fresh journal destination,
then uses status or detach without becoming a hardware or journal owner.

**Why this priority**: Expose the accepted lifecycle without adding a second implementation.
**Independent Test**: Actual006 app/Basic fake/temporary SQLite; CLI process exits,
ambient binary evidence persists, and explicit detach closes through005 only.

**Acceptance Scenarios**:
1. **Given** absolute Profile/journal arguments, **When** attach runs, **Then** the
   existing service resolves/prepares/adopts them; CLI opens neither file nor DUT.
2. **Given** busy/uncertain ownership or invalid Profile, **When** rejected,
   **Then** the existing HTTP error category is presented with no automatic retry.
3. **Given** HTTP200 with failed/immediately terminal runtime, **When** delivered,
   **Then** its report is emitted unchanged in meaning; exit0 confirms report delivery
   only, never active capture or successful cleanup.
4. **Given** successful CLI return, **When** that client exits, **Then** capture
   remains service-owned until explicit detach or authoritative terminal behavior.

### User Story 3 - End client waiting without abandoning service work (Priority: P3)

A developer can interrupt or encounter a finite HTTP timeout without inventing
service cancellation, mutation success or an automatic retry.

**Why this priority**: Delivery loss must preserve006 admitted-operation ownership.
**Independent Test**: Gated real service operations, slow/stalled/oversized responses,
installed-console SIGINT and privacy sentinels with isolated account/loopback only.

**Acceptance Scenarios**:
1. **Given** attach/detach may have reached the service, **When** timeout/Ctrl-C/loss
   ends delivery, **Then** no retry/detach/service signal occurs and mutation outcome
   is described as unknown; an explicit later status observes current facts only.
2. **Given** an indefinitely progressing response, **When** total waiting reaches
   its deadline, **Then** client waiting ends rather than resetting the budget per chunk.
3. **Given** malformed/oversized/noncontract responses, **When** rejected,
   **Then** no partial report, body/credential/exception echo or invented runtime fact appears.
4. **Given** invalid arguments, framework failures or output failure, **When** handled,
   **Then** diagnostics are bounded and input-free, without traceback or locals.

### Edge Cases

- Required port is absent; host is localhost/remote/wildcard/IPv4-mapped IPv6.
- Port80 must still appear explicitly in Host; selected IPv6 authority is bracketed.
- Root callback runs before subcommand help; no credentials may be loaded there.
- Shell syntax errors/unknown options contain private sentinel values.
- Credential changes/removes between read and request;401 does not refresh/replay.
- Credential path/file is symlinked, nonregular, wrong UID/mode/link count or oversized.
- HTTP redirect, compression, malformed JSON/duplicate keys/nonfinite numbers,
  unexpected media/status/envelope or truncation occurs.
- Response reaches exactly the body limit; one detection byte indicates overflow.
- Ctrl-C arrives before request, during send/headers/body or while rendering.
- A body chunk already buffered by the HTTP stack exceeds remaining capacity.
- Output pipe closes; no cleanup request is sent and no traceback leaks.
- Windows lacks supported credential primitives; help still works without platform checks.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: One installable product CLI MUST use Typer solely in CLI delivery; commands are attach/status/detach only.
- **FR-002**: CLI MUST be a thin HTTP client of006; no production Core/service imports or duplicated Profile/runtime/journal/backend/authentication-policy/ownership implementation.
- **FR-003**: Only explicit numeric127.0.0.1(default) or::1 plus required port1..65535 MUST target one already-running service; no arbitrary URL/DNS/proxy/fallback/discovery/autostart.
- **FR-004**: Help/no-command MUST exit0 without credential/account/platform/network/hardware preparation; usage errors MUST be input-free.
- **FR-005**: Actual commands MUST read the fixed effective-UID/passwd-home credential location, ignoring HOME/XDG/token/credential-path overrides.
- **FR-006**: Credential access MUST be read-only, descriptor-based/no-follow, UID-owned0600 regular singly linked file, bounded to65 expected bytes plus one detection byte.
- **FR-007**: Credential MUST be exact64 lowercase hex+LF, read once per invocation and discarded; no generation/rotation/lock/marker inspection, permission repair or401 refresh/replay.
- **FR-008**: Only one Authorization Bearer header MUST transport credentials; no URL/query/cookie/body/argv/environment or diagnostic token exposure.
- **FR-009**: Requests MUST use exact006 Host including port, no Origin/Sec-Fetch/Upgrade, fixed methods/routes and no query; service security remains authority.
- **FR-010**: Attach MUST require explicit absolute Profile/journal strings bounded per006; CLI performs lexical wire validation only, no file/provenance/policy/default resolution.
- **FR-011**: Status/detach MUST send no body; attach MUST send exactly006 fields; no new API or evidence delivery surface.
- **FR-012**: Each invocation MUST perform at most one operation request, with no retry/redirect/fallback/status follow-up or implicit detach.
- **FR-013**: HTTP waiting MUST have a10-second overall monotonic deadline and finite phase limits; the deadline never becomes a Core lifecycle timeout.
- **FR-014**: Response accumulation MUST retain at most1048577 bytes and reject above1048576, with raw uncompressed consumption; no promise of an exact socket-read ceiling.
- **FR-015**: Strict UTF-8 JSON/media/envelope validation MUST precede output, rejecting duplicates/nonfinite numbers and preserving006 wire types/keys without reimplementing domain invariants.
- **FR-016**: A valid HTTP200 MUST emit one bounded complete JSON StatusEnvelope on stdout and exit0, including failed runtime; this means report delivery only.
- **FR-017**: Existing primary/cleanup/trigger/certainty/admissibility/provenance/Profile/capability facts MUST be preserved; CLI MUST NOT recompute or reinterpret them.
- **FR-018**: Contract HTTP errors MUST emit the normalized ErrorEnvelope on stderr and exit4; never echo unrecognized bodies/headers/messages.
- **FR-019**: Local diagnostics MUST use fixed ClientErrorEnvelope categories plus truthful request_outcome (not_submitted/unknown/report_received) and documented exits:2 usage,3 credential/platform,5 transport/protocol,130 interrupt,1 unexpected/output failure.
- **FR-020**: Ctrl-C/request loss/timeout MUST end client delivery only, never signal/cancel the service, replay mutations or claim rollback/completion; uncertain mutations MUST be reported honestly.
- **FR-021**: An explicit subsequent status MUST NOT be represented as recovery/attribution of a lost operation result.
- **FR-022**: HTTP diagnostic logs and framework traceback/local rendering MUST be disabled; caught errors never stringify input-bearing exceptions.
- **FR-023**: Service/Core/schema-v1/Profile-v1/lifecycle contracts and existing security/import constraints MUST remain unchanged; add CLI boundaries after modules exist.
- **FR-024**: CLI MUST never open/read Profile/journal/DUT resources, enumerate hardware, create RX readers, implement timers/matchers/control/reconnect or execute external programs.
- **FR-025**: Initial actual-command platform support MUST match Linux/macOS POSIX credential access; unsupported-platform failure precedes credentials/network; portable Core is unchanged.
- **FR-026**: Tests MUST cover real Typer grammar plus installed entry-wrapper exit/privacy/SIGINT behavior, not just bypassed command callbacks.
- **FR-027**: Hardware-free authenticated integration MUST prove actual006 security/lifecycle, idle capture, client-loss ownership and unchanged001–006 regressions.
- **FR-028**: Applicable reported-fact assertions MUST exercise existing Basic/Enhanced-shaped fixtures without production Enhanced behavior or identity branching.
- **FR-029**: Full uv Ruff/mypy/Import Linter/hardware-free pytest/diff gates and installability MUST pass with strengthened boundaries and no exemptions.
- **FR-030**: No deferred retrieval/streaming/Monitor/TX/Control/reconnect/handoff/catalogue/Profile discovery/Enhanced/MCP/AI/hardware feature MUST be included.

### Key Entities

- CLI invocation: one command, explicit target and lexical arguments.
- Credential read: one private read-only process-local token, never a bootstrap owner.
- Client exchange: one bounded HTTP delivery, not a Core operation owner.
- Delivered report: existing StatusEnvelope/ErrorEnvelope; normalized local failure with client delivery phase otherwise, never a Core operation outcome.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Every help/usage-rejection test observes zero credential/network/device preparation.
- **SC-002**: Every actual invocation issues zero or one request and never opens Profile/journal/DUT resources.
- **SC-003**: Every delivered report preserves documented runtime facts across all six states and both fixture shapes.
- **SC-004**: Every timeout/loss/interrupt test leaves admitted service work authoritative with zero automatic retries/cleanup requests.
- **SC-005**: Every response respects retained-body/output bounds or fails explicitly without partial report.
- **SC-006**: Private sentinels never occur in captured client diagnostics/logs; completed001–006 regressions remain unchanged.

## Assumptions

- Accepted scope is client-only; existing controlled service launcher remains separate.
- Baseline HEAD c2c9ce3153ae24f333b9dcd77565d633d7ac780d;006 implementation
  b4c5730b2a5e593c10c06ad9e8f24c39e06f794b. All001–006 complete/committed.
- Operator explicitly supplies the existing listener port. This slice adds no server
  discovery/identity handshake or extension of006's local HTTP security model.
- Fixed compact JSON output is the smallest inspectable delivery; human formatting/
  alternate representations remain deferred. Exit0 deliberately retains006 report-delivery meaning.
- Credential filesystem calls and final terminal writes are not hard real-time guarantees;
  HTTP waiting alone has the specified cooperative deadline.
- Deferred: service startup/shutdown/daemon management, retrieval/streaming,
  Monitor/follow, TX/Interact/console/Control, reconnect, release/reacquire/handoff,
  annotations, session catalogue/naming/sealing, Profile discovery/defaults/reload,
  Enhanced production behavior, MCP/AI and physical-hardware acceptance.
