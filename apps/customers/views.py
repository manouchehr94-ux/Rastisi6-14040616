import json

from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.catalog.services.product_publish_service import storefront_visible_products
from apps.core.services import session_service
from apps.orders.models import Order
from apps.sms.services import otp_service
from apps.stores.resolution import resolve_store_for_service, resolve_store_for_storefront

from .forms import AddressForm, LoginForm, OtpRequestForm, OtpVerifyForm, ProfileForm, SignupForm
from .models import Address, Customer, Wishlist
from .services import auth_service

_OTP_REMEMBER_SESSION_KEY = "customers_otp_remember_me"


def _can_use_wishlist(request):
    return request.user.is_authenticated and hasattr(request.user, "customer_profile")


def wishlist_list(request):
    # P5-W4A — converge onto the canonical universal storefront shell (see
    # storefront_context_service.build_universal_storefront_context's
    # shell_only contract). Local import: matches the existing
    # catalog/cart/home() call-site convention that avoids a module-level
    # dependency on apps.storefront_builder.
    from apps.storefront_builder.services.storefront_context_service import (
        build_universal_storefront_context,
    )

    store = resolve_store_for_storefront(request)
    can_view = _can_use_wishlist(request)
    products = []
    if can_view:
        # P5-W4A — scoped to the current Store (product__store=store), so a
        # single render only ever shows this Store's products, matching the
        # write path (wishlist_toggle) which was already Store-scoped. A
        # global Customer's wishlist may still hold rows for other Stores'
        # products (Wishlist/Customer have no store FK) — those simply don't
        # appear on THIS Store's render.
        items = (
            Wishlist.objects.filter(customer=request.user.customer_profile, product__store=store)
            .select_related("product", "product__brand")
            .prefetch_related("product__images")
            .order_by("-created_at")
        )
        products = [item.product for item in items]
    context = {"products": products, "can_view": can_view}
    context.update(
        build_universal_storefront_context(
            request, store, "wishlist", page_context=context, shell_only=True,
        )
    )
    return render(request, "customers/wishlist.html", context)


@require_POST
def wishlist_toggle(request, slug):
    store = resolve_store_for_service(request)
    product = get_object_or_404(storefront_visible_products(store), slug=slug)

    if not _can_use_wishlist(request):
        response = render(request, "customers/partials/wishlist_button.html", {"product": product})
        response["HX-Trigger"] = json.dumps({
            "toast": {"message": "برای افزودن به علاقه‌مندی‌ها ابتدا وارد حساب کاربری شوید", "type": "info"},
            "open-login": {},
        })
        return response

    customer = request.user.customer_profile
    existing = Wishlist.objects.filter(customer=customer, product=product).first()
    if existing:
        existing.delete()
        message = "از علاقه‌مندی‌ها حذف شد"
    else:
        Wishlist.objects.create(customer=customer, product=product)
        message = "به علاقه‌مندی‌ها اضافه شد ❤️"

    wishlisted_ids = set(Wishlist.objects.filter(customer=customer).values_list("product_id", flat=True))
    response = render(
        request, "customers/partials/wishlist_button.html",
        {"product": product, "wishlisted_product_ids": wishlisted_ids},
    )
    response["HX-Trigger"] = json.dumps({"toast": {"message": message, "type": "ok"}})
    return response


def _auth_forms_context(*, login_form=None, signup_form=None, active_tab="in"):
    return {
        "login_form": login_form or LoginForm(),
        "signup_form": signup_form or SignupForm(),
        "active_tab": active_tab,
        "otp_stage": "request",
        "otp_request_form": OtpRequestForm(),
    }


@require_POST
def login_view(request):
    form = LoginForm(request.POST)
    if form.is_valid():
        user = auth_service.authenticate_customer_by_identifier(
            request, identifier=form.cleaned_data["identifier"], password=form.cleaned_data["password"]
        )
        if user is not None:
            # ادغام سبد مهمان باید پیش از auth_login انجام شود چون login()
            # برای جلوگیری از session fixation، کلید session را عوض می‌کند.
            auth_service.merge_guest_cart(request, user.customer_profile)
            auth_login(request, user)
            session_service.apply_remember_me(request, form.cleaned_data.get("remember_me", False))
            response = render(request, "customers/partials/auth_forms.html", _auth_forms_context())
            response["HX-Refresh"] = "true"
            return response
        form.add_error(None, auth_service.GENERIC_LOGIN_ERROR)

    response = render(
        request, "customers/partials/auth_forms.html",
        _auth_forms_context(login_form=form, active_tab="in"),
    )
    response["HX-Trigger"] = json.dumps({"toast": {"message": "ورود ناموفق بود", "type": "err"}})
    return response


