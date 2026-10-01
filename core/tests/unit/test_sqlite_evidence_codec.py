"""Strict codec contracts for SQLite evidence storage."""

from dataclasses import replace

import pytest

from dutchmate_core import evidence, model
from dutchmate_core.adapters import basic_serial, sqlite_evidence


def _domain() -> model.BackendObservationTimestampDomain:
    return model.BackendObservationTimestampDomain(
        domain_id="host-domain",
        observer=model.TimestampObserver.HOST,
        meaning=model.TimestampMeaning.OBSERVATION,
        unit=model.TimestampUnit.NANOSECOND,
        origin_id="host-origin",
    )


def _basic_provenance() -> basic_serial.BasicSerialConnectionProvenance:
    configuration = basic_serial.SerialConfiguration(
        baud_rate=115_200,
        data_bits=basic_serial.SerialDataBits.EIGHT,
        parity=basic_serial.SerialParity.NONE,
        stop_bits=basic_serial.SerialStopBits.ONE,
        hardware_flow_control=False,
        software_flow_control=False,
    )
    line_intent = basic_serial.SerialOpenLineIntent(
        dtr=basic_serial.SerialLineState.DEASSERTED,
        rts=basic_serial.SerialLineState.ASSERTED,
    )
    return basic_serial.BasicSerialConnectionProvenance(
        selected_device_name="/dev/ttyUSB0",
        opened_device_name="/dev/ttyUSB0",
        requested_configuration=configuration,
        effective_configuration=configuration,
        open_line_provenance=basic_serial.SerialOpenLineProvenance(
            requested=line_intent,
            apply_strategy=(
                basic_serial.SerialOpenApplyStrategy.PRECONFIGURED_WHILE_CLOSED
            ),
            library_reported_dtr=basic_serial.SerialLineState.DEASSERTED,
            library_reported_rts=basic_serial.SerialLineState.ASSERTED,
            transition_guarantee=(
                basic_serial.SerialOpenTransitionGuarantee.NOT_GUARANTEED
            ),
            electrical_verification=(
                basic_serial.SerialElectricalVerification.NOT_VERIFIED
            ),
        ),
        exclusivity=basic_serial.SerialExclusivityProvenance(
            requested=True,
            mechanism=(
                basic_serial.SerialExclusivityMechanism.POSIX_PYSERIAL_EXCLUSIVE
            ),
            result=(
                basic_serial.SerialExclusivityResult.OPEN_SUCCEEDED_WITH_REQUESTED_MECHANISM
            ),
        ),
    )


def _segment_started(
    connection_provenance: model.BackendConnectionProvenance,
) -> model.SegmentStartedEvidence:
    return model.SegmentStartedEvidence(
        sequence=0,
        provenance=model.SegmentProvenance(
            connection_id=model.ConnectionInstanceId("connection-1"),
            segment_id=model.SegmentId("segment-1"),
            capabilities=model.BackendCapabilities(
                frozenset(
                    {
                        model.BackendCapability.UART_RECEIVE,
                        model.BackendCapability.SERIAL_LINE_CONTROL,
                    }
                )
            ),
            backend_observation_timestamp_domain=_domain(),
            loss_observability=model.UpstreamLossNotObservable(),
            connection_provenance=connection_provenance,
        ),
    )


def _records() -> tuple[model.EvidenceRecord, ...]:
    return (
        _segment_started(_basic_provenance()),
        model.RxBytesEvidence(
            sequence=1,
            connection_id=model.ConnectionInstanceId("connection-1"),
            segment_id=model.SegmentId("segment-1"),
            payload=bytes(range(256)),
            observed_at=model.BackendObservationTimestamp("host-domain", 5),
        ),
        model.ObserverLossEvidence(
            sequence=2,
            connection_id=model.ConnectionInstanceId("connection-1"),
            segment_id=model.SegmentId("segment-1"),
            observer_id="observer-1",
            scope="uart-buffer",
            cause=model.ObserverLossCause.OVERFLOW,
            lost_bytes=None,
            observed_at=model.BackendObservationTimestamp("host-domain", 6),
        ),
        model.SegmentEndedEvidence(
            sequence=3,
            connection_id=model.ConnectionInstanceId("connection-1"),
            segment_id=model.SegmentId("segment-1"),
            reason=model.SegmentEndReason.DISCONNECTED,
        ),
    )


