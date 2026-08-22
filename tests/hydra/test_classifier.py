from hydra.agent.classifier import Evidence, classify, fingerprint


def _ev(**kwargs):
    base = dict(source_id="src", seconds_since_success=10)
    base.update(kwargs)
    return Evidence(**base)


def test_freshness_wins():
    assert classify(_ev(seconds_since_success=999), 100) == "F5"


def test_acquire_error_is_f1():
    assert classify(_ev(stage="acquire", span_status="ERROR"), 1000) == "F1"
    assert classify(_ev(http_status=403), 1000) == "F1"
    assert classify(_ev(error_type="CaptchaBlocked"), 1000) == "F1"


def test_zero_rows_is_f2():
    assert classify(_ev(rows_parsed=0, rows_baseline=12), 1000) == "F2"
    assert classify(_ev(rows_parsed=3, rows_baseline=20), 1000) == "F2"


def test_schema_errors_are_f3():
    assert classify(_ev(rows_parsed=10, schema_errors=4), 1000) == "F3"


def test_poison_is_f6():
    assert classify(_ev(stage="load", span_status="ERROR", rows_parsed=10), 1000) == "F6"
    assert classify(_ev(error_type="ConversionError", rows_parsed=10), 1000) == "F6"


def test_default_is_f4():
    assert classify(_ev(failed_assertions=["null_rate"], rows_parsed=10), 1000) == "F4"


def test_fingerprint_strips_numbers():
    a = fingerprint("F1", _ev(stage="acquire", error_type="HTTPError", error_message="403 at run 99"))
    b = fingerprint("F1", _ev(stage="acquire", error_type="HTTPError", error_message="502 at run 12"))
    assert a == b
