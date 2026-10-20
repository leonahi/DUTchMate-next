# Research: Bounded Interact

**Date**: 2026-10-18. Read-only source/spec research; no tests or hardware.
Core/completed001–011 govern; exact decisions: [contract](contracts/interact.md).

## Optional writer and serialization

**Decision**: Optional normalized connection writer, existing UART_SEND, one
fail-fast Interact owner through settlement. **Rationale**: `backend.py` is RX-only;
`model.py` already has UART_SEND. Old connections/preparations remain usable.
**Alternatives**: Mandatory writer breaks them; send queues/public TX/generic
commands exceed scope; backend-name checks violate Core17.

## Fixed wait and unknown progress

**Decision**: Basic1000 ms write timeout configured while closed, one worker/write,
exact returned prefix or null on exception; no retry/drain.
**Rationale**: Installed locked pyserial3.5 `serialposix.py:write` can accept a
prefix then raise timeout without returning progress; `serialwin32.py:write`
raises finite-time short writes and can return short counts on cancellation.
`serialutil.py:write_timeout` reconfigures an open port. Local dependency source
was inspected; no claim about newer/uninstalled versions.
**Alternatives**: Runtime mutation risks RX configuration; zero/full on exception
fabricates facts; asyncio timeout abandonment loses ownership. No hard OS deadline.

## Boundary and independent decisions

**Decision**: Durable payload intent before write, observation from intent+1,
early match independent of ACK/overall outcome. **Rationale**: Starting after ACK
can miss fast responses; `monitor.py` already has commit gate/post-ACK publication.
**Alternatives**: Holding the gate during write blocks RX; copied/retrieved RX
matching duplicates the stream. Three kinds preserve Monitor's closed marker kind.

## Join at the actual owner

**Decision**: Acquisition admission/seal/join and defensive Basic join-before-close;
runtime joins audit later before recorder close. **Rationale**: Acquisition owns
the connection and closes it before runtime's current operation joins, including
natural failure. `_close_connection` is the existing common choke point.
**Alternatives**: Runtime-only joining is too late; a second owner violates Core;
waiting for audit in physical-close join can cycle; forced timeout cannot prove cleanup.

## Profile and journal versions

**Decision**: Distinct immutable Profile2/policy, journal4/new codecs; keep v1 values
and seven old codecs exact. **Rationale**: `ObservationPolicy` rejects TX itself;
relaxing it broadens v1. Strict SQLite versions/ordinary charges are established
in003/009/010. Extend terminal dispatch, timestamp-context handling and host-only
endpoint scans without changing legacy behavior.
**Alternatives**: Overrides bypass policy; silent upgrade/repair/guessing violates
compatibility; sidecars/tables or retention pins add competing evidence/storage.

## Explicit delivery versions

**Decision**: Literal API2 paths and global CLI --api-version2; default1.
**Rationale**: `client.py:_profile` accepts only1; evidence/Follow have closed seven
variants. V1 must not silently emit new shapes or a filtered stream. Reuse handlers.
**Alternatives**: Widening v1 breaks old clients; auto-probing/fallback adds requests
and unsafe retry; generic version/command infrastructure is unnecessary.

## Cancellation and audit uncertainty

**Decision**: Operation-local cancellation latch, suppress before registration,
join/audit after; attempt TX settlement then end independently. End repeats actual
TX facts if intermediate ACK failed. **Rationale**: Cancellation cannot undo bytes;
intent ACK is not submission, and failed audit ACK does not prove row absence.
Keep009/010 delivery-only cancellation unchanged; seal before HTTP drain as011.
**Alternatives**: Abandoning write or retrying uncertainty risks untracked/double
effects. No public cancellation endpoint/results catalogue needed.

## Research limits

One1200-token Graphify query returned a truncated989-node traversal. It located
candidates, not a complete map. Direct source/contracts and two read-only research
reviews established these decisions. No graph rebuild, agent edits, test run,
serial enumeration/open or physical action. Native/driver/electrical/Enhanced
acceptance remains outstanding. No unresolved contract question remains.