@pytest.mark.parametrize("record", _records())
def test_every_current_evidence_variant_round_trips_strictly(
    record: model.EvidenceRecord,
) -> None:
    encoded = sqlite_evidence.encode_evidence_record(record)

    decoded = sqlite_evidence.decode_evidence_record(encoded)
    if isinstance(record, model.SegmentStartedEvidence):
        assert isinstance(decoded, model.SegmentStartedEvidence)
        assert replace(
            decoded.provenance,
            connection_provenance=record.provenance.connection_provenance,
        ) == record.provenance
        persisted = decoded.provenance.connection_provenance
        assert isinstance(persisted, model.PersistedConnectionProvenance)
        assert persisted.snapshot == record.provenance.connection_provenance.to_snapshot()
    else:
        assert decoded == record
    expected_charge = (
        8
        + 8
        + len(encoded.record_kind.encode("utf-8"))
        + len(encoded.metadata_json)
        + len(encoded.payload or b"")
    )
    assert encoded.charged_bytes == expected_charge


def test_rx_codec_preserves_all_byte_values_in_a_separate_blob() -> None:
    record = _records()[1]

    encoded = sqlite_evidence.encode_evidence_record(record)

    assert encoded.payload == bytes(range(256))
    assert b"payload" not in encoded.metadata_json
    assert encoded.rx_payload_bytes == 256


def test_metadata_encoding_is_canonical_utf8_json() -> None:
    encoded = sqlite_evidence.encode_evidence_record(_records()[3])

    assert encoded.metadata_json == (
        b'{"connection_id":"connection-1","reason":"disconnected",'
        b'"segment_id":"segment-1"}'
    )
    noncanonical = (
        b'{"reason":"disconnected","connection_id":"connection-1",'
        b'"segment_id":"segment-1"}'
    )
    assert len(noncanonical) == len(encoded.metadata_json)
    with pytest.raises(evidence.JournalFailure) as caught:
        sqlite_evidence.decode_evidence_record(
            replace(encoded, metadata_json=noncanonical)
        )
    assert caught.value.operation is evidence.JournalOperation.DECODE
    assert caught.value.kind is evidence.JournalFailureKind.CORRUPT_JOURNAL


def test_unknown_backend_provenance_kind_and_version_round_trip_opaquely() -> None:
    snapshot = model.ConnectionProvenanceSnapshot(
        envelope_version=1,
        backend_kind="unknown/future-backend",
        backend_schema_version=812,
        fields=(
            model.ProvenanceField("flag", False),
            model.ProvenanceField("opaque", "value"),
        ),
    )
    record = _segment_started(model.PersistedConnectionProvenance(snapshot))

    decoded = sqlite_evidence.decode_evidence_record(
        sqlite_evidence.encode_evidence_record(record)
    )

    assert isinstance(decoded, model.SegmentStartedEvidence)
    provenance = decoded.provenance.connection_provenance
    assert isinstance(provenance, model.PersistedConnectionProvenance)
    assert provenance.snapshot == snapshot


def test_unsupported_generic_provenance_envelope_version_is_rejected() -> None:
    encoded = sqlite_evidence.encode_evidence_record(
        _segment_started(_basic_provenance())
    )
    mutated = encoded.metadata_json.replace(
        b'"envelope_version":1',
        b'"envelope_version":2',
    )

    with pytest.raises(evidence.JournalFailure) as caught:
        sqlite_evidence.decode_evidence_record(
            replace(encoded, metadata_json=mutated, charged_bytes=encoded.charged_bytes)
        )

    assert caught.value.kind is (
        evidence.JournalFailureKind.INCOMPATIBLE_PROVENANCE_ENVELOPE_VERSION
    )
