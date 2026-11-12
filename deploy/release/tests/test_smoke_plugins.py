"""The smoke runner and the version-adaptive plugin, against a local fixture web server (no Django, no database).

The fixtures are copies of what the real templates render: the math-CAPTCHA markup (both public designs) and the Turnstile widget of the
production commit. test_real_application_markup() additionally renders the REAL templates when Django is importable (CI)."""

import json
import os
import subprocess
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parent
PLUGIN = TOOLS / "smoke.d" / "20-auth-forms.py"
SMOKE = TOOLS / "rastisi_smoke.py"

CSRF = '<input type="hidden" name="csrfmiddlewaretoken" value="abc">'


def captcha_block(action, design="v2", total=(47, 30)):
    left, right = (str(n).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")) for n in total)
    cls = ("captcha", "captcha-row", "captcha-question", "captcha-input") if design == "v2" else ("p-captcha", "p-captcha-row", "p-captcha-question", "p-captcha-input")
    return ('<div class="%s" role="group" aria-labelledby="captcha-label-%s"><label for="captcha-answer-%s" id="captcha-label-%s">تأیید امنیتی</label>'
            '<div class="%s"><span class="%s" dir="ltr"><bdi dir="ltr">%s + %s = ؟</bdi></span>'
            '<input type="text" name="captcha_answer" id="captcha-answer-%s" class="%s"></div>'
            '<input type="hidden" name="captcha_token" value="tpJ7Sga7OR7AE2oiz0OxGmbEyR12yV42"></div>'
            % (cls[0], action, action, action, cls[1], cls[2], left, right, action, cls[3]))


PAGES = {
    "captcha": {
        "/": "<html>home</html>", "/robots.txt": "User-agent: *",
        "/login/": "<html><form>%s%s%s</form></html>" % (CSRF, captcha_block("login_password"), captcha_block("login_otp")),
        "/register/": "<html><form>%s%s</form></html>" % (CSRF, captcha_block("register")),
        "/reset-password/": "<html><form>%s%s</form></html>" % (CSRF, captcha_block("password_reset")),
        "/contact/": "<html><form>%s%s</form></html>" % (CSRF, captcha_block("contact")),
    },
    "turnstile": {
        "/": "<html>home</html>", "/robots.txt": "User-agent: *",
        **{p: "<html><form>%s<div class='cf-turnstile' data-sitekey='x'></div></form></html>" % CSRF for p in ("/login/", "/register/", "/reset-password/", "/contact/")},
    },
}


class Handler(BaseHTTPRequestHandler):
    pages = {}
    headers_for = {}

    def log_message(self, *a):
        pass

    def do_GET(self):
        body = self.pages.get(self.path)
        if body is None:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"<html>not found</html>")
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        for k, v in self.headers_for.get(self.path, {"Cache-Control": "max-age=0, no-cache, no-store, must-revalidate, private"}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))


class Server:
    def __init__(self, pages, headers_for=None):
        handler = type("H", (Handler,), {"pages": pages, "headers_for": headers_for or {}})
        self.httpd = HTTPServer(("127.0.0.1", 0), handler)
        self.url = "http://127.0.0.1:%d" % self.httpd.server_port
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def run_plugin(url, **env):
    proc = subprocess.run([sys.executable, str(PLUGIN)], capture_output=True, text=True, env=dict(os.environ, BASE_URL=url, **env), timeout=60)
    return proc.returncode, json.loads(proc.stdout.strip().splitlines()[-1])


