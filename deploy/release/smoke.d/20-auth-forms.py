#!/usr/bin/env python3
"""Release smoke plugin: the public authentication and contact forms are well formed (read-only, GET only).

Adapts to the version being verified:
  * a page that carries the math CAPTCHA must have a numeric question, an answer input and an opaque token, must NOT contain the sum,
    and must not be cacheable (a cached page would hand several visitors the same question);
  * the CAPTCHA is REQUIRED when the release being verified contains it (apps/portal/services/captcha_service.py exists in RELEASE_DIR,
    or SMOKE_REQUIRE_CAPTCHA is set): serving the Turnstile widget then means the wrong code or settings are live;
  * otherwise a page that still carries the Cloudflare Turnstile widget is accepted (older releases, including the one a rollback returns to).
Prints one JSON line.
"""

import json
import os
import re
import sys
import urllib.request

BASE = os.environ.get("BASE_URL", "").rstrip("/")
HOST = os.environ.get("SMOKE_HOST", "")
FORMS = (("/login/", ("login_password", "login_otp")), ("/register/", ("register",)), ("/reset-password/", ("password_reset",)), ("/contact/", ("contact",)))
PERSIAN = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
QUESTION = re.compile(r"<bdi[^>]*>\s*([0-9۰-۹٠-٩]+) \+ ([0-9۰-۹٠-٩]+) = ؟\s*</bdi>")


def get(path):
    req = urllib.request.Request(BASE + path)
    if HOST:
        req.add_header("Host", HOST)
    req.add_header("X-Forwarded-Proto", "https")
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        return resp.read().decode("utf-8", "replace"), resp.headers
    except Exception:
        return "", {}


def main():
    passed, failures = [], []
    release_dir = os.environ.get("RELEASE_DIR", "")
    require = bool(os.environ.get("SMOKE_REQUIRE_CAPTCHA")) or bool(release_dir and os.path.exists(os.path.join(release_dir, "apps", "portal", "services", "captcha_service.py")))
    for path, actions in FORMS:
        html, headers = get(path)
        if not html:
            failures.append("%s did not load" % path)
            continue
        if "csrfmiddlewaretoken" not in html:
            failures.append("%s has no CSRF token" % path)
            continue
        if "captcha-answer-" in html:
            cache = str(headers.get("Cache-Control", ""))
            if "no-store" not in cache and "private" not in cache:
                failures.append("%s carries a per-visitor CAPTCHA but is cacheable (Cache-Control=%r)" % (path, cache))
            for action in actions:
                marker = 'id="captcha-label-%s"' % action
                if marker not in html:
                    failures.append("%s: no CAPTCHA question for %s" % (path, action))
                    continue
                block = html[html.index(marker): html.index(marker) + 2500]
                q = QUESTION.search(block)
                token = re.search(r'name="captcha_token" value="([^"]{16,})"', block)
                if not (q and token and 'name="captcha_answer"' in block):
                    failures.append("%s: malformed CAPTCHA for %s" % (path, action))
                    continue
                total = int(q.group(1).translate(PERSIAN)) + int(q.group(2).translate(PERSIAN))
                if re.search(r'(value|data-[a-z-]+)="%d"|data-answer|data-sum' % total, block):
                    failures.append("%s: the CAPTCHA answer is exposed" % path)
                    continue
                passed.append("%s CAPTCHA well formed (%s)" % (path, action))
        elif require:
            failures.append("%s has no CAPTCHA but this release requires one%s" % (path, " (still serving the Turnstile widget)" if "cf-turnstile" in html else ""))
        elif "cf-turnstile" in html:
            passed.append("%s carries the legacy Turnstile widget" % path)
        else:
            passed.append("%s loads" % path)
    print(json.dumps({"ok": not failures, "passed": passed, "failures": failures}))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
