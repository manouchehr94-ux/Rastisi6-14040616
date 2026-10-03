"""Real HTTP round trips (Django live server on a local port) between the protocol simulator (tools/smsrasti_simulator.py) and the
gateway endpoints — proves the wire protocol (query/form encoding, auth, JSON) beyond Django's test client. No SMS is sent."""

import importlib.util
import pathlib

from django.test import LiveServerTestCase

from apps.core.models import ShopSettings
from apps.sms.models import SmsLog, SmsOutboxItem, SmsTemplate
from apps.sms.services.delivery_status_service import get_sms_delivery_status
from apps.sms.services.sms_service import send_raw_sms
from apps.stores.models import Store

SPEC = importlib.util.spec_from_file_location("smsrasti_simulator", pathlib.Path(__file__).resolve().parents[3] / "tools" / "smsrasti_simulator.py")
sim = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sim)
TOKEN = "live-device-token-1"


class LiveProtocolTests(LiveServerTestCase):
    serialized_rollback = True
    def setUp(self):
        SmsTemplate.ensure_defaults()
        # LiveServerTestCase flushes the DB between tests (migration-seeded store is not guaranteed) — create our own
        self.store = Store.objects.create(name="live-sms", slug="live-sms", status=Store.Status.ACTIVE)
        shop = ShopSettings.provision_for(self.store)
        shop.sms_enabled, shop.sms_backend, shop.smsrasti_device_token = True, ShopSettings.SmsBackend.SMSRASTI, TOKEN
        shop.save()

    def test_pairing_poll_ack_and_status_over_real_http(self):
        self.assertEqual(sim.run_once(self.live_server_url, "wrong")["result"], "unauthorized")
        self.assertEqual(sim.run_once(self.live_server_url, TOKEN)["result"], "empty")
        send_raw_sms(phone="09120000001", message="سلام", store=self.store)
        send_raw_sms(phone="09120000002", message="دوم", store=self.store)
        first = sim.run_once(self.live_server_url, TOKEN, "sent")
        second = sim.run_once(self.live_server_url, TOKEN, "failed")
        self.assertEqual((first["phone"], first["result"], first["ack_http"]), ("09120000001", "sent", 200))
        self.assertEqual((second["phone"], second["result"]), ("09120000002", "failed"))
        self.assertEqual(sim.run_once(self.live_server_url, TOKEN)["result"], "empty")
        statuses = dict(SmsOutboxItem.objects.values_list("phone", "status"))
        self.assertEqual(statuses, {"09120000001": "sent", "09120000002": "failed"})
        self.assertEqual(dict(SmsLog.objects.values_list("recipient", "status")), {"09120000001": "sent", "09120000002": "failed"})
        status = get_sms_delivery_status(self.store)
        self.assertTrue(status["device"]["online"])
        self.assertEqual(status["queue"]["failed"], 1)

    def test_claim_without_ack_leaves_the_message_sending_not_sent(self):
        send_raw_sms(phone="09120000003", message="x", store=self.store)
        self.assertEqual(sim.run_once(self.live_server_url, TOKEN, "none")["result"], "claimed")
        self.assertEqual(SmsOutboxItem.objects.get().status, "sending")
