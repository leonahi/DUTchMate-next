# Data Model: Continuous RX Evidence Foundation

These are logical contract types. Exact Python syntax and constructor names may
vary, but fields and invariants are normative for this slice.

## BackendCapability

Named physical ability. Recognized values are `uart_receive`, `uart_send`,
`serial_line_control`, `gpio_control`, and `gpio_events`. Only `uart_receive` is
required or acted on in this slice. Semantic DUT roles are not capabilities.

## BackendCapabilities

| Field | Type | Rules |
|---|---|---|
| `values` | immutable set of `BackendCapability` | Stable during a segment; must contain `uart_receive` for acquisition. |

## ConnectionInstanceId

Opaque, non-empty Device Core-owned identifier. A new value is created for every
successful ownership acquisition. It is not a device path, serial handle,
backend name, or physical device identity.

## SegmentId

Opaque, non-empty Device Core-owned identifier, unique in the active in-process
journal. A new value is created for the first connected segment and after every
accepted timestamp-origin reset.

## BackendObservationTimestampDomain

| Field | Type | Rules |
|---|---|---|
| `domain_id` | non-empty opaque string | Identifies the descriptor. |
| `observer` | `host` or `device` | Where observation occurred, not backend identity. |
| `meaning` | `observation` | This slice defines no DUT-emission timestamp. |
| `unit` | `nanosecond`, `microsecond`, or `tick` | Gives integer values meaning without clock alignment. |
| `origin_id` | non-empty opaque string | Defines clock continuity; reset requires a new value and segment. |

Equal units do not make different domains or origins comparable.

## BackendObservationTimestamp

| Field | Type | Rules |
|---|---|---|
| `domain_id` | reference to `BackendObservationTimestampDomain.domain_id` | Must resolve to the current segment's backend-observation timestamp domain. |
| `value` | non-negative integer | Raw value in the declared unit. |

Comparison is supported only when both timestamps resolve to the same domain
and origin. Evidence order never depends on timestamp comparison.

## LossObservability

Two variants:

1. `UpstreamLossNotObservable`
2. `ObserverReportsUartLoss(observer_id, scope)`

`observer_id` and `scope` are non-empty opaque values. Neither variant claims
an end-to-end lossless path.

## ConnectionDescriptor

Returned for one successfully opened owned backend connection.

| Field | Type | Rules |
|---|---|---|
| `capabilities` | `BackendCapabilities` | Immutable for the initial segment. |
| `backend_observation_timestamp_domain` | `BackendObservationTimestampDomain` | Stable domain for normalized RX/loss observations until reset. |
| `loss_observability` | `LossObservability` | Explicit observer scope or unobservability. |

Backend-specific physical identity/configuration provenance will be added with
the real Basic adapter slice; no serial-specific placeholder is added here.

## Normalized Backend Events

Events arrive in backend observation order through one stream.

### RxBytesObserved

| Field | Type | Rules |
|---|---|---|
| `payload` | immutable bytes | Non-empty; exact content preserved. |
| `observed_at` | `BackendObservationTimestamp` | Must resolve to the current segment's backend-observation timestamp domain. |

### ObserverLossObserved

| Field | Type | Rules |
|---|---|---|
| `observer_id` | non-empty opaque string | Must match current observability provenance. |
| `scope` | non-empty scope value | Must match the declared observer scope. |
| `cause` | `overflow` or `other_observed_loss` | Never inferred from missing bytes or time. |
| `lost_bytes` | positive integer or absent | Absent means unknown; zero is invalid. |
| `observed_at` | `BackendObservationTimestamp` | Must resolve to the current segment's backend-observation timestamp domain. |

### TimestampOriginReset

| Field | Type | Rules |
|---|---|---|
| `new_backend_observation_timestamp_domain` | `BackendObservationTimestampDomain` | Domain and origin must differ from the current segment's backend-observation timestamp domain. |

Acceptance closes the current segment and starts another with copied
capabilities/loss observability and the new backend-observation timestamp
domain. No clock alignment is inferred. This transition does not define or
restrict timestamp domains for future non-backend evidence.

### Disconnected

| Field | Type | Rules |
|---|---|---|
| `reason` | normalized non-empty reason | Must not expose a serial-library exception/type. |

This is terminal for the connection event stream. Later events are invalid.

## SegmentProvenance

| Field | Type | Rules |
|---|---|---|
| `connection_id` | `ConnectionInstanceId` | Stable for all segments from one owned connection. |
| `segment_id` | `SegmentId` | Unique for this provenance interval. |
| `capabilities` | `BackendCapabilities` | Immutable snapshot. |
| `backend_observation_timestamp_domain` | `BackendObservationTimestampDomain` | One stable domain/origin for the normalized RX/loss stream in this segment. |
| `loss_observability` | `LossObservability` | Immutable snapshot. |

## EvidenceSequence

Non-negative integer assigned by Device Core. The first record is `0`; each
accepted subsequent record increments by one. Scope is the active in-process
journal. Durable/session scope is deferred.

## Evidence Records

All variants carry `sequence`, `connection_id`, and `segment_id`.

- **SegmentStartedEvidence**: complete immutable `SegmentProvenance`; first
  record for the segment.
- **RxBytesEvidence**: exact `payload` and `observed_at` from RX observation.
- **ObserverLossEvidence**: observer, scope, cause, optional positive count, and
  timestamp from the loss observation.
- **SegmentEndedEvidence**: normalized reason `timestamp_origin_reset`,
  `disconnected`, `explicit_stop`, `recording_failure`, or `transport_failure`;
  last accepted record for the segment.

## State Transitions

```text
IDLE
  -> acquire receive-capable connection
ACQUIRING
  -> append SegmentStartedEvidence; start sole stream consumer
ACQUIRING_CONTINUOUSLY
  -> RX/loss: append evidence; remain acquiring
  -> origin reset: end segment; start new segment; remain acquiring
  -> disconnect/stop/failure: append terminal boundary when recordable
STOPPED
```

- A second acquire/consumer request while acquiring is rejected.
- Recorder failure is explicit; no later observation is claimed as recorded.
- Automatic reconnect and reacquire transitions are absent.
