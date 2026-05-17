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
PAIRING_TIMEOUT_SECONDS = 120
PAIRING_CONFIRMATION_INPUTS = {"y", "yes"}


@dataclass(slots=True)
class RuntimeHandles:
    announcer: Any
    listener: Any


def _load_sdk() -> dict[str, Any]:
    try:
        from eebus_sdk import IdentityStore
        from eebus_sdk.advertisement import ShipServiceAdvertiser, ShipServiceAdvertisement
        from eebus_sdk.discovery import detect_interface_ip, discover_ship_services, normalize_ski
        from eebus_sdk.server import ShipServer, ShipServerConfig
        from eebus_sdk.ship import ShipConnectionConfig, ShipSession
        from eebus_sdk.trust import TrustStore
    except ImportError as exc:  # pragma: no cover - exercised only when dependency is missing
        raise RuntimeError(
            "Missing dependency 'eebus-sdk'. Install dependencies with `python -m pip install -r requirements.txt`."
        ) from exc

    return {
        "IdentityStore": IdentityStore,
        "detect_interface_ip": detect_interface_ip,
        "discover_ship_services": discover_ship_services,
        "normalize_ski": normalize_ski,
        "ShipServiceAdvertiser": ShipServiceAdvertiser,
        "ShipServiceAdvertisement": ShipServiceAdvertisement,
        "ShipServer": ShipServer,
        "ShipServerConfig": ShipServerConfig,
        "ShipConnectionConfig": ShipConnectionConfig,
        "ShipSession": ShipSession,
        "TrustStore": TrustStore,
    }


def is_discovery_commands(commands: Iterable[str]) -> bool:
    return any(command in DISCOVERY_COMMANDS for command in commands)


def format_lcp_message(payload: Mapping[str, Any]) -> str:
    return json.dumps(dict(payload), sort_keys=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="EEBus heater service")
    parser.add_argument("--identity", required=True, help="Path to eebus-sdk identity.json")
    parser.add_argument("--peer-ski", help="SKI of the coupled EEBus peer")
    parser.add_argument(
        "--pairing-wait",
        action="store_true",
        help="Wait up to 2 minutes for inbound pairing requests and pair with a user-confirmed SKI",
    )
    parser.add_argument("--pairing-ski", help="Discover and pair with the provided HEMS SKI")
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
            trusted_client_skis=(args.peer_ski,) if args.peer_ski else (),
        )
    )
    return RuntimeHandles(announcer=announcer, listener=listener)


def _validate_args(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    selected_modes = int(bool(args.peer_ski)) + int(bool(args.pairing_wait)) + int(bool(args.pairing_ski))
    if selected_modes == 0:
        parser.error("one mode is required: --peer-ski, --pairing-wait, or --pairing-ski")
    if selected_modes > 1:
        parser.error("--peer-ski, --pairing-wait, and --pairing-ski are mutually exclusive")


async def _pair_with_ski(args: argparse.Namespace) -> int:
    sdk = _load_sdk()
    desired_ski = sdk["normalize_ski"](args.pairing_ski)
    if desired_ski is None:
        print(f"Error: invalid SKI '{args.pairing_ski}'.", flush=True)
        return 1

    interface_ip = args.interface_ip or sdk["detect_interface_ip"]()
    services = await asyncio.to_thread(sdk["discover_ship_services"], interface_ip, timeout=3.0)
    service = next((entry for entry in services if sdk["normalize_ski"](entry.ski) == desired_ski), None)
    if service is None:
        print(f"Error: unable to discover HEMS device with SKI {desired_ski}.", flush=True)
        return 1
    if service.port is None:
        print(f"Error: discovered service for SKI {desired_ski} does not provide a SHIP port.", flush=True)
        return 1

    identity = sdk["IdentityStore"].load(args.identity)
    trust = sdk["TrustStore"].from_server_ski(desired_ski)
    config = sdk["ShipConnectionConfig"](
        host=service.preferred_host(),
        port=service.port,
        path=service.path,
        server_name=service.server_name(),
        pairing_wait_seconds=PAIRING_TIMEOUT_SECONDS,
    )
    try:
        session = await sdk["ShipSession"].connect(config, identity, trust)
        await session.close()
    except Exception as exc:
        print(f"Error: pairing failed for SKI {desired_ski}: {exc}", flush=True)
        return 1
    print(f"Pairing successful with SKI {desired_ski}.", flush=True)
    return 0


async def _pairing_wait_mode(args: argparse.Namespace) -> int:
    sdk = _load_sdk()
    runtime = build_runtime(args)
    selected_ski: str | None = None
    deadline = asyncio.get_running_loop().time() + float(PAIRING_TIMEOUT_SECONDS)
    await runtime.listener.start()
    await runtime.announcer.start()
    try:
        print(f"Pairing mode: waiting for pairing requests for up to {PAIRING_TIMEOUT_SECONDS} seconds.", flush=True)
        events = runtime.listener.events()
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                print(f"Pairing mode timeout after {PAIRING_TIMEOUT_SECONDS} seconds.", flush=True)
                return 1
            try:
                event = await asyncio.wait_for(anext(events), timeout=remaining)
            except TimeoutError:
                print(f"Pairing mode timeout after {PAIRING_TIMEOUT_SECONDS} seconds.", flush=True)
                return 1

            if event.kind == "connected":
                raw_ski = event.payload.get("peer_ski")
                normalized_ski = sdk["normalize_ski"](raw_ski)
                display_ski = normalized_ski or str(raw_ski or "UNKNOWN")
                print(f"Pairing request received from SKI: {display_ski}", flush=True)
                response = await asyncio.to_thread(input, f"Pair with SKI {display_ski}? [y/N]: ")
                if response.strip().lower() in PAIRING_CONFIRMATION_INPUTS and normalized_ski is not None:
                    selected_ski = normalized_ski
                    print(f"Selected SKI {selected_ski}. Waiting for pairing to complete...", flush=True)

            if event.kind == "ready":
                peer_ski = sdk["normalize_ski"](event.payload.get("peer_ski"))
                if selected_ski is not None and peer_ski == selected_ski:
                    print(f"Pairing successful with SKI {selected_ski}.", flush=True)
                    return 0
    finally:
        await runtime.announcer.stop()
        await runtime.listener.stop()


async def run_service(args: argparse.Namespace) -> int:
    if args.pairing_ski:
        return await _pair_with_ski(args)
    if args.pairing_wait:
        return await _pairing_wait_mode(args)

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
    parser = build_parser()
    args = parser.parse_args()
    _validate_args(args, parser)
    try:
        return asyncio.run(run_service(args))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
