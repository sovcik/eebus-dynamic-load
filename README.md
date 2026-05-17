# eebus-heater

Python 3.11+ service that hosts an EEBus SHIP endpoint, responds to EEBus discovery requests, and prints received LCP messages to the console.

## Installation

```bash
python -m pip install -r requirements.txt
```

## Run service

```bash
python eebus_heater_service.py \
  --identity /path/to/identity.json \
  --interface-ip 192.168.1.10
```

Options:

- `--bind-host` (default: `0.0.0.0`)
- `--port` (default: `4712`)
- `--path` (default: `/ship/`)
- `--device-id` (default: `EEBUS-HEATER`)
- `--ship-id`, `--instance-name`, `--server-name`

When running, the service logs:

- Discovery-related messages from remote peers
- Incoming LCP (`loadControlLimitListData`) write messages
