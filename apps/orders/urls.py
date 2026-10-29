from django.urls import path

from . import views

app_name = "orders"

urlpatterns = [
    path("", views.checkout_step1, name="checkout-step1"),
    path("pay/", views.checkout_pay, name="checkout-pay"),
    path("pay/otp/verify/", views.checkout_verify_otp, name="checkout-otp-verify"),
    path("pay/otp/resend/", views.checkout_resend_otp, name="checkout-otp-resend"),
    path("pay/otp/cancel/", views.checkout_otp_cancel, name="checkout-otp-cancel"),
    path("items/<int:item_id>/update/", views.checkout_item_update, name="checkout-item-update"),
    path("items/<int:item_id>/remove/", views.checkout_item_remove, name="checkout-item-remove"),
    path("shipping/<int:method_id>/", views.checkout_set_shipping, name="checkout-set-shipping"),
    path("payment/<int:gateway_id>/", views.checkout_set_payment, name="checkout-set-payment"),
    path("coupon/apply/", views.checkout_apply_coupon, name="checkout-coupon-apply"),
    path("coupon/remove/", views.checkout_remove_coupon, name="checkout-coupon-remove"),
    path("order/<str:code>/start/", views.payment_start, name="payment-start"),
    path("order/<str:code>/callback/<str:status>/", views.payment_callback, name="payment-callback"),
    path("order/<str:code>/result/", views.payment_result, name="payment-result"),
    path("order/<str:code>/card-transfer/", views.card_transfer, name="card-transfer"),

    # --- Real payment gateway routes (PR1) ---
    path("order/<str:code>/initiate/", views.payment_initiate, name="payment-initiate"),
    path("gateway/callback/<str:attempt_id>/", views.gateway_callback, name="gateway-callback"),
]
