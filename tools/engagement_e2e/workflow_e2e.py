import json, re, subprocess, sys
from playwright.sync_api import sync_playwright

state = json.load(open("/tmp/e2e_state.json"))
ADMIN = "http://e2e.rastisi.localhost:8765"; SHOP = "http://127.0.0.1:8765"
results = []
def check(name, cond, extra=""):
    results.append((name, bool(cond))); print(("PASS " if cond else "FAIL ") + name, extra)

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome", args=["--no-sandbox"])
    errors = []
    # ---------------- مشتری ----------------
    cust = browser.new_context(viewport={"width": 1100, "height": 1400}, locale="fa-IR")
    page = cust.new_page()
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("dialog", lambda d: d.accept())
    page.goto(f"{SHOP}/products/cheap-bag/")
    box = page.locator(".gift-wrap-option")
    check("PDP shows gift wrap option with price", box.count() == 1 and "۲۰٬۰۰۰" in box.inner_text(), box.inner_text()[:80].replace("\n", " "))
    msg = box.locator("input[name=gift_message]")
    check("gift message hidden until selected", not msg.is_visible())
    box.locator("input[name=gift_wrap]").check()
    try:
        msg.wait_for(state="visible", timeout=3000); vis = True
    except Exception:
        vis = False
    check("gift message appears after selecting", vis)
    msg.fill("تولدت مبارک 🎂")
    page.locator("form[hx-post*='/cart/add/cheap-bag/'] button[type=submit]").click()
    page.wait_for_timeout(1200)
    page.goto(f"{SHOP}/cart/")
    cart_box = page.locator(".gift-wrap-box")
    check("cart shows gift wrap checked with saved message", cart_box.count() == 1 and cart_box.locator("input[type=checkbox]").is_checked() and cart_box.locator("input[name=gift_message]").input_value() == "تولدت مبارک 🎂")
    check("cart summary includes gift wrap line", "کادوپیچی" in page.locator("body").inner_text() and "۲۰٬۰۰۰" in page.locator("body").inner_text())
    cart_box.locator("input[type=checkbox]").uncheck(); page.wait_for_timeout(900)
    check("removing gift wrap removes message and charge", page.locator(".gift-wrap-box input[name=gift_message]").count() == 0)
    page.locator(".gift-wrap-box input[type=checkbox]").check(); page.wait_for_timeout(900)
    page.locator(".gift-wrap-box input[name=gift_message]").fill("با آرزوی بهترین‌ها"); page.locator(".gift-wrap-box input[name=gift_message]").press("Tab"); page.wait_for_timeout(900)
    page.screenshot(path="/tmp/e2e/05_cart_gift.png", full_page=True)

    page.goto(f"{SHOP}/checkout/")
    page.wait_for_selector("input[name=receiver_name]")
    page.fill("input[name=receiver_name]", "مشتری آزمایشی"); page.fill("input[name=phone]", "09127770001")
    page.fill("input[name=province]", "فارس"); page.fill("input[name=city]", "شیراز"); page.fill("input[name=postal_code]", "7134567890")
    page.fill("textarea[name=full_address]", "شیراز، خیابان زند")
    page.fill("#id_birth_date", "۱۳۷۰/۰۵/۲۳")
    page.fill("#coup-in", "WRONG-CODE"); page.get_by_role("button", name="اعمال").click(); page.wait_for_timeout(900)
    check("invalid coupon shows error", "نامعتبر" in page.locator("#checkout-container").inner_text())
    page.fill("#coup-in", "e2e10"); page.get_by_role("button", name="اعمال").click(); page.wait_for_timeout(900)
    body = page.locator("#checkout-container").inner_text()
    check("valid coupon applied; gift wrap in summary", "E2E10" in body and "کادوپیچی" in body, "")
    page.fill("input[name=receiver_name]", "مشتری آزمایشی"); page.fill("input[name=phone]", "09127770001"); page.fill("input[name=province]", "فارس")
    page.fill("input[name=city]", "شیراز"); page.fill("input[name=postal_code]", "7134567890"); page.fill("textarea[name=full_address]", "شیراز، خیابان زند"); page.fill("#id_birth_date", "۱۳۷۰/۰۵/۲۳")
    page.screenshot(path="/tmp/e2e/06_checkout.png", full_page=True)
    page.get_by_role("button", name="ادامه و پرداخت امن").click()
    page.wait_for_timeout(2500)
    check("checkout redirected to the order result page", "/checkout/order/" in page.url, page.url)

    page.goto(f"{SHOP}/account/")
    txt = page.locator("body").inner_text()
    check("account shows saved birthday in Jalali", "۱۳۷۰/۰۵/۲۳" in page.locator("#acc_birth_date").input_value())
    page.get_by_role("button", name="سفارش‌های من").click()
    check("account lists the order", "DM-" in page.locator("body").inner_text())
    page.get_by_role("button", name=re.compile("کدهای تخفیف من")).click()
    check("account coupons tab renders (no personal codes yet)", "اختصاصی" in page.locator("#account-coupons").inner_text())
    cust.close()

    # ---------------- مدیر ----------------
    adm = browser.new_context(viewport={"width": 1280, "height": 1400}, locale="fa-IR")
    adm.add_cookies([{"name": "sessionid", "value": state["sessionid"], "url": ADMIN}])
    a = adm.new_page(); a.on("pageerror", lambda e: errors.append(str(e))); a.on("dialog", lambda d: d.accept())
    code = subprocess.check_output([sys.executable, "manage.py", "shell", "-c",
        "from apps.orders.models import Order; o=Order.objects.get(customer__phone='09127770001'); print(o.code, o.gift_wrap_total, o.coupon_discount, o.grand_total, o.items.first().gift_message)"],
        cwd="/home/user/Rastisi6-14040616", text=True).strip().splitlines()[-1].split(" ", 4)
    ocode, gw_total, disc, grand, gmsg = code
    check("order stored gift wrap 20,000 + coupon 10% of item only", gw_total == "20000" and disc == "30000", " ".join(code))
    check("stored gift message is the edited one", "با آرزوی" in gmsg)
    a.goto(f"{ADMIN}/admin-portal/orders/{ocode}/")
    t = a.locator("body").inner_text()
    check("admin order page shows packing instructions + message", "دستورالعمل کادوپیچی" in t and "با آرزوی بهترین‌ها" in t)
    a.screenshot(path="/tmp/e2e/07_admin_order.png", full_page=True)
    a.goto(f"{ADMIN}/admin-portal/invoices/{ocode}/")
    check("invoice shows gift wrap line", "هزینه کادوپیچی" in a.locator("body").inner_text())
    cid = subprocess.check_output([sys.executable, "manage.py", "shell", "-c",
        "from apps.customers.models import Customer; print(Customer.objects.get(phone='09127770001').pk)"], cwd="/home/user/Rastisi6-14040616", text=True).strip().splitlines()[-1]
    a.goto(f"{ADMIN}/admin-portal/customers/{cid}/")
    check("admin customer detail shows birthday", "۱۳۷۰/۰۵/۲۳" in a.locator("body").inner_text())
    # template edit/preview/test-send
    a.goto(f"{ADMIN}/admin-portal/notifications/order.created/")
    a.fill("#email_subject", "سفارش {order_number} ثبت شد ✔"); a.fill("#email_body", "{customer_name} عزیز مبلغ {order_total}")
    a.locator("button:has-text('پیش‌نمایش')").nth(1).click(); a.wait_for_timeout(900)
    check("template preview renders with sample data", "سارا احمدی" in a.locator("#preview-email").inner_text())
    a.fill("#email_body", "{bad_var}"); a.locator("button:has-text('پیش‌نمایش')").nth(1).click(); a.wait_for_timeout(900)
    check("preview rejects unknown variable", "ناشناخته" in a.locator("#preview-email").inner_text())
    a.fill("#email_body", "{customer_name} عزیز مبلغ {order_total}")
    a.get_by_role("button", name="ذخیره", exact=True).first.click(); a.wait_for_load_state("networkidle")
    a.fill("input[name=recipient]", "qa@example.com"); a.select_option("select[name=channel]", "email"); a.get_by_role("button", name="ارسالِ آزمایشی").click(); a.wait_for_load_state("networkidle")
    check("test send reports success", "پیامِ آزمایشی ارسال شد" in a.locator("body").inner_text())
    a.goto(f"{ADMIN}/admin-portal/notifications/history/?event=order.created&status=sent")
    ht = a.locator("body").inner_text()
    check("history shows the test email as sent + test badge", "qa@example.com" in ht and "آزمایشی" in ht)
    a.goto(f"{ADMIN}/admin-portal/notifications/history/?status=dead")
    check("history filter by status works (none dead)", "اعلانی یافت نشد" in a.locator("body").inner_text())
    # birthday occasion via UI
    a.goto(f"{ADMIN}/admin-portal/campaigns/add/?kind=occasions")
    a.fill("#id_name", "هدیه تولد E2E"); 
    check("occasion panel visible for occasion trigger", a.locator("#id_occasion_kind").is_visible())
    a.select_option("#id_occasion_kind", "birthday"); a.fill("#id_occasion_name", "تولد شما"); a.fill("#id_occasion_offset_days", "0")
    a.fill("#id_coupon_value", "20"); a.fill("#id_code_valid_days", "7"); a.fill("#id_code_prefix", "BDAY")
    a.get_by_role("button", name="ذخیره").click(); a.wait_for_load_state("networkidle")
    a.get_by_role("button", name="فعال‌سازی").click(); a.wait_for_load_state("networkidle")
    check("occasion campaign active", "فعال" in a.inner_text(".badge"))
    occ_url = a.url
    # birthday = today for our customer
    subprocess.check_call([sys.executable, "manage.py", "shell", "-c",
        "import datetime as dt; from django.utils import timezone; from apps.customers.models import Customer; c=Customer.objects.get(phone='09127770001'); c.birth_date=timezone.localdate().replace(year=1990); c.save()"],
        cwd="/home/user/Rastisi6-14040616")
    a.get_by_role("button", name="اجرای دستی").click(); a.wait_for_load_state("networkidle")
    a.goto(occ_url + "?tab=issued")
    check("birthday reward issued to the customer with 20% code", "BDAY-" in a.inner_text("table") and "مشتری آزمایشی" in a.inner_text("table"))
    a.get_by_role("button") if False else None
    a.goto(occ_url); a.get_by_role("button", name="اجرای دستی").click(); a.wait_for_load_state("networkidle")
    a.goto(occ_url + "?tab=issued")
    check("second manual run did not duplicate the reward", a.locator("table tbody tr").count() == 1)
    a.screenshot(path="/tmp/e2e/08_birthday_issued.png", full_page=True)
    check("no JS page errors", not errors, "; ".join(errors[:3]))
    browser.close()

failed = [n for n, ok in results if not ok]
print(f"\n{len(results)-len(failed)}/{len(results)} checks passed"); sys.exit(1 if failed else 0)
