from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

DB_TYPE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,31}$")


def validate_db_type(db_type: str) -> str:
    if not isinstance(db_type, str) or not DB_TYPE_PATTERN.match(db_type):
        raise ValueError(
            f"Invalid db_type '{db_type}'. Must match ^[a-z][a-z0-9_]{{1,31}}$."
        )
    return db_type


def new_uuid() -> str:
    return str(uuid.uuid4())


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def parse_iso(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
