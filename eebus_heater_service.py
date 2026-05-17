from __future__ import annotations

import argparse
import asyncio
import json
import socket
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

DISCOVERY_COMMANDS = {
    "nodeManagementDetailedDiscoveryData",
    "nodeManagementUseCaseData",
}


@dataclass(slots=True)
class RuntimeHandles:
    announcer: Any
    listener: Any


def _load_sdk() -> dict[str, Any]:
    try:
        from eebus_sdk import IdentityStore
        from eebus_sdk.advertisement import ShipServiceAdvertiser, ShipServiceAdvertisement
        from eebus_sdk.discovery import detect_interface_ip
        from eebus_sdk.server import ShipServer, ShipServerConfig
    except ImportError as exc:  # pragma: no cover - exercised only when dependency is missing
        raise RuntimeError(
            "Missing dependency 'eebus-sdk'. Install dependencies with `python -m pip install -r requirements.txt`."
        ) from exc

    return {
        "IdentityStore": IdentityStore,
        "detect_interface_ip": detect_interface_ip,
        "ShipServiceAdvertiser": ShipServiceAdvertiser,
        "ShipServiceAdvertisement": ShipServiceAdvertisement,
        "ShipServer": ShipServer,
        "ShipServerConfig": ShipServerConfig,
    }


def is_discovery_commands(commands: Iterable[str]) -> bool:
    return any(command in DISCOVERY_COMMANDS for command in commands)


def format_lcp_message(payload: Mapping[str, Any]) -> str:
    return json.dumps(dict(payload), sort_keys=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="EEBus heater service")
    parser.add_argument("--identity", required=True, help="Path to eebus-sdk identity.json")
    parser.add_argument("--peer-ski", required=True, help="SKI of the coupled EEBus peer")
    parser.add_argument("--interface-ip", help="IPv4 interface address for discovery advertisement")
    parser.add_argument("--bind-host", default="0.0.0.0", help="Host interface to bind SHIP listener to")
    parser.add_argument("--port", type=int, default=4712, help="SHIP listener port")
    parser.add_argument("--path", default="/ship/", help="SHIP websocket path")
    parser.add_argument("--ship-id", help="Optional SHIP ID override")
    parser.add_argument("--device-id", default="EEBUS-HEATER", help="Advertised device identifier")
    parser.add_argument("--instance-name", help="Optional DNS-SD instance name")
    parser.add_argument("--server-name", help="Optional advertised server name")
    return parser


def build_runtime(args: argparse.Namespace) -> RuntimeHandles:
    sdk = _load_sdk()
    identity = sdk["IdentityStore"].load(args.identity)
    interface_ip = args.interface_ip or sdk["detect_interface_ip"]()
    announcer = sdk["ShipServiceAdvertiser"](
        sdk["ShipServiceAdvertisement"](
            interface_ip=interface_ip,
            port=args.port,
            ski=identity.ski,
            ship_id=args.ship_id or identity.ship_id,
            device_id=args.device_id,
            instance_name=args.instance_name,
            server_name=args.server_name or f"{socket.gethostname()}.local.",
            path=args.path,
        )
    )
    listener = sdk["ShipServer"](
        sdk["ShipServerConfig"](
            identity=identity,
            ship_id=args.ship_id or identity.ship_id,
            bind_host=args.bind_host,
            port=args.port,
            path=args.path,
            device_id=args.device_id,
            trusted_client_skis=(args.peer_ski,),
        )
    )
    return RuntimeHandles(announcer=announcer, listener=listener)


async def run_service(args: argparse.Namespace) -> int:
    runtime = build_runtime(args)
    await runtime.listener.start()
    await runtime.announcer.start()
    try:
        print(f"Service started on {args.bind_host}:{args.port}. Press Ctrl-C to stop.", flush=True)
        async for event in runtime.listener.events():
            if event.kind == "summary":
                commands = [str(command) for command in event.payload.get("commands", [])]
                if is_discovery_commands(commands):
                    print(f"Discover message received: commands={','.join(commands)}", flush=True)
                continue
            if event.kind == "inbound_load_power_write":
                print(f"LCP message received: {format_lcp_message(event.payload)}", flush=True)
    finally:
        await runtime.announcer.stop()
        await runtime.listener.stop()
    return 0


def main() -> int:
    args = build_parser().parse_args()
    try:
        return asyncio.run(run_service(args))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
