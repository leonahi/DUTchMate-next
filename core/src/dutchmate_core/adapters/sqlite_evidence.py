"""SQLite-backed durable evidence journal adapter."""

import asyncio
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from uuid import uuid4

from dutchmate_core.evidence import (
    EvidenceCursor,
    EvidencePage,
    EvidencePageOutcome,
    EvidenceRetrievalRequest,
    JournalFailure,
    JournalFailureKind,
    JournalOperation,
    PendingEvidenceRecord,
    _assign_sequence,
)
from dutchmate_core.model import (
    GENERIC_PROVENANCE_ENVELOPE_VERSION,
    SQLITE_INTEGER_MAX,
    BackendCapabilities,
    BackendCapability,
    BackendObservationTimestamp,
    BackendObservationTimestampDomain,
    ConnectionInstanceId,
    ConnectionProvenanceSnapshot,
    EvidenceRangeReference,
    EvidenceRecord,
    EvidenceReference,
    LossObservability,
    ObserverLossCause,
    ObserverLossEvidence,
    ObserverReportsUartLoss,
    PersistedConnectionProvenance,
    PersistedCounterOverflowError,
    ProvenanceField,
    RetentionMarker,
    RetentionTimestampEndpoint,
    RxBytesEvidence,
    SegmentEndedEvidence,
    SegmentEndReason,
    SegmentId,
    SegmentProvenance,
    SegmentStartedEvidence,
    SequenceRange,
    SessionId,
    SessionPolicy,
    TimestampMeaning,
    TimestampObserver,
    TimestampUnit,
    UpstreamLossNotObservable,
    checked_persisted_add,
    validate_persisted_counter,
    validate_record_sequence,
)

APPLICATION_ID = 0x4455544D
SCHEMA_VERSION = 1
RECORD_VERSION = 1
PAGE_SIZE = 4096

_TABLE_COLUMNS = {
    "session_metadata": (
        "singleton",
        "session_id",
        "schema_version",
        "max_retained_records",
        "max_retained_charged_bytes",
        "max_record_charged_bytes",
        "max_database_pages",
        "max_retrieval_page_records",
        "max_retrieval_page_charged_bytes",
        "next_sequence",
        "low_water_sequence",
        "retained_record_count",
        "retained_charged_bytes",
    ),
    "evidence_records": (
        "sequence",
        "record_kind",
        "record_version",
        "metadata_json",
        "payload",
        "charged_bytes",
        "rx_payload_bytes",
        "timestamp_endpoint_json",
    ),
    "retention_marker": (
        "singleton",
        "expired_start_sequence",
        "expired_end_sequence",
        "first_timestamp_json",
        "last_timestamp_json",
        "discarded_record_count",
        "discarded_rx_payload_byte_count",
        "discarded_charged_bytes",
    ),
}

_SCHEMA_STATEMENTS = (
    """
    CREATE TABLE session_metadata (
        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
        session_id TEXT NOT NULL CHECK (length(session_id) > 0),
        schema_version INTEGER NOT NULL CHECK (schema_version = 1),
        max_retained_records INTEGER NOT NULL CHECK (max_retained_records > 0),
        max_retained_charged_bytes INTEGER NOT NULL
            CHECK (max_retained_charged_bytes > 0),
        max_record_charged_bytes INTEGER NOT NULL
            CHECK (max_record_charged_bytes > 0),
        max_database_pages INTEGER NOT NULL CHECK (max_database_pages > 0),
        max_retrieval_page_records INTEGER NOT NULL
            CHECK (max_retrieval_page_records > 0),
        max_retrieval_page_charged_bytes INTEGER NOT NULL
            CHECK (max_retrieval_page_charged_bytes > 0),
        next_sequence INTEGER NOT NULL CHECK (next_sequence >= 0),
        low_water_sequence INTEGER NOT NULL CHECK (low_water_sequence >= 0),
        retained_record_count INTEGER NOT NULL CHECK (retained_record_count >= 0),
        retained_charged_bytes INTEGER NOT NULL CHECK (retained_charged_bytes >= 0),
        CHECK (max_record_charged_bytes <= max_retained_charged_bytes),
        CHECK (max_record_charged_bytes <= max_retrieval_page_charged_bytes),
        CHECK (low_water_sequence <= next_sequence)
    ) STRICT
    """,
    """
    CREATE TABLE evidence_records (
        sequence INTEGER PRIMARY KEY CHECK (sequence >= 0),
        record_kind TEXT NOT NULL,
        record_version INTEGER NOT NULL CHECK (record_version > 0),
        metadata_json BLOB NOT NULL,
        payload BLOB,
        charged_bytes INTEGER NOT NULL CHECK (charged_bytes > 0),
        rx_payload_bytes INTEGER NOT NULL CHECK (rx_payload_bytes >= 0),
        timestamp_endpoint_json BLOB
    ) STRICT
    """,
    """
    CREATE TABLE retention_marker (
        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
        expired_start_sequence INTEGER NOT NULL
            CHECK (expired_start_sequence = 0),
        expired_end_sequence INTEGER NOT NULL CHECK (expired_end_sequence > 0),
        first_timestamp_json BLOB,
        last_timestamp_json BLOB,
        discarded_record_count INTEGER NOT NULL CHECK (discarded_record_count > 0),
        discarded_rx_payload_byte_count INTEGER NOT NULL
            CHECK (discarded_rx_payload_byte_count >= 0),
        discarded_charged_bytes INTEGER NOT NULL
            CHECK (discarded_charged_bytes >= 0),
        CHECK (discarded_record_count = expired_end_sequence)
    ) STRICT
    """,
)


@dataclass(frozen=True, slots=True)
class EncodedEvidenceRecord:
    sequence: int
    record_kind: str
    record_version: int
    metadata_json: bytes
    payload: bytes | None
    charged_bytes: int
    rx_payload_bytes: int


@dataclass(frozen=True, slots=True)
class _StoredRetentionMarker:
    expired_end_sequence: int
    first_timestamp_json: bytes | None
    last_timestamp_json: bytes | None
    discarded_record_count: int
    discarded_rx_payload_byte_count: int
    discarded_charged_bytes: int


def encode_evidence_record(record: EvidenceRecord) -> EncodedEvidenceRecord:
    """Encode one current evidence variant into strict version-1 components."""

    try:
        sequence = validate_record_sequence(record.sequence)
        payload: bytes | None = None
        rx_payload_bytes = 0
        match record:
            case SegmentStartedEvidence(provenance=provenance):
                record_kind = "segment_started"
                metadata = _encode_segment_provenance(provenance)
            case RxBytesEvidence(
                connection_id=connection_id,
                segment_id=segment_id,
                payload=rx_payload,
                observed_at=observed_at,
            ):
                record_kind = "rx_bytes"
                metadata = {
                    "connection_id": connection_id.value,
                    "observed_at": _encode_timestamp(observed_at),
                    "segment_id": segment_id.value,
                }
                payload = bytes(rx_payload)
                rx_payload_bytes = len(payload)
            case ObserverLossEvidence(
                connection_id=connection_id,
                segment_id=segment_id,
                observer_id=observer_id,
                scope=scope,
                cause=cause,
                lost_bytes=lost_bytes,
                observed_at=observed_at,
            ):
                record_kind = "observer_loss"
                metadata = {
                    "cause": cause.value,
                    "connection_id": connection_id.value,
                    "lost_bytes": lost_bytes,
                    "observed_at": _encode_timestamp(observed_at),
                    "observer_id": observer_id,
                    "scope": scope,
                    "segment_id": segment_id.value,
                }
            case SegmentEndedEvidence(
                connection_id=connection_id,
                segment_id=segment_id,
                reason=reason,
            ):
                record_kind = "segment_ended"
                metadata = {
                    "connection_id": connection_id.value,
                    "reason": reason.value,
                    "segment_id": segment_id.value,
                }
            case _:
                raise TypeError(f"unsupported evidence record: {type(record).__name__}")
        metadata_json = _canonical_json(metadata)
        charged_bytes = _record_charge(record_kind, metadata_json, payload)
        return EncodedEvidenceRecord(
            sequence=sequence,
            record_kind=record_kind,
            record_version=RECORD_VERSION,
            metadata_json=metadata_json,
            payload=payload,
            charged_bytes=charged_bytes,
            rx_payload_bytes=rx_payload_bytes,
        )
    except JournalFailure:
        raise
    except (TypeError, ValueError, OverflowError) as error:
        raise JournalFailure(
            JournalOperation.ENCODE,
            JournalFailureKind.INVALID_INPUT,
            str(error),
        ) from None


