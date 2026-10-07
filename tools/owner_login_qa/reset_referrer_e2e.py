"""Browser check: the password-reset URL (it carries the token) must never be sent as a Referer.

Real Chromium, real request headers (Playwright ``request.all_headers()``), against a running dev server.
Not part of ``manage.py test`` (needs ``pip install playwright`` and Chromium, like ``tools/engagement_e2e``).

    python tools/owner_login_qa/reset_referrer_e2e.py <full-reset-url> [new-password]

``<full-reset-url>`` is a *valid, unused* link, e.g. ``http://rastisi.localhost:8000/reset-password/<uid>/<token>/``
(generate one with ``default_token_generator`` in ``manage.py shell`` or request it through ``/reset-password/``).
The run CONSUMES the link (it completes the password change) and then reopens it to prove it is single-use.

Checks (exit status is non-zero if any fails):
  * valid and invalid responses: ``Referrer-Policy: origin`` and ``Cache-Control`` containing ``no-store``
  * every same-origin CSS/JS request: ``Referer`` == the bare origin (stylesheet-initiated font/image fetches carry the
    ``/static/...`` stylesheet URL); no request anywhere carries ``/reset-password/...``
  * the form POST: ``Origin`` == the real site origin (not ``null``), ``Referer`` == the bare origin
  * the POST succeeds (CSRF passes), the new password is accepted, the used URL is then invalid (HTTP 400)
"""

import sys
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

CHROMIUM = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
results = []


def check(name, cond, extra=""):
    results.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra else ""))


def main(url, password):
    parts = urlsplit(url)
    origin = f"{parts.scheme}://{parts.netloc}"
    path = parts.path
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=CHROMIUM, args=["--no-sandbox"])
        page = browser.new_page()
        seen = []  # (method, url, headers, resource_type)
        page.on("request", lambda r: seen.append((r.method, r.url, r.all_headers(), r.resource_type)))

        response = page.goto(url)
        page.wait_for_load_state("networkidle")
        check("valid link responds 200", response.status == 200, str(response.status))
        headers = response.headers
        check("valid: Referrer-Policy is exactly 'origin'", headers.get("referrer-policy") == "origin", headers.get("referrer-policy"))
        check("valid: Cache-Control has no-store", "no-store" in headers.get("cache-control", ""), headers.get("cache-control"))

        subresources = [s for s in seen if s[1].startswith(origin) and s[3] in ("stylesheet", "script", "image", "font")]
        check("page loaded same-origin CSS/JS", len(subresources) >= 3, f"{len(subresources)} requests")
        # Requests the HTML document itself makes (<link>/<script>) carry the bare origin. A font/image fetched from
        # *inside* a stylesheet legitimately carries that stylesheet's URL (/static/...) as its referrer.
        direct = [s for s in subresources if s[3] in ("stylesheet", "script")]
        indirect = [s for s in subresources if s[3] not in ("stylesheet", "script")]
        check("page-initiated CSS/JS Referer is the bare origin", direct and all(s[2].get("referer") == origin + "/" for s in direct),
              sorted({s[2].get("referer", "") for s in direct}))
        check("stylesheet-initiated requests carry only a /static/ referrer",
              all(s[2].get("referer", "").startswith(origin + "/static/") for s in indirect),
              sorted({s[2].get("referer", "") for s in indirect}))
        check("no request Referer contains the reset path", all("/reset-password/" not in s[2].get("referer", "") for s in seen))

        page.fill("#id_password", password)
        page.fill("#id_password_confirm", password)
        seen.clear()
        with page.expect_navigation():
            page.click("button[type=submit].r-form-submit")
        page.wait_for_load_state("networkidle")
        post = next((s for s in seen if s[0] == "POST"), None)
        check("form POST was sent", post is not None)
        if post:
            check("POST Origin is the real site origin (not null)", post[2].get("origin") == origin, post[2].get("origin"))
            check("POST Referer is the bare origin", post[2].get("referer") == origin + "/", post[2].get("referer"))
        check("password change completed (landed on login)", urlsplit(page.url).path == "/login/", page.url)
        check("success message shown", page.locator('[role="status"]').count() >= 1)
        check("no later request leaked the reset path as Referer", all("/reset-password/" not in s[2].get("referer", "") for s in seen))

        seen.clear()
        again = page.goto(url)
        page.wait_for_load_state("networkidle")
        check("reopened (used) link is invalid: HTTP 400", again.status == 400, str(again.status))
        check("invalid: Referrer-Policy is exactly 'origin'", again.headers.get("referrer-policy") == "origin", again.headers.get("referrer-policy"))
        check("invalid: Cache-Control has no-store", "no-store" in again.headers.get("cache-control", ""))
        check("invalid page: no request Referer contains the reset path", all("/reset-password/" not in s[2].get("referer", "") for s in seen))
        check("invalid page body does not echo the link", path not in page.content())
        browser.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "qa-new-strong-pass-2026")
    print(f"\n{sum(results)}/{len(results)} checks passed")
    sys.exit(0 if all(results) else 1)
