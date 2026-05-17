import unittest
import json
from types import SimpleNamespace
from unittest.mock import patch

from eebus_heater_service import (
    _pair_with_ski,
    _pairing_wait_mode,
    _validate_args,
    build_parser,
    build_runtime,
    format_lcp_message,
    is_discovery_commands,
)


class ServiceHelpersTests(unittest.TestCase):
    def test_is_discovery_commands_detects_discovery(self) -> None:
        self.assertTrue(is_discovery_commands(["nodeManagementDetailedDiscoveryData"]))

    def test_is_discovery_commands_ignores_other_commands(self) -> None:
        self.assertFalse(is_discovery_commands(["loadControlLimitListData"]))

    def test_format_lcp_message_serializes_payload(self) -> None:
        rendered = format_lcp_message({"peer_ski": "abc", "watts": 2500})
        self.assertEqual(json.loads(rendered), {"peer_ski": "abc", "watts": 2500})

    def test_validate_args_requires_single_mode(self) -> None:
        parser = build_parser()
        with self.assertRaises(SystemExit):
            args = parser.parse_args(["--identity", "/tmp/identity.json"])
            _validate_args(args, parser)

    def test_build_runtime_passes_coupled_peer_ski(self) -> None:
        advertisement_kwargs: dict[str, object] = {}
        server_config_kwargs: dict[str, object] = {}

        def fake_advertisement(**kwargs: object) -> SimpleNamespace:
            advertisement_kwargs.update(kwargs)
            return SimpleNamespace(**kwargs)

        def fake_server_config(**kwargs: object) -> SimpleNamespace:
            server_config_kwargs.update(kwargs)
            return SimpleNamespace(**kwargs)

        fake_identity = SimpleNamespace(ski="SERVER_SKI", ship_id="SHIP_ID")
        fake_sdk = {
            "IdentityStore": SimpleNamespace(load=lambda _path: fake_identity),
            "detect_interface_ip": lambda: "192.168.1.10",
            "ShipServiceAdvertiser": lambda advertisement: SimpleNamespace(advertisement=advertisement),
            "ShipServiceAdvertisement": fake_advertisement,
            "ShipServer": lambda config: SimpleNamespace(config=config),
            "ShipServerConfig": fake_server_config,
        }
        args = SimpleNamespace(
            identity="/tmp/identity.json",
            peer_ski="11AA22BB33CC44DD55EE66FF77889900AABBCCDD",
            interface_ip=None,
            bind_host="0.0.0.0",
            port=4712,
            path="/ship/",
            ship_id=None,
            device_id="EEBUS-HEATER",
            instance_name=None,
            server_name=None,
        )

        with patch("eebus_heater_service._load_sdk", return_value=fake_sdk):
            runtime = build_runtime(args)

        self.assertEqual(advertisement_kwargs["ski"], "SERVER_SKI")
        self.assertEqual(
            server_config_kwargs["trusted_client_skis"],
            ("11AA22BB33CC44DD55EE66FF77889900AABBCCDD",),
        )
        self.assertTrue(hasattr(runtime, "announcer"))
        self.assertTrue(hasattr(runtime, "listener"))


class PairingFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_pair_with_ski_reports_error_when_service_not_found(self) -> None:
        fake_sdk = {
            "normalize_ski": lambda value: value,
            "detect_interface_ip": lambda: "192.168.1.10",
            "discover_ship_services": lambda *_args, **_kwargs: [],
        }
        args = SimpleNamespace(
            pairing_ski="11AA22BB33CC44DD55EE66FF77889900AABBCCDD",
            interface_ip=None,
        )

        with patch("eebus_heater_service._load_sdk", return_value=fake_sdk), patch("builtins.print") as mocked_print:
            rc = await _pair_with_ski(args)

        self.assertEqual(rc, 1)
        mocked_print.assert_any_call(
            "Error: unable to discover HEMS device with SKI 11AA22BB33CC44DD55EE66FF77889900AABBCCDD.",
            flush=True,
        )

    async def test_pairing_wait_mode_confirms_and_completes(self) -> None:
        test_ski = "AA"

        class FakeListener:
            def __init__(self) -> None:
                self.started = False
                self.stopped = False

            async def start(self) -> None:
                self.started = True

            async def stop(self) -> None:
                self.stopped = True

            async def events(self):
                yield SimpleNamespace(kind="connected", payload={"peer_ski": test_ski})
                yield SimpleNamespace(kind="ready", payload={"peer_ski": test_ski})

        class FakeAnnouncer:
            async def start(self) -> None:
                return None

            async def stop(self) -> None:
                return None

        fake_runtime = SimpleNamespace(listener=FakeListener(), announcer=FakeAnnouncer())
        args = SimpleNamespace()
        fake_sdk = {"normalize_ski": lambda value: value}

        with (
            patch("eebus_heater_service._load_sdk", return_value=fake_sdk),
            patch("eebus_heater_service.build_runtime", return_value=fake_runtime),
            patch("builtins.input", return_value="y"),
            patch("builtins.print") as mocked_print,
        ):
            rc = await _pairing_wait_mode(args)

        self.assertEqual(rc, 0)
        self.assertTrue(fake_runtime.listener.started)
        self.assertTrue(fake_runtime.listener.stopped)
        mocked_print.assert_any_call(f"Pairing successful with SKI {test_ski}.", flush=True)


if __name__ == "__main__":
    unittest.main()