def decode_evidence_record(encoded: EncodedEvidenceRecord) -> EvidenceRecord:
    """Decode and validate one strict version-1 stored record."""

    try:
        sequence = validate_record_sequence(encoded.sequence)
        if encoded.record_version != RECORD_VERSION:
            raise JournalFailure(
                JournalOperation.DECODE,
                JournalFailureKind.INCOMPATIBLE_RECORD_VERSION,
            )
        if type(encoded.metadata_json) is not bytes:
            raise TypeError("metadata must be a byte string")
        metadata = _decode_canonical_json(encoded.metadata_json)
        expected_charge = _record_charge(
            encoded.record_kind,
            encoded.metadata_json,
            encoded.payload,
        )
        if encoded.charged_bytes != expected_charge:
            raise ValueError("stored charged bytes do not match encoded components")
        match encoded.record_kind:
            case "segment_started":
                if encoded.payload is not None or encoded.rx_payload_bytes != 0:
                    raise ValueError("segment-start record cannot carry a payload")
                return SegmentStartedEvidence(
                    sequence=sequence,
                    provenance=_decode_segment_provenance(metadata),
                )
            case "rx_bytes":
                _expect_keys(
                    metadata,
                    {"connection_id", "observed_at", "segment_id"},
                )
                if type(encoded.payload) is not bytes or not encoded.payload:
                    raise ValueError("RX record requires a non-empty exact payload")
                if encoded.rx_payload_bytes != len(encoded.payload):
                    raise ValueError("stored RX byte count does not match payload")
                return RxBytesEvidence(
                    sequence=sequence,
                    connection_id=ConnectionInstanceId(
                        _text(metadata["connection_id"], "connection ID")
                    ),
                    segment_id=SegmentId(
                        _text(metadata["segment_id"], "segment ID")
                    ),
                    payload=encoded.payload,
                    observed_at=_decode_timestamp(metadata["observed_at"]),
                )
            case "observer_loss":
                _expect_keys(
                    metadata,
                    {
                        "cause",
                        "connection_id",
                        "lost_bytes",
                        "observed_at",
                        "observer_id",
                        "scope",
                        "segment_id",
                    },
                )
                if encoded.payload is not None or encoded.rx_payload_bytes != 0:
                    raise ValueError("observer-loss record cannot carry a payload")
                lost_bytes_raw = metadata["lost_bytes"]
                lost_bytes = (
                    None
                    if lost_bytes_raw is None
                    else _integer(lost_bytes_raw, "lost-byte count")
                )
                return ObserverLossEvidence(
                    sequence=sequence,
                    connection_id=ConnectionInstanceId(
                        _text(metadata["connection_id"], "connection ID")
                    ),
                    segment_id=SegmentId(
                        _text(metadata["segment_id"], "segment ID")
                    ),
                    observer_id=_text(metadata["observer_id"], "observer ID"),
                    scope=_text(metadata["scope"], "observer scope"),
                    cause=ObserverLossCause(
                        _text(metadata["cause"], "observer loss cause")
                    ),
                    lost_bytes=lost_bytes,
                    observed_at=_decode_timestamp(metadata["observed_at"]),
                )
            case "segment_ended":
                _expect_keys(
                    metadata,
                    {"connection_id", "reason", "segment_id"},
                )
                if encoded.payload is not None or encoded.rx_payload_bytes != 0:
                    raise ValueError("segment-end record cannot carry a payload")
                return SegmentEndedEvidence(
                    sequence=sequence,
                    connection_id=ConnectionInstanceId(
                        _text(metadata["connection_id"], "connection ID")
                    ),
                    segment_id=SegmentId(
                        _text(metadata["segment_id"], "segment ID")
                    ),
                    reason=SegmentEndReason(
                        _text(metadata["reason"], "segment end reason")
                    ),
                )
            case _:
                raise ValueError("unknown evidence record kind")
    except JournalFailure:
        raise
    except (KeyError, TypeError, ValueError, UnicodeError, json.JSONDecodeError) as error:
        raise JournalFailure(
            JournalOperation.DECODE,
            JournalFailureKind.CORRUPT_JOURNAL,
            str(error),
        ) from None


def _encode_segment_provenance(provenance: SegmentProvenance) -> dict[str, object]:
    snapshot = provenance.connection_provenance.to_snapshot()
    return {
        "capabilities": sorted(capability.value for capability in provenance.capabilities.values),
        "connection_id": provenance.connection_id.value,
        "connection_provenance": _encode_provenance_snapshot(snapshot),
        "loss_observability": _encode_loss_observability(
            provenance.loss_observability
        ),
        "segment_id": provenance.segment_id.value,
        "timestamp_domain": _encode_timestamp_domain(
            provenance.backend_observation_timestamp_domain
        ),
    }


def _decode_segment_provenance(metadata: dict[str, object]) -> SegmentProvenance:
    _expect_keys(
        metadata,
        {
            "capabilities",
            "connection_id",
            "connection_provenance",
            "loss_observability",
            "segment_id",
            "timestamp_domain",
        },
    )
    capabilities_raw = metadata["capabilities"]
    if not isinstance(capabilities_raw, list) or not all(
        isinstance(value, str) for value in capabilities_raw
    ):
        raise TypeError("capabilities must be a list of strings")
    if capabilities_raw != sorted(set(capabilities_raw)):
        raise ValueError("capabilities must be sorted unique values")
    snapshot = _decode_provenance_snapshot(metadata["connection_provenance"])
    return SegmentProvenance(
        connection_id=ConnectionInstanceId(
            _text(metadata["connection_id"], "connection ID")
        ),
        segment_id=SegmentId(_text(metadata["segment_id"], "segment ID")),
        capabilities=BackendCapabilities(
            frozenset(BackendCapability(value) for value in capabilities_raw)
        ),
        backend_observation_timestamp_domain=_decode_timestamp_domain(
            metadata["timestamp_domain"]
        ),
        loss_observability=_decode_loss_observability(
            metadata["loss_observability"]
        ),
        connection_provenance=PersistedConnectionProvenance(snapshot),
    )


def _encode_provenance_snapshot(
    snapshot: ConnectionProvenanceSnapshot,
) -> dict[str, object]:
    return {
        "backend_kind": snapshot.backend_kind,
        "backend_schema_version": snapshot.backend_schema_version,
        "envelope_version": snapshot.envelope_version,
        "fields": {field.name: field.value for field in snapshot.fields},
    }


def _decode_provenance_snapshot(value: object) -> ConnectionProvenanceSnapshot:
    envelope = _mapping(value, "connection provenance")
    _expect_keys(
        envelope,
        {"backend_kind", "backend_schema_version", "envelope_version", "fields"},
    )
    envelope_version = _integer(envelope["envelope_version"], "envelope version")
    if envelope_version != GENERIC_PROVENANCE_ENVELOPE_VERSION:
        raise JournalFailure(
            JournalOperation.DECODE,
            JournalFailureKind.INCOMPATIBLE_PROVENANCE_ENVELOPE_VERSION,
        )
    fields_raw = _mapping(envelope["fields"], "provenance fields")
    fields = tuple(
        ProvenanceField(name, _provenance_scalar(field_value))
        for name, field_value in sorted(fields_raw.items())
    )
    return ConnectionProvenanceSnapshot(
        envelope_version=envelope_version,
        backend_kind=_text(envelope["backend_kind"], "backend kind"),
        backend_schema_version=_integer(
            envelope["backend_schema_version"],
            "backend schema version",
        ),
        fields=fields,
    )


def _encode_timestamp(timestamp: BackendObservationTimestamp) -> dict[str, object]:
    return {"domain_id": timestamp.domain_id, "value": timestamp.value}


def _decode_timestamp(value: object) -> BackendObservationTimestamp:
    timestamp = _mapping(value, "observation timestamp")
    _expect_keys(timestamp, {"domain_id", "value"})
    return BackendObservationTimestamp(
        domain_id=_text(timestamp["domain_id"], "timestamp domain ID"),
        value=_integer(timestamp["value"], "timestamp value"),
    )


def _encode_timestamp_domain(
    domain: BackendObservationTimestampDomain,
) -> dict[str, object]:
    return {
        "domain_id": domain.domain_id,
        "meaning": domain.meaning.value,
        "observer": domain.observer.value,
        "origin_id": domain.origin_id,
        "unit": domain.unit.value,
    }


def _decode_timestamp_domain(value: object) -> BackendObservationTimestampDomain:
    domain = _mapping(value, "timestamp domain")
    _expect_keys(domain, {"domain_id", "meaning", "observer", "origin_id", "unit"})
    return BackendObservationTimestampDomain(
        domain_id=_text(domain["domain_id"], "timestamp domain ID"),
        observer=TimestampObserver(_text(domain["observer"], "timestamp observer")),
        meaning=TimestampMeaning(_text(domain["meaning"], "timestamp meaning")),
        unit=TimestampUnit(_text(domain["unit"], "timestamp unit")),
        origin_id=_text(domain["origin_id"], "timestamp origin ID"),
    )


def _encode_retention_timestamp_endpoint(
    endpoint: RetentionTimestampEndpoint,
) -> bytes:
    return _canonical_json(
        {
            "domain": _encode_timestamp_domain(endpoint.domain),
            "timestamp": _encode_timestamp(endpoint.timestamp),
        }
    )


def _decode_retention_timestamp_endpoint(
    value: bytes,
) -> RetentionTimestampEndpoint:
    endpoint = _decode_canonical_json(value)
    _expect_keys(endpoint, {"domain", "timestamp"})
    return RetentionTimestampEndpoint(
        timestamp=_decode_timestamp(endpoint["timestamp"]),
        domain=_decode_timestamp_domain(endpoint["domain"]),
    )


def _encode_loss_observability(value: LossObservability) -> dict[str, object]:
    match value:
        case UpstreamLossNotObservable():
            return {"kind": "upstream_not_observable"}
        case ObserverReportsUartLoss(observer_id=observer_id, scope=scope):
            return {
                "kind": "observer_reports",
                "observer_id": observer_id,
                "scope": scope,
            }
        case _:
            raise TypeError("unsupported loss-observability value")


