from django.urls import path

from . import views

app_name = "chat_integration"

# Storefront (Host-resolved store): mounted at /chat/ in shop_core.urls.
urlpatterns = [
    path("identity/", views.customer_identity, name="identity"),
]
