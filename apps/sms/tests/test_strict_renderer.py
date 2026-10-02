"""S2: رندرِ سخت‌گیرانه‌ی قالبِ پیامکِ قدیمی — امنیت، سازگاری با str.format، ممیزی."""

import json
import os
import tempfile
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase

from apps.sms.events import DEFAULT_TEMPLATES, EVENT_VARIABLES, SmsEvent
from apps.sms.models import SmsTemplate
from apps.sms.services import template_renderer as tr
from apps.sms.services.sms_service import SmsTemplateError, _render, send_test_sms, validate_template_body
from apps.stores.models import Store


class RendererSecurityTests(SimpleTestCase):
    ALLOWED = {"customer_name": "", "shop_name": ""}

    def test_rejects_attribute_index_format_and_expression_constructs(self):
        bad = [
            "{customer_name.__class__.__name__}", "{customer_name.upper}", "{customer_name[0]}",
            "{customer_name!r}", "{customer_name:>999999999}", "{customer_name:,}", "{}", "{0}", "{ customer_name }",
            "{customer_name }", "{__import__('os')}", "{a+b}", "{", "}", "x{y", "x}y", "{customer_name}}",
            "{{customer_name}", "{customer_name.__globals__}", "{-1}", "{customer-name}",
        ]
        for body in bad:
            with self.assertRaises(tr.StrictTemplateError, msg=body) as cm:
                tr.validate(body, self.ALLOWED)
            self.assertEqual(cm.exception.kind, "syntax", body)

    def test_unknown_variable_is_distinguished(self):
        with self.assertRaises(tr.StrictTemplateError) as cm:
            tr.validate("{otp_code}", self.ALLOWED)
        self.assertEqual((cm.exception.kind, cm.exception.names), ("unknown", ("otp_code",)))

    def test_no_object_access_even_if_value_is_object(self):
        class Boom:
            def __str__(self):
                return "safe"

            secret = "LEAK"

        with self.assertRaises(tr.StrictTemplateError):
            tr.render("{customer_name.secret}", {"customer_name": Boom()}, self.ALLOWED)
        self.assertEqual(tr.render("{customer_name}", {"customer_name": Boom()}, self.ALLOWED), "safe")

    def test_values_are_inserted_verbatim_not_reinterpreted(self):
        out = tr.render("{customer_name}", {"customer_name": "{shop_name}{0}{x.y}"}, self.ALLOWED)
        self.assertEqual(out, "{shop_name}{0}{x.y}")

    def test_error_message_truncates_long_input(self):
        with self.assertRaises(tr.StrictTemplateError) as cm:
            tr.validate("{" + "a." * 500 + "}", self.ALLOWED)
        self.assertLess(len(str(cm.exception)), 300)


class RendererCompatibilityTests(SimpleTestCase):
    def test_default_templates_render_identically_to_str_format(self):
        for event, body in DEFAULT_TEMPLATES.items():
            allowed = EVENT_VARIABLES[event]
            values = {k: f"v-{k}" for k in allowed}
            self.assertEqual(tr.render(body, values, allowed), body.format(**values), event)

    def test_literal_brace_escapes_match_str_format(self):
        allowed = {"customer_name": ""}
        for body in ["{{literal}} {customer_name}", "{{{customer_name}}}", "a {{ b }} c", "}}{{"]:
            self.assertEqual(tr.render(body, {"customer_name": "X"}, allowed), body.format(customer_name="X"), body)

    def test_missing_or_none_value_renders_empty(self):
        allowed = {"a": "", "b": ""}
        self.assertEqual(tr.render("[{a}][{b}]", {"a": None}, allowed), "[][]")

    def test_numbers_and_decimals_render_like_format(self):
        from decimal import Decimal

        self.assertEqual(tr.render("{a}", {"a": Decimal("1200000")}, {"a": ""}), "{a}".format(a=Decimal("1200000")))
        self.assertEqual(tr.render("{a}", {"a": 5}, {"a": ""}), "5")

    def test_rename_roundtrip_preserves_escapes(self):
        body = "{{x}} {order_code} {amount}"
        new = tr.rename_placeholders(body, {"order_code": "order_number", "amount": "order_total"})
        self.assertEqual(new, "{{x}} {order_number} {order_total}")
        back = tr.rename_placeholders(new, {"order_number": "order_code", "order_total": "amount"})
        self.assertEqual(back, body)


