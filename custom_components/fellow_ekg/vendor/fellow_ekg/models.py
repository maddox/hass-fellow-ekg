from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class FirmwareInfo:
    """Parsed from the kettle's status page at ``/``."""

    version: str | None
    build_date: str | None
    build_time: str | None
    running_partition: str | None


def _measurement(value: str | None) -> tuple[float, str | None] | None:
    """'26.110954 C' -> (26.110954, 'C'); '205 F' -> (205.0, 'F')."""
    if value is None:
        return None
    m = re.match(r"^\s*(-?\d+(?:\.\d+)?)\s*([CF])?\b", value)
    if not m:
        return None
    return float(m.group(1)), m.group(2)


def _celsius(value: str | None) -> float | None:
    measured = _measurement(value)
    if measured is None:
        return None
    number, unit = measured
    return (number - 32) * 5 / 9 if unit == "F" else number


@dataclass(frozen=True)
class EKGState:
    """Output of the ``state`` CLI command.

    ``values`` holds every ``key=value`` line verbatim. Example from a real
    kettle (firmware 1.2.5CL)::

        scrname=wnd
        mode=S_Off
        tempr=26.110954 C       current water temperature
        temprB=100.000000 C     boiling point (altitude-adjusted)
        temprT=96.111115 C      kettle's target temperature
        temps=205 F             target as shown on the display
        ketl= ho 0 wd 0 nw 0 ipb 0 bf 0 tr 0
        units=0
        clock=16:39
        ble conn=0

    The typed properties below interpret the fields whose meaning is clear.
    """

    values: dict[str, str]
    raw: list[str] = field(default_factory=list)

    @property
    def mode(self) -> str | None:
        """Kettle mode, e.g. ``S_Off``."""
        return self.values.get("mode")

    @property
    def temperature(self) -> float | None:
        """Current water temperature in °C."""
        return _celsius(self.values.get("tempr"))

    @property
    def target_temperature(self) -> float | None:
        """The kettle's own target temperature in °C (set on the dial)."""
        return _celsius(self.values.get("temprT"))

    @property
    def boil_temperature(self) -> float | None:
        """Boiling point in °C, adjusted for the altitude setting."""
        return _celsius(self.values.get("temprB"))

    @property
    def display_setpoint(self) -> tuple[float, str | None] | None:
        """Target as shown on the display, e.g. ``(205.0, 'F')``."""
        return _measurement(self.values.get("temps"))

    @property
    def screen(self) -> str | None:
        return self.values.get("scrname")

    @property
    def clock(self) -> str | None:
        return self.values.get("clock")

    @property
    def ble_connected(self) -> bool | None:
        value = self.values.get("ble conn")
        return None if value is None else value != "0"

    @property
    def kettle_flags(self) -> dict[str, int]:
        """The ``ketl`` line as a dict, e.g. ``{'ho': 0, 'wd': 0, ...}``.

        Flag meanings are undocumented.
        """
        tokens = self.values.get("ketl", "").split()
        flags: dict[str, int] = {}
        for key, value in zip(tokens[::2], tokens[1::2]):
            try:
                flags[key] = int(value)
            except ValueError:
                continue
        return flags
