from __future__ import annotations

from typing import Sequence

from dbmonitor_sdk.contracts.manifest import PluginManifest
from dbmonitor_sdk.models.profile import PollingProfile


def validate_profile_against_plugin(
    profile: PollingProfile,
    manifest: PluginManifest,
    platform_min_interval_seconds: int = 30,
) -> list[str]:
    """Returns intersected collector groups or raises ValueError on floor/intersection violation."""
    if profile.interval_seconds < platform_min_interval_seconds:
        raise ValueError(
            f"Profile '{profile.name}' interval {profile.interval_seconds}s violates "
            f"platform floor ({platform_min_interval_seconds}s)."
        )

    intersected = [g for g in profile.collector_groups if g in manifest.collector_groups]
    if not intersected:
        raise ValueError(
            f"Profile '{profile.name}' collector groups {list(profile.collector_groups)} "
            f"have an empty intersection with plugin '{manifest.plugin_id}' "
            f"groups {list(manifest.collector_groups.keys())}."
        )

    for group in intersected:
        spec = manifest.collector_groups[group]
        if profile.interval_seconds < spec.min_interval_seconds:
            raise ValueError(
                f"Profile '{profile.name}' interval {profile.interval_seconds}s violates "
                f"collector group '{group}' floor ({spec.min_interval_seconds}s) "
                f"on plugin '{manifest.plugin_id}'."
            )

    return intersected
