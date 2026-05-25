# eebus-dyn-load-service


## Installation

```bash
python -m pip install -r requirements.txt
```

## Run service

```bash
python eebus_dyn-load_service.py \
  --identity /path/to/identity.json \
  --peer-ski 11AA22BB33CC44DD55EE66FF77889900AABBCCDD \
  --interface-ip 192.168.1.10
```

Options:

- `--peer-ski`: SKI of the coupled EEBus peer
- `--pairing-wait`: wait up to 2 minutes for inbound pairing requests, confirm the SKI in the console, and exit after successful pairing or timeout
- `--pairing-ski <SKI>`: discover the peer by SKI and initiate outbound pairing
- `--bind-host` (default: `0.0.0.0`)
- `--port` (default: `4712`)
- `--path` (default: `/ship/`)
- `--device-id` (default: `EEBUS-DYN-LOAD`)
- `--ship-id`, `--instance-name`, `--server-name`

Choose exactly one coupling mode: `--peer-ski`, `--pairing-wait`, or `--pairing-ski`.

Examples:

```bash
# Wait for inbound pairing requests (2 minutes max)
python eebus_dyn-load_service.py --identity /path/to/identity.json --pairing-wait

# Discover and pair to a specific SKI
python eebus_dyn-load_service.py --identity /path/to/identity.json --pairing-ski <PEER_SKI>
```

## Create identity file

Example using `eebus-sdk` CLI:

```bash
eebus identity create --out-dir /path/to/identity
```

Then use:

```bash
python eebus_dyn-load_service.py --identity /path/to/identity/identity.json --peer-ski <PEER_SKI>
```

When running, the service logs:

- Discovery-related messages from remote peers
- Incoming LCP (`loadControlLimitListData`) write messages
