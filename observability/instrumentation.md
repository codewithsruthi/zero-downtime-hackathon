# Instrumentation

Service name: `zero-downtime-factory`
Resource attribute: `factory.component` = `app` | `pipeline`

Traces continue across CLI and app through `TRACEPARENT`. `make demo-offline` mints one value and exports it for the whole story.

Export: OTLP/HTTP to `OTEL_EXPORTER_OTLP_ENDPOINT` (default `http://127.0.0.1:4318`). Timeout 3s. Failures are swallowed and logged once.

Span names live in SPEC.md section 9. Heal and failure are events (`factory.heal.requested`, `factory.failure`).
