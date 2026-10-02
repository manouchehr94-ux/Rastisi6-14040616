import json
import logging

from django.conf import settings
from django.contrib.auth import login as auth_login
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.cart.models import CartItem
from apps.cart.services.cart_service import get_cart
from apps.customers.models import Customer
from apps.customers.services import auth_service
from apps.sms.services import otp_service
from apps.stores.resolution import resolve_store_for_service

from .forms import CheckoutAddressForm
from .models import Order
from .services import checkout_service
from .services.payment_service import simulate_payment

logger = logging.getLogger(__name__)

CHECKOUT_OTP_SESSION_KEY = "checkout_otp_phone"


def _get_own_order(request, code, queryset=None):
    if not (request.user.is_authenticated and hasattr(request.user, "customer_profile")):
        raise Http404
    queryset = Order.objects.all() if queryset is None else queryset
    order = queryset.filter(code=code, customer=request.user.customer_profile).first()
    if order is None:
        raise Http404
    return order


def _render_body(request, cart, *, address_form=None, coupon_input="", coupon_error=""):
    context = checkout_service.build_context(request, cart)
    context["address_form"] = address_form or CheckoutAddressForm(initial=checkout_service.address_initial(request))
    context["coupon_input"] = coupon_input
    context["coupon_error"] = coupon_error
    return render(request, "orders/partials/checkout_body.html", context)


def _dynamic_response(request, cart, *, toast_message=None, toast_type="ok", **extra):
    response = _render_body(request, cart, **extra)
    if toast_message:
        response["HX-Trigger"] = json.dumps({"toast": {"message": toast_message, "type": toast_type}})
    return response


def checkout_step1(request):
    cart = get_cart(request, create=True)
    context = checkout_service.build_context(request, cart)
    context["address_form"] = CheckoutAddressForm(initial=checkout_service.address_initial(request))
    context["coupon_input"] = ""
    return render(request, "orders/checkout_step1.html", context)


def _finalize_and_redirect(request, cart, customer):
    try:
        order = checkout_service.finalize_order(request, cart, customer)
    except checkout_service.CheckoutError as exc:
        return _dynamic_response(
            request, cart, toast_message=str(exc), toast_type="err",
            address_form=CheckoutAddressForm(initial=checkout_service.address_initial(request)),
        )
    except Exception:
        logger.exception("Unexpected error during checkout finalization")
        return _dynamic_response(
            request, cart,
            toast_message="در ثبت سفارش مشکلی رخ داد. اطلاعات و سبد خرید شما حفظ شده است. لطفاً دوباره تلاش کنید.",
            toast_type="err",
            address_form=CheckoutAddressForm(initial=checkout_service.address_initial(request)),
        )
    response = HttpResponse(status=200)
    response["HX-Redirect"] = reverse("orders:payment-start", args=[order.code])
    return response


