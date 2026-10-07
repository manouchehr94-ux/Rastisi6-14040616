"""Adversarial tests for the authoritative client-IP resolver."""

from django.test import RequestFactory, SimpleTestCase, override_settings

from apps.core.services import client_ip
from apps.core.services.client_ip import (
    MAX_FORWARDED_HOPS,
    get_client_ip,
    get_client_ip_bucket,
    is_trusted_proxy_peer,
)


def _req(remote_addr, xff=None, **extra):
    meta = {"REMOTE_ADDR": remote_addr}
    if xff is not None:
        meta["HTTP_X_FORWARDED_FOR"] = xff
    meta.update(extra)
    return RequestFactory().get("/", **meta)


class DirectClientTests(SimpleTestCase):
    @override_settings(RASTISI_TRUSTED_PROXY_CIDRS=())
    def test_xff_is_ignored_when_no_proxy_is_trusted(self):
        request = _req("203.0.113.10", "1.2.3.4")
        self.assertEqual(get_client_ip(request), "203.0.113.10")

    @override_settings(RASTISI_TRUSTED_PROXY_CIDRS=("10.0.0.0/8",))
    def test_xff_is_ignored_when_peer_is_not_in_the_trusted_network(self):
        request = _req("203.0.113.10", "10.0.0.1, 1.2.3.4")
        self.assertEqual(get_client_ip(request), "203.0.113.10")
        self.assertFalse(is_trusted_proxy_peer(request))

    @override_settings(RASTISI_TRUSTED_PROXY_CIDRS=())
    def test_other_forwarding_headers_are_never_trusted(self):
        request = _req(
            "203.0.113.10", "1.2.3.4",
            HTTP_FORWARDED="for=5.5.5.5", HTTP_CF_CONNECTING_IP="6.6.6.6",
            HTTP_TRUE_CLIENT_IP="7.7.7.7", HTTP_X_REAL_IP="8.8.8.8",
        )
        self.assertEqual(get_client_ip(request), "203.0.113.10")

    @override_settings(RASTISI_TRUSTED_PROXY_CIDRS=("10.0.0.0/8",))
    def test_other_forwarding_headers_are_never_trusted_even_from_a_trusted_peer(self):
        request = _req(
            "10.1.2.3", "203.0.113.44",
            HTTP_FORWARDED="for=5.5.5.5", HTTP_CF_CONNECTING_IP="6.6.6.6", HTTP_X_REAL_IP="8.8.8.8",
        )
        self.assertEqual(get_client_ip(request), "203.0.113.44")
        no_xff = _req("10.1.2.3", None, HTTP_CF_CONNECTING_IP="6.6.6.6", HTTP_FORWARDED="for=5.5.5.5")
        self.assertEqual(get_client_ip(no_xff), "10.1.2.3")

    def test_rotating_spoofed_xff_cannot_change_the_bucket(self):
        with override_settings(RASTISI_TRUSTED_PROXY_CIDRS=()):
            buckets = {get_client_ip_bucket(_req("203.0.113.10", f"9.9.9.{n}")) for n in range(50)}
        self.assertEqual(buckets, {"203.0.113.10"})

    @override_settings(RASTISI_TRUSTED_PROXY_CIDRS=("10.0.0.0/8",))
    def test_invalid_or_missing_peer_is_never_trusted_and_yields_unknown(self):
        for peer in ("", "not-an-ip", "10.0.0.1:80", "10.0.0.1%eth0", None):
            with self.subTest(peer=peer):
                request = _req(peer if peer is not None else "", "203.0.113.44")
                if peer is None:
                    request.META.pop("REMOTE_ADDR")
                self.assertEqual(get_client_ip(request), "")
                self.assertEqual(get_client_ip_bucket(request), client_ip.UNKNOWN_BUCKET)


