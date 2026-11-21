from __future__ import annotations

from typing import Iterable

STANDARD_COLLECTOR_GROUPS: tuple[str, ...] = (
    "health",
    "sessions",
    "replication",
    "performance",
    "capacity",
)


def validate_collector_groups(groups: Iterable[str]) -> list[str]:
    result: list[str] = []
    for g in groups:
        if g not in STANDARD_COLLECTOR_GROUPS:
            raise ValueError(
                f"Unknown collector group '{g}'. Expected one of {STANDARD_COLLECTOR_GROUPS}."
            )
        if g not in result:
            result.append(g)
    return result