def _decode_loss_observability(value: object) -> LossObservability:
    loss = _mapping(value, "loss observability")
    kind = _text(loss.get("kind"), "loss-observability kind")
    if kind == "upstream_not_observable":
        _expect_keys(loss, {"kind"})
        return UpstreamLossNotObservable()
    if kind == "observer_reports":
        _expect_keys(loss, {"kind", "observer_id", "scope"})
        return ObserverReportsUartLoss(
            observer_id=_text(loss["observer_id"], "loss observer ID"),
            scope=_text(loss["scope"], "loss observer scope"),
        )
    raise ValueError("unknown loss-observability kind")


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _decode_canonical_json(value: bytes) -> dict[str, object]:
    decoded = cast("object", json.loads(value.decode("utf-8")))
    mapping = _mapping(decoded, "evidence metadata")
    if _canonical_json(mapping) != value:
        raise ValueError("metadata is not canonical strict JSON")
    return mapping


def _mapping(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(
        isinstance(key, str) for key in value
    ):
        raise TypeError(f"{name} must be an object with string keys")
    return cast("dict[str, object]", value)


def _expect_keys(value: dict[str, object], expected: set[str]) -> None:
    if set(value) != expected:
        raise ValueError("stored metadata fields do not match the record contract")


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise TypeError(f"{name} must be non-empty text")
    return value


def _integer(value: object, name: str) -> int:
    if type(value) is not int:
        raise TypeError(f"{name} must be an integer")
    return value


def _provenance_scalar(value: object) -> None | bool | int | str:
    if value is None or type(value) in (bool, int, str):
        return cast("None | bool | int | str", value)
    raise TypeError("provenance field value must be a supported scalar")


def _record_charge(kind: str, metadata: bytes, payload: bytes | None) -> int:
    charge = 8 + 8 + len(kind.encode("utf-8")) + len(metadata) + len(payload or b"")
    return validate_persisted_counter(charge, name="record charge")


async def _await_submitted_worker[T](future: asyncio.Future[T]) -> T:
    cancelled = False
    while True:
        try:
            result = await asyncio.shield(future)
        except asyncio.CancelledError:
            cancelled = True
            continue
        except BaseException:
            if cancelled:
                raise asyncio.CancelledError from None
            raise
        if cancelled:
            raise asyncio.CancelledError
        return result


async def _await_bootstrap_worker(
    future: asyncio.Future[
        tuple[sqlite3.Connection, SessionId, SessionPolicy, int]
    ],
    executor: ThreadPoolExecutor,
) -> tuple[sqlite3.Connection, SessionId, SessionPolicy, int]:
    cancelled = False
    while True:
        try:
            result = await asyncio.shield(future)
        except asyncio.CancelledError:
            cancelled = True
            continue
        except BaseException:
            if cancelled:
                raise asyncio.CancelledError from None
            raise
        if not cancelled:
            return result
        loop = asyncio.get_running_loop()
        close_future = loop.run_in_executor(
            executor,
            _close_on_worker,
            result[0],
        )
        try:
            await _await_submitted_worker(close_future)
        except (JournalFailure, asyncio.CancelledError):
            pass
        raise asyncio.CancelledError


class SqliteEvidenceJournal:
    """One open schema-version-1 SQLite evidence session."""

    def __init__(
        self,
        *,
        executor: ThreadPoolExecutor,
        connection: sqlite3.Connection,
        session_id: SessionId,
        policy: SessionPolicy,
        physical_page_ceiling: int,
    ) -> None:
        self._executor = executor
        self._connection = connection
        self._gate = asyncio.Lock()
        self._session_id = session_id
        self._policy = policy
        self._physical_page_ceiling = physical_page_ceiling
        self._closed = False

    @property
    def session_id(self) -> SessionId:
        return self._session_id

    @property
    def policy(self) -> SessionPolicy:
        return self._policy

    @property
    def physical_page_ceiling(self) -> int:
        return self._physical_page_ceiling

    @classmethod
    async def create(
        cls,
        path: str | Path,
        session_policy: SessionPolicy,
    ) -> SqliteEvidenceJournal:
        if not isinstance(session_policy, SessionPolicy):
            raise JournalFailure(
                JournalOperation.CREATE,
                JournalFailureKind.INVALID_INPUT,
            )
        journal_path = _validated_path(path, JournalOperation.CREATE)
        executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="dutchmate-sqlite-journal",
        )
        loop = asyncio.get_running_loop()
        try:
            future = loop.run_in_executor(
                executor,
                _create_on_worker,
                journal_path,
                session_policy,
            )
            connection, session_id, policy, ceiling = (
                await _await_bootstrap_worker(future, executor)
            )
        except BaseException:
            executor.shutdown(wait=True, cancel_futures=True)
            raise
        return cls(
            executor=executor,
            connection=connection,
            session_id=session_id,
            policy=policy,
            physical_page_ceiling=ceiling,
        )

    @classmethod
    async def open(
        cls,
        path: str | Path,
        expected_session_id: SessionId | None = None,
    ) -> SqliteEvidenceJournal:
        if expected_session_id is not None and not isinstance(
            expected_session_id,
            SessionId,
        ):
            raise JournalFailure(
                JournalOperation.OPEN,
                JournalFailureKind.INVALID_INPUT,
            )
        journal_path = _validated_path(path, JournalOperation.OPEN)
        executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="dutchmate-sqlite-journal",
        )
        loop = asyncio.get_running_loop()
        try:
            future = loop.run_in_executor(
                executor,
                _open_on_worker,
                journal_path,
                expected_session_id,
            )
            connection, session_id, policy, ceiling = (
                await _await_bootstrap_worker(future, executor)
            )
        except BaseException:
            executor.shutdown(wait=True, cancel_futures=True)
            raise
        return cls(
            executor=executor,
            connection=connection,
            session_id=session_id,
            policy=policy,
            physical_page_ceiling=ceiling,
        )

    async def append(self, draft: PendingEvidenceRecord) -> EvidenceRecord:
        async with self._gate:
            if self._closed:
                raise JournalFailure(
                    JournalOperation.APPEND,
                    JournalFailureKind.CLOSED,
                )
            loop = asyncio.get_running_loop()
            future = loop.run_in_executor(
                self._executor,
                _append_on_worker,
                self._connection,
                self._policy,
                draft,
            )
            return await _await_submitted_worker(future)

    async def resolve_record(self, reference: EvidenceReference) -> EvidencePage:
        if not isinstance(reference, EvidenceReference):
            raise JournalFailure(
                JournalOperation.RETRIEVE,
                JournalFailureKind.INVALID_INPUT,
            )
        async with self._gate:
            if self._closed:
                raise JournalFailure(
                    JournalOperation.RETRIEVE,
                    JournalFailureKind.CLOSED,
                )
            loop = asyncio.get_running_loop()
            future = loop.run_in_executor(
                self._executor,
                _resolve_record_on_worker,
                self._connection,
                reference,
            )
            return await _await_submitted_worker(future)

    async def retrieve(self, request: EvidenceRetrievalRequest) -> EvidencePage:
        if not isinstance(request, EvidenceRetrievalRequest):
            raise JournalFailure(
                JournalOperation.RETRIEVE,
                JournalFailureKind.INVALID_INPUT,
            )
        async with self._gate:
            if self._closed:
                raise JournalFailure(
                    JournalOperation.RETRIEVE,
                    JournalFailureKind.CLOSED,
                )
            loop = asyncio.get_running_loop()
            future = loop.run_in_executor(
                self._executor,
                _retrieve_page_on_worker,
                self._connection,
                self._policy,
                request,
            )
            return await _await_submitted_worker(future)

    async def close(self) -> None:
        async with self._gate:
            if self._closed:
                return
            loop = asyncio.get_running_loop()
            try:
                future = loop.run_in_executor(
                    self._executor,
                    _close_on_worker,
                    self._connection,
                )
                await _await_submitted_worker(future)
            finally:
                self._closed = True
                self._executor.shutdown(wait=True, cancel_futures=True)


def _validated_path(path: str | Path, operation: JournalOperation) -> Path:
    if not isinstance(path, (str, Path)):
        raise JournalFailure(operation, JournalFailureKind.INVALID_INPUT)
    candidate = Path(path)
    if not str(candidate):
        raise JournalFailure(operation, JournalFailureKind.INVALID_INPUT)
    return candidate


def _connect_sqlite(database: str, *, uri: bool = False) -> sqlite3.Connection:
    return sqlite3.connect(database, uri=uri)


