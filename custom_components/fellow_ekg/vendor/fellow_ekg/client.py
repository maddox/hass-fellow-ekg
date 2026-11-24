from __future__ import annotations

import asyncio
import logging

import aiohttp

from .exceptions import EKGCommandError, EKGConnectionError
from .models import EKGState, FirmwareInfo
from .parser import parse_cli_output, parse_firmware_info, parse_state

_LOGGER = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 10
# Safety net for raw heater control, in seconds. See heat_on().
DEFAULT_MAX_HEAT_SECONDS = 600


class EKGClient:
    """Async client for the kettle's unauthenticated HTTP CLI.

    Pass in Home Assistant's shared ``aiohttp.ClientSession``
    (``async_get_clientsession(hass)``). If you don't, the client creates one
    and ``close()`` shuts it down.
    """

    def __init__(
        self,
        host: str,
        session: aiohttp.ClientSession | None = None,
        *,
        port: int = 80,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.host = host
        self._base_url = f"http://{host}:{port}"
        self._session = session
        self._owns_session = session is None
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        # The device has a single shared log buffer, so don't let commands overlap.
        self._lock = asyncio.Lock()
        self._heat_off_task: asyncio.Task[None] | None = None

    async def __aenter__(self) -> EKGClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    async def close(self) -> None:
        self._cancel_heat_watchdog()
        if self._owns_session and self._session is not None:
            await self._session.close()
            self._session = None

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self._session

    async def _get(self, path: str, params: dict[str, str] | None = None) -> str:
        try:
            async with self._get_session().get(
                f"{self._base_url}{path}", params=params, timeout=self._timeout
            ) as resp:
                resp.raise_for_status()
                return await resp.text()
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise EKGConnectionError(f"error talking to {self.host}: {err}") from err

    async def command(self, cmd: str) -> list[str]:
        """Send one CLI command and return its output lines."""
        async with self._lock:
            body = await self._get("/cli", {"cmd": cmd})
        return parse_cli_output(body, cmd)

    # -- Read-only ---------------------------------------------------------

    async def get_firmware_info(self) -> FirmwareInfo:
        """Read the status page. A cheap, side-effect-free connectivity check."""
        return parse_firmware_info(await self._get("/"))

    async def get_state(self) -> EKGState:
        """Full kettle state: mode, temperatures (°C), flags. One request."""
        return parse_state(await self.command("state"))

    async def get_temperature(self) -> float | None:
        """Current water temperature in °C.

        Read from ``state``; the ``temp`` command only reports statistics
        after ``tstprd`` has been configured, and returns zeros otherwise.
        """
        return (await self.get_state()).temperature

    # -- Heater ------------------------------------------------------------

    async def heat_on(self, max_seconds: float | None = DEFAULT_MAX_HEAT_SECONDS) -> None:
        """Drive the heater GPIO high (CLI ``heaton``).

        WARNING: this sets the relay pin directly. It very likely bypasses the
        firmware's target-temperature control and boil-dry protection, so the
        heater stays on until something turns it off. As a safety net the
        client sends ``heatoff`` after ``max_seconds`` (default 10 minutes).
        Pass ``max_seconds=None`` to disable that, at your own risk.

        The watchdog only lives as long as this process, so a Home Assistant
        integration should also turn the heater off at a target temperature.
        """
        self._cancel_heat_watchdog()
        await self._expect_ok("heaton")
        if max_seconds is not None:
            self._heat_off_task = asyncio.create_task(self._heat_watchdog(max_seconds))

    async def heat_off(self) -> None:
        """Drive the heater GPIO low (CLI ``heatoff``)."""
        self._cancel_heat_watchdog()
        await self._expect_ok("heatoff")

    async def _expect_ok(self, cmd: str) -> None:
        # command() raises EKGCommandError if the firmware rejects it.
        await self.command(cmd)

    async def _heat_watchdog(self, seconds: float) -> None:
        await asyncio.sleep(seconds)
        _LOGGER.warning("Heater on for %ss on %s; sending heatoff", seconds, self.host)
        self._heat_off_task = None
        try:
            await self._expect_ok("heatoff")
        except (EKGConnectionError, EKGCommandError):
            _LOGGER.exception("Watchdog failed to turn heater off on %s", self.host)

    def _cancel_heat_watchdog(self) -> None:
        task, self._heat_off_task = self._heat_off_task, None
        if task is not None and task is not asyncio.current_task():
            task.cancel()
