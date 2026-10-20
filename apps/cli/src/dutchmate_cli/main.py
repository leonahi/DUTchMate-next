"""Pure observation command grammar and a fixed-diagnostic console boundary."""

import asyncio
import errno
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Annotated, TypedDict, cast

import typer

from dutchmate_cli import annotation as annotation_wire
from dutchmate_cli import client, context, evidence
from dutchmate_cli import follow as follow_wire
from dutchmate_cli import interact as interact_wire
from dutchmate_cli import monitor as monitor_wire

app = typer.Typer(
    invoke_without_command=True,
    no_args_is_help=False,
    add_completion=False,
    suggest_commands=False,
    rich_markup_mode=None,
    pretty_exceptions_enable=False,
    pretty_exceptions_show_locals=False,
    context_settings={"color": False},
    help=(
        "Request observation from one already-running DUTchMate service. Exit 0 means a complete "
        "validated report was delivered, including failed runtime states. "
        "Request loss ends client waiting only; it does not cancel service work."
    ),
)


class _VersionOptions(TypedDict, total=False):
    api_version: int


@dataclass(slots=True)
class _Invocation:
    options: context.InvocationOptions = field(default_factory=context.InvocationOptions)
    delivery: client.DeliveryState = field(default_factory=client.DeliveryState)
    api_version: str = "1"

    def version_options(self) -> _VersionOptions:
        # Preserve existing v1 call shapes as well as their default validators.
        return {"api_version": 2} if self.api_version == "2" else {}


@app.callback()
def root(
    ctx: typer.Context,
    host: Annotated[str, typer.Option("--host", help="127.0.0.1 or ::1.")] = "127.0.0.1",
    port: Annotated[int | None, typer.Option(
        "--port", help="Required service port (1..65535) for commands.", show_default=False,
    )] = None,
    api_version: Annotated[str, typer.Option(
        "--api-version", help="Explicit HTTP API version: 1 or 2.",
    )] = "1",
) -> None:
    if api_version not in {"1", "2"}:
        raise context.CliFailure(context.CliFailureKind.INVALID_ARGUMENTS)
    options = context.InvocationOptions(host=host, port=port)
    if isinstance(ctx.obj, _Invocation):
        ctx.obj.options = options
    else:
        ctx.obj = _Invocation(options=options)
    cast(_Invocation, ctx.obj).api_version = api_version
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help(), color=False)


def _write(record: bytes, *, error: bool) -> None:
    stream = sys.stderr if error else sys.stdout
    try:
        if stream.buffer.write(record) != len(record):
            raise context.CliFailure(context.CliFailureKind.OUTPUT_FAILED)
        stream.flush()
        return
    except BrokenPipeError:
        # Closing marks the failed stream closed even if its final flush also
        # raises EPIPE. CPython then skips its shutdown flush, preserving our
        # fixed diagnostic/exit instead of an unraisable message and exit120.
        try:
            stream.close()
        except Exception:
            pass
    except Exception:
        pass
    raise context.CliFailure(context.CliFailureKind.OUTPUT_FAILED)


@app.command()
def status(ctx: typer.Context) -> int:
    """Deliver the service's complete status JSON; exit 0 means report delivery."""
    invocation = cast(_Invocation, ctx.obj)
    endpoint = invocation.options.target()
    credential = context.read_credential()
    code, record = asyncio.run(client.exchange(
        endpoint=endpoint, command="status", credential=credential,
        delivery=invocation.delivery,
        **invocation.version_options(),
    ))
    _write(record, error=code != 0)
    return code


@app.command()
def attach(
    ctx: typer.Context,
    profile: Annotated[str, typer.Option(
        "--profile", help="Explicit absolute Profile path; passed to the service.",
    )],
    journal: Annotated[str, typer.Option(
        "--journal", help="Explicit absolute journal path; passed to the service.",
    )],
) -> int:
    """Request observation attach; exit 0 means report delivery, including failed states."""
    invocation = cast(_Invocation, ctx.obj)
    endpoint = invocation.options.target()
    paths = context.AttachPaths(profile_path=profile, journal_path=journal)
    credential = context.read_credential()
    code, record = asyncio.run(client.exchange(
        endpoint=endpoint, command="attach", paths=paths, credential=credential,
        delivery=invocation.delivery,
        **invocation.version_options(),
    ))
    _write(record, error=code != 0)
    return code