def _create_on_worker(
    path: Path,
    policy: SessionPolicy,
) -> tuple[sqlite3.Connection, SessionId, SessionPolicy, int]:
    if path.exists():
        raise JournalFailure(
            JournalOperation.CREATE,
            JournalFailureKind.JOURNAL_EXISTS,
        )
    connection: sqlite3.Connection | None = None
    try:
        connection = _connect_sqlite(str(path))
        connection.execute(f"PRAGMA page_size = {PAGE_SIZE}")
        connection.execute(f"PRAGMA application_id = {APPLICATION_ID}")
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        _configure_writable_connection(connection)
        ceiling = _establish_physical_ceiling(
            connection,
            policy.max_database_pages,
            JournalOperation.CREATE,
        )
        session_id = SessionId(str(uuid4()))
        connection.execute("BEGIN IMMEDIATE")
        for statement in _SCHEMA_STATEMENTS:
            connection.execute(statement)
        connection.execute(
            """
            INSERT INTO session_metadata (
                singleton, session_id, schema_version,
                max_retained_records, max_retained_charged_bytes,
                max_record_charged_bytes, max_database_pages,
                max_retrieval_page_records, max_retrieval_page_charged_bytes,
                next_sequence, low_water_sequence,
                retained_record_count, retained_charged_bytes
            ) VALUES (1, ?, 1, ?, ?, ?, ?, ?, ?, 0, 0, 0, 0)
            """,
            (
                session_id.value,
                policy.max_retained_records,
                policy.max_retained_charged_bytes,
                policy.max_record_charged_bytes,
                policy.max_database_pages,
                policy.max_retrieval_page_records,
                policy.max_retrieval_page_charged_bytes,
            ),
        )
        connection.commit()
        loaded_session_id, loaded_policy = _read_session_metadata(
            connection,
            JournalOperation.CREATE,
        )
        ceiling = _establish_physical_ceiling(
            connection,
            loaded_policy.max_database_pages,
            JournalOperation.CREATE,
        )
        return connection, loaded_session_id, loaded_policy, ceiling
    except JournalFailure:
        if connection is not None:
            connection.close()
        raise
    except (sqlite3.Error, OSError) as error:
        if connection is not None:
            try:
                connection.rollback()
            except sqlite3.Error:
                pass
            connection.close()
        raise _normalize_storage_failure(
            JournalOperation.CREATE,
            error,
            during_bootstrap=True,
        ) from None


def _open_on_worker(
    path: Path,
    expected_session_id: SessionId | None,
) -> tuple[sqlite3.Connection, SessionId, SessionPolicy, int]:
    if not path.is_file():
        raise JournalFailure(
            JournalOperation.OPEN,
            JournalFailureKind.JOURNAL_MISSING,
        )
    connection: sqlite3.Connection | None = None
    try:
        database_uri = f"{path.resolve().as_uri()}?mode=rw"
        connection = _connect_sqlite(database_uri, uri=True)
        _force_rollback_recovery(connection)
        session_id, policy = _validate_existing_journal(connection)
        if expected_session_id is not None and session_id != expected_session_id:
            raise JournalFailure(
                JournalOperation.OPEN,
                JournalFailureKind.SESSION_MISMATCH,
            )
        _prove_writable_connection(connection)
        _configure_writable_connection(connection)
        ceiling = _establish_physical_ceiling(
            connection,
            policy.max_database_pages,
            JournalOperation.OPEN,
        )
        return connection, session_id, policy, ceiling
    except JournalFailure:
        if connection is not None:
            connection.close()
        raise
    except (sqlite3.Error, OSError) as error:
        if connection is not None:
            connection.close()
        raise _normalize_storage_failure(JournalOperation.OPEN, error) from None


def _validate_existing_journal(
    connection: sqlite3.Connection,
) -> tuple[SessionId, SessionPolicy]:
    try:
        return _validate_existing_journal_contents(connection)
    except JournalFailure as failure:
        if failure.operation is JournalOperation.DECODE:
            raise JournalFailure(
                JournalOperation.OPEN,
                failure.kind,
            ) from None
        if failure.kind is JournalFailureKind.INVARIANT_VIOLATION:
            raise JournalFailure(
                JournalOperation.OPEN,
                JournalFailureKind.CORRUPT_JOURNAL,
            ) from None
        raise


def _validate_existing_journal_contents(
    connection: sqlite3.Connection,
) -> tuple[SessionId, SessionPolicy]:
    if _pragma_integer(connection, "application_id") != APPLICATION_ID:
        raise JournalFailure(
            JournalOperation.OPEN,
            JournalFailureKind.INCOMPATIBLE_APPLICATION,
        )
    if _pragma_integer(connection, "user_version") != SCHEMA_VERSION:
        raise JournalFailure(
            JournalOperation.OPEN,
            JournalFailureKind.INCOMPATIBLE_SCHEMA_VERSION,
        )
    if _pragma_integer(connection, "page_size") != PAGE_SIZE:
        raise JournalFailure(
            JournalOperation.OPEN,
            JournalFailureKind.CORRUPT_JOURNAL,
        )
    integrity = connection.execute("PRAGMA quick_check").fetchone()
    if integrity != ("ok",):
        raise JournalFailure(
            JournalOperation.OPEN,
            JournalFailureKind.CORRUPT_JOURNAL,
        )
    table_names = {
        cast("str", row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_schema WHERE type = 'table'"
        )
    }
    if table_names != set(_TABLE_COLUMNS):
        raise JournalFailure(
            JournalOperation.OPEN,
            JournalFailureKind.CORRUPT_JOURNAL,
        )
    for table_name, expected_columns in _TABLE_COLUMNS.items():
        actual_columns = tuple(
            cast("str", row[1])
            for row in connection.execute(f"PRAGMA table_info({table_name})")
        )
        if actual_columns != expected_columns:
            raise JournalFailure(
                JournalOperation.OPEN,
                JournalFailureKind.CORRUPT_JOURNAL,
            )
    session_id, policy = _read_session_metadata(connection, JournalOperation.OPEN)
    _validate_stored_records(connection)
    session_row = connection.execute(
        "SELECT low_water_sequence FROM session_metadata WHERE singleton = 1"
    ).fetchone()
    if session_row is None:
        raise JournalFailure(
            JournalOperation.OPEN,
            JournalFailureKind.INVARIANT_VIOLATION,
        )
    low_water = cast("int", session_row[0])
    marker = _read_retention_marker(connection, JournalOperation.OPEN)
    if (low_water == 0) != (marker is None):
        raise JournalFailure(
            JournalOperation.OPEN,
            JournalFailureKind.INVARIANT_VIOLATION,
        )
    if marker is not None and marker.expired_end_sequence != low_water:
        raise JournalFailure(
            JournalOperation.OPEN,
            JournalFailureKind.INVARIANT_VIOLATION,
        )
    return session_id, policy


def _force_rollback_recovery(connection: sqlite3.Connection) -> None:
    user_version = _pragma_integer(connection, "user_version")
    connection.execute("BEGIN IMMEDIATE")
    try:
        # A same-value header write makes SQLite process a pending rollback
        # journal; rolling back preserves a clean source byte-for-byte.
        connection.execute(f"PRAGMA user_version = {user_version}")
    finally:
        connection.execute("ROLLBACK")


def _prove_writable_connection(connection: sqlite3.Connection) -> None:
    connection.execute("BEGIN IMMEDIATE")
    try:
        connection.execute(
            """
            UPDATE session_metadata
            SET singleton = singleton
            WHERE singleton = 1
            """
        )
    finally:
        connection.execute("ROLLBACK")


def _read_session_metadata(
    connection: sqlite3.Connection,
    operation: JournalOperation,
) -> tuple[SessionId, SessionPolicy]:
    rows = connection.execute(
        """
        SELECT singleton, session_id, schema_version,
               max_retained_records, max_retained_charged_bytes,
               max_record_charged_bytes, max_database_pages,
               max_retrieval_page_records, max_retrieval_page_charged_bytes,
               next_sequence, low_water_sequence,
               retained_record_count, retained_charged_bytes
        FROM session_metadata
        """
    ).fetchall()
    if len(rows) != 1:
        raise JournalFailure(operation, JournalFailureKind.INVARIANT_VIOLATION)
    row = rows[0]
    try:
        if row[0] != 1 or row[2] != SCHEMA_VERSION:
            raise ValueError("invalid singleton session metadata")
        session_id = SessionId(cast("str", row[1]))
        policy = SessionPolicy(
            max_retained_records=cast("int", row[3]),
            max_retained_charged_bytes=cast("int", row[4]),
            max_record_charged_bytes=cast("int", row[5]),
            max_database_pages=cast("int", row[6]),
            max_retrieval_page_records=cast("int", row[7]),
            max_retrieval_page_charged_bytes=cast("int", row[8]),
        )
        next_sequence = validate_persisted_counter(
            cast("int", row[9]),
            name="next sequence",
        )
        low_water = validate_persisted_counter(
            cast("int", row[10]),
            name="low-water sequence",
        )
        retained_count = validate_persisted_counter(
            cast("int", row[11]),
            name="retained record count",
        )
        retained_charge = validate_persisted_counter(
            cast("int", row[12]),
            name="retained charged bytes",
        )
        if low_water > next_sequence:
            raise ValueError("low-water sequence exceeds next sequence")
        if retained_count != next_sequence - low_water:
            raise ValueError("retained record aggregate disagrees with sequence range")
        if retained_count == 0 and retained_charge != 0:
            raise ValueError("empty session has a non-zero retained charge")
    except (TypeError, ValueError, IndexError):
        raise JournalFailure(
            operation,
            JournalFailureKind.INVARIANT_VIOLATION,
        ) from None
    return session_id, policy


