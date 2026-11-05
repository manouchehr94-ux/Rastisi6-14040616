"""Evidence-based provider matrix for PLATFORM billing (RastiSi collecting from store owners).

This is the single source of truth for *whether a provider may be offered for platform payments* and *why not*.
A gateway that works for store orders is NOT automatically approved for SaaS platform billing: each row records the
contract evidence, and ``platform`` is one of

* ``approved``         — real adapter + verified official contract covering a plain online payment that RastiSi can
                         sell any product through (no category restriction found) → may be enabled.
* ``pending_contract`` — real adapter exists, but the contract/merchant authorisation for SaaS purchases is unverified.
* ``not_implemented``  — no functional adapter (documentation-blocked skeleton): no request/verify contract exists in code.
* ``not_eligible``     — structurally unsuitable for platform billing (offline method, no server-verifiable payment).

Rows are evidence, not opinion: ``evidence`` names the source and the date it was last read. Changing a row to
``approved`` requires new evidence; ``tests`` pins the matrix to the adapters' own declarations so it cannot drift."""

from __future__ import annotations

from dataclasses import dataclass, field

APPROVED = "approved"
PENDING_CONTRACT = "pending_contract"
NOT_IMPLEMENTED = "not_implemented"
NOT_ELIGIBLE = "not_eligible"


@dataclass(frozen=True)
class ProviderFacts:
    code: str
    platform: str                                   # approved | pending_contract | not_implemented | not_eligible
    summary: str                                    # one line, Persian, shown in Platform Admin
    evidence: str                                   # source + date (English, for the matrix doc / reviewers)
    blocker: str = ""                               # exact reason it is not approved (Persian)
    sandbox: str = "none"                           # "official" | "none"  (honest: only what the docs state)
    sandbox_note: str = ""
    callback: str = ""                              # what the browser return carries (hint only — never proof)
    verify: str = ""                                # authoritative verification mechanism
    reconciliation: str = ""                        # how a missed return is recovered
    refund: str = "manual"                          # "api" | "manual" | "none"
    order_code_style: str = "token"                 # "token" (attempt token) | "numeric" (digits only — provider invoice id)
    prerequisites: tuple = ()                       # external steps (Persian) — shown as setup instructions
    setup_steps: tuple = field(default_factory=tuple)


