# cart — Code Map

```
domain_id: D5
code_baseline: 5883a140
```

```
apps/cart/
├── models.py               3 models (Cart[+checkout_token], CartItem[server unit_price], Coupon[store-owned])
├── services/               cart_service, pricing, coupon_service, gift_wrap_service, cart_preview
├── urls.py                 cart add/update/remove
├── views.py
├── context_processors.py   cart_badge
├── static/ + templates/
├── migrations/
└── tests/                  test_cart_service, test_pricing, test_cart_security, test_gift_wrap

# Cross-domain writers into cart (M9):
apps/orders/services/order_service.py     reprice CartItem; Coupon.used_count += 1
apps/orders/services/checkout_service.py  cart.items.all().delete()
apps/orders/views.py                      checkout_item_update/remove (L2)
apps/customers/services/auth_service.py   merge_guest_cart
```

## Where to look
| Concern | File |
|---|---|
| Add/reprice cart | `services/cart_service.py` |
| Totals/coupons | `services/pricing.py`, `services/coupon_service.py` |
| Gift wrap | `services/gift_wrap_service.py` |
| Checkout idempotency token | `models.py` (Cart.checkout_token) |
| Cross-domain writers | orders + customers (see above) |
