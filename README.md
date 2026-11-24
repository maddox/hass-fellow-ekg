# Fellow EKG Pro for Home Assistant

A local Home Assistant integration for the **Fellow Stagg EKG Pro** electric
kettle. No cloud, no app.

The EKG Pro is discontinued, but its firmware still serves a small HTTP
interface on your LAN. This integration uses the
[`fellow-ekg`](https://github.com/maddox/fellow-ekg) library to read the
kettle's temperature and mode, and to switch its heater on and off with
automatic shut-off.

> Not affiliated with or endorsed by Fellow. Read [Safety](#safety) before
> using the heater switch.

## Installation (HACS)

1. In Home Assistant, open **HACS**, then the **⋮** menu, then **Custom repositories**.
2. Add `https://github.com/maddox/hass-fellow-ekg` with type **Integration**.
3. Search HACS for **Fellow EKG Pro**, download it, and restart Home Assistant.
4. Your kettle should appear under **Settings → Devices & services** as
   *Discovered*. Click **Add**. If it doesn't appear, click
   **Add integration**, search for **Fellow EKG Pro**, and enter the kettle's IP address.

### Manual installation

Copy `custom_components/fellow_ekg` into your Home Assistant
`config/custom_components/` directory and restart.

## Entities

| Entity | Type | Description |
|---|---|---|
| Water temperature | Sensor | Current water temperature |
| Kettle target temperature | Sensor | The target set on the kettle's dial |
| Mode | Sensor | Kettle mode as the firmware reports it, e.g. `S_Off`. Attributes include the screen, the kettle clock, and raw status flags |
| Boiling point | Sensor (diagnostic) | Boiling point, adjusted for the kettle's altitude setting |
| Heater | Switch | Turns the heating element on or off. See [Safety](#safety) |
| Auto-off temperature | Number | The heater switch turns off when the water reaches this. It defaults to the kettle's own target |

Temperatures are reported in °C, and Home Assistant converts them to your
unit system.

The kettle is polled every 15 seconds, and every 2 seconds while the Heater
switch is on.

## Options

**Settings → Devices & services → Fellow EKG Pro → Configure**

- **Maximum heating time** (1–30 minutes, default 10): the Heater switch always
  turns off after this long, even if the auto-off temperature hasn't been reached.

## Safety

The kettle's local interface has no "heat to X°" command. The Heater switch
drives the heating element's relay directly, which very likely **bypasses the
kettle's own temperature control and boil-dry protection**. This integration
adds its own safeguards:

1. **Auto-off temperature:** it polls every 2 seconds while heating and turns
   the heater off once the water reaches the Auto-off temperature.
2. **Time limit:** it turns the heater off after the Maximum heating time.
3. **Library timer:** the underlying library separately sends `heatoff` after
   the same time limit.
4. **Already hot:** it refuses to turn on if the water is already at or above
   the auto-off temperature.
5. **Unload:** removing, reloading, or reconfiguring the integration turns the
   heater off first.
6. **Retries:** if a safety shut-off fails, for example during a Wi-Fi blip,
   it retries on every poll.

Even so, **never run the heater with an empty kettle or with the kettle off its
base**. Don't automate it without someone around until you trust it. The
heater switch's state is *assumed*: it shows what Home Assistant last
commanded, because the kettle doesn't report the relay state.

Turning the kettle on with its own button and dial isn't affected by this
integration.

## Security

The kettle's HTTP interface has no authentication. Anyone who can reach it can
turn on the heater or flash firmware. Put it on an isolated IoT network, block
its internet access, and allow only Home Assistant to reach it.

## Troubleshooting

- **Not discovered:** the kettle advertises `_ekg._tcp.local.` over mDNS. If
  Home Assistant is on a different VLAN, you need an mDNS reflector, or you
  can add the kettle by IP address.
- **Diagnostics:** on the device page, **⋮ → Download diagnostics** includes
  the kettle's raw `state` output. Please attach it to bug reports, especially
  if you see a mode that isn't `S_Off`. Only `S_Off` has been observed so far.

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install pytest-homeassistant-custom-component -e ../fellow-ekg[discovery]
.venv/bin/pytest
```

The tests mock the kettle client and zeroconf, so they never touch a real device.
