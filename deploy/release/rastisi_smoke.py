#!/usr/bin/env python3
"""HTTP smoke tests against the local application port (standard library only). Read-only: GET requests, no state change, no SMS.

HTTP 200 on '/' is not health. This runner checks several real pages, that errors are proper 404s and not 500s or debug pages, that
the response carries the security basics, and then runs the plugin checks that ship WITH the release being verified
(``deploy/smoke.d/*.py`` inside the release) and the tooling's own version-adaptive plugins, so each version can state what "working" means.

Plugins are executed as separate processes with BASE_URL, SMOKE_HOST, EXPECT_RELEASE in the environment; each prints one JSON line
``{"ok": bool, "failures": [...], "passed": [...]}``.

Prints exactly one JSON line; exit 0 only when everything passed.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def fetch(base_url, path, host="", headers=None, timeout=15):
    req = urllib.request.Request(base_url.rstrip("/") + path, method="GET")
    if host:
        req.add_header("Host", host)
    req.add_header("User-Agent", "rastisi-deploy-smoke/1")
    req.add_header("X-Forwarded-Proto", "https")          # honoured only from a trusted proxy address (127.0.0.1 in production)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    opener = urllib.request.build_opener(NoRedirect)
    started = time.time()
    try:
        resp = opener.open(req, timeout=timeout)
        status, body, hdrs = resp.status, resp.read(400000), resp.headers
    except urllib.error.HTTPError as exc:
        status, body, hdrs = exc.code, exc.read(400000), exc.headers
    except Exception as exc:  # noqa: BLE001
        return {"status": 0, "body": "", "headers": {}, "error": exc.__class__.__name__, "seconds": time.time() - started}
    return {"status": status, "body": body.decode("utf-8", "replace"), "headers": hdrs, "error": "", "seconds": time.time() - started}


def core_checks(base_url, host):
    """The BASELINE: only properties every release that ever ran in production already has, so that verifying the rollback target
    can never fail merely because the check is newer than that release. Version-specific expectations live in plugins."""
    passed, failures = [], []

    def expect(name, ok, why=""):
        (passed if ok else failures).append(name if ok else "%s: %s" % (name, why))

    home = fetch(base_url, "/", host)
    expect("home page 200", home["status"] == 200, "status %s %s" % (home["status"], home["error"]))
    expect("home page is HTML", "<html" in home["body"].lower(), "no <html>")
    login = fetch(base_url, "/login/", host)
    expect("login page 200", login["status"] == 200, "status %s" % login["status"])
    expect("login page has a CSRF form", "csrfmiddlewaretoken" in login["body"], "no csrf token field")
    robots = fetch(base_url, "/robots.txt", host)
    expect("robots.txt 200", robots["status"] == 200, "status %s" % robots["status"])
    missing = fetch(base_url, "/__smoke-%s/" % uuid.uuid4().hex[:8], host)
    expect("unknown URL is a clean 404", missing["status"] == 404, "status %s" % missing["status"])
    expect("no debug page", "Django tried these URL patterns" not in missing["body"] and "Traceback (most recent call last)" not in missing["body"],
           "debug output is exposed")
    expect("platform admin is not public", fetch(base_url, "/admin/", host)["status"] in (301, 302, 303, 307, 308, 403, 404), "")
    slow = [r["seconds"] for r in (home, login, robots) if r["seconds"] > 8]
    expect("pages answer within 8 s", not slow, "slow: %s" % ", ".join("%.1fs" % s for s in slow))
    expect("no server errors", all(r["status"] < 500 for r in (home, login, robots, missing)), "a 5xx was returned")
    return passed, failures


def run_plugins(release_dir, base_url, host, expect_release):
    """Plugins come from two places: the tooling's own smoke.d (installed root-owned, version-adaptive, applies to every release,
    including ones built before this tooling existed) and the release's own deploy/smoke.d (checks specific to that version)."""
    passed, failures = [], []
    folders = [Path(__file__).resolve().parent / "smoke.d"]
    if release_dir:
        folders.append(Path(release_dir) / "deploy" / "smoke.d")
    env = dict(os.environ, BASE_URL=base_url, SMOKE_HOST=host, EXPECT_RELEASE=expect_release, RELEASE_DIR=release_dir or "")
    for folder in folders:
        if not folder.is_dir():
            continue
        for plugin in sorted(folder.glob("[0-9][0-9]-*.py")):
            try:
                proc = subprocess.run([sys.executable, str(plugin)], env=env, capture_output=True, text=True, timeout=90)
                data = {}
                for line in reversed(proc.stdout.strip().splitlines()):
                    try:
                        data = json.loads(line)
                        break
                    except ValueError:
                        continue
                if proc.returncode == 0 and data.get("ok"):
                    passed += ["%s: %s" % (plugin.stem, p) for p in data.get("passed", [plugin.stem])]
                else:
                    failures += ["%s: %s" % (plugin.stem, f) for f in (data.get("failures") or ["plugin failed (exit %s)" % proc.returncode])]
            except subprocess.TimeoutExpired:
                failures.append("%s: timed out" % plugin.stem)
    return passed, failures


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--host", default="")
    ap.add_argument("--release-dir", default="")
    ap.add_argument("--expect-release", default="")
    args = ap.parse_args(argv)
    passed, failures = core_checks(args.base_url, args.host)
    p2, f2 = run_plugins(args.release_dir, args.base_url, args.host, args.expect_release)
    passed += p2
    failures += f2
    print(json.dumps({"ok": not failures, "passed": passed, "failures": failures}))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