@require_POST
def signup_view(request):
    form = SignupForm(request.POST)
    if form.is_valid():
        try:
            customer = auth_service.signup(
                full_name=form.cleaned_data["full_name"],
                phone=form.cleaned_data["phone"],
                password=form.cleaned_data["password"],
                store=resolve_store_for_service(request),
            )
        except auth_service.AuthError as exc:
            form.add_error(None, str(exc))
        else:
            user = auth_service.authenticate_customer(
                request, phone=form.cleaned_data["phone"], password=form.cleaned_data["password"]
            )
            auth_service.merge_guest_cart(request, customer)
            auth_login(request, user)
            response = render(request, "customers/partials/auth_forms.html", _auth_forms_context())
            response["HX-Refresh"] = "true"
            return response

    response = render(
        request, "customers/partials/auth_forms.html",
        _auth_forms_context(signup_form=form, active_tab="up"),
    )
    response["HX-Trigger"] = json.dumps({"toast": {"message": "ثبت‌نام ناموفق بود", "type": "err"}})
    return response


def _otp_login_context(*, stage="request", phone="", error="", remember_me=False, request_form=None, verify_form=None):
    return {
        "otp_stage": stage,
        "phone": phone,
        "otp_error": error,
        "remember_me": remember_me,
        "otp_request_form": request_form or OtpRequestForm(),
        "otp_verify_form": verify_form or OtpVerifyForm(initial={"phone": phone, "remember_me": remember_me}),
    }


def otp_reset_view(request):
    """بازگشت به مرحله‌ی وارد کردن شماره — بدون ارسال کد جدید."""
    return render(request, "customers/partials/otp_login_body.html", _otp_login_context(stage="request"))


@require_POST
def otp_request_view(request):
    """گام اول ورود با کد: شماره را می‌گیرد، فقط برای حساب‌های موجود کد می‌فرستد."""
    form = OtpRequestForm(request.POST)
    if form.is_valid():
        phone = form.cleaned_data["phone"]
        remember_me = form.cleaned_data.get("remember_me", False)
        if not Customer.objects.filter(phone=phone).exists():
            form.add_error("phone", "حسابی با این شماره موبایل یافت نشد")
        else:
            try:
                otp_service.request_otp(
                    phone, store=resolve_store_for_service(request),
                    ip_address=request.META.get("REMOTE_ADDR", "unknown"),
                )
            except otp_service.OtpRateLimitError as exc:
                form.add_error(None, str(exc))
            else:
                return render(
                    request, "customers/partials/otp_login_body.html",
                    _otp_login_context(stage="verify", phone=phone, remember_me=remember_me),
                )

    return render(
        request, "customers/partials/otp_login_body.html",
        _otp_login_context(stage="request", request_form=form),
    )


@require_POST
def otp_login_view(request):
    """گام دوم ورود با کد: تأیید کد و ورود واقعی — کنار ورود با رمز، نه جایگزین آن."""
    form = OtpVerifyForm(request.POST)
    if not form.is_valid():
        return render(
            request, "customers/partials/otp_login_body.html",
            _otp_login_context(stage="verify", phone=request.POST.get("phone", ""), verify_form=form),
        )

    phone = form.cleaned_data["phone"]
    remember_me = form.cleaned_data.get("remember_me", False)
    try:
        otp_service.verify_otp(phone, form.cleaned_data["code"])
    except otp_service.OtpInvalidError as exc:
        return render(
            request, "customers/partials/otp_login_body.html",
            _otp_login_context(stage="verify", phone=phone, remember_me=remember_me, error=str(exc)),
        )

    customer = Customer.objects.filter(phone=phone).select_related("user").first()
    if customer is None:
        return render(
            request, "customers/partials/otp_login_body.html",
            _otp_login_context(stage="request", error="حسابی با این شماره موبایل یافت نشد"),
        )

    # ادغام سبد مهمان باید پیش از auth_login انجام شود چون login() کلید session را عوض می‌کند.
    auth_service.merge_guest_cart(request, customer)
    auth_login(request, customer.user)
    session_service.apply_remember_me(request, remember_me)
    response = render(request, "customers/partials/auth_forms.html", _auth_forms_context())
    response["HX-Refresh"] = "true"
    return response