@override_settings(RASTISI_TRUSTED_PROXY_CIDRS=("10.0.0.0/8",))
class TrustedProxyTests(SimpleTestCase):
    def test_single_trusted_proxy_reports_the_client(self):
        self.assertEqual(get_client_ip(_req("10.1.2.3", "203.0.113.44")), "203.0.113.44")

    def test_spoofed_left_entry_does_not_win(self):
        # the proxy appended the real peer to an attacker-supplied value
        self.assertEqual(get_client_ip(_req("10.1.2.3", "1.2.3.4, 203.0.113.44")), "203.0.113.44")

    def test_trusted_peer_without_xff_is_its_own_bucket(self):
        self.assertEqual(get_client_ip(_req("10.1.2.3")), "10.1.2.3")
        self.assertEqual(get_client_ip(_req("10.1.2.3", "")), "10.1.2.3")
        self.assertEqual(get_client_ip(_req("10.1.2.3", "   ")), "10.1.2.3")

    def test_multiple_trusted_hops_are_walked_right_to_left(self):
        request = _req("10.0.0.3", "6.6.6.6, 203.0.113.9, 10.0.0.1, 10.0.0.2")
        self.assertEqual(get_client_ip(request), "203.0.113.9")

    def test_untrusted_middle_hop_stops_the_walk(self):
        # an untrusted address in the chain is the client; everything left of it is hearsay
        request = _req("10.0.0.3", "6.6.6.6, 198.51.100.7, 203.0.113.9, 10.0.0.1")
        self.assertEqual(get_client_ip(request), "203.0.113.9")

    def test_leftmost_and_rightmost_blind_choices_are_not_used(self):
        request = _req("10.0.0.3", "1.1.1.1, 203.0.113.9, 10.0.0.1")
        self.assertNotEqual(get_client_ip(request), "1.1.1.1")  # not first
        self.assertNotEqual(get_client_ip(request), "10.0.0.1")  # not last

    def test_chain_made_only_of_trusted_hops_falls_back_to_the_peer(self):
        self.assertEqual(get_client_ip(_req("10.0.0.3", "10.0.0.1, 10.0.0.2")), "10.0.0.3")

    def test_whitespace_and_multi_value_formatting_is_equivalent(self):
        a = get_client_ip(_req("10.0.0.3", "203.0.113.9,10.0.0.1"))
        b = get_client_ip(_req("10.0.0.3", " 203.0.113.9 ,   10.0.0.1 "))
        self.assertEqual(a, b)
        self.assertEqual(a, "203.0.113.9")

    def test_ipv4_mapped_ipv6_is_normalised(self):
        self.assertEqual(get_client_ip(_req("10.0.0.3", "::ffff:203.0.113.9")), "203.0.113.9")
        self.assertTrue(is_trusted_proxy_peer(_req("::ffff:10.0.0.3")))


class MalformedHeaderTests(SimpleTestCase):
    @override_settings(RASTISI_TRUSTED_PROXY_CIDRS=("10.0.0.0/8",))
    def test_malformed_values_fail_safe_to_the_direct_peer(self):
        cases = [
            "garbage", "203.0.113.9, garbage", "203.0.113.9,", ",", "203.0.113.9, ,10.0.0.1",
            "203.0.113.9:8080", "[2001:db8::1]:443", "203.0.113.999", "203.0.113.9%eth0",
            "unknown", "203.0.113.9; for=1.1.1.1", "\x00", "１２３.４.５.６",
        ]
        for header in cases:
            with self.subTest(header=header):
                self.assertEqual(get_client_ip(_req("10.0.0.3", header)), "10.0.0.3")

    @override_settings(RASTISI_TRUSTED_PROXY_CIDRS=("10.0.0.0/8",))
    def test_garbage_left_of_the_real_client_is_never_parsed(self):
        # only the proxy-appended rightmost hop matters
        self.assertEqual(get_client_ip(_req("10.0.0.3", "garbage, ,;;, 203.0.113.9")), "203.0.113.9")

    @override_settings(RASTISI_TRUSTED_PROXY_CIDRS=("10.0.0.0/8",))
    def test_absurdly_long_header_is_bounded_and_safe(self):
        padding = ", ".join(["6.6.6.6"] * 100_000)
        self.assertEqual(get_client_ip(_req("10.0.0.3", f"{padding}, 203.0.113.9")), "203.0.113.9")
        only_trusted = ", ".join(["10.0.0.1"] * 100_000)
        self.assertEqual(get_client_ip(_req("10.0.0.3", only_trusted)), "10.0.0.3")
        self.assertEqual(get_client_ip(_req("10.0.0.3", "x" * 1_000_000)), "10.0.0.3")

    @override_settings(RASTISI_TRUSTED_PROXY_CIDRS=("10.0.0.0/8",))
    def test_hop_limit_stops_a_real_client_hidden_behind_too_many_trusted_hops(self):
        deep = ", ".join(["203.0.113.9"] + ["10.0.0.1"] * (MAX_FORWARDED_HOPS + 1))
        self.assertEqual(get_client_ip(_req("10.0.0.3", deep)), "10.0.0.3")
        within = ", ".join(["203.0.113.9"] + ["10.0.0.1"] * (MAX_FORWARDED_HOPS - 1))
        self.assertEqual(get_client_ip(_req("10.0.0.3", within)), "203.0.113.9")

    @override_settings(RASTISI_TRUSTED_PROXY_CIDRS=("10.0.0.0/8",))
    def test_non_string_meta_values_do_not_crash(self):
        request = _req("10.0.0.3")
        request.META["HTTP_X_FORWARDED_FOR"] = b"203.0.113.9"
        self.assertEqual(get_client_ip(request), "10.0.0.3")