@require_POST
def checkout_pay(request):
    """اعتبارسنجی آدرس + ساخت سفارش از سبد + هدایت به شروع پرداخت.

    کاربر مهمان هرگز به مودال ورود هدایت نمی‌شود:
    - اگر شماره‌ی موبایلِ آدرس حساب نداشته باشد، حساب خودکار ساخته و وارد
      می‌شود (پیامک خوش‌آمد با امکان ورود بعدی از طریق کد یکبار مصرف).
    - اگر شماره‌ی موبایل از قبل حساب دارد، به‌جای ورود خودکار (که خطر امنیتی
      دارد) کد تأیید پیامک می‌شود و فقط پس از تأیید، سفارش روی همان حساب
      قبلی ثبت می‌شود.
    """
    cart = get_cart(request, create=True)
    form = CheckoutAddressForm(request.POST)
    if not form.is_valid():
        return _dynamic_response(
            request, cart,
            toast_message="لطفاً خطاهای فرم را برطرف کنید", toast_type="err",
            address_form=form,
        )

    checkout_service.save_address(request, form.cleaned_data)

    if request.user.is_authenticated and hasattr(request.user, "customer_profile"):
        request.session.pop(CHECKOUT_OTP_SESSION_KEY, None)
        return _finalize_and_redirect(request, cart, request.user.customer_profile)

    phone = form.cleaned_data["phone"]
    existing_customer = Customer.objects.filter(phone=phone).first()

    if existing_customer is None:
        request.session.pop(CHECKOUT_OTP_SESSION_KEY, None)
        customer = auth_service.create_account_for_guest(
            full_name=form.cleaned_data["receiver_name"], phone=phone,
            store=resolve_store_for_service(request),
        )
        auth_service.merge_guest_cart(request, customer)
        auth_login(request, customer.user)
        cart = get_cart(request, create=True)
        return _finalize_and_redirect(request, cart, customer)

    try:
        otp_service.request_otp(
            phone, store=resolve_store_for_service(request),
            ip_address=request.META.get("REMOTE_ADDR", "unknown"),
        )
    except otp_service.OtpRateLimitError as exc:
        return _dynamic_response(
            request, cart, toast_message=str(exc), toast_type="err",
            address_form=CheckoutAddressForm(initial=form.cleaned_data),
        )

    request.session[CHECKOUT_OTP_SESSION_KEY] = phone
    request.session.modified = True
    return render(request, "orders/partials/checkout_otp.html", {"phone": phone})


@require_POST
def checkout_verify_otp(request):
    """کد تأیید مرحله‌ی قبل را بررسی می‌کند؛ در صورت موفقیت سفارش روی حساب قبلیِ همین موبایل ثبت می‌شود."""
    phone = request.session.get(CHECKOUT_OTP_SESSION_KEY)
    if not phone:
        return redirect("orders:checkout-step1")

    code = request.POST.get("code", "")
    try:
        otp_service.verify_otp(phone, code)
    except otp_service.OtpInvalidError as exc:
        return render(request, "orders/partials/checkout_otp.html", {"phone": phone, "error": str(exc)})

    customer = get_object_or_404(Customer, phone=phone)
    # ادغام سبد مهمان باید پیش از auth_login انجام شود چون login() کلید session را عوض می‌کند؛
    # merge_guest_cart آیتم‌ها را به سبد خودِ customer منتقل و سبد مهمان را حذف می‌کند، پس سبد
    # باید *بعد* از این دو مرحله دوباره از روی کاربر واردشده خوانده شود، نه سبد مهمان قبلی.
    auth_service.merge_guest_cart(request, customer)
    auth_login(request, customer.user)
    request.session.pop(CHECKOUT_OTP_SESSION_KEY, None)

    cart = get_cart(request, create=True)
    return _finalize_and_redirect(request, cart, customer)


@require_POST
def checkout_resend_otp(request):
    phone = request.session.get(CHECKOUT_OTP_SESSION_KEY)
    if not phone:
        return redirect("orders:checkout-step1")
    try:
        otp_service.request_otp(
            phone, store=resolve_store_for_service(request),
            ip_address=request.META.get("REMOTE_ADDR", "unknown"),
        )
        message, message_type = "کد جدید پیامک شد", "ok"
    except otp_service.OtpRateLimitError as exc:
        message, message_type = str(exc), "err"
    response = render(request, "orders/partials/checkout_otp.html", {"phone": phone})
    response["HX-Trigger"] = json.dumps({"toast": {"message": message, "type": message_type}})
    return response


@require_POST
def checkout_otp_cancel(request):
    request.session.pop(CHECKOUT_OTP_SESSION_KEY, None)
    cart = get_cart(request, create=True)
    return _dynamic_response(request, cart)


