#!/usr/bin/env python
"""Before/after screenshot pairs for the visual-regression review.

    python tools/contrast_audit/shots.py --before-port 8766 --after-port 8765 --out DIR [--viewport 1366x768] [--only substr]

`before` is a second dev server on a pristine checkout of the base commit (see README); both share the DB.
Writes DIR/<name>__before.png, __after.png and a side-by-side __pair.png (before | after).
"""
from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..")))

import run_audit  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--before-port", default="8766")
    ap.add_argument("--after-port", default="8765")
    ap.add_argument("--out", required=True)
    ap.add_argument("--viewport", default="1366x768")
    ap.add_argument("--suite", default="all")
    ap.add_argument("--only", default="")
    ap.add_argument("--full", action="store_true", help="full-page screenshots")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    run_audit.django_setup()
    session = run_audit.make_sessions(os.environ.get("AUDIT_OWNER", "09120000001"))
    ids = run_audit.discover_ids()
    from PIL import Image
    from playwright.sync_api import sync_playwright

    surfaces = run_audit.build_surfaces(args.suite, ids, args.after_port, run_audit.DEFAULT_STORE_HOST)
    if args.only:
        surfaces = [s for s in surfaces if args.only in s["name"]]
    launch = {"args": ["--no-sandbox", "--host-resolver-rules=MAP *.rastisi.localhost 127.0.0.1, MAP rastisi.localhost 127.0.0.1"],
              "executable_path": run_audit.pick_chromium()}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(**launch)
        for surface in surfaces:
            tag = surface["name"].replace(":", "_").replace("/", "_")
            shots = {}
            for label, port in (("before", args.before_port), ("after", args.after_port)):
                hosts = {run_audit.PLATFORM_HOST, run_audit.DEFAULT_STORE_HOST, run_audit.PADMIN_HOST}
                cookies = [] if surface.get("auth") == "anon" else [
                    {"name": "sessionid", "value": session, "url": f"http://{h}:{port}"} for h in hosts]
                ctx = run_audit.new_context(browser, args.viewport, cookies)
                page = ctx.new_page()
                try:
                    page.goto(surface["url"].replace(f":{args.after_port}", f":{port}"), wait_until="load", timeout=45000)
                    page.wait_for_timeout(700)
                    path = os.path.join(args.out, f"{tag}__{label}.png")
                    page.screenshot(path=path, full_page=args.full)
                    shots[label] = path
                except Exception as exc:  # noqa: BLE001
                    print("skip", tag, label, str(exc).splitlines()[0][:100])
                ctx.close()
            if len(shots) == 2:
                a, b = Image.open(shots["before"]), Image.open(shots["after"])
                pair = Image.new("RGB", (a.width + b.width + 12, max(a.height, b.height)), "#ff00ff")
                pair.paste(a, (0, 0)); pair.paste(b, (a.width + 12, 0))
                pair.save(os.path.join(args.out, f"{tag}__pair.png"))
                print("pair", tag)
        browser.close()


if __name__ == "__main__":
    main()
