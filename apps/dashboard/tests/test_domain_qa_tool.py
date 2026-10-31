"""The QA-only fake-infrastructure tool must be inert unless it is explicitly started, and must never reach the network."""

import importlib.util
import tempfile
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase

TOOL = Path(__file__).resolve().parents[3] / "tools" / "domain_qa" / "fake_infra_server.py"


def load():
    spec = importlib.util.spec_from_file_location("fake_infra_server_under_test", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeInfraToolTests(SimpleTestCase):
    def test_importing_the_tool_patches_nothing(self):
        from apps.stores.services import domain_verification_service as dvs

        before = (dvs._txt_records_match, dvs.check_dns_routing, dvs.check_ssl_connection)
        load()
        self.assertEqual((dvs._txt_records_match, dvs.check_dns_routing, dvs.check_ssl_connection), before)

    def test_state_file_drives_the_fakes_and_they_never_touch_the_network(self):
        from apps.stores.services import domain_verification_service as dvs

        module = load()
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(module, "STATE_FILE", Path(tmp) / "state.json"), \
                mock.patch.multiple(dvs, _txt_records_match=dvs._txt_records_match, check_dns_routing=dvs.check_dns_routing,
                                    check_ssl_connection=dvs.check_ssl_connection), \
                mock.patch("dns.resolver.resolve", side_effect=AssertionError("network")), \
                mock.patch("socket.create_connection", side_effect=AssertionError("network")), \
                self.settings(RASTISI_CUSTOM_DOMAIN_A_TARGETS=(module.FAKE_A_TARGET,)):
            module.install_fakes()
            self.assertFalse(dvs._txt_records_match("shop.example.com", "x"))
            self.assertEqual(module.main(["set", "txt", "on"]), 0)
            self.assertTrue(dvs._txt_records_match("shop.example.com", "x"))
            self.assertFalse(dvs.check_dns_routing("shop.example.com").connected)
            module.main(["set", "routing", "on"])
            self.assertTrue(dvs.check_dns_routing("shop.example.com").connected)
            self.assertFalse(dvs.check_ssl_connection("shop.example.com").reachable)
            module.main(["set", "tls", "on"])
            self.assertTrue(dvs.check_ssl_connection("shop.example.com").reachable)
            module.main(["reset"])
            self.assertEqual(module.read_state(), {"txt": False, "routing": False, "tls": False})

    def test_it_refuses_unknown_commands(self):
        self.assertEqual(load().main(["set", "bogus", "on"]), 2)
