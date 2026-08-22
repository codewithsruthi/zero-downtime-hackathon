from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

FAILURE_CLASSES = {
    "F1": "acquisition_failure",
    "F2": "structural_drift",
    "F3": "contract_violation",
    "F4": "statistical_anomaly",
    "F5": "freshness_violation",
    "F6": "poison_pill",
}

_NUM = re.compile(r"\d+")
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


@dataclass
class Evidence:
    source_id: str
    stage: str | None = None
    span_status: str | None = None
    http_status: int | None = None
    error_type: str | None = None
    error_message: str | None = None
    rows_parsed: int | None = None
    rows_baseline: int | None = None
    schema_errors: int = 0
    failed_assertions: list[str] = field(default_factory=list)
    seconds_since_success: float = 0.0
    trace_id: str | None = None
    run_id: str | None = None


def classify(ev: Evidence, freshness_slo_s: float) -> str:
    """Map any observed symptom to exactly one of six classes. First match wins."""
    if ev.seconds_since_success > freshness_slo_s:
        return "F5"

    if ev.stage == "acquire" and ev.span_status == "ERROR":
        return "F1"
    if ev.http_status is not None and ev.http_status >= 400:
        return "F1"
    if ev.error_type in {"Timeout", "ConnectionError", "CaptchaBlocked", "EmptyBody", "HTTPError"}:
        return "F1"

    if ev.rows_parsed == 0:
        return "F2"
    if (ev.rows_baseline or 0) > 0 and ev.rows_parsed is not None:
        if ev.rows_parsed < 0.5 * ev.rows_baseline:
            return "F2"

    if ev.schema_errors > 0:
        return "F3"

    if ev.stage == "load" and ev.span_status == "ERROR":
        return "F6"
    if ev.error_type in {"UnicodeDecodeError", "IntegrityError", "ConversionError"}:
        return "F6"

    return "F4"


def fingerprint(failure_class: str, ev: Evidence) -> str:
    msg = (ev.error_message or "")[:300]
    msg = _UUID.sub("<uuid>", msg)
    msg = _NUM.sub("<n>", msg)
    failed = ",".join(sorted(ev.failed_assertions))
    key = f"{failure_class}|{ev.source_id}|{ev.stage}|{ev.error_type}|{msg}|{failed}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]