def _validate_stored_records(connection: sqlite3.Connection) -> None:
    rows = connection.execute(
        """
        SELECT sequence, record_kind, record_version, metadata_json,
               payload, charged_bytes, rx_payload_bytes, timestamp_endpoint_json
        FROM evidence_records ORDER BY sequence
        """
    ).fetchall()
    session = connection.execute(
        """
        SELECT low_water_sequence, next_sequence,
               retained_record_count, retained_charged_bytes
        FROM session_metadata WHERE singleton = 1
        """
    ).fetchone()
    if session is None:
        raise JournalFailure(
            JournalOperation.OPEN,
            JournalFailureKind.INVARIANT_VIOLATION,
        )
    low_water = cast("int", session[0])
    next_sequence = cast("int", session[1])
    if not _rows_have_contiguous_sequences(rows, low_water, next_sequence):
        raise JournalFailure(
            JournalOperation.OPEN,
            JournalFailureKind.INVARIANT_VIOLATION,
        )
    charged_total = 0
    for row in rows:
        encoded = EncodedEvidenceRecord(
            sequence=cast("int", row[0]),
            record_kind=cast("str", row[1]),
            record_version=cast("int", row[2]),
            metadata_json=cast("bytes", row[3]),
            payload=cast("bytes | None", row[4]),
            charged_bytes=cast("int", row[5]),
            rx_payload_bytes=cast("int", row[6]),
        )
        record = decode_evidence_record(encoded)
        timestamp_endpoint_json = cast("bytes | None", row[7])
        timestamp = _record_timestamp(record)
        if timestamp_endpoint_json is not None:
            if type(timestamp_endpoint_json) is not bytes or timestamp is None:
                raise JournalFailure(
                    JournalOperation.OPEN,
                    JournalFailureKind.INVARIANT_VIOLATION,
                )
            try:
                endpoint = _decode_retention_timestamp_endpoint(
                    timestamp_endpoint_json
                )
            except (TypeError, ValueError, UnicodeError, json.JSONDecodeError):
                raise JournalFailure(
                    JournalOperation.OPEN,
                    JournalFailureKind.INVARIANT_VIOLATION,
                ) from None
            if endpoint.timestamp != timestamp:
                raise JournalFailure(
                    JournalOperation.OPEN,
                    JournalFailureKind.INVARIANT_VIOLATION,
                )
        charged_total += encoded.charged_bytes
    if len(rows) != session[2] or charged_total != session[3]:
        raise JournalFailure(
            JournalOperation.OPEN,
            JournalFailureKind.INVARIANT_VIOLATION,
        )


def _rows_have_contiguous_sequences(
    rows: list[tuple[object, ...]],
    start_inclusive: int,
    end_exclusive: int,
) -> bool:
    if end_exclusive < start_inclusive:
        return False
    if len(rows) != end_exclusive - start_inclusive:
        return False
    return all(
        cast("int", row[0]) == start_inclusive + offset
        for offset, row in enumerate(rows)
    )


def _read_retention_marker(
    connection: sqlite3.Connection,
    operation: JournalOperation,
) -> _StoredRetentionMarker | None:
    rows = connection.execute(
        """
        SELECT singleton, expired_start_sequence, expired_end_sequence,
               first_timestamp_json, last_timestamp_json,
               discarded_record_count, discarded_rx_payload_byte_count,
               discarded_charged_bytes
        FROM retention_marker
        """
    ).fetchall()
    if not rows:
        return None
    if len(rows) != 1:
        raise JournalFailure(operation, JournalFailureKind.INVARIANT_VIOLATION)
    row = rows[0]
    try:
        expired_end = validate_persisted_counter(
            cast("int", row[2]),
            name="expired end sequence",
        )
        discarded_count = validate_persisted_counter(
            cast("int", row[5]),
            name="discarded record count",
        )
        discarded_rx_bytes = validate_persisted_counter(
            cast("int", row[6]),
            name="discarded RX payload byte count",
        )
        discarded_charge = validate_persisted_counter(
            cast("int", row[7]),
            name="discarded charged bytes",
        )
        first_timestamp = cast("bytes | None", row[3])
        last_timestamp = cast("bytes | None", row[4])
        if row[0] != 1 or row[1] != 0 or expired_end == 0:
            raise ValueError("invalid retention-marker range")
        if discarded_count != expired_end:
            raise ValueError("retention-marker count disagrees with range")
        if (first_timestamp is None) != (last_timestamp is None):
            raise ValueError("retention-marker timestamp endpoints disagree")
        for endpoint_json in (first_timestamp, last_timestamp):
            if endpoint_json is not None:
                if type(endpoint_json) is not bytes:
                    raise TypeError("retention endpoint must be a byte string")
                _decode_retention_timestamp_endpoint(endpoint_json)
    except (TypeError, ValueError, UnicodeError, json.JSONDecodeError):
        raise JournalFailure(
            operation,
            JournalFailureKind.INVARIANT_VIOLATION,
        ) from None
    return _StoredRetentionMarker(
        expired_end_sequence=expired_end,
        first_timestamp_json=first_timestamp,
        last_timestamp_json=last_timestamp,
        discarded_record_count=discarded_count,
        discarded_rx_payload_byte_count=discarded_rx_bytes,
        discarded_charged_bytes=discarded_charge,
    )


def _configure_writable_connection(connection: sqlite3.Connection) -> None:
    journal_mode = connection.execute("PRAGMA journal_mode = DELETE").fetchone()
    if journal_mode is None or str(journal_mode[0]).casefold() != "delete":
        raise sqlite3.OperationalError("journal mode unavailable")
    connection.execute("PRAGMA synchronous = FULL")
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 0")


def _establish_physical_ceiling(
    connection: sqlite3.Connection,
    requested_pages: int,
    operation: JournalOperation,
) -> int:
    page_count = _pragma_integer(connection, "page_count")
    if page_count > requested_pages:
        raise JournalFailure(
            operation,
            JournalFailureKind.DATABASE_OVER_CEILING,
        )
    effective = _apply_max_page_count(connection, requested_pages)
    if effective != requested_pages:
        raise JournalFailure(
            operation,
            JournalFailureKind.PHYSICAL_CEILING_UNAVAILABLE,
        )
    return effective


def _apply_max_page_count(
    connection: sqlite3.Connection,
    requested_pages: int,
) -> int:
    row = connection.execute(
        f"PRAGMA max_page_count = {requested_pages}"
    ).fetchone()
    if row is None or type(row[0]) is not int:
        raise sqlite3.DatabaseError("max_page_count returned no integer")
    return row[0]


def _pragma_integer(connection: sqlite3.Connection, name: str) -> int:
    row = connection.execute(f"PRAGMA {name}").fetchone()
    if row is None or type(row[0]) is not int:
        raise sqlite3.DatabaseError(f"PRAGMA {name} returned no integer")
    return row[0]


def _record_timestamp(
    record: EvidenceRecord,
) -> BackendObservationTimestamp | None:
    match record:
        case RxBytesEvidence(observed_at=timestamp):
            return timestamp
        case ObserverLossEvidence(observed_at=timestamp):
            return timestamp
        case _:
            return None


def _record_stream_identity(record: EvidenceRecord) -> tuple[str, str]:
    match record:
        case SegmentStartedEvidence(provenance=provenance):
            return provenance.connection_id.value, provenance.segment_id.value
        case RxBytesEvidence(connection_id=connection_id, segment_id=segment_id):
            return connection_id.value, segment_id.value
        case ObserverLossEvidence(
            connection_id=connection_id,
            segment_id=segment_id,
        ):
            return connection_id.value, segment_id.value
        case SegmentEndedEvidence(
            connection_id=connection_id,
            segment_id=segment_id,
        ):
            return connection_id.value, segment_id.value


def _timestamp_endpoint_for_candidate(
    connection: sqlite3.Connection,
    candidate: EvidenceRecord,
) -> bytes | None:
    timestamp = _record_timestamp(candidate)
    if timestamp is None:
        return None
    candidate_identity = _record_stream_identity(candidate)
    rows = connection.execute(
        """
        SELECT sequence, record_kind, record_version, metadata_json,
               payload, charged_bytes, rx_payload_bytes, timestamp_endpoint_json
        FROM evidence_records ORDER BY sequence DESC
        """
    ).fetchall()
    for row in rows:
        encoded = EncodedEvidenceRecord(
            sequence=cast("int", row[0]),
            record_kind=cast("str", row[1]),
            record_version=cast("int", row[2]),
            metadata_json=cast("bytes", row[3]),
            payload=cast("bytes | None", row[4]),
            charged_bytes=cast("int", row[5]),
            rx_payload_bytes=cast("int", row[6]),
        )
        retained_record = decode_evidence_record(encoded)
        if _record_stream_identity(retained_record) != candidate_identity:
            continue
        endpoint_json = cast("bytes | None", row[7])
        if endpoint_json is not None:
            endpoint = _decode_retention_timestamp_endpoint(endpoint_json)
            return _encode_retention_timestamp_endpoint(
                RetentionTimestampEndpoint(
                    timestamp=timestamp,
                    domain=endpoint.domain,
                )
            )
        if isinstance(retained_record, SegmentStartedEvidence):
            return _encode_retention_timestamp_endpoint(
                RetentionTimestampEndpoint(
                    timestamp=timestamp,
                    domain=(
                        retained_record.provenance.backend_observation_timestamp_domain
                    ),
                )
            )
    return None