def payment_start(request, code):
    """نقطه‌ی شروع پرداخت — هدایت به درگاه واقعی یا شبیه‌سازی.

    اگر درگاه واقعی فعال برای Store موجود باشد، به payment_initiate هدایت
    می‌شود. در غیر این صورت، اگر شبیه‌سازی فعال باشد، مستقیم به callback
    با نتیجه‌ی موفق هدایت می‌شود.
    """
    from apps.orders.models import PaymentGatewayConfig

    order = _get_own_order(request, code)
    if order.payment_status != Order.PaymentStatus.PENDING:
        return redirect("customers:account-order-detail", code=order.code)

    store = resolve_store_for_service(request)

    # Check if any real gateway config exists for this store
    has_real_config = PaymentGatewayConfig.objects.filter(
        store=store, is_active=True
    ).exists()

    if has_real_config:
        return redirect("orders:payment-initiate", code=order.code)

    if not settings.PAYMENTS_SIMULATION_ENABLED:
        raise Http404
    return redirect("orders:payment-callback", code=order.code, status="success")


def payment_callback(request, code, status):
    """نقطه‌ی بازگشت درگاه پرداخت — بعداً درگاه واقعی با امضای معتبر به همین آدرس برمی‌گردد.

    پردازش idempotent است: اگر سفارش قبلاً پردازش شده باشد، فقط به صفحه‌ی
    نتیجه هدایت می‌شود بدون ثبت تراکنش تکراری.

    ``status`` یک segment مسیر است — یعنی کاملاً از سمت کلاینت قابل‌کنترل —
    و تا وصل‌شدن درگاه واقعی (Zibal، PR بعدی) هیچ تأیید واقعی‌ای روی آن انجام
    نمی‌شود. به همین دلیل این ویو هم دقیقاً مثل ``payment_start`` پشت
    ``settings.PAYMENTS_SIMULATION_ENABLED`` است — در یک استقرار واقعی
    (``DJANGO_DEBUG=False``) کاملاً غیرقابل‌دسترس می‌ماند، نه فقط «مستندشده
    به‌عنوان placeholder».
    """
    if not settings.PAYMENTS_SIMULATION_ENABLED:
        raise Http404
    order = _get_own_order(request, code)
    if order.payment_status == Order.PaymentStatus.PENDING:
        simulate_payment(order, status == "success", store=resolve_store_for_service(request))
    return redirect("orders:payment-result", code=order.code)


def payment_result(request, code):
    order = _get_own_order(
        request, code,
        queryset=Order.objects.select_related("shipping_method", "payment_gateway").prefetch_related(
            "items", "transactions"
        ),
    )
    return render(request, "orders/payment_result.html", {"order": order})


@require_POST
def checkout_item_update(request, item_id):
    cart = get_cart(request, create=True)
    item = get_object_or_404(CartItem, pk=item_id, cart=cart)

    try:
        quantity = int(request.POST.get("quantity", 1))
    except (TypeError, ValueError):
        quantity = 1
    quantity = max(1, quantity)

    # موجودیِ مرجع باید همانِ تنوعِ انتخاب‌شده باشد، نه کالای مادر — پیش از
    # این اصلاح، این ویو همیشه ``item.product.stock`` را بررسی می‌کرد، حتی
    # برای اقلامِ دارای تنوع (ADR-31: کالای دارای تنوع می‌تواند
    # Product.stock صفر و ProductVariant.stock مثبت داشته باشد یا برعکس).
    # همچنین، وقتی موجودی صفر بود، شرطِ قبلی کِلَمپ‌کردن را کاملاً رد
    # می‌کرد (نه این‌که به صفر/حذف برساند) — یعنی مشتری می‌توانست در صفحه‌ی
    # تسویه‌حساب تعدادِ دلخواهی از یک قلمِ کاملاً ناموجود را نگه دارد.
    if item.variant_id:
        item.variant.refresh_from_db()
        available_stock = item.variant.stock
    else:
        item.product.refresh_from_db()
        available_stock = item.product.stock

    if available_stock <= 0:
        item.delete()
        return _dynamic_response(
            request, cart, toast_message="این کالا دیگر موجود نیست و از سبد حذف شد", toast_type="err",
        )

    quantity = min(quantity, available_stock)

    item.quantity = quantity
    item.save(update_fields=["quantity", "updated_at"])
    return _dynamic_response(request, cart)


