from django.urls import path

from apps.chat_integration import views as chat_views

from . import platform_admin_views as views
from . import platform_admin_photo_views as photo_views

app_name = "portal_platform_admin"

urlpatterns = [
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
    # --- گفتگوی آنلاین (RastiChat) ---
    path("stores/<uuid:store_public_id>/chat/enable/", chat_views.platform_store_chat_enable, name="store-chat-enable"),
    path("stores/<uuid:store_public_id>/chat/disable/", chat_views.platform_store_chat_disable, name="store-chat-disable"),
    path("stores/<uuid:store_public_id>/chat/message/", chat_views.platform_store_chat_message, name="store-chat-message"),
    path("chat/inbox/", chat_views.platform_chat_inbox, name="chat-inbox"),

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

    # --- پلن‌های اشتراک ---
    path("plans/", views.plans, name="plans"),
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
