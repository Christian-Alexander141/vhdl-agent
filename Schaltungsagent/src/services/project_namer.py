import re
import uuid


MAX_NAME_LENGTH = 60
UNIQUE_SUFFIX_LENGTH = 6


def sanitize(name: str) -> str:
    """Normalize a name: lowercase, dashes instead of separators, safe charset."""
    name = (name or "").lower().strip()
    name = re.sub(r"[^a-zäöüß0-9]+", "-", name)
    name = re.sub(r"-+", "-", name).strip("-")
    return name[:MAX_NAME_LENGTH].rstrip("-")


def slugify(request: str) -> str:
    """Derive a file-safe name from the raw request text."""
    return sanitize(request) or "projekt"


def make_unique(name: str) -> str:
    """Append a short unique suffix so project folders never collide."""
    suffix = uuid.uuid4().hex[:UNIQUE_SUFFIX_LENGTH]
    return f"{name}-{suffix}"