def _resolve_record_on_worker(
    connection: sqlite3.Connection,
    reference: EvidenceReference,
) -> EvidencePage:
    try:
        session_id, low_water, next_sequence, marker = _read_reference_state(
            connection
        )
        if reference.session_id != session_id:
            raise JournalFailure(
                JournalOperation.RETRIEVE,
                JournalFailureKind.SESSION_MISMATCH,
            )
        if reference.sequence < low_water:
            if marker is None:
                raise JournalFailure(
                    JournalOperation.RETRIEVE,
                    JournalFailureKind.INVARIANT_VIOLATION,
                )
            return _resolved_page(
                snapshot_end_exclusive=reference.sequence + 1,
                expired_range=SequenceRange(
                    reference.sequence,
                    reference.sequence + 1,
                ),
                retention_marker=marker,
                outcome=EvidencePageOutcome.EXPIRED,
            )
        if reference.sequence >= next_sequence:
            never_existed_range = (
                None
                if reference.sequence == SQLITE_INTEGER_MAX
                else SequenceRange(reference.sequence, reference.sequence + 1)
            )
            return _resolved_page(
                snapshot_end_exclusive=next_sequence,
                never_existed_range=never_existed_range,
                outcome=EvidencePageOutcome.NOT_FOUND,
            )
        records, charged_bytes = _read_evidence_range(
            connection,
            reference.sequence,
            reference.sequence + 1,
        )
        return _resolved_page(
            records=records,
            snapshot_end_exclusive=reference.sequence + 1,
            outcome=EvidencePageOutcome.COMPLETE,
            charged_bytes=charged_bytes,
        )
    except JournalFailure:
        raise
    except (sqlite3.Error, OSError) as error:
        raise _normalize_storage_failure(JournalOperation.RETRIEVE, error) from None
    except (TypeError, ValueError, OverflowError) as error:
        raise JournalFailure(
            JournalOperation.RETRIEVE,
            JournalFailureKind.INVARIANT_VIOLATION,
            str(error),
        ) from None


def _retrieve_page_on_worker(
    connection: sqlite3.Connection,
    policy: SessionPolicy,
    request: EvidenceRetrievalRequest,
) -> EvidencePage:
    try:
        if (
            request.max_records > policy.max_retrieval_page_records
            or request.max_charged_bytes
            > policy.max_retrieval_page_charged_bytes
        ):
            raise JournalFailure(
                JournalOperation.RETRIEVE,
                JournalFailureKind.INVALID_INPUT,
            )
        session_id, low_water, next_sequence, marker = _read_reference_state(
            connection
        )
        reference = request.reference
        reference_session_id = (
            reference
            if isinstance(reference, SessionId)
            else reference.session_id
        )
        if reference_session_id != session_id:
            raise JournalFailure(
                JournalOperation.RETRIEVE,
                JournalFailureKind.SESSION_MISMATCH,
            )

        if isinstance(reference, SessionId):
            range_start = 0
            range_end: int | None = None
            available_snapshot_end = next_sequence
        else:
            range_start = reference.start_inclusive
            range_end = reference.end_exclusive
            available_snapshot_end = min(range_end, next_sequence)

        cursor = request.cursor
        if cursor is not None:
            if cursor.session_id != session_id:
                raise JournalFailure(
                    JournalOperation.RETRIEVE,
                    JournalFailureKind.SESSION_MISMATCH,
                )
            if (
                cursor.range_start_inclusive != range_start
                or cursor.range_end_exclusive != range_end
                or cursor.snapshot_end_exclusive > available_snapshot_end
                or cursor.next_sequence > available_snapshot_end
            ):
                raise JournalFailure(
                    JournalOperation.RETRIEVE,
                    JournalFailureKind.INVALID_INPUT,
                )
        snapshot_end = (
            available_snapshot_end
            if cursor is None
            else cursor.snapshot_end_exclusive
        )

        if (
            isinstance(reference, EvidenceRangeReference)
            and reference.is_empty
        ):
            outcome = (
                EvidencePageOutcome.COMPLETE
                if reference.start_inclusive <= next_sequence
                else EvidencePageOutcome.NOT_FOUND
            )
            return _resolved_page(
                snapshot_end_exclusive=min(
                    reference.end_exclusive,
                    next_sequence,
                ),
                outcome=outcome,
            )

        requested_start = (
            cursor.next_sequence if cursor is not None else range_start
        )
        page_start = max(requested_start, low_water)
        expired_range = (
            SequenceRange(
                requested_start,
                min(snapshot_end, low_water),
            )
            if requested_start < min(snapshot_end, low_water)
            else None
        )
        never_existed_range = (
            SequenceRange(
                max(range_start, snapshot_end),
                range_end,
            )
            if range_end is not None and range_end > snapshot_end
            else None
        )
        retained_end = snapshot_end
        has_retained_interval = page_start < retained_end
        records: tuple[EvidenceRecord, ...] = ()
        charged_bytes = 0
        next_sequence_position = page_start
        next_record_required_bytes: int | None = None
        truncated = False
        if has_retained_interval:
            (
                records,
                charged_bytes,
                next_sequence_position,
                next_record_required_bytes,
                truncated,
            ) = _read_bounded_evidence_page(
                connection,
                page_start,
                retained_end,
                max_records=request.max_records,
                max_charged_bytes=request.max_charged_bytes,
            )

        if expired_range is not None and marker is None:
            raise JournalFailure(
                JournalOperation.RETRIEVE,
                JournalFailureKind.INVARIANT_VIOLATION,
            )
        if (
            expired_range is not None
            and never_existed_range is None
            and not has_retained_interval
        ):
            outcome = EvidencePageOutcome.EXPIRED
        elif (
            never_existed_range is not None
            and expired_range is None
            and not has_retained_interval
        ):
            outcome = EvidencePageOutcome.NOT_FOUND
        elif expired_range is not None or never_existed_range is not None:
            outcome = EvidencePageOutcome.PARTIAL
        else:
            outcome = EvidencePageOutcome.COMPLETE

        continuation = (
            EvidenceCursor(
                session_id=session_id,
                range_start_inclusive=range_start,
                range_end_exclusive=range_end,
                snapshot_end_exclusive=snapshot_end,
                next_sequence=next_sequence_position,
            )
            if truncated
            else None
        )
        return _resolved_page(
            records=records,
            snapshot_end_exclusive=snapshot_end,
            expired_range=expired_range,
            retention_marker=marker if expired_range is not None else None,
            never_existed_range=never_existed_range,
            outcome=outcome,
            truncated=truncated,
            continuation=continuation,
            charged_bytes=charged_bytes,
            next_record_required_bytes=next_record_required_bytes,
        )
    except JournalFailure:
        raise
    except (sqlite3.Error, OSError) as error:
        raise _normalize_storage_failure(JournalOperation.RETRIEVE, error) from None
    except (TypeError, ValueError, OverflowError) as error:
        raise JournalFailure(
            JournalOperation.RETRIEVE,
            JournalFailureKind.INVARIANT_VIOLATION,
            str(error),
        ) from None


def _read_reference_state(
    connection: sqlite3.Connection,
) -> tuple[SessionId, int, int, RetentionMarker | None]:
    row = connection.execute(
        """
        SELECT session_id, low_water_sequence, next_sequence
        FROM session_metadata WHERE singleton = 1
        """
    ).fetchone()
    if row is None:
        raise JournalFailure(
            JournalOperation.RETRIEVE,
            JournalFailureKind.INVARIANT_VIOLATION,
        )
    session_id = SessionId(cast("str", row[0]))
    low_water = validate_persisted_counter(
        cast("int", row[1]),
        name="low-water sequence",
    )
    next_sequence = validate_persisted_counter(
        cast("int", row[2]),
        name="next sequence",
    )
    if low_water > next_sequence:
        raise JournalFailure(
            JournalOperation.RETRIEVE,
            JournalFailureKind.INVARIANT_VIOLATION,
        )
    stored_marker = _read_retention_marker(connection, JournalOperation.RETRIEVE)
    if (low_water == 0) != (stored_marker is None):
        raise JournalFailure(
            JournalOperation.RETRIEVE,
            JournalFailureKind.INVARIANT_VIOLATION,
        )
    if stored_marker is None:
        return session_id, low_water, next_sequence, None
    if stored_marker.expired_end_sequence != low_water:
        raise JournalFailure(
            JournalOperation.RETRIEVE,
            JournalFailureKind.INVARIANT_VIOLATION,
        )
    first_endpoint = (
        None
        if stored_marker.first_timestamp_json is None
        else _decode_retention_timestamp_endpoint(
            stored_marker.first_timestamp_json
        )
    )
    last_endpoint = (
        None
        if stored_marker.last_timestamp_json is None
        else _decode_retention_timestamp_endpoint(stored_marker.last_timestamp_json)
    )
    marker = RetentionMarker(
        expired_range=SequenceRange(0, stored_marker.expired_end_sequence),
        first_discarded_timestamp=first_endpoint,
        last_discarded_timestamp=last_endpoint,
        discarded_record_count=stored_marker.discarded_record_count,
        discarded_rx_payload_byte_count=(
            stored_marker.discarded_rx_payload_byte_count
        ),
        discarded_charged_bytes=stored_marker.discarded_charged_bytes,
    )
    return session_id, low_water, next_sequence, marker