class IPv6Tests(SimpleTestCase):
    @override_settings(RASTISI_TRUSTED_PROXY_CIDRS=("fd00::/8",))
    def test_trusted_ipv6_proxy_with_ipv6_client(self):
        request = _req("fd00::1", "2001:db8::44")
        self.assertEqual(get_client_ip(request), "2001:db8::44")

    @override_settings(RASTISI_TRUSTED_PROXY_CIDRS=("fd00::/8",))
    def test_ipv6_spoof_and_chain(self):
        request = _req("fd00::2", "2001:db8::bad, 2001:db8::44, fd00::1")
        self.assertEqual(get_client_ip(request), "2001:db8::44")

    @override_settings(RASTISI_TRUSTED_PROXY_CIDRS=("fd00::/8", "10.0.0.0/8"))
    def test_mixed_families(self):
        self.assertEqual(get_client_ip(_req("10.0.0.2", "2001:db8::44, fd00::1")), "2001:db8::44")
        self.assertEqual(get_client_ip(_req("fd00::2", "203.0.113.5, 10.0.0.1")), "203.0.113.5")

    @override_settings(RASTISI_TRUSTED_PROXY_CIDRS=("10.0.0.0/8",))
    def test_ipv6_peer_is_not_trusted_by_an_ipv4_network(self):
        self.assertEqual(get_client_ip(_req("2001:db8::1", "1.2.3.4")), "2001:db8::1")

    @override_settings(RASTISI_TRUSTED_PROXY_CIDRS=())
    def test_ipv6_text_forms_are_normalised(self):
        self.assertEqual(get_client_ip(_req("2001:0DB8:0000:0000:0000:0000:0000:0001")), "2001:db8::1")

    @override_settings(RASTISI_TRUSTED_PROXY_CIDRS=())
    def test_ipv6_bucket_is_the_slash_64(self):
        a = get_client_ip_bucket(_req("2001:db8:1:2:aaaa:bbbb:cccc:dddd"))
        b = get_client_ip_bucket(_req("2001:db8:1:2:1111:2222:3333:4444"))
        c = get_client_ip_bucket(_req("2001:db8:1:3::1"))
        self.assertEqual(a, b)
        self.assertEqual(a, "2001:db8:1:2::/64")
        self.assertNotEqual(a, c)
        self.assertEqual(get_client_ip_bucket(_req("203.0.113.7")), "203.0.113.7")


class UnixSocketPeerTests(SimpleTestCase):
    @override_settings(RASTISI_TRUSTED_PROXY_CIDRS=("unix",))
    def test_empty_peer_is_trusted_only_when_the_unix_token_is_configured(self):
        self.assertEqual(get_client_ip(_req("", "203.0.113.9")), "203.0.113.9")
        self.assertEqual(get_client_ip(_req("", None)), "")
        self.assertEqual(get_client_ip(_req("garbage", "203.0.113.9")), "")
        self.assertEqual(get_client_ip(_req("203.0.113.1", "1.2.3.4")), "203.0.113.1")

    @override_settings(RASTISI_TRUSTED_PROXY_CIDRS=("10.0.0.0/8",))
    def test_empty_peer_is_untrusted_without_the_token(self):
        self.assertEqual(get_client_ip(_req("", "203.0.113.9")), "")
