from hydra.telemetry import current_trace_id, shutdown_telemetry, stage_span, telemetry_enabled


def test_disabled_telemetry_is_noop(app):
    assert telemetry_enabled() is False
    with stage_span("acquire", "amazon_products", "run_test") as span:
        span.set_attribute("hydra.rows_in", 1)
        assert current_trace_id() is None
    shutdown_telemetry()