@require_POST
def checkout_item_remove(request, item_id):
    cart = get_cart(request, create=True)
    item = get_object_or_404(CartItem, pk=item_id, cart=cart)
    item.delete()
    return _dynamic_response(request, cart, toast_message="کالا از سبد حذف شد", toast_type="info")


@require_POST
def checkout_set_shipping(request, method_id):
    cart = get_cart(request, create=True)
    checkout_service.set_shipping_method(request, method_id)
    return _dynamic_response(request, cart)


@require_POST
def checkout_set_payment(request, gateway_id):
    cart = get_cart(request, create=True)
    checkout_service.set_payment_gateway(request, gateway_id)
    return _dynamic_response(request, cart)


@require_POST
def checkout_apply_coupon(request):
    cart = get_cart(request, create=True)
    code = request.POST.get("code", "")
    ok, message = checkout_service.apply_coupon(request, cart, code)
    return _dynamic_response(
        request, cart, toast_message=message, toast_type="ok" if ok else "err",
        coupon_input="" if ok else code,
        coupon_error="" if ok else message,
    )


@require_POST
def checkout_remove_coupon(request):
    cart = get_cart(request, create=True)
    checkout_service.remove_coupon(request)
    return _dynamic_response(request, cart, toast_message="کد تخفیف حذف شد", toast_type="info")



# ===========================================================================
# Real payment gateway views (PR1)
# ===========================================================================


