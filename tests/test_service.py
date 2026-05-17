import unittest
import json

from eebus_heater_service import format_lcp_message, is_discovery_commands


class ServiceHelpersTests(unittest.TestCase):
    def test_is_discovery_commands_detects_discovery(self) -> None:
        self.assertTrue(is_discovery_commands(["nodeManagementDetailedDiscoveryData"]))

    def test_is_discovery_commands_ignores_other_commands(self) -> None:
        self.assertFalse(is_discovery_commands(["loadControlLimitListData"]))

    def test_format_lcp_message_serializes_payload(self) -> None:
        rendered = format_lcp_message({"peer_ski": "abc", "watts": 2500})
        self.assertEqual(json.loads(rendered), {"peer_ski": "abc", "watts": 2500})


if __name__ == "__main__":
    unittest.main()
