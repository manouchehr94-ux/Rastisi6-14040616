# orders — Code Map

```
domain_id: D6
code_baseline: 5883a140
```

```
apps/orders/
├── models.py                     16 model classes (Order, OrderItem, OrderStatusHistory,
│                                 Transaction, PaymentAttempt, PaymentGatewayConfig, PaymentGateway,
│                                 Refund, RefundItem, ReturnRequest, ReturnItem, ShippingZone,
│                                 ShippingMethod, ShippingRateRule, TaxClass, TaxRate)
│                                 · Order.payment_status field ~:387
│                                 · ReturnRequest.ALLOWED_TRANSITIONS ~:1047
├── views.py                      checkout + payment views (thin controllers)
│                                 · payment_start / payment_callback (sim) / payment_initiate / gateway_callback
│                                 · checkout_item_update/remove (cross-domain cart writes, L2)
├── urls.py                       routes under checkout/
├── forms.py                      checkout forms
├── encryption.py                 Fernet credential encryption (reused by stores)
├── services/
│   ├── order_service.py          ALLOWED_TRANSITIONS :45 (FINAL_STATUSES :54); change_order_status guard :550;
│   │                             create_order_from_cart
│   ├── payment_service.py        simulate_payment (LEGACY) — payment_status writes :86-98; SMS :91-100
│   ├── gateway_payment_service.py process_callback_and_verify — payment_status update :313-316; SMS :353-357
│   ├── refund_service.py         execute_order_refund — payment_status→REFUNDED :234
│   ├── return_service.py         _transition :84-96; create/review/approve/reject/mark_received/inspect/complete
│   ├── checkout_service.py       finalize_order (deletes cart items)
│   ├── shipping_service.py
│   ├── tax_service.py
│   └── best_seller_service.py
├── gateways/
│   ├── base.py                   abstract PaymentGatewayAdapter (create/build_redirect/verify)
│   ├── registry.py               get_adapter(code); _load_zibal/_load_cod; GATEWAY_CHOICES
│   ├── zibal.py                  ZibalAdapter (online)
│   └── cod.py                    CodAdapter (offline)
├── management/commands/
│   └── seed_default_shipping_methods.py
├── migrations/
└── tests/                        test_order_service / test_payment_service /
                                  test_gateway_payment_service / test_refund_service(+_tax) /
                                  test_return_service / test_checkout_* / test_cat002_checkout_valuation
```

## Where to look for a given concern
| Concern | File |
|---|---|
| Order lifecycle / status guard | `services/order_service.py` |
| Real payment | `services/gateway_payment_service.py` + `gateways/` |
| Simulated payment (legacy) | `services/payment_service.py` |
| `payment_status` writers (all 3) | order_service callers + payment_service + refund_service |
| Refunds | `services/refund_service.py` |
| Returns | `services/return_service.py` + `models.py` (ALLOWED_TRANSITIONS) |
| Gateway config / creds | `models.py` (PaymentGatewayConfig) + `encryption.py` |
| Cross-domain cart writes | `services/order_service.py`, `services/checkout_service.py`, `views.py` |
