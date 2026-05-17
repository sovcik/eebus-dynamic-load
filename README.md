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
  --peer-ski 11AA22BB33CC44DD55EE66FF77889900AABBCCDD \
  --interface-ip 192.168.1.10
```

Options:

- `--peer-ski` SKI of the coupled EEBus peer (required)
- `--bind-host` (default: `0.0.0.0`)
- `--port` (default: `4712`)
- `--path` (default: `/ship/`)
- `--device-id` (default: `EEBUS-HEATER`)
- `--ship-id`, `--instance-name`, `--server-name`

Coupling is done via the required `--peer-ski` parameter. The service allows incoming SHIP sessions only from this peer SKI, so coupling is completed before LCP messages can be received.

## Create identity file

Example using `eebus-sdk` CLI:

```bash
eebus identity create --out-dir /path/to/identity
```

Then use:

```bash
python eebus_heater_service.py --identity /path/to/identity/identity.json --peer-ski <PEER_SKI>
```

When running, the service logs:

- Discovery-related messages from remote peers
- Incoming LCP (`loadControlLimitListData`) write messages
