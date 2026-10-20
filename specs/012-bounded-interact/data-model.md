# Data Model: Bounded Interact

The values below describe the bounded transaction and its explicit additive
versions independently of task progress.
[Contract](contracts/interact.md) defines exact fields/validation/serialization;
current verification is in development status. No general command/event model.

## New Values and Constraints

| Value | Constraint / relationship |
|---|---|
|InteractRequest|`payload: bytes length1..4096`; `conditions: tuple count1..4, each bytes length1..256`; `timeout_ms: exact int1..4000`; `max_rx_bytes: exact int1..1048576`; explicit SessionId|
|BackendWriteResult|`status: acknowledged/partial/timeout/disconnected/failure`; prefix0..N only on normal return, null for unknown exception progress; no bool|
|TX facts|`submitted=false` requires not_submitted/null count/null failure; otherwise normalized result; `acknowledgement_scope=backend_acceptance`; `settled_at_ns: exact int0..MAX`|
|InteractionPolicy|RX/recording true, TX exact bool defaultfalse, Control/reconnect false; independent new v2 type|
|ResolvedInteractionProfile|Explicit version2, same004 closed shape; immutable captured policy; no v1 constructor relaxation|
|Observation|009 window/count/loss/clock; match adds `condition_index: exact int0..conditions.count-1`; prefix state<=1024 bytes|
|Report|Identity/provenance/request/outcome, mandatory start ref, nullable TX/end refs, independent TX/observation, four-state durability, <=2 audit failures|
|PreparedInteractAccess|Optional defaultNone; matching session/policy/coordinator/clock and pure charge callback; no physical handle|

MAX=9223372036854775807; sequences0..MAX-1. No caller clock/permission/operation
ID/cursor/backend ref. Wire sessions retain0081..256 UTF-8 bytes/no NUL.

## Evidence

`InteractStartedEvidence`, `UartTxSettledEvidence`, `InteractEndedEvidence` plus
pending counterparts; kind/version/BLOB/metadata exactly contract§5. Only new
records use version4. Start stores requested bytes, not confirmed wire bytes.
End repeats actual TX summary after an unconfirmed intermediate audit ACK.

Zero RX telemetry/null backend endpoints; ordinary003 charge/rolling retention,
no table/reservation/pin. Refs can expire before delivery; unpaired retained/crash
records legal. Pair agreement checked only where corresponding records remain.

## State and Owner Boundaries

Normal TX/audit: admitted → intent_pending → intent_acknowledged → write_submitted
→ write_settled → audit_settled. Stop before submission permits not_submitted;
intent ACK failure never permits write. Once registered, join despite cancellation.
Slot stays occupied through audit; no public task catalogue.

Observation runs independently: observing → frozen(matched/timeout/byte_limit/
connection/failure/stop/tx_failed). Keep only bounded prefixes/counters/positions/
one decision, no RX transcript. Overall waits for write settlement and follows
contract§4 precedence; frozen observation never rewritten. Continue the external
boundary/stop latch after observation freezes until overall decision.

Seal → join write → physical close. Join acquisition and Interact audit → final
Follow metadata/read cleanup → recorder close. Writer never waits for audit or
network.005/008 cleanup uncertainty remains independent.

## Compatibility Matrix

| Boundary | Legacy | Explicit new |
|---|---|---|
|Profile|TOML1/current values unchanged|TOML2/new values, TX false default|
|Basic|Default RX-only/provenance1|Opt-in writer/provenance2/fixed1000 ms wait|
|Journal|Default1, explicit2/3 unchanged|Explicit4, seven delegated codecs plus three kinds|
|Composition|Profile1 → journal3|Profile2 → journal4|
|API|v1 runs/shapes unchanged|v2 Profile1/2, schemas1–4, Interact|
|CLI|Default version1 unchanged|Explicit2 paths/validators; Interact requires2|

V1 selecting a v2-only run rejects unsupported_api_version before action/query;
never filter a v4 stream. No migration or automatic fallback.
