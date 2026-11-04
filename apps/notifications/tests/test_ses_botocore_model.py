"""SES adapter against the REAL botocore ``sesv2`` client + the official API service model, with botocore's ``Stubber``
(no network, no credentials: dummy static keys). The Stubber rejects any request whose parameters do not match the SES v2
API model, so this proves our request shapes and exception handling are valid for the real SDK.

What this is NOT: delivery. Nothing here contacts AWS; DKIM verification, quotas, sandbox rules and bounce behaviour can
only be proven with a real account (see docs/notifications/ACTIVATION_CHECKLIST.md)."""

from unittest import skipUnless

from django.test import SimpleTestCase, override_settings

from apps.notifications.mail import base
from apps.notifications.mail.ses import SesTransport

try:
    import boto3
    from botocore.stub import Stubber
except ImportError:  # pragma: no cover
    boto3 = None


@skipUnless(boto3, "boto3 not installed (only required for RASTISI_EMAIL_PROVIDER=ses)")
class BotocoreModelTests(SimpleTestCase):
    def setUp(self):
        self.client = boto3.client("sesv2", region_name="eu-west-1", aws_access_key_id="AKIAXXXXXXXXXXXXXXXX",
                                   aws_secret_access_key="x" * 40)
        self.stub = Stubber(self.client)
        self.t = SesTransport(region="eu-west-1")
        self.t._client = self.client

    def get_identity_response(self, status="PENDING", verified=False):
        return {
            "IdentityType": "DOMAIN", "VerifiedForSendingStatus": verified,
            "DkimAttributes": {"SigningEnabled": True, "Status": status, "Tokens": ["aaa", "bbb", "ccc"],
                               "SigningAttributesOrigin": "AWS_SES"},
            "VerificationStatus": status,
        }

    def test_create_identity_request_matches_the_ses_v2_model_and_maps_the_response(self):
        self.stub.add_response("create_email_identity", {"IdentityType": "DOMAIN", "VerifiedForSendingStatus": False,
                                                         "DkimAttributes": {"Tokens": ["aaa", "bbb", "ccc"]}},
                               expected_params={"EmailIdentity": "shop.test"})
        self.stub.add_response("get_email_identity", self.get_identity_response(), expected_params={"EmailIdentity": "shop.test"})
        with self.stub:
            state = self.t.create_identity("shop.test")
        self.assertEqual(state.status, base.PROVIDER_PENDING)
        self.assertEqual([r.name for r in state.dns_records],
                         [f"{t}._domainkey.shop.test" for t in ("aaa", "bbb", "ccc")])
        self.assertEqual({r.value for r in state.dns_records}, {f"{t}.dkim.amazonses.com" for t in ("aaa", "bbb", "ccc")})

    def test_already_exists_is_handled_with_the_real_exception_class(self):
        self.stub.add_client_error("create_email_identity", service_error_code="AlreadyExistsException", http_status_code=400)
        self.stub.add_response("get_email_identity", self.get_identity_response("SUCCESS", True))
        with self.stub:
            state = self.t.create_identity("shop.test")
        self.assertEqual((state.status, state.verified_for_sending), (base.PROVIDER_VERIFIED, True))

    def test_not_found_is_handled_with_the_real_exception_class(self):
        self.stub.add_client_error("get_email_identity", service_error_code="NotFoundException", http_status_code=404)
        with self.stub:
            self.assertEqual(self.t.get_identity("nope.test").status, base.PROVIDER_NOT_FOUND)

    def test_identity_quota_error_is_a_platform_side_temporary_failure_never_verified(self):
        for code in ("LimitExceededException", "TooManyRequestsException", "ConcurrentModificationException"):
            self.stub = Stubber(self.client)
            self.stub.add_client_error("create_email_identity", service_error_code=code, http_status_code=400)
            with self.stub:
                state = self.t.create_identity("shop.test")
            self.assertEqual((state.status, state.verified_for_sending), (base.PROVIDER_TEMPORARY_FAILURE, False), code)

    def test_send_email_request_is_valid_against_the_api_model(self):
        self.stub.add_response("send_email", {"MessageId": "0100018c-abcd"}, expected_params={
            "FromEmailAddress": "فروشگاه <info@shop.test>", "Destination": {"ToAddresses": ["c@example.com"]},
            "Content": {"Simple": {"Subject": {"Data": "موضوع", "Charset": "UTF-8"},
                                   "Body": {"Text": {"Data": "متن", "Charset": "UTF-8"},
                                            "Html": {"Data": "<p>متن</p>", "Charset": "UTF-8"}}}},
            "EmailTags": [{"Name": "event_key", "Value": "order.created"}],
        })
        with self.stub:
            out = self.t.send(base.OutboundEmail("info@shop.test", "فروشگاه", "c@example.com", "موضوع", "متن", "<p>متن</p>",
                                                 tags={"event_key": "order.created"}))
        self.assertEqual((out.ok, out.message_id), (True, "0100018c-abcd"))

    @override_settings(RASTISI_SES_CONFIGURATION_SET="rastisi-events")
    def test_send_with_configuration_set_is_valid_against_the_api_model(self):
        self.stub.add_response("send_email", {"MessageId": "m"}, expected_params={
            "FromEmailAddress": "info@shop.test", "Destination": {"ToAddresses": ["c@example.com"]},
            "Content": {"Simple": {"Subject": {"Data": "s", "Charset": "UTF-8"}, "Body": {"Text": {"Data": "t", "Charset": "UTF-8"}}}},
            "ConfigurationSetName": "rastisi-events",
        })
        with self.stub:
            self.assertTrue(self.t.send(base.OutboundEmail("info@shop.test", "", "c@example.com", "s", "t")).ok)

    def test_real_error_codes_are_classified(self):
        msg = base.OutboundEmail("info@shop.test", "n", "c@example.com", "s", "t")
        for code, status, retryable in (("TooManyRequestsException", 429, True), ("MessageRejected", 400, False),
                                        ("MailFromDomainNotVerifiedException", 400, False), ("AccountSuspendedException", 400, False),
                                        ("SendingPausedException", 400, False)):
            self.stub.add_client_error("send_email", service_error_code=code, http_status_code=status)
            with self.stub:
                out = self.t.send(msg)
            self.assertEqual((out.ok, out.error_code, out.retryable), (False, code, retryable), code)
            self.stub.deactivate()
            self.stub = Stubber(self.client)

    def test_the_sdk_would_reject_a_malformed_request(self):
        """Sanity check of the method itself: Stubber really validates (a wrong parameter name fails)."""
        from botocore.exceptions import ParamValidationError

        self.stub.add_response("send_email", {"MessageId": "m"})
        with self.stub, self.assertRaises(ParamValidationError):
            self.client.send_email(From="info@shop.test")