@app.command()
def detach(ctx: typer.Context) -> int:
    """Request observation detach; exit 0 means report delivery, not confirmed cleanup."""
    invocation = cast(_Invocation, ctx.obj)
    endpoint = invocation.options.target()
    credential = context.read_credential()
    code, record = asyncio.run(client.exchange(
        endpoint=endpoint, command="detach", credential=credential,
        delivery=invocation.delivery,
        **invocation.version_options(),
    ))
    _write(record, error=code != 0)
    return code


@app.command("follow")
def follow(
    ctx: typer.Context,
    session: Annotated[str, typer.Option("--session", help="Explicit active session ID.")],
) -> int:
    """Follow new evidence; exit 0 means a valid terminal, including failure or unknown tail."""
    invocation = cast(_Invocation, ctx.obj)
    body = follow_wire.request(session)
    endpoint = invocation.options.target()
    credential = context.read_credential()
    code, record = asyncio.run(client.exchange_follow(
        endpoint=endpoint, request_body=body, credential=credential,
        delivery=invocation.delivery, emit=lambda frame: _write(frame, error=False),
        **invocation.version_options(),
    ))
    if record is not None:
        _write(record, error=True)
    return code


@app.command("monitor")
def monitor(
    ctx: typer.Context,
    session: Annotated[
        str, typer.Option("--session", help="Explicit active session ID.")
    ],
    condition_base64: Annotated[
        str,
        typer.Option(
            "--condition-base64", help="Canonical base64 literal (1..256 bytes)."
        ),
    ],
    timeout_ms: Annotated[
        int,
        typer.Option("--timeout-ms", help="Required observation bound (1..4000 ms)."),
    ],
    max_rx_bytes: Annotated[
        int,
        typer.Option(
            "--max-rx-bytes", help="Required examined-byte bound (1..1048576)."
        ),
    ],
) -> int:
    """Deliver one bounded Monitor report; every outcome and durability exits 0."""
    invocation = cast(_Invocation, ctx.obj)
    endpoint = invocation.options.target()
    body = monitor_wire.request(session, condition_base64, timeout_ms, max_rx_bytes)
    credential = context.read_credential()
    code, record = asyncio.run(
        client.exchange_monitor(
            endpoint=endpoint,
            request_body=body,
            credential=credential,
            delivery=invocation.delivery,
            **invocation.version_options(),
        )
    )
    _write(record, error=code != 0)
    return code


@app.command("annotate")
def annotate(
    ctx: typer.Context,
    session: Annotated[str, typer.Option("--session", help="Explicit active session ID.")],
    text: Annotated[str, typer.Option("--text", help="Client assertion (1..1024 UTF-8 bytes).")],
) -> int:
    """Record a bounded client assertion; receipt delivery does not verify its truth."""
    invocation = cast(_Invocation, ctx.obj)
    body = annotation_wire.request(session, text)
    endpoint = invocation.options.target()
    credential = context.read_credential()
    code, record = asyncio.run(client.exchange_annotation(
        endpoint=endpoint, request_body=body, credential=credential,
        delivery=invocation.delivery,
        **invocation.version_options(),
    ))
    _write(record, error=code != 0)
    return code


@app.command("interact")
def interact(
    ctx: typer.Context,
    session: Annotated[str, typer.Option("--session", help="Explicit active session ID.")],
    payload_base64: Annotated[str, typer.Option(
        "--payload-base64", help="Exact payload in canonical base64 (1..4096 bytes).",
    )],
    condition_base64: Annotated[list[str], typer.Option(
        "--condition-base64", help="Ordered literal in canonical base64; repeat 1..4 times.",
    )],
    timeout_ms: Annotated[int, typer.Option("--timeout-ms", help="Observation bound (1..4000 ms).")],
    max_rx_bytes: Annotated[int, typer.Option("--max-rx-bytes", help="Examined-byte bound (1..1048576).")],
) -> int:
    """Deliver bounded Interact facts; exit 0 never proves wire transmission or DUT receipt."""
    invocation = cast(_Invocation, ctx.obj)
    if invocation.api_version != "2":
        raise context.CliFailure(context.CliFailureKind.INVALID_ARGUMENTS)
    body = interact_wire.request(session, payload_base64, condition_base64, timeout_ms, max_rx_bytes)
    endpoint = invocation.options.target()
    credential = context.read_credential()
    code, record = asyncio.run(client.exchange_interact(
        endpoint=endpoint, request_body=body, credential=credential,
        delivery=invocation.delivery,
    ))
    _write(record, error=code != 0)
    return code


