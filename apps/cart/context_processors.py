from django.db.models import Sum

from apps.cart.models import Cart
from apps.customers.models import Wishlist


def cart_badge(request):
    """شمارنده‌ی زنده‌ی سبد و علاقه‌مندی — بدون ساخت سبد جدید، فقط برای نمایش."""
    cart_count = 0
    wishlist_count = 0

    if request.user.is_authenticated and hasattr(request.user, "customer_profile"):
        customer = request.user.customer_profile
        cart = Cart.objects.filter(customer=customer).first()
        store = getattr(request, "store", None)
        if store is not None:
            wishlist_count = Wishlist.objects.filter(customer=customer, product__store=store).count()
    else:
        session_key = request.session.session_key
        cart = Cart.objects.filter(session_key=session_key, customer=None).first() if session_key else None

    if cart is not None:
        cart_count = cart.items.aggregate(total=Sum("quantity"))["total"] or 0

    # Phase 7: پیش‌تر این پیش‌فرض بر اساسِ Familyِ فعال تعیین می‌شد
    # (heritage_premium=mini_cart)؛ با بازنشستگیِ سیستمِ Family، پیش‌فرضِ
    # سراسری همیشه count_link است. حالتِ mini_cart همچنان از طریقِ
    # پارامترِ ``mode`` در ``cart_preview_partial`` در دسترس می‌ماند
    # (نگاه کنید به ``apps/cart/views.py::cart_preview_partial``).
    cart_preview_mode = "count_link"

    result = {"cart_count": cart_count, "wishlist_count": wishlist_count, "cart_preview_mode": cart_preview_mode}

    # در حالتِ mini_cart، اطلاعاتِ اقلام هم ارائه شود
    if cart_preview_mode == "mini_cart" and cart is not None and cart_count > 0:
        from apps.cart.services.cart_preview import get_cart_preview_data

        preview_data = get_cart_preview_data(request, mode="mini_cart")
        result.update(preview_data)
    else:
        result["cart_items_preview"] = []
        result["cart_total"] = 0
        result["cart_is_empty"] = cart_count == 0

    return result
