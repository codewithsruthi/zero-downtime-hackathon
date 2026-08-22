from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Iterator

_TRACER = None
_INIT = False


def init_telemetry(service_name: str, *, disabled: bool = False) -> None:
    global _TRACER, _INIT
    if _INIT:
        return
    _INIT = True
    if disabled or os.environ.get("HYDRA_OTEL_DISABLED") == "1":
        _TRACER = None
        return
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        _TRACER = None
        return
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        _TRACER = None
        return
    headers = {}
    ingest = os.environ.get("SIGNOZ_INGESTION_KEY")
    extra = os.environ.get("OTEL_EXPORTER_OTLP_HEADERS", "")
    if ingest:
        headers["signoz-ingestion-key"] = ingest
    if extra:
        for part in extra.split(","):
            if "=" in part:
                k, v = part.split("=", 1)
                headers[k.strip()] = v.strip()
    resource = Resource.create(
        {
            "service.name": service_name,
            "service.version": os.getenv("HYDRA_VERSION", "1.0.0"),
            "deployment.environment": os.getenv("HYDRA_ENV", "hackathon"),
        }
    )
    provider = TracerProvider(resource=resource)
    traces_url = endpoint.rstrip("/")
    if not traces_url.endswith("/v1/traces"):
        traces_url = f"{traces_url}/v1/traces"
    try:
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=traces_url, headers=headers or None))
        )
        trace.set_tracer_provider(provider)
        _TRACER = trace.get_tracer("hydra")
    except Exception:
        _TRACER = None


class _NoopSpan:
    def set_attribute(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def set_status(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def record_exception(self, *_args: Any, **_kwargs: Any) -> None:
        return None


@contextmanager
def stage_span(stage: str, source_id: str, run_id: str, **extra: Any) -> Iterator[Any]:
    """Every pipeline stage goes through here. Attribute names are a contract with the Detector."""
    span_name = f"hydra.ingest.{stage}" if not stage.startswith("hydra.") else stage
    if _TRACER is None:
        span = _NoopSpan()
        try:
            yield span
        except Exception:
            raise
        return
    from opentelemetry.trace import Status, StatusCode

    with _TRACER.start_as_current_span(span_name) as span:
        span.set_attribute("hydra.source_id", source_id)
        span.set_attribute("hydra.run_id", run_id)
        span.set_attribute("hydra.stage", stage.split(".")[-1])
        for key, value in extra.items():
            if value is None:
                continue
            span.set_attribute(f"hydra.{key}", value)
        try:
            yield span
            span.set_status(Status(StatusCode.OK))
        except Exception as exc:
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
            span.set_attribute("hydra.error_signature", f"{type(exc).__name__}:{str(exc)[:200]}")
            raise


@contextmanager
def heal_span(step: str, **attrs: Any) -> Iterator[Any]:
    source_id = attrs.pop("source_id", "")
    run_id = attrs.pop("run_id", "")
    with stage_span(f"hydra.heal.{step}", source_id, run_id, **attrs) as span:
        yield span