class LegacyValidatorAndSendTests(TestCase):
    def setUp(self):
        SmsTemplate.ensure_defaults()
        self.template = SmsTemplate.objects.get(event_key=SmsEvent.WELCOME)

    def test_validator_rejects_attribute_access_that_used_to_pass(self):
        with self.assertRaises(SmsTemplateError):
            validate_template_body(SmsEvent.WELCOME, "{customer_name.__class__.__name__}")
        validate_template_body(SmsEvent.WELCOME, "{{ok}} {customer_name}")

    def test_validator_keeps_unknown_variable_message(self):
        with self.assertRaises(SmsTemplateError) as cm:
            validate_template_body(SmsEvent.WELCOME, "{otp_code}")
        self.assertIn("otp_code", str(cm.exception))

    def test_send_falls_back_to_default_for_unsafe_syntax_but_not_for_unknown_variable(self):
        self.template.body = "{customer_name.__class__}"
        self.assertEqual(
            _render(self.template, {"customer_name": "سارا"}, "فروشگاه", fallback_unsafe=True),
            DEFAULT_TEMPLATES[SmsEvent.WELCOME].format(customer_name="سارا", shop_name="فروشگاه"),
        )
        with self.assertRaises(SmsTemplateError):
            _render(self.template, {}, "فروشگاه")  # بدونِ fallback (ارسالِ آزمایشی) → خطا
        self.template.body = "{otp_code}"  # قبلاً هم ارسال نمی‌شد؛ رفتار حفظ می‌شود
        with self.assertRaises(SmsTemplateError):
            _render(self.template, {}, "فروشگاه", fallback_unsafe=True)

    def test_valid_legacy_template_renders_unchanged(self):
        self.template.body = "{customer_name} عزیز {{!}} به {shop_name}"
        self.assertEqual(_render(self.template, {"customer_name": "سارا"}, "ف", fallback_unsafe=True), "سارا عزیز {!} به ف")

    def test_test_send_with_unsafe_template_raises(self):
        SmsTemplate.objects.filter(pk=self.template.pk).update(body="{customer_name[0]}")
        with self.assertRaises(SmsTemplateError):
            send_test_sms(event_key=SmsEvent.WELCOME, phone="09120000000", store=Store.objects.get(slug="akhlaghi"))


class AuditCommandTests(TestCase):
    def setUp(self):
        SmsTemplate.ensure_defaults()

    def run_cmd(self, *args):
        out = StringIO()
        call_command("audit_sms_templates", *args, stdout=out)
        return out.getvalue()

    def test_default_templates_are_clean_and_command_is_read_only(self):
        before = list(SmsTemplate.objects.values_list("pk", "body"))
        out = self.run_cmd()
        self.assertIn("unsafe_syntax=0 unknown_variable=0", out)
        self.assertEqual(before, list(SmsTemplate.objects.values_list("pk", "body")))

    def test_classification_and_apply_with_backup(self):
        SmsTemplate.objects.filter(event_key=SmsEvent.WELCOME).update(body="{customer_name.__class__}")
        SmsTemplate.objects.filter(event_key=SmsEvent.ORDER_SHIPPED).update(body="{nope}")
        out = self.run_cmd()
        self.assertIn("unsafe_syntax=1 unknown_variable=1", out)
        with self.assertRaises(CommandError):
            self.run_cmd("--fail-on-issues")
        with self.assertRaises(CommandError):
            self.run_cmd("--apply")  # --backup الزامی است
        path = os.path.join(tempfile.mkdtemp(), "backup.json")
        self.run_cmd("--apply", "--backup", path)
        saved = json.load(open(path, encoding="utf-8"))
        self.assertEqual([r["body"] for r in saved], ["{customer_name.__class__}"])
        self.assertEqual(SmsTemplate.objects.get(event_key=SmsEvent.WELCOME).body, DEFAULT_TEMPLATES[SmsEvent.WELCOME])
        # الگویِ دارایِ متغیرِ ناشناخته دست‌نخورده می‌ماند (نیازِ به تصمیمِ مدیر)
        self.assertEqual(SmsTemplate.objects.get(event_key=SmsEvent.ORDER_SHIPPED).body, "{nope}")
