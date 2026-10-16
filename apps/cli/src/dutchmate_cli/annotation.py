"""Closed annotation wire values; no Core imports or insertion policy."""

from dutchmate_cli import context, evidence

_ERRORS = {
    (404, "no_associated_session"),
    (409, "session_not_associated"),
    (409, "not_active"),
    (503, "annotation_unavailable"),
    (422, "evidence_policy_incompatible"),
    (409, "busy"),
    (429, "rate_limited"),
    (413, "delivery_too_large"),
}


def request(session: str, text: str) -> dict[str, object]:
    try:
        return {
            "session_id": evidence._input_session(session),
            "text": evidence._annotation_text(text),
            "client_surface": "cli",
        }
    except ValueError, TypeError:
        pass
    raise context.CliFailure(context.CliFailureKind.INVALID_ARGUMENTS)


def reply(value: object) -> dict[str, object]:
    view = evidence._view(value, ("run_id", "session_id", "reference", "annotation"))
    evidence._text(view["run_id"])
    evidence._input_session(evidence._text(view["session_id"]))
    reference = evidence._view(view["reference"], ("session_id", "sequence"))
    evidence._input_session(evidence._text(reference["session_id"]))
    evidence._counter(reference["sequence"], maximum=evidence._MAX - 1)
    record = evidence._client_annotation(view["annotation"])
    evidence._choice(record["client_surface"], {"cli", "http"})
    if (
        reference["session_id"] != view["session_id"]
        or reference["sequence"] != record["sequence"]
    ):
        raise ValueError("invalid_response")
    view["reference"], view["annotation"] = reference, record
    return view


def recognized_error(value: object, status: int) -> bool:
    error = evidence._view(
        evidence._view(value, ("error",))["error"], ("source", "code")
    )
    source, code = evidence._text(error["source"]), evidence._text(error["code"])
    return (source == "annotation" and (status, code) in _ERRORS) or (
        source == "journal" and (status, code) in evidence._JOURNAL_ERRORS
    )
