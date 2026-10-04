"""Cross-viewport / accessibility E2E for the campaign rule builder (the existing UI — no second builder).

Run after `bash tools/engagement_e2e/reset.sh` (see README). Needs `pip install playwright` and, for the axe scan,
`npm i axe-core` in tools/engagement_e2e (node_modules is git-ignored) or AXE_PATH=/path/to/axe.min.js.

Engines: Chromium is always tested. Firefox/WebKit are attempted when their runtimes are installed
(PLAYWRIGHT_BROWSERS_PATH); otherwise they are reported as NOT RUN — never as passed.
Writes /tmp/e2e/a11y_report.json and exits non-zero on any failed check."""

import json
import os
import sys

from playwright.sync_api import sync_playwright

state = json.load(open("/tmp/e2e_state.json"))
BASE = "http://e2e.rastisi.localhost:8765"
HERE = os.path.dirname(os.path.abspath(__file__))
AXE = os.environ.get("AXE_PATH") or os.path.join(HERE, "node_modules", "axe-core", "axe.min.js")
CHROMIUM = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
VIEWPORTS = [("desktop", 1280, 900, False), ("tablet", 768, 1024, True), ("mobile", 390, 844, True)]
results, report = [], {"engines": {}, "axe": {}}


def check(name, cond, extra=""):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name, extra)


def launch(p, engine):
    try:
        if engine == "chromium":
            return p.chromium.launch(executable_path=CHROMIUM if os.path.exists(CHROMIUM) else None, args=["--no-sandbox"])
        return getattr(p, engine).launch()
    except Exception as exc:  # noqa: BLE001
        return str(exc).splitlines()[0][:160]


def accessible_name(el):
    return el.evaluate("""n => (n.getAttribute('aria-label') || (n.labels && n.labels[0] && n.labels[0].innerText) ||
        n.getAttribute('title') || n.innerText || '').trim()""")


