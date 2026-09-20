# cbpi4-ESPHome

CraftBeerPi4 plugin that talks directly to [ESPHome](https://esphome.io) nodes
using the ESPHome **native API** (`aioesphomeapi`). Home Assistant is **not**
required.

The plugin registers two types:

| Type | Kind | What it does |
| ---- | ---- | ------------ |
| **ESPHome Sensor** | Sensor | Reads a CO2, temperature or relative humidity value from an ESPHome sensor entity |
| **ESPHome Actor** | Actor | Switches an ESPHome switch entity (for example a relay) on and off |

The actor is a plain on/off switch, there is no PWM / power control.

Typical use: a Sonoff / ESP32 / ESP8266 node with one or more temperature
sensors and relays that control a fridge, heater or cooler of a fermenter.

## Requirements

* CraftBeerPi4 (`cbpi4 >= 4.0.0.34`)
* `aioesphomeapi >= 17.0.0` (installed automatically with the plugin)
* An ESPHome node with the `api:` component enabled

## Installation

    sudo pip3 install https://github.com/arcidodo/cbpi4-ESPHome/archive/refs/heads/main.zip

Or from a local copy of this repository:

    sudo pip3 install .

Then restart CraftBeerPi (or the Pi). If CraftBeerPi runs in a virtualenv, use
that environment's `pip`.

## ESPHome configuration

The node only needs the native API enabled. Encryption is optional but
recommended:

```yaml
api:
  encryption:
    key: "<your base64 key>"

sensor:
  - platform: dallas_temp          # or any other temperature sensor
    name: "kast_temp"

switch:
  - platform: gpio
    pin: GPIO12
    name: "Koeling"
```

The **Entity Name** you enter in CraftBeerPi has to match the `name:` (or the
resulting object id, for example `kast_temp`) of the entity in your ESPHome
configuration.

## Usage

### Sensor

1. Go to **Hardware > Sensor** and add a sensor.
2. Choose the type **ESPHome Sensor** and fill in the properties below.
3. Use the sensor in a fermenter or kettle, or as a dashboard widget.

| Property | Description |
| -------- | ----------- |
| Type | What the entity measures: `CO2`, `Temperature` or `Relative Humidity` |
| Host | IP address or hostname of the ESPHome node, for example `192.168.1.50` |
| Port | Native API port of the node (default `6053`) |
| Encryption Key | API encryption key (base64) from the ESPHome `api:` section. Leave empty if the API is not encrypted |
| Entity Name | Name or object id of the sensor entity in ESPHome |
| Request Timeout | Seconds to wait before reconnecting after a connection error (default `5`) |

### Actor

1. Go to **Hardware > Actor** and add an actor.
2. Choose the type **ESPHome Actor** and fill in the properties below.
3. Assign it as heater or cooler of a fermenter or kettle, or add it to the
   dashboard as an Actor widget.

| Property | Description |
| -------- | ----------- |
| Host | IP address or hostname of the ESPHome node |
| Port | Native API port of the node (default `6053`) |
| Encryption Key | API encryption key (base64). Leave empty if the API is not encrypted |
| Entity Name | Name or object id of the switch entity in ESPHome |
| Request Timeout | Seconds to wait before reconnecting after a connection error (default `5`) |

## How it works

* On startup the plugin lists the entities of the node, looks up the entity
  with the configured name (or object id) and subscribes to its state updates.
  The sensor therefore follows the node live, it does not poll.
* Sensors and actors that use the same host and port share one connection to
  the node.
* If the connection is lost (node reboot, WiFi drop, ...) the plugin logs a
  warning and keeps retrying every *Request Timeout* seconds until the node is
  reachable again.

## Notes

* The relay state is kept by the ESPHome node itself. Use the
  `restore_mode` setting of the ESPHome switch to decide what it does after a
  power loss of the node.
* Keep the encryption key private. Do not paste it in screenshots or issues.

## License

GPLv3
