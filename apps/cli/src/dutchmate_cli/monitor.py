"""Closed Monitor wire values; no Core imports or observation policy."""

from dutchmate_cli import context, evidence

_ERRORS = {
    (404, "no_associated_session"),
    (409, "session_not_associated"),
    (409, "not_active"),
    (503, "monitor_unavailable"),
    (409, "capability_unavailable"),
    (409, "busy"),
    (422, "evidence_policy_incompatible"),
    (413, "delivery_too_large"),
}


def request(
    session: str, condition_base64: str, timeout_ms: int, max_rx_bytes: int
) -> dict[str, object]:
    try:
        return {
            "session_id": evidence._input_session(session),
            "condition_base64": evidence._condition_base64(condition_base64),
            "timeout_ms": evidence._counter(timeout_ms, minimum=1, maximum=4000),
            "max_rx_bytes": evidence._counter(max_rx_bytes, minimum=1, maximum=1048576),
        }
    except ValueError, TypeError:
        pass
    raise context.CliFailure(context.CliFailureKind.INVALID_ARGUMENTS)


def _reference(value: object) -> dict[str, object]:
    view = evidence._view(value, ("session_id", "sequence"))
    evidence._text(view["session_id"])
    evidence._counter(view["sequence"], maximum=evidence._MAX - 1)
    return view


def _end_failure(value: object) -> dict[str, object]:
    view = evidence._view(value, ("source", "code"))
    source = evidence._text(view["source"])
    code = evidence._text(view["code"])
    if (
        source == "journal" and code in {code for _, code in evidence._JOURNAL_ERRORS}
    ) or (source == "service" and code == "internal_failure"):
        return view
    raise ValueError("invalid_response")


def reply(value: object) -> dict[str, object]:
    view = evidence._view(
        value,
        (
            "run_id",
            "session_id",
            "operation_id",
            "provenance",
            "outcome",
            "started_record",
            "ended_record",
            "window",
            "examined_rx_bytes",
            "observer_loss_records",
            "match",
            "clock",
            "durability",
            "end_failure",
        ),
    )
    evidence._text(view["run_id"])
    evidence._text(view["session_id"])
    evidence._uuid(view["operation_id"])
    view["provenance"] = evidence._provenance(view["provenance"])
    view["started_record"] = _reference(view["started_record"])
    evidence._operation_facts(view)
    durability = evidence._choice(view["durability"], {"complete", "end_unconfirmed"})
    if durability == "complete":
        if view["end_failure"] is not None:
            raise ValueError("invalid_response")
        view["ended_record"] = _reference(view["ended_record"])
    else:
        if view["ended_record"] is not None:
            raise ValueError("invalid_response")
        view["end_failure"] = _end_failure(view["end_failure"])
    return view


def recognized_error(value: object, status: int) -> bool:
    error = evidence._view(
        evidence._view(value, ("error",))["error"], ("source", "code")
    )
    source, code = evidence._text(error["source"]), evidence._text(error["code"])
    return (source == "monitor" and (status, code) in _ERRORS) or (
        source == "journal" and (status, code) in evidence._JOURNAL_ERRORS
    )
