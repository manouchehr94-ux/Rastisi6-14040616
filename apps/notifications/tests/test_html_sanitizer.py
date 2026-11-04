"""Allowlist HTML sanitizer: strips scripts/styles/event handlers/dangerous schemes, keeps safe formatting."""

from django.test import TestCase

from apps.notifications.services.html_sanitizer import sanitize_html


class SanitizerTests(TestCase):
    def test_script_tag_and_its_content_are_removed(self):
        out = sanitize_html("<p>hi</p><script>alert(document.cookie)</script>")
        self.assertNotIn("<script", out)
        self.assertNotIn("alert", out)

    def test_style_tag_content_is_removed(self):
        self.assertNotIn("background", sanitize_html("<style>body{background:url(x)}</style><p>ok</p>"))

    def test_iframe_and_object_are_removed(self):
        out = sanitize_html('<iframe src="https://evil.test"></iframe><object data="x"></object><p>ok</p>')
        self.assertNotIn("iframe", out)
        self.assertNotIn("object", out)

    def test_event_handler_attributes_are_stripped(self):
        out = sanitize_html('<p onclick="steal()" onmouseover="x()">hi</p>')
        self.assertNotIn("onclick", out)
        self.assertNotIn("onmouseover", out)

    def test_style_and_class_attributes_are_stripped(self):
        out = sanitize_html('<p style="display:none" class="x">hi</p>')
        self.assertNotIn("style=", out)
        self.assertNotIn("class=", out)

    def test_javascript_href_is_removed_but_tag_kept(self):
        out = sanitize_html('<a href="javascript:alert(1)">click</a>')
        self.assertNotIn("javascript:", out)
        self.assertIn("<a", out)

    def test_javascript_href_with_control_chars_is_removed(self):
        out = sanitize_html('<a href="\tjav\tascript:alert(1)">x</a>')
        self.assertNotIn("javascript:", out)

    def test_data_uri_href_is_removed(self):
        out = sanitize_html('<a href="data:text/html,<script>1</script>">x</a>')
        self.assertNotIn("data:", out)

    def test_http_https_mailto_tel_hrefs_are_kept(self):
        for href in ("https://example.com", "http://example.com", "mailto:a@b.com", "tel:+989120000000"):
            out = sanitize_html(f'<a href="{href}">x</a>')
            self.assertIn(href, out)

    def test_links_get_rel_noopener(self):
        self.assertIn('rel="noopener noreferrer"', sanitize_html('<a href="https://x.test">x</a>'))

    def test_placeholder_href_allowed_only_at_save_time(self):
        self.assertIn("href=\"{order_url}\"", sanitize_html('<a href="{order_url}">x</a>', allow_placeholders=True))
        self.assertNotIn("href=", sanitize_html('<a href="{order_url}">x</a>', allow_placeholders=False))

    def test_unclosed_tags_are_closed_and_well_formed(self):
        out = sanitize_html("<p>hi<strong>bold")
        self.assertEqual(out.count("<p>"), out.count("</p>"))
        self.assertEqual(out.count("<strong>"), out.count("</strong>"))

    def test_html_comments_are_removed(self):
        self.assertNotIn("secret", sanitize_html("<!-- secret --><p>ok</p>"))

    def test_svg_and_math_are_removed(self):
        self.assertNotIn("svg", sanitize_html('<svg onload="x()"><script>1</script></svg><p>ok</p>').lower())

    def test_text_is_escaped_not_interpreted(self):
        out = sanitize_html("<p>a &lt;b&gt; c</p>")
        self.assertIn("&lt;b&gt;", out)

    def test_disallowed_tag_is_dropped_but_text_kept(self):
        out = sanitize_html("<marquee>hi</marquee>")
        self.assertNotIn("marquee", out)
        self.assertIn("hi", out)

    def test_empty_and_none_input(self):
        self.assertEqual(sanitize_html(""), "")
        self.assertEqual(sanitize_html(None), "")


class RenderHtmlSecurityTests(TestCase):
    """A variable VALUE containing markup/script must never become live HTML — ``render_html`` re-sanitizes
    strictly (``allow_placeholders=False``) after substitution."""

    def test_variable_value_with_script_tag_is_neutralized(self):
        from apps.notifications.services.template_service import render_html

        out, missing = render_html("ev", "<p>{customer_name}</p>", {"customer_name": "<script>alert(1)</script>"})
        self.assertNotIn("<script", out)
        self.assertEqual(missing, [])

    def test_variable_value_with_javascript_href_is_neutralized(self):
        from apps.notifications.services.template_service import render_html

        out, _ = render_html("ev", '<a href="{order_url}">link</a>', {"order_url": "javascript:alert(1)"})
        self.assertNotIn("javascript:", out)
