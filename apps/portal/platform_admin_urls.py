from django.urls import path

from apps.notifications.inbox_views import VIEWS_PLAT, url_patterns as _inbox_patterns
from . import platform_admin_views as views
from . import platform_admin_features as feature_views
from . import platform_admin_photo_views as photo_views
from . import platform_admin_trial as trial_views
from . import platform_admin_site_views as site_views
from . import notification_admin_views as notif_views
from . import platform_admin_coupon_views as coupon_views

app_name = "portal_platform_admin"

urlpatterns = [
    *_inbox_patterns(VIEWS_PLAT),     # صندوقِ اعلانِ مدیرانِ پلتفرم (همان پیاده‌سازیِ مشترک)
    path("", views.home, name="home"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),

    # --- فروشگاه‌ها ---
    path("stores/", views.stores, name="stores"),
    path("stores/<uuid:store_public_id>/", views.store_detail, name="store-detail"),
    path("stores/<uuid:store_public_id>/suspend/", views.store_suspend, name="store-suspend"),
    path("stores/<uuid:store_public_id>/activate/", views.store_activate, name="store-activate"),
    path("stores/<uuid:store_public_id>/support-login/", views.store_support_login, name="store-support-login"),
    path("stores/<uuid:store_public_id>/extend-trial/", views.store_extend_trial, name="store-extend-trial"),
    path("stores/<uuid:store_public_id>/set-trial-end/", views.store_set_trial_end, name="store-set-trial-end"),
    path("stores/<uuid:store_public_id>/end-trial-now/", views.store_end_trial_now, name="store-end-trial-now"),
    path("stores/<uuid:store_public_id>/change-plan/", views.store_change_plan, name="store-change-plan"),
    path("stores/<uuid:store_public_id>/extend-subscription/", views.store_extend_subscription, name="store-extend-subscription"),
    path("stores/<uuid:store_public_id>/add-note/", views.store_add_note, name="store-add-note"),

    # --- کاربران ---
    path("users/", views.users, name="users"),
    path("users/<int:user_id>/", views.user_detail, name="user-detail"),
    path("users/<int:user_id>/activate/", views.user_activate, name="user-activate"),
    path("users/<int:user_id>/suspend/", views.user_suspend, name="user-suspend"),
    path("users/<int:user_id>/add-note/", views.user_add_note, name="user-add-note"),

    # --- عکس‌های سایت عمومی (فقط مدیر پلتفرم) ---
    path("public-photos/", photo_views.public_photos, name="public-photos"),
    path("public-photos/<slug:slot>/", photo_views.public_photo_edit, name="public-photo-edit"),
    path("public-photos/<slug:slot>/reset/", photo_views.public_photo_reset, name="public-photo-reset"),

    # --- متن‌ها، رنگ‌ها و فونت‌های سایت عمومی (فقط مدیر پلتفرم) ---
    path("public-site/", site_views.public_site_home, name="public-site"),
    path("public-site/switch/", site_views.public_site_switch, name="public-site-switch"),
    path("public-site/<slug:slug>/", site_views.public_site_edit, name="public-site-edit"),
    path("public-site/<slug:slug>/reset/", site_views.public_site_reset, name="public-site-reset"),

    # --- پلن‌های اشتراک ---
    path("trial/", trial_views.trial_settings, name="trial-settings"),
    path("plans/", views.plans, name="plans"),
    path("plans/content/", views.pricing_content, name="pricing-content"),
    path("plans/assignments/", feature_views.assignment_matrix, name="assignment-matrix"),
    path("plans/<int:plan_id>/migrate/", feature_views.plan_migration, name="plan-migration"),
    path("features/", feature_views.features, name="features"),
    path("features/add/", feature_views.feature_form, name="feature-add"),
    path("features/<int:feature_id>/edit/", feature_views.feature_form, name="feature-edit"),
    path("plans/add/", views.plan_form, name="plan-add"),
    path("plans/<int:plan_id>/edit/", views.plan_form, name="plan-edit"),
    path("plans/<int:plan_id>/archive/", views.plan_archive, name="plan-archive"),
    path("plans/<int:plan_id>/versions/<int:version_id>/publish/", views.plan_version_publish, name="plan-version-publish"),

    # --- اشتراک فروشگاه‌ها ---
    path("subscriptions/", views.subscriptions, name="subscriptions"),
    path("subscriptions/<int:subscription_id>/cancel/", views.subscription_cancel, name="subscription-cancel"),
    path("subscriptions/<int:subscription_id>/suspend/", views.subscription_suspend, name="subscription-suspend"),
    path("subscriptions/<int:subscription_id>/resume/", views.subscription_resume, name="subscription-resume"),

    # --- پرداخت‌ها و فاکتورها ---
    path("payments/", views.payments, name="payments"),
    path("payments/invoice/<int:invoice_id>/", views.payment_invoice_detail, name="payment-invoice-detail"),
    path("payments/manual/", views.payment_manual_add, name="payment-manual-add"),
    path("payments/zibal/", views.billing_zibal_settings, name="billing-zibal-settings"),
    path("payments/gateways/", views.payment_gateways, name="payment-gateways"),
    path("payments/transactions/", views.payment_transactions, name="payment-transactions"),
    path("payments/reconciliation/", views.payment_reconciliation, name="payment-reconciliation"),
    path("payments/verify/<str:kind>/<int:attempt_id>/", views.payment_verify_now, name="payment-verify-now"),
    path("payments/duplicates/<str:kind>/<int:attempt_id>/<str:action>/", views.payment_duplicate_action, name="payment-duplicate-action"),
    path("payments/card-claims/", views.manual_claims, name="manual-claims"),
    path("payments/card-claims/<int:claim_id>/", views.manual_claim_detail, name="manual-claim-detail"),
    path("payments/card-claims/<int:claim_id>/receipt/", views.manual_claim_receipt, name="manual-claim-receipt"),
    path("payments/card-claims/<int:claim_id>/<str:action>/", views.manual_claim_action, name="manual-claim-action"),
    path("payments/invoice/<int:invoice_id>/refund/", views.payment_invoice_refund, name="payment-invoice-refund"),
    path("payments/refund/<int:refund_id>/complete/", views.payment_refund_complete, name="payment-refund-complete"),
    path("payments/sms-purchases/", views.sms_purchases, name="sms-purchases"),
    path("payments/sms-purchases/<int:purchase_id>/<str:action>/", views.sms_purchase_action, name="sms-purchase-action"),

    # --- کوپن و کمپینِ پلتفرم ---
    path("coupons/", coupon_views.coupons, name="coupons"),
    path("coupons/add/", coupon_views.coupon_form, name="coupon-add"),
    path("coupons/<int:coupon_id>/", coupon_views.coupon_detail, name="coupon-detail"),
    path("coupons/<int:coupon_id>/edit/", coupon_views.coupon_form, name="coupon-edit"),
    path("coupons/<int:coupon_id>/duplicate/", coupon_views.coupon_duplicate, name="coupon-duplicate"),
    path("coupons/<int:coupon_id>/<str:action>/", coupon_views.coupon_status, name="coupon-status"),

    # --- پیامک ---
    path("sms/settings/", views.sms_settings, name="sms-settings"),  # legacy alias
    path("sms/providers/", views.sms_providers, name="sms-providers"),
    path("sms/templates/", views.sms_templates, name="sms-templates"),
    path("sms/templates/<str:event_key>/", views.sms_template_edit, name="sms-template-edit"),
    path("sms/messages/", views.sms_messages, name="sms-messages"),
    path("sms/packages/", views.sms_packages, name="sms-packages"),
    path("sms/packages/add/", views.sms_package_form, name="sms-package-add"),
    path("sms/packages/<int:package_id>/edit/", views.sms_package_form, name="sms-package-edit"),
    path("sms/packages/<int:package_id>/archive/", views.sms_package_archive, name="sms-package-archive"),
    path("sms/credits/", views.sms_credits, name="sms-credits"),
    path("sms/credits/<uuid:store_public_id>/adjust/", views.sms_credit_adjust, name="sms-credit-adjust"),
    path("sms/logs/", views.sms_logs, name="sms-logs"),

    # --- اعلان‌ها (SMS + ایمیل)
    path("notifications/", notif_views.notification_catalog, name="notification-catalog"),
    path("notifications/senders/", notif_views.notification_senders, name="notification-senders"),
    path("notifications/senders/<int:pk>/toggle/", notif_views.notification_sender_toggle, name="notification-sender-toggle"),
    path("notifications/delivery/", notif_views.notification_delivery, name="notification-delivery"),
    path("notifications/audit/", notif_views.notification_audit, name="notification-audit"),
    path("notifications/<str:event_key>/", notif_views.notification_platform_template, name="notification-platform-template"),
    path("notifications/<str:event_key>/preview/", notif_views.notification_platform_template_preview, name="notification-platform-template-preview"),
    path("notifications/<str:event_key>/test/", notif_views.notification_platform_template_test, name="notification-platform-template-test"),

    # --- صنف‌ها و قالب‌ها ---
    path("industries/", views.industries, name="industries"),
    path("industries/<int:template_id>/", views.industry_detail, name="industry-detail"),

    # --- دامنه‌ها ---
    path("domains/", views.domains, name="domains"),
    path("domains/<int:domain_id>/check/", views.domain_check, name="domain-check"),
    path("domains/<int:domain_id>/set-primary/", views.domain_set_primary, name="domain-set-primary"),

    # --- رخدادها و تنظیمات ---
    path("audit-log/", views.audit_log, name="audit-log"),
    path("configuration/", views.configuration, name="configuration"),
]