MATRIX: dict[str, ProviderFacts] = {
    "zibal": ProviderFacts(
        code="zibal", platform=APPROVED,
        summary="درگاه زیبال — قرارداد REST v1 تأییدشده؛ آماده‌ی پیکربندی.",
        evidence="help.zibal.ir/ipg (read 2026-11-03); adapter apps/orders/gateways/zibal.py (CREATE, VERIFY); mocked contract tests.",
        sandbox="official", sandbox_note="مرچنتِ ثابتِ «zibal» طبقِ مستندات؛ بدونِ پرداختِ واقعی.",
        callback="success/status/trackId (فقط راهنما)", verify="POST /v1/verify (server-to-server) + تطبیقِ orderId و مبلغ",
        reconciliation="reconcile_platform_payments (verify با trackId)",
        refund="manual",
        prerequisites=("ثبتِ دامنه‌ی بازگشتِ پلتفرم در پنل زیبال",),
        setup_steps=(
            "در پنل زیبال یک درگاهِ پرداخت برای دامنه‌ی راستیسی بسازید و «Merchant ID» را کپی کنید.",
            "دامنه‌ی بازگشت (callback) باید با دامنه‌ی ثبت‌شده در زیبال یکی باشد.",
            "ابتدا حالتِ آزمایشی (Sandbox) را روشن کنید و «تستِ پیکربندی» را بزنید.",
            "پس از تراکنشِ آزمایشیِ موفق، Sandbox را خاموش و Merchant واقعی را وارد کنید.",
        ),
    ),
    "zarinpal": ProviderFacts(
        code="zarinpal", platform=APPROVED,
        summary="درگاه زرین‌پال — قرارداد REST v4 تأییدشده؛ آماده‌ی پیکربندی.",
        evidence="zarinpal.com/docs/paymentGateway/* (read 2026-11-03); adapter zarinpal.py (CREATE, VERIFY); mocked contract tests.",
        sandbox="none", sandbox_note="در مستنداتِ خوانده‌شده میزبانِ Sandbox مشخص نشده؛ ساختگی ارائه نمی‌شود.",
        callback="Authority/Status (فقط راهنما)", verify="POST /pg/v4/payment/verify.json با Authority و مبلغِ مورد انتظار",
        reconciliation="reconcile_platform_payments (verify با Authority)", refund="manual",
        prerequisites=("Merchant ID ۳۶ کاراکتری", "دامنه‌ی بازگشت مطابقِ درگاهِ ثبت‌شده"),
        setup_steps=(
            "در پنل زرین‌پال درگاهِ مربوط به دامنه‌ی راستیسی را بسازید و Merchant ID (۳۶ کاراکتر) را کپی کنید.",
            "ذخیره و فعال‌سازی؛ سپس «تستِ پیکربندی» (یک درخواستِ پرداختِ آزمایشیِ بدونِ انتقال) را اجرا کنید.",
            "اولین تراکنشِ واقعی را با مبلغِ حداقلی خودتان انجام دهید.",
        ),
    ),
    "pasargad": ProviderFacts(
        code="pasargad", platform=APPROVED,
        summary="پاسارگاد (درسا) — قرارداد REST مستندِ رسمی؛ نیازمندِ اعتبارنامه‌ی پایانه‌ی خودِ راستیسی.",
        evidence=(
            "raw.githubusercontent.com/pep-ipg/Dorsa-IPG-pasargad docs api-reference.md + usage-guides.md (re-read 2026-11-05): "
            "getToken(Bearer), purchase, payment-inquiry, verify-transactions, confirm-transactions, reverse-transactions; "
            "callback params invoiceId/status/referenceNumber/trackId; Referer required on the customer redirect; "
            "no sandbox base URL documented; no business-category restriction stated in the technical docs."
        ),
        order_code_style="numeric",
        sandbox="none", sandbox_note="مستنداتِ فنی هیچ میزبانِ Sandbox ذکر نکرده‌اند.",
        callback="invoiceId/status(success|failed|unknown|cancel|expire)/referenceNumber/trackId (فقط راهنما)",
        verify="payment-inquiry (وضعیت+مبلغ) سپس verify-transactions؛ پس از مهلت (پیش‌فرض ۲۵ دقیقه) مبلغ خودکار به مشتری برمی‌گردد",
        reconciliation="reconcile_platform_payments باید هر ۵ دقیقه اجرا شود (مهلتِ verify ۲۵ دقیقه است)",
        refund="manual",
        prerequisites=(
            "نام‌کاربری/گذرواژه/شماره‌ی پایانه‌ی خودِ راستیسی از بانک پاسارگاد (پایانه‌ی پلتفرم، نه فروشگاه‌ها)",
            "ثبتِ IP سرورِ راستیسی نزدِ پاسارگاد (whitelist)",
            "دامنه‌ی بازگشت = دامنه‌ی ثبت‌شده در قراردادِ پایانه (کدِ ۱۳۰۲۸ در غیرِ این صورت)",
        ),
        setup_steps=(
            "از بانک پاسارگاد نام‌کاربری، گذرواژه، شماره‌ی پایانه و کد سرویس (پیش‌فرض ۸) پایانه‌ی راستیسی را بگیرید.",
            "IP سرورِ تولید را برای دسترسی به pep.shaparak.ir در بانک ثبت کنید.",
            "اعتبارنامه را وارد و ذخیره کنید؛ «تستِ پیکربندی» ابتدا احرازِ هویت (getToken) و سپس یک درخواستِ خریدِ بدونِ پرداخت را می‌سنجد (خطای ۱۳۰۲۸ = دامنه‌ی بازگشت نامعتبر).",
            "کرونِ reconcile_platform_payments را هر ۵ دقیقه اجرا کنید (مهلتِ verify ۲۵ دقیقه).",
            "اولین تراکنشِ واقعی را با مبلغِ حداقلی انجام دهید.",
        ),
    ),
    "snappay": ProviderFacts(
        code="snappay", platform=PENDING_CONTRACT,
        summary="اسنپ‌پی (BNPL) — آداپتر برای سبدِ کالای فروشگاه‌ها هست؛ استفاده برای خریدِ SaaS در انتظارِ تأییدِ قرارداد.",
        evidence="academy.snapppay.ir/self-cms REST v2.1 (read 2026-11-03; host not reachable from this session on 2026-11-05); adapter snappay.py.",
        blocker=(
            "قراردادِ منتشرشده سبدِ کالا (cartList) و قراردادِ اقساطِ مصرف‌کننده را توصیف می‌کند؛ هیچ مدرکی نیست که "
            "فروشِ اشتراکِ نرم‌افزار/اعتبارِ پیامک را پوشش دهد. فعال‌سازی نیازمندِ تأییدِ کتبیِ اسنپ‌پی برای حسابِ پذیرنده‌ی راستیسی است."
        ),
        callback="paymentToken/state (فقط راهنما)", verify="verify + settle (دو مرحله)", reconciliation="inquire (status)",
        prerequisites=("تأییدِ کتبیِ اسنپ‌پی برای فروشِ خدماتِ SaaS", "اعتبارنامه‌ی پذیرنده + IP whitelist + returnURL مجاز"),
        setup_steps=("ابتدا تأییدِ قراردادی را از اسنپ‌پی بگیرید؛ تا آن زمان این درگاه برای پرداختِ پلتفرم فعال نمی‌شود.",),
    ),
    "torobpay": ProviderFacts(
        code="torobpay", platform=PENDING_CONTRACT,
        summary="ترب‌پی (BNPL) — آداپتر برای سبدِ کالای فروشگاه‌ها هست؛ استفاده برای خریدِ SaaS در انتظارِ تأییدِ قرارداد.",
        evidence="provider-published WooCommerce plugin source class-torobpay-api.php (read 2026-11-03; host not reachable on 2026-11-05); adapter torobpay.py.",
        blocker=(
            "قراردادِ در دسترس فقط سبدِ کالا و اقساط را توصیف می‌کند؛ پوششِ خریدِ SaaS تأیید نشده است. "
            "نیازمندِ تأییدِ کتبیِ ترب‌پی برای حسابِ پذیرنده‌ی راستیسی."
        ),
        callback="(فقط راهنما)", verify="verify + settle (دو مرحله)", reconciliation="inquire (status)",
        prerequisites=("تأییدِ کتبیِ ترب‌پی برای فروشِ خدماتِ SaaS", "اعتبارنامه‌ی پذیرنده + IP whitelist"),
        setup_steps=("ابتدا تأییدِ قراردادی را از ترب‌پی بگیرید؛ تا آن زمان این درگاه برای پرداختِ پلتفرم فعال نمی‌شود.",),
    ),
    "saman": ProviderFacts(
        code="saman", platform=NOT_IMPLEMENTED,
        summary="سامان (سپ) — پیاده‌سازی فنی وجود ندارد.",
        evidence="adapter saman.py is a registered skeleton (no capabilities); official contract not obtained (sep.ir marketing-only 2026-11-03; sep.shaparak.ir not reachable from this session 2026-11-05).",
        blocker="قراردادِ فنیِ رسمی (token/redirect/verify/reverse) در دسترس نیست و آداپترِ کارکردی وجود ندارد. با دریافتِ مستندِ رسمی از سپ پیاده‌سازی می‌شود.",
        prerequisites=("مستندِ فنیِ رسمیِ سپ + قراردادِ پذیرنده",),
        setup_steps=("مستندِ فنیِ رسمی و اعتبارنامه‌ی پذیرنده را از سپ بگیرید؛ سپس آداپتر پیاده‌سازی و تست می‌شود.",),
    ),
    "parsian": ProviderFacts(
        code="parsian", platform=NOT_IMPLEMENTED,
        summary="پارسیان (پک) — پیاده‌سازی فنی وجود ندارد.",
        evidence="adapter parsian.py skeleton; pec.ir contract unreachable 2026-11-03 and www.pec.ir not reachable from this session 2026-11-05.",
        blocker="مستندِ فنی/WSDLِ رسمی در دسترس نیست؛ آداپترِ کارکردی وجود ندارد.",
        prerequisites=("مستندِ فنی/WSDL رسمیِ پارسیان + قراردادِ پذیرنده",),
        setup_steps=("مستندِ رسمی را از بانک پارسیان بگیرید؛ سپس آداپتر پیاده‌سازی می‌شود.",),
    ),
    "mellat": ProviderFacts(
        code="mellat", platform=NOT_IMPLEMENTED,
        summary="ملت (به‌پرداخت) — پیاده‌سازی فنی وجود ندارد.",
        evidence="adapter mellat.py skeleton; behpardakht.com unreachable 2026-11-03; api.mellatbank.ir not reachable from this session 2026-11-05.",
        blocker="مستندِ رسمیِ به‌پرداخت در دسترس نیست؛ settle باید مرحله‌ی جدا باشد و بدونِ مستند قابل پیاده‌سازی نیست.",
        prerequisites=("مستندِ فنی رسمیِ به‌پرداخت + قراردادِ پذیرنده",),
        setup_steps=("مستندِ رسمی را از به‌پرداخت ملت بگیرید؛ سپس آداپتر (با settle جدا) پیاده‌سازی می‌شود.",),
    ),
    "sadad": ProviderFacts(
        code="sadad", platform=NOT_IMPLEMENTED,
        summary="سداد (ملی) — پیاده‌سازی فنی وجود ندارد.",
        evidence="adapter sadad.py skeleton; sadadpsp.ir unreachable 2026-11-03 and 2026-11-05 (outside allowed network domains).",
        blocker="مستندِ فنیِ رسمیِ سداد در دسترس نیست؛ آداپترِ کارکردی وجود ندارد.",
        prerequisites=("مستندِ فنی رسمیِ سداد + قراردادِ پذیرنده",),
        setup_steps=("مستندِ رسمی را از سداد بگیرید؛ سپس آداپتر پیاده‌سازی می‌شود.",),
    ),
    "tejarat": ProviderFacts(
        code="tejarat", platform=NOT_IMPLEMENTED,
        summary="تجارت — پیاده‌سازی فنی وجود ندارد و PSPِ زیرینِ آن مشخص نیست.",
        evidence="adapter tejarat.py is a display-label skeleton; underlying PSP unconfirmed (IranKish not assumed); irankish.com connection reset 2026-11-03.",
        blocker="مشخص نیست بانک تجارت از کدام PSP استفاده می‌کند و مستندِ فنی در دسترس نیست.",
        prerequisites=("مشخص‌شدنِ PSPِ زیرین + مستندِ فنیِ رسمیِ آن",),
        setup_steps=("از بانک تجارت PSP و مستندِ فنیِ مربوط را بگیرید؛ سپس آداپتر پیاده‌سازی می‌شود.",),
    ),
    "card_to_card": ProviderFacts(
        code="card_to_card", platform=NOT_ELIGIBLE,
        summary="کارت‌به‌کارت — روشِ آفلاین؛ پرداختِ قابل‌تأییدِ سرور-به-سرور ندارد.",
        evidence="adapter card_to_card.py is_online=False (manual approval by a merchant).",
        blocker="برای پرداختِ پلتفرم یک گردشِ کارِ تازه (تأییدِ دستیِ مدیرِ پلتفرم) لازم است که تصمیمِ محصولی/مالی جداست؛ اینجا فعال نمی‌شود.",
    ),
    "cod": ProviderFacts(
        code="cod", platform=NOT_ELIGIBLE,
        summary="پرداخت در محل — برای خدماتِ دیجیتال/SaaS بی‌معنی است.",
        evidence="adapter cod.py is_online=False.",
        blocker="پرداخت در محل برای اشتراک/اعتبارِ پیامک کاربرد ندارد.",
    ),
}

#: درگاه‌هایی که برای پرداختِ پلتفرم مجازند — مشتق از ماتریس (نه فهرستِ جداگانه).
APPROVED_CODES = tuple(code for code, facts in MATRIX.items() if facts.platform == APPROVED)


def facts_for(code: str) -> ProviderFacts | None:
    return MATRIX.get(code)
