"""mDNS discovery of EKG kettles.

The firmware advertises ``EKG._ekg._tcp.local.`` with hostname
``EKG-<last 3 MAC bytes>.local.`` and port 8888. Port 8888 has been observed
closed; the HTTP CLI is on port 80, so only the address is used.

Requires the ``zeroconf`` package (``pip install fellow-ekg[discovery]``).
Home Assistant already ships it; there, prefer declaring the service type in
the integration's manifest.json (``"zeroconf": ["_ekg._tcp.local."]``) and
use :func:`kettle_from_service_info` in the config flow.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from zeroconf.asyncio import AsyncZeroconf

SERVICE_TYPE = "_ekg._tcp.local."
_HOSTNAME_MAC = re.compile(r"^EKG-([0-9a-f]{2})-([0-9a-f]{2})-([0-9a-f]{2})\.", re.I)


@dataclass(frozen=True)
class DiscoveredKettle:
    name: str
    hostname: str
    host: str
    mdns_port: int | None
    mac_suffix: str | None  # e.g. "f0:73:3c"; stable id for HA's unique_id

    @property
    def unique_id(self) -> str:
        return self.mac_suffix or self.hostname


def kettle_from_service_info(info: Any) -> DiscoveredKettle | None:
    """Build a DiscoveredKettle from a zeroconf ``ServiceInfo``-like object.

    Accepts anything with ``name``, ``server``, ``port`` and
    ``parsed_addresses()``, so it also works on HA's ``ZeroconfServiceInfo``
    after adapting. Returns None if there's no IPv4 address.
    """
    addresses = [a for a in info.parsed_addresses() if ":" not in a]
    if not addresses:
        return None
    hostname = info.server or ""
    m = _HOSTNAME_MAC.match(hostname)
    return DiscoveredKettle(
        name=info.name.removesuffix(f".{SERVICE_TYPE}"),
        hostname=hostname,
        host=addresses[0],
        mdns_port=info.port,
        mac_suffix=":".join(m.groups()).lower() if m else None,
    )


async def async_discover(
    timeout: float = 5.0, aiozc: AsyncZeroconf | None = None
) -> list[DiscoveredKettle]:
    """Browse the LAN for ``timeout`` seconds and return kettles found.

    Pass an existing ``AsyncZeroconf`` to reuse it (in HA:
    ``await zeroconf.async_get_async_instance(hass)``); otherwise one is
    created and closed here.
    """
    from zeroconf import ServiceStateChange
    from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo, AsyncZeroconf

    owns = aiozc is None
    zc = aiozc or AsyncZeroconf()
    names: set[str] = set()

    def on_change(zeroconf: Any, service_type: str, name: str, state_change: Any) -> None:
        if state_change in (ServiceStateChange.Added, ServiceStateChange.Updated):
            names.add(name)

    browser = AsyncServiceBrowser(zc.zeroconf, SERVICE_TYPE, handlers=[on_change])
    try:
        await asyncio.sleep(timeout)
    finally:
        await browser.async_cancel()

    try:
        found: dict[str, DiscoveredKettle] = {}
        for name in names:
            info = AsyncServiceInfo(SERVICE_TYPE, name)
            if not await info.async_request(zc.zeroconf, 3000):
                continue
            kettle = kettle_from_service_info(info)
            if kettle:
                found[kettle.unique_id] = kettle
        return sorted(found.values(), key=lambda k: k.host)
    finally:
        if owns:
            await zc.async_close()