@require_POST
def logout_view(request):
    auth_logout(request)
    return redirect("catalog:home")


def _account_context(request, *, profile_form=None, address_form=None):
    customer = request.user.customer_profile
    return {
        "can_view": True,
        "customer": customer,
        "profile_form": profile_form or ProfileForm(initial={
            "full_name": customer.full_name, "email": customer.email, "city": customer.city,
        }),
        "address_form": address_form or AddressForm(),
        "orders": Order.objects.filter(customer=customer).select_related("shipping_method").order_by("-created_at"),
        "addresses": customer.addresses.all(),
    }


def account_home(request):
    if not _can_use_wishlist(request):
        return render(request, "customers/account.html", {"can_view": False})
    return render(request, "customers/account.html", _account_context(request))


@require_POST
def account_profile_update(request):
    customer = request.user.customer_profile
    form = ProfileForm(request.POST)
    if form.is_valid():
        customer.full_name = form.cleaned_data["full_name"]
        customer.email = form.cleaned_data["email"]
        customer.city = form.cleaned_data["city"]
        customer.save(update_fields=["full_name", "email", "city", "updated_at"])
        response = render(
            request, "customers/partials/account_profile.html",
            {"customer": customer, "profile_form": ProfileForm(initial=form.cleaned_data)},
        )
        response["HX-Trigger"] = json.dumps({"toast": {"message": "پروفایل به‌روزرسانی شد", "type": "ok"}})
        return response
    response = render(
        request, "customers/partials/account_profile.html", {"customer": customer, "profile_form": form}
    )
    response["HX-Trigger"] = json.dumps({"toast": {"message": "لطفاً خطاهای فرم را برطرف کنید", "type": "err"}})
    return response


@require_POST
def address_add(request):
    customer = request.user.customer_profile
    form = AddressForm(request.POST)
    if form.is_valid():
        is_first = not customer.addresses.exists()
        Address.objects.create(customer=customer, is_default=is_first, **form.cleaned_data)
        response = render(
            request, "customers/partials/account_addresses.html",
            {"addresses": customer.addresses.all(), "address_form": AddressForm()},
        )
        response["HX-Trigger"] = json.dumps({"toast": {"message": "آدرس جدید ثبت شد", "type": "ok"}})
        return response
    response = render(
        request, "customers/partials/account_addresses.html",
        {"addresses": customer.addresses.all(), "address_form": form},
    )
    response["HX-Trigger"] = json.dumps({"toast": {"message": "لطفاً خطاهای فرم را برطرف کنید", "type": "err"}})
    return response


@require_POST
def address_delete(request, address_id):
    customer = request.user.customer_profile
    address = get_object_or_404(Address, pk=address_id, customer=customer)
    was_default = address.is_default
    address.delete()
    if was_default:
        fallback = customer.addresses.first()
        if fallback:
            fallback.is_default = True
            fallback.save(update_fields=["is_default", "updated_at"])
    response = render(
        request, "customers/partials/account_addresses.html",
        {"addresses": customer.addresses.all(), "address_form": AddressForm()},
    )
    response["HX-Trigger"] = json.dumps({"toast": {"message": "آدرس حذف شد", "type": "info"}})
    return response


@require_POST
def address_set_default(request, address_id):
    customer = request.user.customer_profile
    address = get_object_or_404(Address, pk=address_id, customer=customer)
    customer.addresses.exclude(pk=address.pk).update(is_default=False)
    address.is_default = True
    address.save(update_fields=["is_default", "updated_at"])
    response = render(
        request, "customers/partials/account_addresses.html",
        {"addresses": customer.addresses.all(), "address_form": AddressForm()},
    )
    response["HX-Trigger"] = json.dumps({"toast": {"message": "آدرس پیش‌فرض تغییر کرد", "type": "ok"}})
    return response


def account_order_detail(request, code):
    if not _can_use_wishlist(request):
        return render(request, "customers/order_detail.html", {"can_view": False})
    order = get_object_or_404(
        Order.objects.select_related("shipping_method", "payment_gateway").prefetch_related(
            "items", "status_history", "transactions"
        ),
        code=code, customer=request.user.customer_profile,
    )
    return render(request, "customers/order_detail.html", {"can_view": True, "order": order})