def run_viewport(browser, engine, vp):
    label, w, h, touch = vp
    tag = f"[{engine}/{label}]"
    ctx = browser.new_context(viewport={"width": w, "height": h}, locale="fa-IR", has_touch=touch, is_mobile=(label == "mobile") and engine != "firefox")
    ctx.add_cookies([{"name": "sessionid", "value": state["sessionid"], "url": BASE}])
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" and "favicon" not in m.text else None)
    page.on("dialog", lambda d: d.accept())
    page.goto(f"{BASE}/admin-portal/campaigns/add/?kind=campaigns")
    page.wait_for_selector("#rule-builder .rb-group")

    check(f"{tag} document is RTL/Persian", page.evaluate("document.documentElement.dir") == "rtl" and page.evaluate("document.documentElement.lang").startswith("fa"))

    # --- building a tree with the keyboard only ------------------------------------------------
    picker = page.locator("#rule-builder > .rb-group > div:last-child select").first
    picker.focus()
    page.keyboard.press("ArrowDown")  # first condition in the list
    leaf = page.locator("#rule-builder > .rb-group > .rb-leaf")
    check(f"{tag} keyboard: ArrowDown on picker adds a condition", leaf.count() == 1)
    in_leaf = page.evaluate("!!document.activeElement.closest('.rb-leaf')")
    check(f"{tag} keyboard: focus moves into the new condition (not lost to <body>)", in_leaf, page.evaluate("document.activeElement.tagName"))

    nested_btn = page.locator("#rule-builder > .rb-group > div:last-child").get_by_text("＋ گروهِ تودرتو")
    nested_btn.focus()
    page.keyboard.press("Enter")
    check(f"{tag} keyboard: Enter adds a nested group", page.locator("#rule-builder .rb-group .rb-group").count() == 1)
    in_group = page.evaluate("!!document.activeElement.closest('.rb-group .rb-group')")
    check(f"{tag} keyboard: focus moves into the new nested group", in_group, page.evaluate("document.activeElement.tagName"))

    # NOT / AND-OR via keyboard on the nested group
    nested = page.locator("#rule-builder .rb-group .rb-group").first
    nested.get_by_label("برعکس", exact=False).first.check() if nested.get_by_label("برعکس", exact=False).count() else None
    op = nested.locator("select[aria-label^='عملگر گروه']").first
    op.focus()
    page.keyboard.press("ArrowUp")
    tree = json.loads(page.input_value("#id_rules_json"))
    ngroup = next((c for c in tree["children"] if c["type"] == "group"), {})
    check(f"{tag} AND/OR toggled by keyboard and NOT recorded", ngroup.get("op") == "and" and ngroup.get("negate") is True, json.dumps(ngroup, ensure_ascii=False)[:120])

    # --- accessible names / roles / uniqueness --------------------------------------------------
    controls = page.locator("#rule-builder input:not([type=hidden]), #rule-builder select, #rule-builder button")
    unnamed = [i for i in range(controls.count()) if not accessible_name(controls.nth(i))]
    check(f"{tag} every builder control has an accessible name", not unnamed, f"unnamed={len(unnamed)}")
    page.locator("#rule-builder > .rb-group > div:last-child select").first.select_option(index=2)
    page.locator("#rule-builder > .rb-group > div:last-child select").first.select_option(index=3)
    delete_names = [accessible_name(b) for b in page.locator("#rule-builder .rb-leaf button").all()]
    check(f"{tag} delete buttons have unique, descriptive names", len(delete_names) >= 2 and len(set(delete_names)) == len(delete_names), str(delete_names))
    op_names = [accessible_name(s) for s in page.locator("#rule-builder select[aria-label^='عملگر']").all()]
    check(f"{tag} group operator selects are distinguishable by name", len(op_names) >= 2 and len(set(op_names)) == len(op_names), str(op_names))
    roles = page.evaluate("[...document.querySelectorAll('#rule-builder .rb-group')].map(g => g.getAttribute('role'))")
    check(f"{tag} groups expose role=group", roles and all(r == "group" for r in roles), str(roles))
    check(f"{tag} builder region is labelled", page.evaluate("(() => { const e = document.getElementById('rule-builder'); return !!e.getAttribute('role') && !!e.getAttribute('aria-label'); })()"))

    # --- tab order follows DOM order, never traps or drops to body -------------------------------
    page.locator("#rule-builder > .rb-group select").first.focus()
    seen, lost = [], 0
    for _ in range(25):
        page.keyboard.press("Tab")
        info = page.evaluate("""(() => { const a = document.activeElement; if (!a || a === document.body) return null;
            const all = [...document.querySelectorAll('a,button,input,select,textarea,[tabindex]')].filter(e => !e.disabled && e.tabIndex >= 0);
            return all.indexOf(a); })()""")
        if info is None:
            lost += 1
        else:
            seen.append(info)
    check(f"{tag} Tab order is monotonic in DOM order and focus is never lost", lost == 0 and seen == sorted(seen), f"lost={lost}")

    # --- Persian digits / Jalali in the existing leaves -------------------------------------------
    page.locator("#rule-builder > .rb-group > div:last-child select").first.select_option("order_total")
    ot = page.locator("#rule-builder > .rb-group > .rb-leaf").filter(has_text="مبلغ").last
    val = ot.get_by_label("مقدار", exact=True)
    val.fill("۱۰٬۰۰۰٬۰۰۰")
    val.press("Tab")
    serialized = json.dumps(json.loads(page.input_value("#id_rules_json")), ensure_ascii=False)
    check(f"{tag} Persian digits are normalised in rule values", '"value": "10000000"' in serialized, serialized[:160])
    page.select_option("#id_period_mode", "dates")
    page.fill("#id_period_start_date", "۱۴۰۵/۰۷/۰۱")
    check(f"{tag} Jalali date input accepts Persian digits", page.input_value("#id_period_start_date") == "۱۴۰۵/۰۷/۰۱")
    page.select_option("#id_period_mode", "none")

    # --- layout ---------------------------------------------------------------------------------
    overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
    check(f"{tag} no horizontal page overflow", overflow <= 1, f"overflow={overflow}px")
    off = page.evaluate("""(() => { const vw = document.documentElement.clientWidth; const bad = [];
        document.querySelectorAll('#rule-builder button, #rule-builder input, #rule-builder select').forEach(e => {
          const r = e.getBoundingClientRect(); if (r.width && (r.left < -1 || r.right > vw + 1)) bad.push(e.tagName + ':' + (e.getAttribute('aria-label') || '')); });
        return bad; })()""")
    check(f"{tag} no builder control is clipped outside the viewport", not off, str(off[:3]))
    small = page.evaluate("""(() => [...document.querySelectorAll('#rule-builder button')].filter(b => { const r = b.getBoundingClientRect(); return r.width < 24 || r.height < 24; }).length)()""")
    check(f"{tag} touch targets are at least 24x24 CSS px (WCAG 2.2 AA)", small == 0, f"too_small={small}")

    # --- touch interaction ------------------------------------------------------------------------
    if touch:
        before = page.locator("#rule-builder .rb-leaf").count()
        page.locator("#rule-builder .rb-leaf button").first.tap()
        check(f"{tag} touch: tapping delete removes a condition", page.locator("#rule-builder .rb-leaf").count() == before - 1)
        page.locator("#rule-builder > .rb-group > div:last-child").get_by_text("＋ گروهِ تودرتو").tap()
        check(f"{tag} touch: tapping adds a nested group", page.locator("#rule-builder .rb-group").count() >= 2)

    # --- axe-core (WCAG 2.1 A/AA + best practices) ------------------------------------------------
    if os.path.exists(AXE):
        page.add_script_tag(path=AXE)
        res = page.evaluate("""async () => (await axe.run(document, {runOnly: {type: 'tag', values: ['wcag2a','wcag2aa','wcag21a','wcag21aa','best-practice']}})).violations
            .map(v => ({id: v.id, impact: v.impact, nodes: v.nodes.length, help: v.help, targets: v.nodes.slice(0, 4).map(n => n.target.join(' ') + ' | ' + (n.any[0] ? n.any[0].message : ''))}))""")
        report["axe"][f"{engine}/{label}"] = res
        serious = [v for v in res if v["impact"] in ("serious", "critical")]
        for v in serious:
            print(f"INFO {tag} axe {v['id']}: {v['targets']}")
        check(f"{tag} axe: no serious/critical violations", not serious, json.dumps(serious, ensure_ascii=False)[:300])
        minor = [v for v in res if v["impact"] not in ("serious", "critical")]
        print(f"INFO {tag} axe moderate/minor: {[(v['id'], v['nodes']) for v in minor]}")
    else:
        print(f"SKIP {tag} axe (axe-core not installed)")

    # --- validation errors are announced -------------------------------------------------------------
    page.goto(f"{BASE}/admin-portal/campaigns/add/?kind=campaigns")
    page.wait_for_selector("#rule-builder .rb-group")
    page.fill("#id_name", "خطا")
    page.select_option("#id_period_mode", "dates")
    page.fill("#id_period_start_date", "۱۴۰۴/۱۲/۳۰")
    page.fill("#id_coupon_value", "20")
    page.fill("#id_code_valid_days", "5")
    page.get_by_role("button", name="ذخیره").click()
    page.wait_for_load_state("networkidle")
    live = page.evaluate("[...document.querySelectorAll('.coup-err')].map(e => e.getAttribute('role') || (e.closest('[aria-live],[role=alert]') ? 'live' : ''))")
    check(f"{tag} field errors are announced (role=alert / live region)", live and all(live), str(live))
    invalid = page.evaluate("[...document.querySelectorAll('[aria-invalid=true]')].length")
    check(f"{tag} invalid fields are flagged aria-invalid", invalid >= 1, f"count={invalid}")

    check(f"{tag} no JavaScript errors", not errors, "; ".join(errors[:2]))
    ctx.close()


with sync_playwright() as p:
    for engine in ("chromium", "firefox", "webkit"):
        browser = launch(p, engine)
        if isinstance(browser, str):
            report["engines"][engine] = f"NOT RUN: {browser}"
            print(f"NOT RUN {engine}: {browser}")
            continue
        report["engines"][engine] = "ran"
        for vp in VIEWPORTS:
            run_viewport(browser, engine, vp)
        browser.close()

os.makedirs("/tmp/e2e", exist_ok=True)
failed = [n for n, ok in results if not ok]
report.update({"checks": len(results), "failed": failed})
json.dump(report, open("/tmp/e2e/a11y_report.json", "w"), ensure_ascii=False, indent=1)
print(f"\n{len(results) - len(failed)}/{len(results)} checks passed; engines: {report['engines']}")
sys.exit(1 if failed else 0)
