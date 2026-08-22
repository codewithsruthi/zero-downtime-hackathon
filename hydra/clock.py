from datetime import datetime, timezone


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(ts: datetime | None = None) -> str:
    stamp = ts or now()
    return stamp.isoformat()