evidence_app = typer.Typer(
    invoke_without_command=True, no_args_is_help=False, add_completion=False,
    suggest_commands=False, rich_markup_mode=None, pretty_exceptions_enable=False,
    pretty_exceptions_show_locals=False, context_settings={"color": False},
    help="Retrieve bounded binary-safe evidence from an explicitly known session.",
)
app.add_typer(evidence_app, name="evidence")


@evidence_app.callback()
def evidence_root(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help(), color=False)


def _deliver_evidence(
    ctx: typer.Context, operation: str, body: dict[str, object],
) -> int:
    invocation = cast(_Invocation, ctx.obj)
    endpoint = invocation.options.target()
    credential = context.read_credential()
    code, record = asyncio.run(client.exchange_evidence(
        endpoint=endpoint, operation=operation, request_body=body,
        credential=credential, delivery=invocation.delivery,
        **invocation.version_options(),
    ))
    _write(record, error=code != 0)
    return code


@evidence_app.command("record")
def evidence_record(
    ctx: typer.Context,
    session: Annotated[str, typer.Option("--session", help="Explicit associated session ID.")],
    sequence: Annotated[int, typer.Option("--sequence", help="Exact observation sequence.")],
) -> int:
    """Retrieve one stable reference; expired/not-found reports also exit0."""
    return _deliver_evidence(ctx, "record", evidence.record_request(session, sequence))


@evidence_app.command("page")
def evidence_page(
    ctx: typer.Context,
    session: Annotated[str, typer.Option("--session", help="Explicit associated session ID.")],
    max_records: Annotated[int, typer.Option("--max-records", help="Required page record bound.")],
    max_charged_bytes: Annotated[int, typer.Option("--max-charged-bytes", help="Required journal charge bound.")],
    start: Annotated[int | None, typer.Option("--start", help="Inclusive sequence, paired with --end.")] = None,
    end: Annotated[int | None, typer.Option("--end", help="Exclusive sequence, paired with --start.")] = None,
    cursor: Annotated[str | None, typer.Option("--cursor", help="Opaque bounded continuation token.")] = None,
) -> int:
    """Deliver one bounded page; no automatic continuation or text conversion."""
    return _deliver_evidence(ctx, "page", evidence.page_request(
        session, max_records, max_charged_bytes, start, end, cursor,
    ))


def _failure(kind: context.CliFailureKind, delivery: client.DeliveryState) -> int:
    code, record = client.local_failure(kind, delivery)
    try:
        _write(record, error=True)
    except (KeyboardInterrupt, typer.Abort):
        return 130
    except Exception:
        # Unusable stderr permits exit-only failure. Never print a fallback
        # exception, repeat the write or send a service cleanup request.
        return 1
    return code


def main(args: Sequence[str] | None = None) -> int:
    """Installed entry and direct wrapper; every invocation owns its receipt phase."""
    invocation = _Invocation()
    previous_hook = sys.excepthook
    try:
        result = app(
            args=args, prog_name="dutchmate", standalone_mode=False,
            obj=invocation,
        )
        if result is None:
            return 0
        if type(result) is int:
            if result != 130:
                return result
            kind = context.CliFailureKind.INTERRUPTED
        else:
            kind = context.CliFailureKind.INTERNAL_FAILURE
    except context.CliFailure as error:
        kind = error.kind
    except typer.TyperException as error:
        kind = (
            context.CliFailureKind.INVALID_ARGUMENTS if error.exit_code == 2
            else context.CliFailureKind.INTERNAL_FAILURE
        )
    except (KeyboardInterrupt, typer.Abort):
        kind = context.CliFailureKind.INTERRUPTED
    except SystemExit as error:
        if error.code == 0:
            return 0
        if error.code == 130:
            kind = context.CliFailureKind.INTERRUPTED
        elif (
            error.code == 1
            and isinstance(error.__context__, OSError)
            and error.__context__.errno == errno.EPIPE
        ):
            # Pinned Typer translates help's EPIPE into SystemExit(1). Inspect
            # only the OS category; never render its text, cause or locals.
            kind = context.CliFailureKind.OUTPUT_FAILED
        else:
            kind = context.CliFailureKind.INTERNAL_FAILURE
    except Exception:
        kind = context.CliFailureKind.INTERNAL_FAILURE
    finally:
        # Typer installs its global hook even when its exception is caught.
        sys.excepthook = previous_hook
    return _failure(kind, invocation.delivery)
