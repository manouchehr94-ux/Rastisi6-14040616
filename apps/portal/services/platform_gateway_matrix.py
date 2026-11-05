"""Evidence-based provider matrix for PLATFORM billing (RastiSi collecting from store owners).

This is the single source of truth for *whether a provider may be offered for platform payments* and *under which gates*.
A gateway that works for store orders is NOT automatically approved for SaaS platform billing: each row records the
contract evidence, and ``platform`` is one of

* ``approved``        — real adapter + verified official contract covering a plain online payment (no category restriction
                        found) → ready once configured and enabled. (``platform_card`` is the manual-payment equivalent.)
* ``gated``           — a real adapter / workflow exists, but live use is blocked until the platform owner records the
                        evidence named in ``gates`` (provider approval for the purchase type, contract verification against
                        the official document, an authorised live test). Mocked tests never open a gate.
* ``not_implemented`` — no functional adapter (documentation-blocked skeleton): no request/verify contract exists in code.

Store-only methods (cash on delivery, store card-to-card) are **not platform billing methods at all** — see ``STORE_ONLY``.

Rows are evidence, not opinion: ``evidence`` names the source and the date it was last read. Changing a row requires new
evidence; the tests pin the matrix to the adapters' own declarations so it cannot drift."""

from __future__ import annotations

from dataclasses import dataclass, field

APPROVED = "approved"
GATED = "gated"
NOT_IMPLEMENTED = "not_implemented"

KIND_ONLINE = "online"
KIND_MANUAL = "manual"

#: گیت‌هایِ آمادگی (هر کدام یک گواهیِ صریحِ مدیر با ارجاع، ثبت‌شده در حسابرسی):
GATE_PROVIDER_APPROVAL = "provider_approval"          # تأییدِ کتبیِ ارائه‌دهنده برای نوعِ خریدِ مشخص (مثلاً SaaS در BNPL)
GATE_CONTRACT_VERIFICATION = "contract_verification"  # تطبیقِ آداپتر با مستندِ فنیِ رسمیِ جاری
GATE_LIVE_VERIFICATION = "live_verification"          # یک تراکنشِ واقعیِ مجاز با موفقیتِ verify/settle

PURCHASE_SUBSCRIPTION = "subscription"
PURCHASE_SMS = "sms_package"
PURCHASE_TYPES = (PURCHASE_SUBSCRIPTION, PURCHASE_SMS)
PURCHASE_LABELS = {PURCHASE_SUBSCRIPTION: "اشتراک (خرید و تمدید)", PURCHASE_SMS: "بسته‌ی اعتبار پیامک"}

#: روش‌هایی که فقط برای سفارشِ فروشگاه‌اند و **هرگز** روشِ پرداختِ پلتفرم نیستند (پرداخت در محل، کارت‌به‌کارتِ فروشگاه).
STORE_ONLY = frozenset({"cod", "card_to_card"})

#: کدِ روشِ دستیِ کارت‌به‌کارتِ **پلتفرم** — کاملاً جدا از ``card_to_card`` (آداپترِ فروشگاه).
PLATFORM_CARD = "platform_card"


