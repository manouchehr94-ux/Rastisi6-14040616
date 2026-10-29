from django.urls import path

from . import views

app_name = "customers"

urlpatterns = [
    path("", views.account_home, name="account"),
    path("login/", views.login_view, name="login"),
    path("signup/", views.signup_view, name="signup"),
    path("otp/request/", views.otp_request_view, name="otp-request"),
    path("otp/login/", views.otp_login_view, name="otp-login"),
    path("otp/reset/", views.otp_reset_view, name="otp-reset"),
    path("logout/", views.logout_view, name="logout"),
    path("profile/", views.account_profile_update, name="account-profile-update"),
    path("security/password/", views.account_password_change, name="account-password-change"),
    path("security/password/code/", views.account_password_code_request, name="account-password-code"),
    path("security/password/set/", views.account_password_set, name="account-password-set"),
    path("addresses/add/", views.address_add, name="address-add"),
    path("addresses/<int:address_id>/delete/", views.address_delete, name="address-delete"),
    path("addresses/<int:address_id>/default/", views.address_set_default, name="address-set-default"),
    path("orders/<str:code>/", views.account_order_detail, name="account-order-detail"),
    path("wishlist/", views.wishlist_list, name="wishlist"),
    path("wishlist/<uslug:slug>/toggle/", views.wishlist_toggle, name="wishlist-toggle"),
]
