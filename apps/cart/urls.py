from django.urls import path

from . import views

app_name = "cart"

urlpatterns = [
    path("", views.cart_detail, name="detail"),
    path("add/<uslug:slug>/", views.cart_add, name="add"),
    path("items/<int:item_id>/update/", views.cart_item_update, name="item-update"),
    path("items/<int:item_id>/gift-wrap/", views.cart_item_gift_wrap, name="item-gift-wrap"),
    path("items/<int:item_id>/remove/", views.cart_item_remove, name="item-remove"),
    path("preview/", views.cart_preview_partial, name="preview"),
]
