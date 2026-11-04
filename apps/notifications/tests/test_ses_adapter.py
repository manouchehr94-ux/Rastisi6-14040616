"""SES adapter against a stub that mimics the boto3 ``sesv2`` client surface (request shape + response shape from the
official API reference). Proves our mapping/classification logic; it does NOT prove real AWS behaviour."""

from django.test import SimpleTestCase, override_settings

from apps.notifications.mail import base
from apps.notifications.mail.ses import SesTransport


class _Exceptions:
    class NotFoundException(Exception):
        pass

    class AlreadyExistsException(Exception):
        pass

    class ClientError(Exception):
        def __init__(self, code="X"):
            super().__init__(code)
            self.response = {"Error": {"Code": code}}


class StubSes:
    exceptions = _Exceptions

    def __init__(self):
        self.identities = {}
        self.sent = []
        self.send_error = None
        self.get_error = None

    def create_email_identity(self, EmailIdentity):
        if EmailIdentity in self.identities:
            raise _Exceptions.AlreadyExistsException()
        self.identities[EmailIdentity] = {"Status": "PENDING", "Verified": False, "Tokens": ["t1", "t2", "t3"]}
        return {"IdentityType": "DOMAIN", "DkimAttributes": {"Tokens": ["t1", "t2", "t3"]}}

    def get_email_identity(self, EmailIdentity):
        if self.get_error:
            raise self.get_error
        if EmailIdentity not in self.identities:
            raise _Exceptions.NotFoundException()
        i = self.identities[EmailIdentity]
        return {"DkimAttributes": {"Status": i["Status"], "Tokens": i["Tokens"]}, "VerifiedForSendingStatus": i["Verified"],
                "VerificationInfo": {"ErrorType": "HOST_NOT_FOUND" if i["Status"] == "FAILED" else ""}}

    def send_email(self, **kwargs):
        if self.send_error:
            raise self.send_error
        self.sent.append(kwargs)
        return {"MessageId": "0100018c-abcd"}


def transport(stub):
    t = SesTransport(region="eu-west-1", access_key="", secret_key="")
    t._client = stub
    return t


class SesAdapterTests(SimpleTestCase):
    def setUp(self):
        self.stub = StubSes()
        self.t = transport(self.stub)

    def test_create_identity_returns_dkim_cname_records_in_the_documented_shape(self):
        state = self.t.create_identity("shop.test")
        self.assertEqual(state.status, base.PROVIDER_PENDING)
        self.assertFalse(state.verified_for_sending)
        self.assertEqual([r.as_dict() for r in state.dns_records][0],
                         {"type": "CNAME", "name": "t1._domainkey.shop.test", "value": "t1.dkim.amazonses.com", "purpose": "dkim"})
        self.assertEqual(len(state.dns_records), 3)

    def test_create_is_idempotent(self):
        self.t.create_identity("shop.test")
        self.assertEqual(self.t.create_identity("shop.test").status, base.PROVIDER_PENDING)

    def test_verified_requires_both_dkim_success_and_verified_for_sending(self):
        self.t.create_identity("shop.test")
        self.stub.identities["shop.test"].update(Status="SUCCESS", Verified=False)
        s = self.t.get_identity("shop.test")
        self.assertEqual(s.status, base.PROVIDER_VERIFIED)
        self.assertFalse(s.verified_for_sending)  # provisioning_service additionally requires this flag
        self.stub.identities["shop.test"]["Verified"] = True
        self.assertTrue(self.t.get_identity("shop.test").verified_for_sending)

    def test_status_mapping(self):
        self.t.create_identity("shop.test")
        for raw, expected in (("FAILED", base.PROVIDER_FAILED), ("TEMPORARY_FAILURE", base.PROVIDER_TEMPORARY_FAILURE),
                              ("NOT_STARTED", base.PROVIDER_PENDING), ("PENDING", base.PROVIDER_PENDING)):
            self.stub.identities["shop.test"]["Status"] = raw
            self.assertEqual(self.t.get_identity("shop.test").status, expected, raw)

    def test_unknown_identity_is_not_found_not_verified(self):
        self.assertEqual(self.t.get_identity("nope.test").status, base.PROVIDER_NOT_FOUND)

    def test_any_other_lookup_error_is_temporary_never_verified(self):
        self.stub.get_error = RuntimeError("socket reset")
        s = self.t.get_identity("shop.test")
        self.assertEqual(s.status, base.PROVIDER_TEMPORARY_FAILURE)
        self.assertFalse(s.verified_for_sending)

    def test_send_email_request_shape_utf8_text_html_and_tags(self):
        out = self.t.send(base.OutboundEmail(
            from_address="info@shop.test", from_name="فروشگاه", to_address="c@example.com", subject="موضوع",
            text_body="متن", html_body="<p>متن</p>", tags={"event_key": "order.created", "store_id": "7"}))
        self.assertEqual((out.ok, out.message_id), (True, "0100018c-abcd"))
        req = self.stub.sent[0]
        self.assertEqual(req["FromEmailAddress"], "فروشگاه <info@shop.test>")
        self.assertEqual(req["Destination"], {"ToAddresses": ["c@example.com"]})
        simple = req["Content"]["Simple"]
        self.assertEqual(simple["Subject"], {"Data": "موضوع", "Charset": "UTF-8"})
        self.assertEqual(simple["Body"]["Text"]["Charset"], "UTF-8")
        self.assertEqual(simple["Body"]["Html"]["Data"], "<p>متن</p>")
        self.assertEqual({t["Name"] for t in req["EmailTags"]}, {"event_key", "store_id"})
        self.assertNotIn("ConfigurationSetName", req)

    def test_error_classification_throttling_is_retryable_rejection_is_permanent(self):
        msg = base.OutboundEmail("info@shop.test", "n", "c@example.com", "s", "t")
        for code, retryable in (("TooManyRequestsException", True), ("Throttling", True), ("MessageRejected", False),
                                ("MailFromDomainNotVerifiedException", False), ("AccountSuspendedException", False)):
            self.stub.send_error = _Exceptions.ClientError(code)
            out = self.t.send(msg)
            self.assertEqual((out.ok, out.retryable, out.error_code), (False, retryable, code), code)

    def test_generic_network_error_is_retryable_and_does_not_leak_secrets(self):
        self.stub.send_error = OSError("connect failed AKIAIOSFODNN7EXAMPLE " + "x" * 500)
        out = self.t.send(base.OutboundEmail("info@shop.test", "n", "c@example.com", "s", "t"))
        self.assertTrue(out.retryable and not out.ok)
        self.assertLessEqual(len(out.error), 260)

    def test_missing_region_is_a_clear_not_configured_error_and_no_client_is_built_at_import(self):
        with self.assertRaises(base.TransportNotConfigured):
            SesTransport(region="", access_key="", secret_key="")._get_client()

    @override_settings(RASTISI_EMAIL_PROVIDER="nonsense")
    def test_unknown_provider_setting_fails_loudly(self):
        from apps.notifications.mail.registry import get_transport

        with self.assertRaises(ValueError):
            get_transport()
