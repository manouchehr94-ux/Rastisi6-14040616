#!/usr/bin/env python
"""Trace *why* an element has the colours it has: prints, highest priority first,
every matched CSS rule that sets color / background / opacity, with its source
file and line (Chrome DevTools protocol, the same data the Styles pane shows).

    python tools/contrast_audit/explain.py URL "css selector" [--text SUBSTRING] [--hover]

Use it on a failure from run_audit.py to find the owning token / rule instead
of guessing which of the stacked stylesheets wins. Needs the dev server running
(see README.md); sessions are created like run_audit.py does.
"""

from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..")))

import run_audit  # noqa: E402

PROPS = ("color", "background", "background-color", "background-image", "opacity", "-webkit-text-fill-color")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("selector")
    ap.add_argument("--text", default="", help="pick the first match whose text contains this")
    ap.add_argument("--hover", action="store_true", help="force :hover while inspecting")
    ap.add_argument("--anon", action="store_true")
    ap.add_argument("--viewport", default="1366x768")
    args = ap.parse_args()

    run_audit.django_setup()
    session = run_audit.make_sessions(os.environ.get("AUDIT_OWNER", "09120000001"))
    from urllib.parse import urlsplit

    from playwright.sync_api import sync_playwright

    host = urlsplit(args.url)
    cookies = [] if args.anon else [{"name": "sessionid", "value": session, "url": f"{host.scheme}://{host.netloc}"}]
    launch = {"args": ["--no-sandbox", "--host-resolver-rules=MAP *.rastisi.localhost 127.0.0.1, MAP rastisi.localhost 127.0.0.1"]}
    exe = run_audit.pick_chromium()
    if exe:
        launch["executable_path"] = exe
    with sync_playwright() as pw:
        browser = pw.chromium.launch(**launch)
        ctx = run_audit.new_context(browser, args.viewport, cookies)
        page = ctx.new_page()
        page.goto(args.url, wait_until="load", timeout=45000)
        page.wait_for_timeout(500)
        page.evaluate(
            """([sel, text]) => { document.querySelectorAll('[data-explain]').forEach(n => n.removeAttribute('data-explain'));
            const el = Array.from(document.querySelectorAll(sel)).find(n => !text || (n.textContent || '').includes(text));
            if (el) el.setAttribute('data-explain', '1'); return !!el; }""",
            [args.selector, args.text],
        )
        cdp = ctx.new_cdp_session(page)
        sheet_urls = {}
        cdp.on("CSS.styleSheetAdded", lambda e: sheet_urls.__setitem__(e["header"]["styleSheetId"], e["header"].get("sourceURL") or "(inline <style>)"))
        cdp.send("DOM.enable")
        cdp.send("CSS.enable")
        root = cdp.send("DOM.getDocument", {"depth": 0})["root"]["nodeId"]
        node = cdp.send("DOM.querySelector", {"nodeId": root, "selector": "[data-explain]"})["nodeId"]
        if not node:
            print("no element matched")
            return 1
        if args.hover:
            cdp.send("CSS.forcePseudoState", {"nodeId": node, "forcedPseudoClasses": ["hover"]})
        styles = cdp.send("CSS.getMatchedStylesForNode", {"nodeId": node})
        print("computed:", page.evaluate(
            "() => { const e=document.querySelector('[data-explain]'); const c=getComputedStyle(e);"
            " return {color:c.color, bg:c.backgroundColor, bgimg:c.backgroundImage.slice(0,60), opacity:c.opacity}; }"))
        inline = styles.get("inlineStyle")
        if inline:
            for p in inline.get("cssProperties", []):
                if p["name"] in PROPS:
                    print(f"  [inline style] {p['name']}: {p['value']}")
        rules = styles.get("matchedCSSRules", [])
        print(f"matched rules ({len(rules)}), lowest -> highest priority; showing property-setting ones:")
        seen = []
        for entry in rules:
            rule = entry["rule"]
            props = [p for p in rule["style"].get("cssProperties", []) if p["name"] in PROPS and not p.get("disabled")]
            if not props:
                continue
            origin = rule.get("origin")
            sel = rule["selectorList"]["text"][:110]
            rng = rule["style"].get("range", {})
            seen.append((origin, sel, [(p["name"], p["value"] + (" !important" if p.get("important") else "")) for p in props],
                         rng.get("startLine"), rule["style"].get("styleSheetId")))
        for origin, sel, props, line, sid in seen:
            print(f"  ({origin}) {sheet_urls.get(sid, '?').split('/static/')[-1]}:{(line or 0) + 1} :: {sel}")
            for n, v in props:
                print(f"        {n}: {v}")
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