def _read_evidence_range(
    connection: sqlite3.Connection,
    start_inclusive: int,
    end_exclusive: int,
) -> tuple[tuple[EvidenceRecord, ...], int]:
    rows = connection.execute(
        """
        SELECT sequence, record_kind, record_version, metadata_json,
               payload, charged_bytes, rx_payload_bytes
        FROM evidence_records
        WHERE sequence >= ? AND sequence < ?
        ORDER BY sequence
        """,
        (start_inclusive, end_exclusive),
    ).fetchall()
    if not _rows_have_contiguous_sequences(
        rows,
        start_inclusive,
        end_exclusive,
    ):
        raise JournalFailure(
            JournalOperation.RETRIEVE,
            JournalFailureKind.INVARIANT_VIOLATION,
        )
    records: list[EvidenceRecord] = []
    charged_bytes = 0
    for row in rows:
        encoded = EncodedEvidenceRecord(
            sequence=cast("int", row[0]),
            record_kind=cast("str", row[1]),
            record_version=cast("int", row[2]),
            metadata_json=cast("bytes", row[3]),
            payload=cast("bytes | None", row[4]),
            charged_bytes=cast("int", row[5]),
            rx_payload_bytes=cast("int", row[6]),
        )
        records.append(decode_evidence_record(encoded))
        charged_bytes = checked_persisted_add(
            charged_bytes,
            encoded.charged_bytes,
            name="retrieval page charged bytes",
        )
    return tuple(records), charged_bytes


def _read_bounded_evidence_page(
    connection: sqlite3.Connection,
    start_inclusive: int,
    end_exclusive: int,
    *,
    max_records: int,
    max_charged_bytes: int,
) -> tuple[tuple[EvidenceRecord, ...], int, int, int | None, bool]:
    query_limit = (
        SQLITE_INTEGER_MAX
        if max_records == SQLITE_INTEGER_MAX
        else max_records + 1
    )
    rows = connection.execute(
        """
        SELECT sequence, record_kind, record_version, metadata_json,
               payload, charged_bytes, rx_payload_bytes
        FROM evidence_records
        WHERE sequence >= ? AND sequence < ?
        ORDER BY sequence
        LIMIT ?
        """,
        (start_inclusive, end_exclusive, query_limit),
    ).fetchall()
    if not _rows_have_contiguous_sequences(
        rows,
        start_inclusive,
        start_inclusive + len(rows),
    ):
        raise JournalFailure(
            JournalOperation.RETRIEVE,
            JournalFailureKind.INVARIANT_VIOLATION,
        )

    records: list[EvidenceRecord] = []
    charged_bytes = 0
    next_record_required_bytes: int | None = None
    for row in rows:
        if len(records) == max_records:
            break
        encoded = EncodedEvidenceRecord(
            sequence=cast("int", row[0]),
            record_kind=cast("str", row[1]),
            record_version=cast("int", row[2]),
            metadata_json=cast("bytes", row[3]),
            payload=cast("bytes | None", row[4]),
            charged_bytes=cast("int", row[5]),
            rx_payload_bytes=cast("int", row[6]),
        )
        record = decode_evidence_record(encoded)
        if charged_bytes + encoded.charged_bytes > max_charged_bytes:
            next_record_required_bytes = encoded.charged_bytes
            break
        records.append(record)
        charged_bytes = checked_persisted_add(
            charged_bytes,
            encoded.charged_bytes,
            name="retrieval page charged bytes",
        )

    next_position = start_inclusive + len(records)
    truncated = next_position < end_exclusive
    if not truncated and len(rows) != end_exclusive - start_inclusive:
        raise JournalFailure(
            JournalOperation.RETRIEVE,
            JournalFailureKind.INVARIANT_VIOLATION,
        )
    return (
        tuple(records),
        charged_bytes,
        next_position,
        next_record_required_bytes,
        truncated,
    )


def _resolved_page(
    *,
    records: tuple[EvidenceRecord, ...] = (),
    snapshot_end_exclusive: int,
    expired_range: SequenceRange | None = None,
    retention_marker: RetentionMarker | None = None,
    never_existed_range: SequenceRange | None = None,
    outcome: EvidencePageOutcome,
    truncated: bool = False,
    continuation: EvidenceCursor | None = None,
    charged_bytes: int = 0,
    next_record_required_bytes: int | None = None,
) -> EvidencePage:
    return EvidencePage(
        records=records,
        snapshot_end_exclusive=snapshot_end_exclusive,
        expired_range=expired_range,
        retention_marker=retention_marker,
        never_existed_range=never_existed_range,
        outcome=outcome,
        truncated=truncated,
        continuation=continuation,
        charged_bytes=charged_bytes,
        next_record_required_bytes=next_record_required_bytes,
    )


