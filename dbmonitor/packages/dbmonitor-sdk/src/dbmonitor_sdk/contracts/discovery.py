from __future__ import annotations

from typing import Iterable, Protocol

from dbmonitor_sdk.models.server import DiscoveredServer, DiscoveryContext


class DiscoveryPlugin(Protocol):
    plugin_id: str

    def discover(self, context: DiscoveryContext) -> Iterable[list[DiscoveredServer]]:
        """Yields pages of normalized DiscoveredServer items."""
        ...
