# Data Model: Observation CLI

Delivery-only values; no Core/evidence/Profile/runtime/schema changes.
[CLI contract](contracts/observation-cli.md) defines exact external behavior;
[006 data model](../006-local-observation-service/data-model.md) defines reports.

## Invocation options

- host: string exactly127.0.0.1(default) or::1.
- port: optional during parsing/help; actual commands require exact integer1..65535.
- command: attach/status/detach, chosen by Typer; no aliases or job IDs.
- profile/journal: attach-only strings, each absolute POSIX1..4096 UTF-8 bytes,
  no NUL; no existence/resolve/read/expansion/domain validation.
- No credential path/token, arbitrary URL, timeout, output-mode, process-manager
  or Profile/session discovery value.

Argument validation precedes credential/network. Callback stores values only;
commands validate actual target/lexical inputs. Help needs no valid target.

## Credential read

Fixed passwd/effective-UID location, exactly65 bytes:64 lowercase hex+LF.
Read-only no-follow descriptor traversal; file regular/effective UID/0600/nlink1;
at most66 bytes including detection. Cached token excludes LF and exists only
during one invocation/request. No mutable store, bootstrap state, lock/marker,
directory ownership-policy replica, generation, refresh/retry or persistence.

Ordinary client failure exceptions may carry only a fixed code; do not use frozen
exception dataclasses or input-bearing request/response/credential metadata.

## Client delivery phase

One per-invocation value, never shared with service:
not_submitted → unknown → report_received.

- not_submitted: before attempting any operation request.
- unknown: set synchronously immediately before the request attempt, until a
  complete documented response is validated. This conservatively includes
  connection failure and malformed response, without inferring service admission.
- report_received: valid006 StatusEnvelope/ErrorEnvelope received by CLI; final
  terminal output can still fail or be interrupted.

This describes HTTP delivery, not the actual attach/detach outcome, service task
identity, Core stop intent or physical ownership. No replay cache/history/queue.
If interruption makes phase unavailable, conservatively report unknown after an
attempt; never optimistically claim rollback.

## ClientErrorEnvelope and exit mapping

Exactly error and request_outcome. error has exactly source:"cli" and one fixed
code; request_outcome is one of the three values above.

| Code | Exit |
|---|---|
| invalid_arguments |2|
| unsupported_platform |3|
| credential_unavailable |3|
| unsafe_credential |3|
| request_timeout |5|
| transport_failed |5|
| invalid_response |5|
| interrupted |130|
| output_failed |1|
| internal_failure |1|

No detail/message/path/body/header/token/exception fields. Successful help/report
exit0; valid remote ErrorEnvelope exit4. Exit0 never means successful runtime
activation/detachment; inspect the complete report.

## Delivered wire values

Use006's closed StatusEnvelope/RuntimeStatusView/ProfileView/AcquisitionView/
provenance/loss/IssueView keys and JSON types. Optional unknowns stay null; arrays
and generic fields retain order and scalar types. Capability values and provenance
are reported data, not selection of Basic/Enhanced logic.

Validate wire shape, not domain cross-field invariants: no recomputed
attach_admissible/cleanup certainty, Profile policy validation, failure trigger
decoding, timestamp conversion or generic arbitrary-object serialization.
No Core/service imports or construction of ResolvedDutProfile/RuntimeStatus.
Server ErrorEnvelope remains exactly006's source/code with documented HTTP pairs.

Keep at most1048577 raw response bytes; accept body<=1048576. Strict JSON/media/
encoding then bounded compact UTF-8 serialization<=1048576, plus LF for output.
No partial record on intentional validation failure. JSON object allocation and
HTTP stack buffering are finite by input/protocol bounds but not claimed to be
exactly the accumulator size. No UART/evidence bytes/decoded text are delivered here.

## Compatibility

Core remains only owner of Profile/runtime/backend/journal facts.006 remains
authenticator/admitted-operation owner.003 schema-v1 and004 Profile-v1 unchanged.
Transport deadline and local delivery phase cannot become Core lifecycle semantics.
