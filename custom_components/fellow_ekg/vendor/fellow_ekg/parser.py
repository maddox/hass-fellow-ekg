"""Pure parsing helpers for the kettle's HTTP responses.

The CLI endpoint (``GET /cli?cmd=<command>``) returns a small HTML form
followed by ESP-IDF log lines and the command's plain-text output::

    <form ...>...</form>
    I (2864731213) Cli: cmd len 5: 'state'
    I (2864731223) Main: OTA vd 1 ldt 2765075 ...
    scrname=wnd
    mode=S_Off
    I (2864731243) Cli: command 'state' ret 0

The page appears to show the device's recent log buffer, so it can contain
output from earlier commands. We only keep lines after the *last* echo of
the command we sent, and stop at its ``ret`` trailer.
"""

from __future__ import annotations

import html
import re

from .exceptions import EKGCommandError
from .models import EKGState, FirmwareInfo

# "I (2855011453) Cli: " -- level letter, tick count, tag
_LOG_PREFIX = re.compile(r"^[EWIDV] \(\d+\) (?P<tag>[^:]+):\s?")
_CMD_ECHO = re.compile(r"^cmd len \d+: '(?P<cmd>.*)'$")
_CMD_RET = re.compile(r"^command '(?P<cmd>.*)' ret (?P<ret>-?\d+)$")


def _split_lines(text: str) -> list[str]:
    text = re.sub(r"<form.*?</form>", "", text, flags=re.S | re.I)
    # Tags act as line breaks: "<h1>EKG</h1>Current version: ..." must split.
    text = re.sub(r"<[^>]+>", "\n", text)
    text = html.unescape(text)
    return [line.strip() for line in text.splitlines() if line.strip()]


def parse_cli_output(body: str, command: str) -> list[str]:
    """Return the plain output lines produced by ``command``.

    ESP-IDF log lines from other tasks (``I (123) Main: ...``) are dropped;
    lines logged by the ``Cli`` tag are kept without their prefix, since
    commands like ``help`` print their output that way.

    Raises EKGCommandError if the firmware doesn't echo the command, doesn't
    know it, or reports a non-zero return code.
    """
    lines = _split_lines(body)

    start = None
    for i, line in enumerate(lines):
        m = _LOG_PREFIX.match(line)
        if m and m.group("tag") == "Cli":
            echo = _CMD_ECHO.match(line[m.end():])
            if echo and echo.group("cmd") == command:
                start = i + 1
    if start is None:
        # No echo of our command: don't risk returning stale output.
        raise EKGCommandError(f"no output for command {command!r}")

    output: list[str] = []
    for line in lines[start:]:
        m = _LOG_PREFIX.match(line)
        if m is None:
            output.append(line)
            continue
        if m.group("tag") != "Cli":
            continue
        text = line[m.end():]
        if text.startswith("cannot find command"):
            raise EKGCommandError(text)
        ret = _CMD_RET.match(text)
        if ret and ret.group("cmd") == command:
            if ret.group("ret") != "0":
                raise EKGCommandError(f"command {command!r} returned {ret.group('ret')}")
            break
        output.append(text)
    return output


def parse_firmware_info(body: str) -> FirmwareInfo:
    """Parse the status page served at ``/``."""
    text = "\n".join(_split_lines(body))

    def grab(label: str) -> str | None:
        m = re.search(rf"^{label}:\s*(.*)$", text, flags=re.M)
        return (m.group(1).strip() or None) if m else None

    return FirmwareInfo(
        version=grab("Current version"),
        build_date=grab("Build date"),
        build_time=grab("Build time"),
        running_partition=grab("Running partition"),
    )


def parse_state(lines: list[str]) -> EKGState:
    """Parse ``state`` output: one ``key=value`` per line, value kept verbatim."""
    values: dict[str, str] = {}
    for line in lines:
        key, sep, value = line.partition("=")
        if sep and key.strip():
            values[key.strip()] = value.strip()
    return EKGState(values=values, raw=list(lines))
