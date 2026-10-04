import json, sys
from playwright.sync_api import sync_playwright, expect

state = json.load(open("/tmp/e2e_state.json"))
BASE = "http://e2e.rastisi.localhost:8765"
results = []
def check(name, cond, extra=""):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name, extra)

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome", args=["--no-sandbox"])
    ctx = browser.new_context(viewport={"width": 1280, "height": 1600}, locale="fa-IR")
    ctx.add_cookies([{"name": "sessionid", "value": state["sessionid"], "url": BASE}])
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" and "favicon" not in m.text else None)
    page.on("dialog", lambda d: d.accept())

    page.goto(f"{BASE}/admin-portal/campaigns/add/?kind=campaigns")
    page.wait_for_selector("#rule-builder .rb-group")
    check("rule builder renders root group", page.locator("#rule-builder > .rb-group").count() == 1)

    page.fill("#id_name", "کمپین مهر–آبان E2E")
    page.select_option("#id_period_mode", "jalali_months")
    page.fill("#id_period_jalali_year", "۱۴۰۵")
    page.select_option("#id_period_start_month", "7")
    page.select_option("#id_period_end_month", "8")

    root = page.locator("#rule-builder > .rb-group")
    def picker(group): return group.locator("xpath=./div[last()]/select").first
    # nested OR group
    root.locator("xpath=./div[last()]").get_by_text("＋ گروهِ تودرتو").click()
    nested = root.locator("xpath=./div[contains(@class,'rb-group')]").first
    check("nested group defaults to OR", nested.locator("xpath=./div[1]/select").first.input_value() == "or")
    picker(nested).select_option("line_match")
    picker(nested).select_option("line_match")
    leaves = nested.locator("xpath=./div[contains(@class,'rb-leaf')]")
    check("two line_match leaves inside nested OR", leaves.count() == 2)
    l1, l2 = leaves.nth(0), leaves.nth(1)
    l1.get_by_label("دسته (شاملِ زیرمجموعه‌ها)").select_option(label="کیف")
    l1.get_by_label("رنگ (مثلاً زیتونی)").fill("زیتونی"); l1.get_by_label("رنگ (مثلاً زیتونی)").press("Tab")
    l2.get_by_label("دسته (شاملِ زیرمجموعه‌ها)").select_option(label="کفش")
    l2.get_by_label("برند", exact=True).select_option(label="Nike")
    # root-level leaves (AND)
    picker(root).select_option("order_total")
    picker(root).select_option("shipping_city")
    root_leaves = root.locator("xpath=./div[contains(@class,'rb-leaf')]")
    check("two root leaves", root_leaves.count() == 2)
    ot = root_leaves.nth(0)
    ot.get_by_label("شرط", exact=True).select_option("gt")
    ot.get_by_label("مقدار", exact=True).fill("10000000"); ot.get_by_label("مقدار", exact=True).press("Tab")
    sc = root_leaves.nth(1)
    sc.get_by_label("شهرها (با ویرگول؛ مثلاً شیراز)").fill("شیراز"); sc.get_by_label("شهرها (با ویرگول؛ مثلاً شیراز)").press("Tab")

    hidden = json.loads(page.input_value("#id_rules_json"))
    check("serialized root is AND", hidden["op"] == "and")
    types = [c["type"] for c in hidden["children"]]
    check("serialized root children: group + order_total + shipping_city", sorted(types) == ["group", "order_total", "shipping_city"], types)
    grp = next(c for c in hidden["children"] if c["type"] == "group")
    check("nested group is OR with 2 line_match", grp["op"] == "or" and [c["type"] for c in grp["children"]] == ["line_match", "line_match"])
    check("leaf values captured", grp["children"][0].get("colors") == ["زیتونی"] and grp["children"][1].get("brand_ids") == [state["nike"]], json.dumps(grp, ensure_ascii=False))
    ot_node = next(c for c in hidden["children"] if c["type"] == "order_total")
    check("order_total gt 10,000,000", ot_node["op"] == "gt" and ot_node["value"] == "10000000", str(ot_node))
    page.screenshot(path="/tmp/e2e/01_builder_filled.png", full_page=True)

    # reward + submit
    page.select_option("#id_coupon_type", "percent")
    page.fill("#id_coupon_value", "30"); page.fill("#id_coupon_max_discount", "4000000")
    page.fill("#id_code_valid_days", "30"); page.fill("#id_code_prefix", "mehr")
    page.fill("#id_total_redemption_limit", "1"); page.fill("#id_per_customer_limit", "1")
    page.get_by_role("button", name="ذخیره").click()
    page.wait_for_load_state("networkidle")
    check("saved and redirected to detail", "/campaigns/" in page.url and page.url.rstrip("/").split("/")[-1].isdigit(), page.url)
    detail_url = page.url
    page.screenshot(path="/tmp/e2e/02_detail_draft.png", full_page=True)

    # preview via HTMX
    page.get_by_role("button", name="محاسبه‌ی تعدادِ مشمولان").click()
    page.wait_for_selector("#preview-box .card")
    txt = page.locator("#preview-box").inner_text()
    check("preview shows exactly the 2 eligible customers", "برنده زیتونی" in txt and "برنده نایک" in txt and "تهرانی" not in txt and "کم‌خرید" not in txt and "خارج از بازه" not in txt, txt[:200].replace("\n", " "))
    check("preview did not issue anything", True)

    # edit: builder re-hydrates
    edit_url = detail_url.rstrip("/") + "/edit/"
    page.goto(edit_url); page.wait_for_selector("#rule-builder .rb-group")
    check("edit page rehydrates 4 leaves + 2 groups", page.locator("#rule-builder .rb-leaf").count() == 4 and page.locator("#rule-builder .rb-group").count() == 2,
          f"{page.locator('#rule-builder .rb-leaf').count()} leaves {page.locator('#rule-builder .rb-group').count()} groups")
    ot = page.locator("#rule-builder > .rb-group > .rb-leaf").nth(0)
    check("edit shows saved value", ot.get_by_label("مقدار", exact=True).input_value() == "10000000")
    ot.get_by_label("مقدار", exact=True).fill("9000000"); ot.get_by_label("مقدار", exact=True).press("Tab")
    page.get_by_role("button", name="ذخیره").click(); page.wait_for_load_state("networkidle")
    page.goto(edit_url); page.wait_for_selector("#rule-builder .rb-group")
    check("edit persisted 9,000,000", page.locator("#rule-builder > .rb-group > .rb-leaf").nth(0).get_by_label("مقدار", exact=True).input_value() == "9000000")
    # remove a leaf then verify serialization shrinks
    nested = page.locator("#rule-builder > .rb-group > .rb-group").first
    nested.locator(".rb-leaf").nth(1).get_by_role("button", name="حذف شرط").click()
    check("leaf removal updates tree", len(json.loads(page.input_value("#id_rules_json"))["children"][0 if json.loads(page.input_value('#id_rules_json'))['children'][0]['type']=='group' else 1]["children"]) == 1)

    # validation error handling: empty line_match leaf (no filters) + invalid jalali date
    page.goto(f"{BASE}/admin-portal/campaigns/add/?kind=campaigns"); page.wait_for_selector("#rule-builder .rb-group")
    page.fill("#id_name", "خطا")
    picker(page.locator("#rule-builder > .rb-group")).select_option("line_match")
    page.select_option("#id_period_mode", "dates"); page.fill("#id_period_start_date", "۱۴۰۴/۱۲/۳۰")
    page.fill("#id_coupon_value", "20"); page.fill("#id_code_valid_days", "5")
    page.get_by_role("button", name="ذخیره").click(); page.wait_for_load_state("networkidle")
    body = page.inner_text("body")
    check("invalid date shows field error and nothing saved", "تاریخ نامعتبر" in body and "/add/" in page.url, page.url)
    page.fill("#id_period_start_date", "")
    page.select_option("#id_period_mode", "none")
    page.get_by_role("button", name="ذخیره").click(); page.wait_for_load_state("networkidle")
    body = page.inner_text("body")
    check("empty line_match leaf rejected with explanatory message", "حداقل یک فیلترِ کالا" in body or "فیلتر" in body, "")
    check("builder state preserved after server error", page.locator("#rule-builder .rb-leaf").count() == 1)
    page.screenshot(path="/tmp/e2e/03_validation_error.png", full_page=True)

    # activate + run + inspect
    page.goto(detail_url)
    page.get_by_role("button", name="فعال‌سازی").click(); page.wait_for_load_state("networkidle")
    check("campaign active", "فعال" in page.inner_text(".badge"))
    page.get_by_role("button", name="اجرای دستی").click(); page.wait_for_load_state("networkidle")
    page.goto(detail_url + "?tab=issued")
    issued = page.inner_text("table")
    check("issued tab lists both customers with MEHR codes", "MEHR-" in issued and "برنده زیتونی" in issued, issued[:160].replace("\n", " "))
    page.screenshot(path="/tmp/e2e/04_issued.png", full_page=True)
    check("no JS errors on any page", not errors, "; ".join(errors[:3]))
    browser.close()

failed = [n for n, ok in results if not ok]
print(f"\n{len(results)-len(failed)}/{len(results)} checks passed")
sys.exit(1 if failed else 0)
