from __future__ import annotations

from dbmonitor_sdk.contracts.manifest import PluginManifest
from dbmonitor_sdk.models.profile import PollingProfile, RetryPolicy
from dbmonitor_sdk.validation.profile_rules import validate_profile_against_plugin


def verify_profile_contract(manifest: PluginManifest) -> list[str]:
    checks: list[str] = []
    for group_name, spec in manifest.collector_groups.items():
        assert spec.min_interval_seconds >= 30, (
            f"Collector group '{group_name}' floor {spec.min_interval_seconds}s is below 30s platform floor."
        )

    hf_groups = tuple(g for g, s in manifest.collector_groups.items() if s.min_interval_seconds <= 60)
    if hf_groups:
        hf = PollingProfile(
            name="high_frequency",
            pool="high_frequency",
            interval_seconds=60,
            collector_groups=hf_groups,
            timeout_seconds=20,
            retry=RetryPolicy(max_attempts=1),
        )
        matched = validate_profile_against_plugin(hf, manifest)
        checks.append(f"high_frequency profile validated for groups {matched}")

    lf = PollingProfile(
        name="low_frequency",
        pool="low_frequency",
        interval_seconds=900,
        collector_groups=tuple(manifest.collector_groups.keys()),
        timeout_seconds=120,
        retry=RetryPolicy(max_attempts=3, backoff="exponential", jitter=True),
    )
    matched_lf = validate_profile_against_plugin(lf, manifest)
    checks.append(f"low_frequency profile validated for groups {matched_lf}")

    # Verify floor enforcement rejects 10s interval
    try:
        too_fast = PollingProfile(
            name="invalid_fast",
            pool="high_frequency",
            interval_seconds=10,
            collector_groups=tuple(manifest.collector_groups.keys()),
            timeout_seconds=5,
        )
        validate_profile_against_plugin(too_fast, manifest)
        raise AssertionError("Expected interval floor violation for 10s interval.")
    except ValueError:
        checks.append("interval floor enforcement rejected sub-floor 10s profile")

    return checks