@dataclass(frozen=True)
class ProviderFacts:
    code: str
    platform: str                                   # approved | gated | not_implemented
    summary: str                                    # one line, Persian, shown in Platform Admin
    evidence: str                                   # source + date (English, for the matrix doc / reviewers)
    kind: str = KIND_ONLINE                         # online | manual
    gates: tuple = ()                               # GATE_* that must be attested before live use
    default_purchase_types: tuple = PURCHASE_TYPES  # used when the admin has not chosen types explicitly
    blocker: str = ""                               # exact reason it is not approved (Persian)
    sandbox: str = "none"                           # "official" | "none"  (honest: only what the docs state)
    sandbox_note: str = ""
    callback: str = ""                              # what the browser return carries (hint only — never proof)
    verify: str = ""                                # authoritative verification mechanism
    reconciliation: str = ""                        # how a missed return is recovered
    refund: str = "manual"                          # "api" | "manual" | "none"
    order_code_style: str = "token"                 # "token" (attempt token) | "numeric" | "alnum" (provider order id)
    prerequisites: tuple = ()                       # external steps (Persian) — shown as setup instructions
    setup_steps: tuple = field(default_factory=tuple)
    manual_fields: tuple = ()                       # for KIND_MANUAL: ({name,label,public,required})


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
        code="snappay", platform=GATED, gates=(GATE_PROVIDER_APPROVAL, GATE_LIVE_VERIFICATION), default_purchase_types=(),
        summary="اسنپ‌پی (BNPL) — مسیرِ پرداختِ پلتفرم پیاده شده؛ استفاده فقط با تأییدِ کتبیِ ارائه‌دهنده برای نوعِ خرید و تستِ واقعیِ مجاز.",
        evidence=(
            "adapter apps/orders/gateways/snappay.py (REST v2.1 from academy.snapppay.ir/self-cms, read 2026-11-03; host not "
            "resolvable from this session on 2026-11-05): OAuth, eligibility, payment/token (itemised cartList), verify, SETTLE, "
            "cancel, status. Contract describes retail carts + consumer installment contracts; no statement covering SaaS "
            "subscriptions / SMS credit."
        ),
        blocker=(
            "پیش از هر استفاده‌ی زنده باید اسنپ‌پی کتباً فروشِ همین خدمت (اشتراک/اعتبار پیامک) را برای حسابِ پذیرنده‌ی راستیسی تأیید کرده باشد؛ "
            "مرجعِ آن تأیید و نوع‌های خریدِ مجاز در گیتِ «تأییدِ ارائه‌دهنده» ثبت می‌شود."
        ),
        callback="POST returnURL: transactionId, state (OK|FAILED), amount (فقط راهنما)",
        verify="verify (بدونِ نهایی‌سازی) ← settle (نهایی‌سازیِ جدا)؛ اشتراک/پیامک فقط پس از موفقیتِ هر دو فعال می‌شود؛ ابهامِ settle ⇒ status/inquiry",
        reconciliation="reconcile_platform_payments: verify→settle یا استعلام (status)", refund="manual",
        order_code_style="alnum",
        prerequisites=("تأییدِ کتبیِ اسنپ‌پی برای فروشِ خدماتِ SaaS", "client_id / client_secret پذیرنده‌ی راستیسی", "IP سرور در whitelist و returnURL مجاز",
                       "نشانیِ محیطِ stage/production که اسنپ‌پی می‌دهد (api_base)"),
        setup_steps=(
            "تأییدِ کتبیِ اسنپ‌پی را بگیرید و مرجعِ آن را در گیتِ «تأییدِ ارائه‌دهنده» (با نوع‌های خریدِ مجاز) ثبت کنید.",
            "اعتبارنامه‌ی پذیرنده و (در صورتِ ارائه) api_base محیط stage را وارد کنید؛ «تستِ پیکربندی» فقط OAuth را می‌سنجد.",
            "با یک خریدِ آزمایشیِ واقعیِ حداقلی از فروشگاهِ خودتان (حالتِ آزمایشی مدیر) verify→settle را بررسی و گیتِ «تستِ واقعی» را ثبت کنید.",
            "سپس روش را فعال کنید.",
        ),
    ),
    "torobpay": ProviderFacts(
        code="torobpay", platform=GATED, gates=(GATE_PROVIDER_APPROVAL, GATE_LIVE_VERIFICATION), default_purchase_types=(),
        summary="ترب‌پی (BNPL) — مسیرِ پرداختِ پلتفرم پیاده شده؛ استفاده فقط با تأییدِ کتبیِ ارائه‌دهنده برای نوعِ خرید و تستِ واقعیِ مجاز.",
        evidence=(
            "adapter apps/orders/gateways/torobpay.py (from the provider-published WooCommerce plugin source class-torobpay-api.php, "
            "read 2026-11-03; host not resolvable on 2026-11-05): token, eligibility, verify, SETTLE, cancel, status. "
            "No statement covering SaaS subscriptions / SMS credit."
        ),
        blocker=(
            "پیش از هر استفاده‌ی زنده باید ترب‌پی کتباً فروشِ همین خدمت را برای حسابِ پذیرنده‌ی راستیسی تأیید کرده باشد؛ مرجعِ تأیید در گیتِ «تأییدِ ارائه‌دهنده» ثبت می‌شود."
        ),
        callback="(فقط راهنما)", verify="verify ← settle (دو مرحله)؛ فعال‌سازی فقط پس از هر دو؛ ابهام ⇒ inquiry",
        reconciliation="reconcile_platform_payments: verify→settle یا استعلام", refund="manual", order_code_style="alnum",
        prerequisites=("تأییدِ کتبیِ ترب‌پی برای فروشِ خدماتِ SaaS", "client_id / client_secret / username / password پذیرنده", "IP سرور در whitelist"),
        setup_steps=(
            "تأییدِ کتبیِ ترب‌پی را بگیرید و مرجعِ آن را در گیتِ «تأییدِ ارائه‌دهنده» ثبت کنید.",
            "اعتبارنامه را وارد کنید و «تستِ پیکربندی» را بزنید.",
            "با یک خریدِ آزمایشیِ واقعیِ حداقلی verify→settle را بررسی و گیتِ «تستِ واقعی» را ثبت کنید.",
        ),
    ),
    "saman": ProviderFacts(
        code="saman", platform=GATED, gates=(GATE_CONTRACT_VERIFICATION, GATE_LIVE_VERIFICATION),
        summary="سامان (سپ) — آداپترِ توکنی پیاده شده؛ فعال‌سازی فقط پس از تطبیقِ با مستندِ رسمیِ جاری و تستِ واقعیِ مجاز.",
        evidence=(
            "No official SEP document was reachable on 2026-11-05 (sep.ir marketing-only; sep.shaparak.ir / docs not resolvable from this "
            "session). Contract encoded from secondhand sources ONLY: pkg.go.dev/github.com/aliworkshop/samanpayment (JSON token request "
            "{action,TerminalId,RedirectUrl,TxnRandomSessionKey,ResNum,Amount,CellNumber}, callback {MID,State,Status,RRN,RefNum,ResNum,"
            "TerminalId,TraceNo,Amount,Wage,SecurePan}, VerifyTransaction/ReverseTransaction {RefNum,TerminalNumber,TxnRandomSessionKey} "
            "→ {Success,ResultCode,TransactionDetail{OrginalAmount,AffectiveAmount,...}}), shetabit/multipay Saman driver (legacy SOAP "
            "variant: RequestToken/VerifyTransaction/ReverseTransaction; POST form Token+RedirectUrl), WordPress/PyPI wrappers (server IP "
            "whitelist on sep.shaparak.ir). Which variant is current is UNVERIFIED."
        ),
        blocker=(
            "مستندِ فنیِ رسمیِ جاریِ سپ در دسترس نبود؛ آدرس‌ها و فیلدها از منابعِ ثانویه‌اند. تا زمانی که مدیر پیاده‌سازی را با مستندِ رسمیِ "
            "جاری تطبیق ندهد (گیتِ «تأییدِ قرارداد فنی») و یک تراکنشِ واقعیِ مجاز موفق نشود، فعال‌سازیِ زنده مسدود است."
        ),
        callback="POST form: State/Status, RefNum, ResNum, RRN, TraceNo, Amount, SecurePan (فقط راهنما)",
        verify="VerifyTransaction (RefNum + TerminalNumber) با تطبیقِ ResNum و مبلغِ اصلی؛ RefNum یکتا (جلوگیری از استفاده‌ی دوباره)",
        reconciliation="reconcile_platform_payments (verify با RefNum؛ بدونِ RefNum امکانِ تطبیق نیست)", refund="manual",
        order_code_style="alnum",
        prerequisites=("TerminalId (و در صورتِ لزوم کلیدِ تراکنش) پذیرنده‌ی راستیسی از سپ", "IP سرور در whitelist سپ", "تطبیقِ آداپتر با مستندِ رسمیِ جاری"),
        setup_steps=(
            "مستندِ فنیِ رسمیِ جاریِ سپ را از بانک بگیرید و آداپتر (apps/orders/gateways/saman.py) را با آن تطبیق دهید؛ سپس گیتِ «تأییدِ قرارداد فنی» را با مرجعِ سند ثبت کنید.",
            "TerminalId را وارد کنید و IP سرور را نزدِ سپ ثبت کنید.",
            "«تستِ پیکربندی» یک توکنِ پرداختِ پرداخت‌نشده می‌سازد.",
            "با یک خریدِ واقعیِ حداقلی از فروشگاهِ خودتان verify را بررسی و گیتِ «تستِ واقعی» را ثبت کنید.",
        ),
    ),
    "mellat": ProviderFacts(
        code="mellat", platform=GATED, gates=(GATE_CONTRACT_VERIFICATION, GATE_LIVE_VERIFICATION),
        summary="ملت (به‌پرداخت) — آداپتر با چرخه‌ی pay/verify/settle پیاده شده؛ فعال‌سازی فقط پس از تطبیقِ با مستندِ رسمیِ جاری و تستِ واقعیِ مجاز.",
        evidence=(
            "No official Behpardakht document was reachable on 2026-11-05 (api.mellatbank.ir / behpardakht.com not resolvable). "
            "Secondhand sources: shetabit/multipay Behpardakht driver (raw.githubusercontent.com, read 2026-11-05: SOAP bpPayRequest/"
            "bpVerifyRequest/bpSettleRequest/bpReversalRequest; params terminalId,userName,userPassword,orderId,amount(rial),localDate "
            "Ymd,localTime His,additionalData,callBackUrl,payerId; verify/settle/reversal take orderId,saleOrderId,saleReferenceId; "
            "response 'code,RefId'; POST form field RefId; callback ResCode,RefId,SaleOrderId,SaleReferenceId,CardHolderPan; verify 43=already "
            "verified, settle 45/48 accepted; reversal on failed verify/settle); a 2013 'Mellat PGW User Manual Rev 1.1' copy and WSDL "
            "location bpm.shaparak.ir/pgwchannel/services/pgw?wsdl (third-party hosts). Whether this still matches the current contract is UNVERIFIED."
        ),
        blocker=(
            "مستندِ رسمیِ جاریِ به‌پرداخت در دسترس نبود؛ ساختارِ SOAP از منابعِ ثانویه است. تا زمانی که مدیر پیاده‌سازی را با مستندِ رسمیِ جاری "
            "تطبیق ندهد و یک تراکنشِ واقعیِ مجاز (verify + settle) موفق نشود، فعال‌سازیِ زنده مسدود است. ردِ callback بدونِ verify+settle هرگز خریدی را فعال نمی‌کند."
        ),
        callback="POST: ResCode, RefId, SaleOrderId, SaleReferenceId, CardHolderPan (فقط راهنما)",
        verify="bpVerifyRequest ← bpSettleRequest (settle مرحله‌ی جدا)؛ فعال‌سازی فقط پس از هر دو؛ ابهام ⇒ bpInquiryRequest",
        reconciliation="reconcile_platform_payments: verify+settle یا bpInquiryRequest", refund="manual", order_code_style="numeric",
        prerequisites=("terminalId / userName / userPassword پذیرنده‌ی راستیسی از به‌پرداخت", "IP سرور در whitelist بانک", "تطبیقِ آداپتر با مستندِ رسمیِ جاری"),
        setup_steps=(
            "مستندِ فنیِ رسمیِ جاریِ به‌پرداخت را بگیرید و آداپتر (apps/orders/gateways/mellat.py) را با آن تطبیق دهید؛ سپس گیتِ «تأییدِ قرارداد فنی» را با مرجعِ سند ثبت کنید.",
            "terminalId، نام‌کاربری و گذرواژه را وارد کنید و IP سرور را ثبت کنید.",
            "«تستِ پیکربندی» یک bpPayRequest پرداخت‌نشده می‌سازد.",
            "با یک خریدِ واقعیِ حداقلی از فروشگاهِ خودتان verify و settle را بررسی و گیتِ «تستِ واقعی» را ثبت کنید.",
        ),
    ),
    "parsian": ProviderFacts(
        code="parsian", platform=NOT_IMPLEMENTED,
        summary="پارسیان (پک) — پیاده‌سازی فنی وجود ندارد.",
        evidence="adapter parsian.py skeleton; pec.ir contract unreachable 2026-11-03 and www.pec.ir not reachable from this session 2026-11-05.",
        blocker="مستندِ فنی/WSDLِ رسمی در دسترس نیست؛ آداپترِ کارکردی وجود ندارد.",
        prerequisites=("مستندِ فنی/WSDL رسمیِ پارسیان + قراردادِ پذیرنده",),
        setup_steps=("مستندِ رسمی را از بانک پارسیان بگیرید؛ سپس آداپتر پیاده‌سازی می‌شود.",),
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
    PLATFORM_CARD: ProviderFacts(
        code=PLATFORM_CARD, platform=APPROVED, kind=KIND_MANUAL, default_purchase_types=(),
        summary="کارت‌به‌کارتِ پلتفرم — روشِ دستیِ درجه‌یک: ادعای پرداخت + تأییدِ مالیِ مستقل؛ هرگز فعال‌سازیِ خودکار.",
        evidence="First-class manual workflow in apps/billing (PlatformManualPaymentClaim): receipts are evidence, never proof of funds; approval needs an authorised finance admin's independent bank-statement confirmation.",
        callback="(ندارد — ثبتِ ادعا توسطِ مالک)", verify="تأییدِ دستیِ مدیرِ مالی با صورتحسابِ بانکی؛ سپس همان مسیرِ confirm_payment (یک‌بار، قفل‌دار، دفتر)",
        reconciliation="صفِ بررسی + انقضای خودکارِ ادعاهای رسیدگی‌نشده", refund="manual",
        prerequisites=("کارتِ مقصدِ اختصاصیِ پلتفرم (جدا از کارتِ فروشگاه‌ها)", "یک مدیرِ مالیِ مجاز برای تأیید"),
        setup_steps=(
            "شماره‌کارت مقصد، نامِ دارنده و (اختیاری) شبا و نامِ بانکِ **پلتفرم** را وارد کنید (جدا از تنظیماتِ کارت‌به‌کارتِ فروشگاه‌ها).",
            "نوع‌های خریدی را که با این روش مجازند انتخاب کنید و فعال کنید.",
            "ادعاها در «بررسیِ کارت‌به‌کارت» ظاهر می‌شوند؛ فقط پس از دیدنِ واردشدنِ پول در صورتحسابِ بانکی تأیید کنید.",
        ),
        manual_fields=(
            {"name": "destination_card", "label": "شماره‌کارتِ مقصدِ پلتفرم", "public": True, "required": True},
            {"name": "holder_name", "label": "نامِ دارنده‌ی کارت", "public": True, "required": True},
            {"name": "bank_name", "label": "نامِ بانک", "public": True, "required": False},
            {"name": "sheba", "label": "شماره‌ی شبا (اختیاری)", "public": True, "required": False},
            {"name": "instructions", "label": "توضیحاتِ پرداخت برای مالک (اختیاری)", "public": True, "required": False},
        ),
    ),
}

#: روش‌هایی که پیاده‌سازیِ کارکردی دارند (approved + gated) — مشتق از ماتریس، نه فهرستِ جداگانه.
APPROVED_CODES = tuple(code for code, f in MATRIX.items() if f.platform == APPROVED)
IMPLEMENTED_CODES = tuple(code for code, f in MATRIX.items() if f.platform in (APPROVED, GATED))
ONLINE_CODES = tuple(code for code in IMPLEMENTED_CODES if MATRIX[code].kind == KIND_ONLINE)
MANUAL_CODES = tuple(code for code in IMPLEMENTED_CODES if MATRIX[code].kind == KIND_MANUAL)


def facts_for(code: str) -> ProviderFacts | None:
    return MATRIX.get(code)