class PluginTests(unittest.TestCase):
    def serve(self, pages, headers_for=None):
        srv = Server(pages, headers_for)
        self.addCleanup(srv.close)
        return srv.url

    def test_the_captcha_markup_of_both_designs_passes(self):
        for design in ("v2", "legacy"):
            pages = json.loads(json.dumps(PAGES["captcha"]))
            pages["/login/"] = "<html><form>%s%s%s</form></html>" % (CSRF, captcha_block("login_password", design), captcha_block("login_otp", design))
            code, data = run_plugin(self.serve(pages), SMOKE_REQUIRE_CAPTCHA="1")
            self.assertEqual(code, 0, (design, data))
            self.assertEqual(sum("CAPTCHA well formed" in p for p in data["passed"]), 5)

    def test_the_production_commit_with_turnstile_passes_so_rollback_verification_works(self):
        code, data = run_plugin(self.serve(PAGES["turnstile"]))
        self.assertEqual(code, 0, data)
        self.assertTrue(all("Turnstile" in p for p in data["passed"]))

    def test_a_release_that_must_have_the_captcha_fails_on_the_turnstile_build(self):
        code, data = run_plugin(self.serve(PAGES["turnstile"]), SMOKE_REQUIRE_CAPTCHA="1")
        self.assertEqual(code, 1)
        self.assertIn("requires one", " ".join(data["failures"]))

    def test_the_requirement_is_detected_from_the_release_itself(self):
        import tempfile, shutil
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(d), True)
        (d / "apps" / "portal" / "services").mkdir(parents=True)
        url = self.serve(PAGES["turnstile"])
        code, _ = run_plugin(url, RELEASE_DIR=str(d))
        self.assertEqual(code, 0, "no captcha_service.py in the release: the Turnstile build is fine")
        (d / "apps" / "portal" / "services" / "captcha_service.py").write_text("")
        code, data = run_plugin(url, RELEASE_DIR=str(d))
        self.assertEqual(code, 1, "the release ships the CAPTCHA but serves Turnstile: that must fail verification")
        self.assertIn("still serving the Turnstile", " ".join(data["failures"]))

    def test_an_exposed_answer_is_a_failure(self):
        pages = dict(PAGES["captcha"])
        pages["/contact/"] = pages["/contact/"].replace('<input type="hidden" name="captcha_token"', '<input type="hidden" value="77" name="captcha_token"')
        pages["/contact/"] = pages["/contact/"].replace("</form>", '<span data-answer="77"></span></form>')
        code, data = run_plugin(self.serve(pages))
        self.assertEqual(code, 1)
        self.assertIn("answer is exposed", " ".join(data["failures"]))

    def test_a_cacheable_captcha_page_is_a_failure(self):
        code, data = run_plugin(self.serve(PAGES["captcha"], {"/login/": {"Cache-Control": "public, max-age=600"}}))
        self.assertEqual(code, 1)
        self.assertIn("cacheable", " ".join(data["failures"]))

    def test_a_missing_csrf_token_or_a_dead_page_is_a_failure(self):
        pages = dict(PAGES["captcha"])
        pages["/register/"] = pages["/register/"].replace(CSRF, "")
        del pages["/contact/"]
        code, data = run_plugin(self.serve(pages))
        self.assertEqual(code, 1)
        text = " ".join(data["failures"])
        self.assertIn("/register/ has no CSRF", text)
        self.assertIn("/contact/ did not load", text)

    def test_malformed_question_is_a_failure(self):
        pages = dict(PAGES["captcha"])
        pages["/reset-password/"] = pages["/reset-password/"].replace("= ؟", "= ")
        code, data = run_plugin(self.serve(pages))
        self.assertEqual(code, 1)
        self.assertIn("malformed", " ".join(data["failures"]))


class SmokeRunnerTests(unittest.TestCase):
    def run_smoke(self, pages, extra=()):
        srv = Server(pages)
        self.addCleanup(srv.close)
        proc = subprocess.run([sys.executable, str(SMOKE), "--base-url", srv.url] + list(extra), capture_output=True, text=True, timeout=120)
        return proc.returncode, json.loads(proc.stdout.strip().splitlines()[-1])

    def test_baseline_passes_on_a_healthy_site_whether_or_not_login_is_cacheable(self):
        """The production commit sends no Cache-Control on /login/; the baseline must not demand it (rollback targets must verify)."""
        code, data = self.run_smoke(PAGES["turnstile"])
        self.assertEqual(code, 0, data)
        self.assertNotIn("not cacheable", " ".join(data["passed"] + data["failures"]))

    def test_baseline_fails_on_a_500_or_a_debug_page(self):
        class Five(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                self.send_response(500)
                self.end_headers()
                self.wfile.write(b"Traceback (most recent call last): Django tried these URL patterns")
        httpd = HTTPServer(("127.0.0.1", 0), Five)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        proc = subprocess.run([sys.executable, str(SMOKE), "--base-url", "http://127.0.0.1:%d" % httpd.server_port], capture_output=True, text=True, timeout=120)
        data = json.loads(proc.stdout.strip().splitlines()[-1])
        self.assertEqual(proc.returncode, 1)
        self.assertGreaterEqual(len(data["failures"]), 3)

    def test_baseline_fails_when_nothing_listens(self):
        proc = subprocess.run([sys.executable, str(SMOKE), "--base-url", "http://127.0.0.1:9"], capture_output=True, text=True, timeout=120)
        self.assertEqual(proc.returncode, 1)

    def test_release_plugins_run_too(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(str(d), True))
        (d / "deploy" / "smoke.d").mkdir(parents=True)
        (d / "deploy" / "smoke.d" / "10-custom.py").write_text('import json;print(json.dumps({"ok": False, "failures": ["custom check failed"]}))\n')
        code, data = self.run_smoke(PAGES["turnstile"], ["--release-dir", str(d)])
        self.assertEqual(code, 1)
        self.assertIn("10-custom: custom check failed", data["failures"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