def _append_on_worker(
    connection: sqlite3.Connection,
    policy: SessionPolicy,
    draft: PendingEvidenceRecord,
) -> EvidenceRecord:
    transaction_started = False
    try:
        candidate = encode_evidence_record(_assign_sequence(draft, 0))
        if (
            candidate.charged_bytes > policy.max_record_charged_bytes
            or candidate.charged_bytes > policy.max_retained_charged_bytes
        ):
            raise JournalFailure(
                JournalOperation.APPEND,
                JournalFailureKind.CAPACITY,
            )
        _establish_physical_ceiling(
            connection,
            policy.max_database_pages,
            JournalOperation.APPEND,
        )
        connection.execute("BEGIN IMMEDIATE")
        transaction_started = True
        row = connection.execute(
            """
            SELECT next_sequence, low_water_sequence,
                   retained_record_count, retained_charged_bytes
            FROM session_metadata WHERE singleton = 1
            """
        ).fetchone()
        if row is None:
            raise JournalFailure(
                JournalOperation.APPEND,
                JournalFailureKind.INVARIANT_VIOLATION,
            )
        next_sequence = validate_persisted_counter(
            cast("int", row[0]),
            name="next sequence",
        )
        if next_sequence == SQLITE_INTEGER_MAX:
            raise JournalFailure(
                JournalOperation.APPEND,
                JournalFailureKind.SEQUENCE_EXHAUSTED,
            )
        low_water = validate_persisted_counter(
            cast("int", row[1]),
            name="low-water sequence",
        )
        retained_count = validate_persisted_counter(
            cast("int", row[2]),
            name="retained record count",
        )
        retained_charge = validate_persisted_counter(
            cast("int", row[3]),
            name="retained charged bytes",
        )
        new_next_sequence = checked_persisted_add(
            next_sequence,
            1,
            name="next sequence",
        )
        new_retained_count = checked_persisted_add(
            retained_count,
            1,
            name="retained record count",
        )
        new_retained_charge = checked_persisted_add(
            retained_charge,
            candidate.charged_bytes,
            name="retained charged bytes",
        )
        if (
            low_water > next_sequence
            or retained_count != next_sequence - low_water
            or (retained_count == 0 and retained_charge != 0)
        ):
            raise JournalFailure(
                JournalOperation.APPEND,
                JournalFailureKind.INVARIANT_VIOLATION,
            )
        accepted = EncodedEvidenceRecord(
            sequence=next_sequence,
            record_kind=candidate.record_kind,
            record_version=candidate.record_version,
            metadata_json=candidate.metadata_json,
            payload=candidate.payload,
            charged_bytes=candidate.charged_bytes,
            rx_payload_bytes=candidate.rx_payload_bytes,
        )
        accepted_record = decode_evidence_record(accepted)
        timestamp_endpoint_json = _timestamp_endpoint_for_candidate(
            connection,
            accepted_record,
        )
        retained_rows = connection.execute(
            """
            SELECT sequence, charged_bytes, rx_payload_bytes,
                   timestamp_endpoint_json
            FROM evidence_records ORDER BY sequence
            """
        ).fetchall()
        if (
            not _rows_have_contiguous_sequences(
                retained_rows,
                low_water,
                next_sequence,
            )
            or len(retained_rows) != retained_count
            or sum(cast("int", retained_row[1]) for retained_row in retained_rows)
            != retained_charge
        ):
            raise JournalFailure(
                JournalOperation.APPEND,
                JournalFailureKind.INVARIANT_VIOLATION,
            )

        discarded_rows: list[tuple[object, ...]] = []
        discarded_charge = 0
        while (
            new_retained_count - len(discarded_rows)
            > policy.max_retained_records
            or new_retained_charge - discarded_charge
            > policy.max_retained_charged_bytes
        ):
            if len(discarded_rows) >= len(retained_rows):
                raise JournalFailure(
                    JournalOperation.APPEND,
                    JournalFailureKind.INVARIANT_VIOLATION,
                )
            discarded_row = retained_rows[len(discarded_rows)]
            discarded_rows.append(discarded_row)
            discarded_charge = checked_persisted_add(
                discarded_charge,
                validate_persisted_counter(
                    cast("int", discarded_row[1]),
                    name="discarded record charge",
                ),
                name="discarded charged bytes",
            )

        discarded_count = len(discarded_rows)
        discarded_rx_bytes = 0
        for discarded_row in discarded_rows:
            discarded_rx_bytes = checked_persisted_add(
                discarded_rx_bytes,
                validate_persisted_counter(
                    cast("int", discarded_row[2]),
                    name="discarded RX payload bytes",
                ),
                name="discarded RX payload bytes",
            )
        new_low_water = checked_persisted_add(
            low_water,
            discarded_count,
            name="low-water sequence",
        )
        final_retained_count = new_retained_count - discarded_count
        final_retained_charge = new_retained_charge - discarded_charge

        marker = _read_retention_marker(connection, JournalOperation.APPEND)
        if (low_water == 0) != (marker is None):
            raise JournalFailure(
                JournalOperation.APPEND,
                JournalFailureKind.INVARIANT_VIOLATION,
            )
        if marker is not None and marker.expired_end_sequence != low_water:
            raise JournalFailure(
                JournalOperation.APPEND,
                JournalFailureKind.INVARIANT_VIOLATION,
            )
        if discarded_count:
            prior_discarded_count = (
                0 if marker is None else marker.discarded_record_count
            )
            prior_discarded_rx_bytes = (
                0 if marker is None else marker.discarded_rx_payload_byte_count
            )
            prior_discarded_charge = (
                0 if marker is None else marker.discarded_charged_bytes
            )
            cumulative_discarded_count = checked_persisted_add(
                prior_discarded_count,
                discarded_count,
                name="discarded record count",
            )
            cumulative_discarded_rx_bytes = checked_persisted_add(
                prior_discarded_rx_bytes,
                discarded_rx_bytes,
                name="discarded RX payload byte count",
            )
            cumulative_discarded_charge = checked_persisted_add(
                prior_discarded_charge,
                discarded_charge,
                name="discarded charged bytes",
            )
            if cumulative_discarded_count != new_low_water:
                raise JournalFailure(
                    JournalOperation.APPEND,
                    JournalFailureKind.INVARIANT_VIOLATION,
                )
            discarded_timestamp_json = [
                cast("bytes", discarded_row[3])
                for discarded_row in discarded_rows
                if discarded_row[3] is not None
            ]
            first_timestamp_json = (
                marker.first_timestamp_json if marker is not None else None
            )
            last_timestamp_json = (
                marker.last_timestamp_json if marker is not None else None
            )
            if discarded_timestamp_json:
                if first_timestamp_json is None:
                    first_timestamp_json = discarded_timestamp_json[0]
                last_timestamp_json = discarded_timestamp_json[-1]
            connection.execute(
                """
                INSERT INTO retention_marker (
                    singleton, expired_start_sequence, expired_end_sequence,
                    first_timestamp_json, last_timestamp_json,
                    discarded_record_count,
                    discarded_rx_payload_byte_count,
                    discarded_charged_bytes
                ) VALUES (1, 0, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(singleton) DO UPDATE SET
                    expired_end_sequence = excluded.expired_end_sequence,
                    first_timestamp_json = excluded.first_timestamp_json,
                    last_timestamp_json = excluded.last_timestamp_json,
                    discarded_record_count = excluded.discarded_record_count,
                    discarded_rx_payload_byte_count =
                        excluded.discarded_rx_payload_byte_count,
                    discarded_charged_bytes = excluded.discarded_charged_bytes
                """,
                (
                    new_low_water,
                    first_timestamp_json,
                    last_timestamp_json,
                    cumulative_discarded_count,
                    cumulative_discarded_rx_bytes,
                    cumulative_discarded_charge,
                ),
            )
            deleted = connection.execute(
                "DELETE FROM evidence_records WHERE sequence < ?",
                (new_low_water,),
            )
            if deleted.rowcount != discarded_count:
                raise JournalFailure(
                    JournalOperation.APPEND,
                    JournalFailureKind.INVARIANT_VIOLATION,
                )
        connection.execute(
            """
            INSERT INTO evidence_records (
                sequence, record_kind, record_version, metadata_json,
                payload, charged_bytes, rx_payload_bytes, timestamp_endpoint_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                accepted.sequence,
                accepted.record_kind,
                accepted.record_version,
                accepted.metadata_json,
                accepted.payload,
                accepted.charged_bytes,
                accepted.rx_payload_bytes,
                timestamp_endpoint_json,
            ),
        )
        updated = connection.execute(
            """
            UPDATE session_metadata
            SET next_sequence = ?, low_water_sequence = ?,
                retained_record_count = ?, retained_charged_bytes = ?
            WHERE singleton = 1 AND next_sequence = ?
            """,
            (
                new_next_sequence,
                new_low_water,
                final_retained_count,
                final_retained_charge,
                next_sequence,
            ),
        )
        if updated.rowcount != 1:
            raise JournalFailure(
                JournalOperation.APPEND,
                JournalFailureKind.INVARIANT_VIOLATION,
            )
        postcondition = connection.execute(
            """
            SELECT next_sequence, low_water_sequence,
                   retained_record_count, retained_charged_bytes
            FROM session_metadata WHERE singleton = 1
            """
        ).fetchone()
        if postcondition != (
            new_next_sequence,
            new_low_water,
            final_retained_count,
            final_retained_charge,
        ):
            raise JournalFailure(
                JournalOperation.APPEND,
                JournalFailureKind.INVARIANT_VIOLATION,
            )
        stored_record = connection.execute(
            """
            SELECT sequence, record_kind, record_version, metadata_json,
                   payload, charged_bytes, rx_payload_bytes,
                   timestamp_endpoint_json
            FROM evidence_records WHERE sequence = ?
            """,
            (next_sequence,),
        ).fetchone()
        if stored_record != (
            accepted.sequence,
            accepted.record_kind,
            accepted.record_version,
            accepted.metadata_json,
            accepted.payload,
            accepted.charged_bytes,
            accepted.rx_payload_bytes,
            timestamp_endpoint_json,
        ):
            raise JournalFailure(
                JournalOperation.APPEND,
                JournalFailureKind.INVARIANT_VIOLATION,
            )
        retained_postcondition = connection.execute(
            """
            SELECT sequence, charged_bytes
            FROM evidence_records ORDER BY sequence
            """
        ).fetchall()
        if (
            not _rows_have_contiguous_sequences(
                retained_postcondition,
                new_low_water,
                new_next_sequence,
            )
            or len(retained_postcondition) != final_retained_count
            or sum(
                cast("int", retained_row[1])
                for retained_row in retained_postcondition
            )
            != final_retained_charge
        ):
            raise JournalFailure(
                JournalOperation.APPEND,
                JournalFailureKind.INVARIANT_VIOLATION,
            )
        final_marker = _read_retention_marker(connection, JournalOperation.APPEND)
        if (new_low_water == 0) != (final_marker is None):
            raise JournalFailure(
                JournalOperation.APPEND,
                JournalFailureKind.INVARIANT_VIOLATION,
            )
        if (
            final_marker is not None
            and final_marker.expired_end_sequence != new_low_water
        ):
            raise JournalFailure(
                JournalOperation.APPEND,
                JournalFailureKind.INVARIANT_VIOLATION,
            )
        connection.commit()
        transaction_started = False
        return accepted_record
    except PersistedCounterOverflowError:
        if transaction_started:
            _rollback_append(connection)
        raise JournalFailure(
            JournalOperation.APPEND,
            JournalFailureKind.COUNTER_EXHAUSTED,
        ) from None
    except JournalFailure as error:
        if transaction_started:
            _rollback_append(connection)
        if error.operation is JournalOperation.APPEND:
            raise
        raise JournalFailure(
            JournalOperation.APPEND,
            error.kind,
            error.detail,
        ) from None
    except (sqlite3.Error, OSError) as error:
        if transaction_started:
            _rollback_append(connection)
        raise _normalize_storage_failure(JournalOperation.APPEND, error) from None
    except (TypeError, ValueError, OverflowError) as error:
        if transaction_started:
            _rollback_append(connection)
        raise JournalFailure(
            JournalOperation.APPEND,
            JournalFailureKind.INVARIANT_VIOLATION,
            str(error),
        ) from None


def _rollback_append(connection: sqlite3.Connection) -> None:
    try:
        connection.rollback()
    except sqlite3.Error:
        pass


def _close_on_worker(connection: sqlite3.Connection) -> None:
    try:
        connection.close()
    except sqlite3.Error:
        raise JournalFailure(
            JournalOperation.CLOSE,
            JournalFailureKind.IO_FAILURE,
        ) from None


def _normalize_storage_failure(
    operation: JournalOperation,
    error: sqlite3.Error | OSError,
    *,
    during_bootstrap: bool = False,
) -> JournalFailure:
    if isinstance(error, sqlite3.Error):
        code = getattr(error, "sqlite_errorcode", None)
        if code in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
            kind = JournalFailureKind.BUSY
        elif code == sqlite3.SQLITE_FULL:
            kind = (
                JournalFailureKind.PHYSICAL_CEILING_UNAVAILABLE
                if during_bootstrap
                else JournalFailureKind.CAPACITY
            )
        elif code == sqlite3.SQLITE_READONLY:
            kind = JournalFailureKind.READ_ONLY
        elif code == sqlite3.SQLITE_PERM:
            kind = JournalFailureKind.PERMISSION_DENIED
        elif code in (sqlite3.SQLITE_CORRUPT, sqlite3.SQLITE_NOTADB):
            kind = JournalFailureKind.CORRUPT_JOURNAL
        else:
            kind = JournalFailureKind.IO_FAILURE
    elif isinstance(error, PermissionError):
        kind = JournalFailureKind.PERMISSION_DENIED
    else:
        kind = JournalFailureKind.IO_FAILURE
    return JournalFailure(operation, kind)
