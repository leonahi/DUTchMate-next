# Data Model: Local Observation Service

No Core model or evidence union changes. Bootstrap schema below is separate from
feature-003 journal schema-v1. HTTP rules are in [the contract](contracts/local-observation-service.md).

## ServiceConfig and bootstrap values

ServiceConfig: required port integer1..65535 (not bool), host exactly127.0.0.1
(default) or ::1. No workers/reload, arbitrary bind address, alternate state root,
credential input, Profile default or journal default.
BootstrapFailure: ordinary exception with read-only normalized kind (not frozen
exception transport), no raw cause/message copied to HTTP/logs. Kinds:
unsupported_platform, invalid_configuration, unsafe_bootstrap, owner_active,
previous_cleanup_unconfirmed, bootstrap_io_failed, listener_unavailable,
teardown_incomplete. These are process/bootstrap failures, not runtime issues.

Effective UID/passwd home selects fixed private directory; token is exactly64
lowercase hex ASCII characters from32 cryptographic random bytes, file65 bytes
including LF. Token/lock/marker files0600, directory0700, no unsafe links or ownership.
Owner marker: strict singleton version1 + cleanup_confirmed:boolean, max256 bytes.
Absent fresh → false before runtime → true only after all joined cleanup;
false/malformed on restart blocks. True replacement may already be visible if
subsequent fsync fails; actual cleanup was confirmed, but durable publication is
not claimed successful. No PID, path, Profile or session history.

Service phases: starting → ready → stopping → stopped; latched startup stop goes
starting → stopping → stopped without admission. Startup failure enters
stopped after unwind. Only ready accepts new mutations. HTTP status envelope
service_state is ready or stopping; starting/stopped do not serve new requests.
One runtime and finite registry of at most8 pending mutations; no public operation IDs.

## Attach request

Exactly profile_path and journal_path: each explicit absolute POSIX string,
1..4096 UTF-8 bytes, no NUL; no coercion, missing/extra/duplicate fields,
NaN/infinity, expansions or filesystem probing. Maximum actual body16384 bytes,
read at most16385. GET status and POST detach have zero body bytes.

## StatusEnvelope and RuntimeStatusView

Exactly service_state and runtime. RuntimeStatusView has these exact keys:

| Key | JSON projection |
|---|---|
| state | Feature-005 RuntimeState string |
| run_id | RunId.value string or null |
| profile | ProfileView below or null |
| session_id | SessionId.value string or null |
| acquisition | AcquisitionView below or null |
| stop_intent | Feature-005 RuntimeStopIntent string |
| terminal_reason | Feature-005 RuntimeTerminalReason string or null |
| primary_issue | IssueView or null |
| cleanup_issues | Ordered array of0..2 IssueViews |
| owner_settled | boolean |
| physical_release_confirmed | boolean |
| recorder_close_confirmed | boolean |
| attach_admissible | derived feature-005 boolean, never independently computed from HTTP codes |

ProfileView contains exactly format_version (integer1), dut (id/name strings),
backend (kind/expected_device strings), uart (baud_rate/data_bits/parity/stop_bits/
hardware_flow_control/software_flow_control with their existing numeric/string/
boolean types), open_lines (dtr/rts strings), policy (uart_rx_enabled,
evidence_recording_enabled, uart_tx_enabled, semantic_control_enabled,
automatic_reconnect_enabled booleans), session_policy (six existing SessionPolicy
integer fields). Project captured immutable values, never reread source. Device
selector is existing resolved Profile data, not Profile source/journal destination.

IssueView exactly source and code strings from normalized feature-005 values.
No detail, exception, message, traceback or context.

AcquisitionView exactly state, descriptor, provenance, terminal_trigger,
primary_failure_kind, close_failed, physical_release_confirmed. Nullable fields
remain null; actual primary kind projects directly, independent of trigger/close.
DescriptorView exactly capabilities, backend_observation_timestamp_domain,
loss_observability, connection_provenance. ProvenanceView adds connection_id and
segment_id string values to those same descriptor fields. Only committed provenance
supplies IDs; descriptor alone never invents them.

- capabilities: sorted array of reported BackendCapability.value strings.
- backend_observation_timestamp_domain: exact domain_id/observer/meaning/unit/origin_id
  fields with existing string meanings, without timestamp conversion.
- loss_observability: {"kind":"upstream_loss_not_observable"} or
  {"kind":"observer_reports_uart_loss","observer_id":string,"scope":string}.
  These are normalized loss variants, not backend identity cases.
- connection_provenance: generic to_snapshot() envelope with exact envelope_version,
  backend_kind, backend_schema_version and fields array of {"name":string,"value":scalar}.
  Preserve order/scalar null/bool/int/string, without decoding opaque backend identity.

JSON objects above are closed. Enum values are current completed-contract values;
optional unknowns remain null. No filesystem source paths, UART bytes, resource/task
handles, private object dumps, record reconstruction or growing summaries.
Response encoding is bounded to1048576 UTF-8 bytes (1MiB), stopping at bound+1.
Overflow returns500 service/internal_failure, never silently truncates or changes runtime.
No generic recursive serialization of arbitrary backend/task objects.

## ErrorEnvelope

Exactly {"error":{"source":string,"code":string}}. Sources request/profile/runtime/
service; allowable code/status pairs are only those in contract §5.
Malformed transport rejected before ASGI may return fixed input-free400 plain text;
application errors use this envelope. Errors carry no runtime rollback/success assertion or echoed input.200 RuntimeStatus
with failed state is not rewritten into an admission error. JSON field order is
irrelevant; array order and nullable facts are authoritative.

## Internal operation ownership

One service-owned task plus its bounded validated paths until completion. Created/
registered atomically before any await, retained strongly until done. Handler delivery
is a separate waiter. Terminal result/exception is consumed and task/paths discarded.
Shutdown closes registration → joins all tasks → runtime.detach settlement → inspect
owner_settled AND both cleanup facts → invalidate credential/close listener → marker.
No queue, history, replay cache, public task reference or lifecycle cancellation.
