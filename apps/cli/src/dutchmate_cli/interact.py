"""Bounded Interact wire validation; Core alone owns execution and matching."""

import base64
from typing import cast

from dutchmate_cli import context, evidence

_ERRORS = {
    (404, "no_associated_session"),
    (409, "session_not_associated"),
    (409, "not_active"),
    (409, "busy"),
    (409, "policy_denied"),
    (409, "capability_unavailable"),
    (503, "interact_unavailable"),
    (422, "evidence_policy_incompatible"),
    (413, "delivery_too_large"),
}


def request(
    session: str,
    payload_base64: str,
    conditions_base64: list[str],
    timeout_ms: int,
    max_rx_bytes: int,
) -> dict[str, object]:
    try:
        return {
            "session_id": evidence._input_session(session),
            "payload_base64": evidence._payload_base64(payload_base64),
            "conditions_base64": evidence._conditions(conditions_base64),
            "timeout_ms": evidence._counter(timeout_ms, minimum=1, maximum=4000),
            "max_rx_bytes": evidence._counter(max_rx_bytes, minimum=1, maximum=1048576),
        }
    except ValueError, TypeError:
        raise context.CliFailure(context.CliFailureKind.INVALID_ARGUMENTS) from None


def _reference(value: object, session: str) -> dict[str, object]:
    view = evidence._view(value, ("session_id", "sequence"))
    if evidence._input_session(evidence._text(view["session_id"])) != session:
        raise ValueError("invalid_response")
    evidence._counter(view["sequence"], maximum=evidence._MAX - 1)
    return view


def reply(value: object, requested: dict[str, object]) -> dict[str, object]:
    view = evidence._view(
        value,
        (
            "run_id",
            "session_id",
            "operation_id",
            "provenance",
            "payload_base64",
            "conditions_base64",
            "outcome",
            "started_record",
            "tx_settled_record",
            "ended_record",
            "tx",
            "observation",
            "durability",
            "audit_failures",
        ),
    )
    evidence._text(view["run_id"])
    session = evidence._input_session(evidence._text(view["session_id"]))
    evidence._uuid(view["operation_id"])
    payload = evidence._payload_base64(view["payload_base64"])
    conditions = evidence._conditions(view["conditions_base64"])
    if any(
        view[key] != requested[key]
        for key in (
            "session_id",
            "payload_base64",
            "conditions_base64",
        )
    ):
        raise ValueError("invalid_response")
    provenance = evidence._view(
        view["provenance"],
        (
            "connection_id",
            "segment_id",
            "capabilities",
            "backend_observation_timestamp_domain",
            "loss_observability",
            "connection_provenance",
            "boundary_basis",
            "causation",
        ),
    )
    limits = {key: provenance.pop(key) for key in ("boundary_basis", "causation")}
    evidence._choice(limits["boundary_basis"], {"core_observation_order"})
    evidence._choice(limits["causation"], {"not_established"})
    view["provenance"] = {**evidence._provenance(provenance), **limits}
    start = _reference(view["started_record"], session)
    tx_ref = (
        None
        if view["tx_settled_record"] is None
        else _reference(view["tx_settled_record"], session)
    )
    end_ref = (
        None
        if view["ended_record"] is None
        else _reference(view["ended_record"], session)
    )
    start_sequence = evidence._counter(start["sequence"])
    if tx_ref is not None:
        evidence._counter(tx_ref["sequence"], minimum=start_sequence + 1)
    end_sequence = None
    if end_ref is not None:
        end_sequence = evidence._counter(
            end_ref["sequence"], minimum=start_sequence + 1
        )
        if tx_ref is not None and end_sequence <= evidence._counter(tx_ref["sequence"]):
            raise ValueError("invalid_response")
    tx = evidence._tx_facts(view["tx"])
    observation = evidence._interact_observation(view["observation"])
    evidence._interact_facts(
        start_sequence, tx, observation, view["outcome"], end_sequence=end_sequence
    )
    size = len(base64.b64decode(payload, validate=True))
    if (tx["status"] == "acknowledged" and tx["accepted_prefix_bytes"] != size) or (
        tx["status"] == "partial"
        and evidence._counter(tx["accepted_prefix_bytes"]) >= size
    ):
        raise ValueError("invalid_response")
    clock = cast(dict[str, object], observation["clock"])
    if (
        evidence._counter(clock["deadline_at_ns"])
        - evidence._counter(clock["started_at_ns"])
        != evidence._counter(requested["timeout_ms"]) * 1000000
    ):
        raise ValueError("invalid_response")
    examined = evidence._counter(observation["examined_rx_bytes"])
    maximum = evidence._counter(requested["max_rx_bytes"])
    if examined > maximum or (
        observation["outcome"] == "byte_limit" and examined != maximum
    ):
        raise ValueError("invalid_response")
    match = observation["match"]
    if match is not None:
        match = cast(dict[str, object], match)
        index = evidence._counter(match["condition_index"], maximum=len(conditions) - 1)
        length = len(base64.b64decode(conditions[index], validate=True))
        first, last = (
            cast(dict[str, object], match["start"]),
            cast(dict[str, object], match["end"]),
        )
        if examined < length or (
            first["sequence"] == last["sequence"]
            and (
                evidence._counter(last["byte_offset_exclusive"])
                - evidence._counter(first["byte_offset"])
                != length
            )
        ):
            raise ValueError("invalid_response")
    missing = tuple(
        kind
        for kind, ref in (("uart_tx_settled", tx_ref), ("interact_ended", end_ref))
        if ref is None
    )
    expected = {
        (): "complete",
        ("uart_tx_settled",): "tx_unconfirmed",
        ("interact_ended",): "end_unconfirmed",
        ("uart_tx_settled", "interact_ended"): "both_unconfirmed",
    }[missing]
    evidence._choice(view["durability"], {expected})
    failures = evidence._array(view["audit_failures"])
    if len(failures) != len(missing):
        raise ValueError("invalid_response")
    checked: list[dict[str, object]] = []
    for kind, failure in zip(missing, failures, strict=True):
        item = evidence._view(failure, ("record_kind", "source", "code"))
        evidence._choice(item["record_kind"], {kind})
        evidence._tx_audit_failure({"source": item["source"], "code": item["code"]})
        checked.append(item)
    view.update(
        started_record=start,
        tx_settled_record=tx_ref,
        ended_record=end_ref,
        tx=tx,
        observation=observation,
        audit_failures=checked,
    )
    return view


def recognized_error(value: object, status: int) -> bool:
    error = evidence._view(
        evidence._view(value, ("error",))["error"], ("source", "code")
    )
    source, code = evidence._text(error["source"]), evidence._text(error["code"])
    return (
        (source == "interact" and (status, code) in _ERRORS)
        or (source == "journal" and (status, code) in evidence._JOURNAL_ERRORS)
        or (source == "service" and (status, code) == (503, "interact_capacity"))
    )
