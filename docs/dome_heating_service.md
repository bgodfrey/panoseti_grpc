# Dome Heating Telemetry Service

The dome heating telemetry service is a DAQ-node process that reads local dome
temperature and humidity sensors and publishes a latest-value environmental
snapshot to the head node's Telemetry gRPC service.

Despite the name, the current implementation does not control heater hardware.
It only reports telemetry and can emit a telemetry-only `TURN_ON_HEATER` notice
when the configured roof/internal temperature delta threshold is exceeded.

## Runtime Model

This service uses the existing Telemetry service instead of adding a new gRPC
server interface.

| Location | Process | Responsibility |
| --- | --- | --- |
| DAQ node / dome computer | `pseti-grpc dome-temperature` | Read USB sensors, calculate derived values, publish telemetry |
| Head node | `pseti-grpc server --profile headnode` | Run Telemetry gRPC server |
| Head node | Redis | Store the latest dome environmental payload |

The DAQ node pushes samples to the head node. The head node does not poll the
DAQ node for these values.

## Sensor Inputs

The current sensor support comes from the `temp_config` submodule, which points
at the environmental monitoring hardware repository.

Supported sensors:

- SHT45/SHT4x Trinkey: internal temperature and relative humidity
- DS18B20 probe on QT Py RP2040: roof temperature

The default config maps:

```toml
[sensors]
roof_source = "ds18b20"
internal_source = "sht45"
```

The sources can be swapped for testing, but the expected dome setup is DS18B20
for roof temperature and SHT45 for internal temperature/humidity.

## Head Node Setup

Start Redis and then run the unified server with Telemetry enabled. For the
current head-node profile:

```bash
pseti-grpc server --profile headnode
```

The Telemetry config includes the experimental dome environment device type:

```toml
[devices.dome_environment]
mode = "experimental"
redis_prefix = "DEV_DOME_ENV_"
ttl_seconds = 86400
description = "Dome environmental telemetry prototype"
```

Payloads are stored as Redis hashes. For a DAQ node with
`device_id = "dome_a"`, the Redis key is:

```text
DEV_DOME_ENV_dome_a
```

## DAQ Node Config

Each DAQ node should have its own local TOML config. Do not edit the checked-in
example on each machine; instead copy it to a deployment path such as:

```bash
sudo mkdir -p /etc/panoseti
sudo cp src/panoseti_grpc/dome_heating/config/dome_a.toml /etc/panoseti/dome-temperature.toml
```

Then edit `/etc/panoseti/dome-temperature.toml` for that dome:

```toml
[dome]
device_id = "dome_a"
description = "Dome A environmental monitor"

[telemetry]
host = "HEADNODE_IP_OR_DNS_NAME"
port = 50051
device_type = "dome_environment"
interval_seconds = 30

[sensors]
roof_source = "ds18b20"
internal_source = "sht45"

# Leave blank for USB VID:PID auto-discovery.
sht45_port = ""
ds18b20_port = ""

[notices]
delta_notice_threshold_c = 2.5

[heater]
heater_on = false

[logging]
quiet = true
```

The `host` value must be something the operating system can resolve. gRPC does
not read SSH aliases from `~/.ssh/config`. Use an IP address, DNS name, mDNS
name, or an `/etc/hosts` entry.

The fields that usually differ per DAQ node are:

- `device_id`
- `description`
- any explicit serial port overrides, if auto-discovery is not used

The fields that are usually shared are:

- `host`
- `port`
- `device_type`
- `interval_seconds`
- sensor role mapping

## Running Manually

From the `panoseti_grpc` repo root:

```bash
pseti-grpc dome-temperature \
  --config src/panoseti_grpc/dome_heating/config/dome_a.toml \
  --once \
  --no-publish \
  --verbose
```

That reads one hardware sample, prints it, and exits without publishing to gRPC.

To publish one sample to the configured Telemetry server:

```bash
pseti-grpc dome-temperature \
  --config src/panoseti_grpc/dome_heating/config/dome_a.toml \
  --once \
  --verbose
```

For normal continuous operation:

```bash
pseti-grpc dome-temperature --config /etc/panoseti/dome-temperature.toml
```

With `quiet = true`, the process still publishes every sample, but it suppresses
normal sample lines after startup. It still prints errors, the first sample, and
heater-notice transitions.

## Redis Verification

On the head node, inspect the latest payload:

```bash
docker exec -it panoseti-redis redis-cli HGETALL DEV_DOME_ENV_dome_a
```

If Docker requires elevated access on the host, use `sudo docker ...` or add the
user to the `docker` group and start a new login shell.

Expected fields include:

```text
roof_temp_c
internal_temp_c
delta_temp_c
humidity_percent
dew_point_c
heater_notice
heater_notice_active
heater_on
client_unix_time
Computer_UTC
```

`client_unix_time` should change as new samples are published.

## Heater Notice

The heater notice is currently informational only.

When the absolute temperature delta is greater than or equal to
`delta_notice_threshold_c`, the payload reports:

```text
heater_notice = "TURN_ON_HEATER"
heater_notice_active = true
```

Otherwise it reports:

```text
heater_notice = "none"
heater_notice_active = false
```

This logic is intentionally isolated in a helper function so it can later include
humidity, dew point, hysteresis, or more conservative state handling.

## systemd Deployment

The repository includes a generic service file:

```text
systemd/dome-temp-telemetry.service
```

It reads local overrides from:

```text
/etc/panoseti/dome-temperature.env
```

Example environment file:

```bash
sudo cp systemd/dome-temperature.env.example /etc/panoseti/dome-temperature.env
```

Edit it for the DAQ node:

```sh
PSETI_GRPC_BIN=/home/panoseti/anaconda3/envs/py314/bin/pseti-grpc
DOME_TEMPERATURE_CONFIG=/etc/panoseti/dome-temperature.toml
DOME_TEMPERATURE_FLAGS=
```

Install and start the service:

```bash
sudo cp systemd/dome-temp-telemetry.service /etc/systemd/system/dome-temp-telemetry.service
sudo systemctl daemon-reload
sudo systemctl enable --now dome-temp-telemetry.service
```

Useful checks:

```bash
systemctl status dome-temp-telemetry.service
journalctl -u dome-temp-telemetry.service -f
sudo systemctl restart dome-temp-telemetry.service
```

For long-running deployments, keep `quiet = true` and cap journal usage with
`SystemMaxUse` in `/etc/systemd/journald.conf` or a drop-in under
`/etc/systemd/journald.conf.d/`.

## Tests

Run the dome heating unit tests from the repo root:

```bash
scripts/run-ci-tests/run-dome-heating-ci-test.sh
```

The script also works when run from inside `scripts/run-ci-tests/` because it
resolves the repository root from its own path.

To force a specific Python interpreter:

```bash
PYTHON=/home/panoseti/anaconda3/envs/py314/bin/python \
  scripts/run-ci-tests/run-dome-heating-ci-test.sh
```
