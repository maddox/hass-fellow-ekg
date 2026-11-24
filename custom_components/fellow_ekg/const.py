from datetime import timedelta

DOMAIN = "fellow_ekg"

CONF_MAX_HEAT_MINUTES = "max_heat_minutes"
DEFAULT_MAX_HEAT_MINUTES = 10

IDLE_INTERVAL = timedelta(seconds=15)
HEATING_INTERVAL = timedelta(seconds=2)

# HA-side auto-off target, in °C.
MIN_TARGET = 40.0
MAX_TARGET = 100.0
DEFAULT_TARGET = 96.0
