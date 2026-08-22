import re
import uuid

SLUG_RE = re.compile(r"^[a-z][a-z0-9_]{1,62}$")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def require_slug(value: str, *, what: str = "id") -> str:
    if not SLUG_RE.match(value):
        raise ValueError(f"{what} must be a slug like gh_trending_repos, got {value!r}")
    return value
