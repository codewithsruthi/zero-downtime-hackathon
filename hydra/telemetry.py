from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Iterator

_TRACER = None
_PROVIDER = None
_INIT = False
_LAST_EXPORT: str | None = None
_LAST_ERROR: str | None = None
_EXPORTED = 0


def telemetry_enabled() -> bool:
    return _TRACER is not None


def telemetry_status() -> dict[str, Any]:
    return {
        "enabled": _TRACER is not None,
        "last_export": _LAST_EXPORT,
        "last_error": _LAST_ERROR,
        "exported": _EXPORTED,
    }


def current_trace_id() -> str | None:
    if _TRACER is None:
        return None
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        ctx = span.get_span_context() if span is not None else None
        if ctx is None or not getattr(ctx, "is_valid", False):
            return None
        return format(ctx.trace_id, "032x")
    except Exception:
        return None


class _RecordingExporter:
    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def export(self, spans: Any) -> Any:
        global _LAST_EXPORT, _LAST_ERROR, _EXPORTED
        try:
            from opentelemetry.sdk.trace.export import SpanExportResult

            result = self._inner.export(spans)
            ok = result == SpanExportResult.SUCCESS
            _LAST_EXPORT = "ok" if ok else "fail"
            _EXPORTED += len(spans or [])
            if not ok:
                _LAST_ERROR = "export_failed"
            return result
        except Exception as exc:
            _LAST_EXPORT = "fail"
            _LAST_ERROR = type(exc).__name__
            try:
                from opentelemetry.sdk.trace.export import SpanExportResult

                return SpanExportResult.FAILURE
            except Exception:
                return 1

    def shutdown(self) -> Any:
        return self._inner.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        if hasattr(self._inner, "force_flush"):
            return bool(self._inner.force_flush(timeout_millis))
        return True


def init_telemetry(service_name: str, *, disabled: bool = False) -> None:
    global _TRACER, _INIT, _PROVIDER, _LAST_EXPORT, _LAST_ERROR
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
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    except ImportError:
        _TRACER = None
        _LAST_ERROR = "opentelemetry_missing"
        return
    headers: dict[str, str] = {}
    extra = os.environ.get("OTEL_EXPORTER_OTLP_HEADERS", "")
    if extra:
        for part in extra.split(","):
            if "=" in part:
                k, v = part.split("=", 1)
                headers[k.strip()] = v.strip()
    ingest = os.environ.get("SIGNOZ_INGESTION_KEY") or os.environ.get("SIGNOZ_API_KEY")
    if ingest:
        headers["signoz-ingestion-key"] = ingest
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
        timeout_ms = int(os.environ.get("OTEL_EXPORTER_OTLP_TIMEOUT", "3000"))
        exporter = _RecordingExporter(
            OTLPSpanExporter(
                endpoint=traces_url,
                headers=headers or None,
                timeout=max(1.0, timeout_ms / 1000.0),
            )
        )
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        _PROVIDER = provider
        _TRACER = trace.get_tracer("hydra")
    except Exception:
        _TRACER = None
        _LAST_ERROR = "exporter_init_failed"


def shutdown_telemetry(timeout_millis: int = 4000) -> None:
    global _PROVIDER, _TRACER
    provider = _PROVIDER
    if provider is None:
        return
    try:
        provider.force_flush(timeout_millis)
    except Exception:
        pass
    try:
        provider.shutdown()
    except Exception:
        pass
    _PROVIDER = None
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