def payment_initiate(request, code):
    """Initiate real payment for an order.

    Replaces payment_start for stores with real gateway configuration.
    If no real gateway config exists, falls back to simulation (if enabled).

    Flow:
    1. Validate order ownership and payment eligibility
    2. Resolve gateway config for the order
    3. Initiate payment via gateway_payment_service
    4. Redirect to gateway (online) or order result (COD)
    """
    from apps.orders.models import PaymentAttempt, PaymentGatewayConfig
    from apps.orders.services.gateway_payment_service import (
        PaymentAlreadyPaidError,
        PaymentConfigError,
        PaymentInitiationError,
        initiate_payment,
    )
    from apps.orders.gateways import get_adapter

    order = _get_own_order(request, code)
    store = resolve_store_for_service(request)

    # Already paid — go to result
    if order.payment_status == Order.PaymentStatus.PAID:
        return redirect("orders:payment-result", code=order.code)

    # Find active gateway config for this order's gateway code
    # Try to match by slug from the legacy PaymentGateway on the order
    gateway_config = None
    if order.payment_gateway:
        gateway_config = PaymentGatewayConfig.objects.filter(
            store=store,
            gateway_code=order.payment_gateway.slug,
            is_active=True,
        ).first()

    # If no matching config, try any active online config for this store
    if gateway_config is None:
        gateway_config = PaymentGatewayConfig.objects.filter(
            store=store,
            is_active=True,
        ).exclude(gateway_code="cod").first()

    # Still nothing — fall back to simulation if enabled
    if gateway_config is None:
        if settings.PAYMENTS_SIMULATION_ENABLED:
            return redirect("orders:payment-start", code=order.code)
        return render(request, "orders/payment_result.html", {
            "order": order,
            "error": "هیچ درگاه پرداخت فعالی پیکربندی نشده است",
        })

    # Generate idempotency key — uses a server-side nonce to avoid races.
    # The gateway_payment_service checks this key BEFORE creating a new attempt,
    # so concurrent requests with the same key return the existing attempt.
    import secrets as _secrets
    idem_key = f"pay-{order.code}-{gateway_config.pk}-{_secrets.token_hex(8)}"

    # Initiate payment — attempt is created FIRST, then we build the callback URL
    # using the attempt's public_id. For online gateways the callback_url passed here
    # is a placeholder; the real Zibal callback URL is built below once we have the
    # attempt's public_id. The adapter stores the trackId internally and Zibal sends
    # the callback to the URL we registered. We MUST pass the final URL to the adapter.
    #
    # Strategy: create the attempt first (initiate_payment handles creation and gateway
    # request in two phases). We pass a preliminary callback_url and then, critically,
    # the adapter builds the redirect URL from the trackId — which is what the customer
    # follows. The callback_url registered with Zibal needs the attempt's public_id.
    #
    # Fix: We need a two-step approach or a predictable URL. Since the public_id is
    # generated at creation time (before the gateway request), we can pre-generate it.
    # But initiate_payment creates the attempt internally. Instead, we use a general
    # callback URL pattern that includes the trackId (Zibal sends it back as a param).
    # However, our current URL pattern uses attempt_id in the path.
    #
    # Correct fix: Build the callback URL using a placeholder, then after initiate_payment
    # returns the attempt, we know the public_id. But the callback_url was ALREADY sent
    # to Zibal. So we need to pass the correct URL to the service BEFORE calling Zibal.
    #
    # The cleanest solution: pass the callback base URL and let the service construct
    # the final URL with the attempt's public_id. But that requires refactoring the
    # service interface. Simpler: pre-generate the public_id before calling the service.
    pre_public_id = _secrets.token_hex(16)
    callback_url = request.build_absolute_uri(
        reverse("orders:gateway-callback", args=[pre_public_id])
    )

    try:
        attempt = initiate_payment(
            order=order,
            gateway_config=gateway_config,
            callback_url=callback_url,
            store=store,
            idempotency_key=idem_key,
            pre_public_id=pre_public_id,
        )
    except PaymentAlreadyPaidError:
        return redirect("orders:payment-result", code=order.code)
    except (PaymentConfigError, PaymentInitiationError) as exc:
        logger.warning("Payment initiation failed for order %s: %s", order.code, exc)
        return render(request, "orders/payment_result.html", {
            "order": order,
            "error": str(exc),
        })

    # For online gateways, redirect to gateway payment page
    if gateway_config.is_online:
        adapter = get_adapter(gateway_config.gateway_code)
        redirect_url = adapter.build_redirect_url(
            attempt.gateway_track_id,
            sandbox=gateway_config.is_sandbox,
        )
        return redirect(redirect_url)

    # COD — go straight to result
    return redirect("orders:payment-result", code=order.code)


def gateway_callback(request, attempt_id):
    """Public callback endpoint for payment gateways.

    This view:
    - Does NOT require authentication (gateway redirects the customer here)
    - Accepts GET only (Zibal redirects with query params)
    - Processes the callback server-to-server verification
    - Redirects to payment result page

    Security:
    - Never trusts callback params alone for payment confirmation
    - Always verifies server-to-server with gateway
    - Idempotent — duplicate callbacks are safe
    - Does not expose sensitive information in the result page
    """
    if request.method != "GET":
        from django.http import HttpResponseNotAllowed
        return HttpResponseNotAllowed(["GET"])

    from apps.orders.models import PaymentAttempt
    from apps.orders.services.gateway_payment_service import (
        PaymentVerificationFailed,
        process_callback_and_verify,
    )

    store = resolve_store_for_service(request)

    # Find the attempt (no auth required — public callback)
    attempt = PaymentAttempt.objects.select_related("order").filter(
        public_id=attempt_id,
        store=store,
    ).first()

    if attempt is None:
        raise Http404

    order = attempt.order

    # Collect callback data from query params
    callback_data = dict(request.GET.items())

    try:
        attempt = process_callback_and_verify(
            attempt_public_id=attempt_id,
            callback_data=callback_data,
            store=store,
        )
    except PaymentVerificationFailed as exc:
        logger.info("Payment verification failed for attempt %s: %s", attempt_id, exc)
        # Don't expose error details to the customer — redirect to result
        pass

    return redirect("orders:payment-result", code=order.code)
