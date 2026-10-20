from django.urls import path

from . import views

app_name = "catalog"

urlpatterns = [
    path("", views.home, name="home"),
    path("products/", views.product_list, name="product-list"),
    path("products/<uslug:slug>/", views.product_detail, name="product-detail"),
    path("products/<uslug:slug>/review/", views.product_review_create, name="product-review-create"),
    path("collections/", views.collection_index, name="collection-index"),
    path("collections/<uslug:slug>/", views.collection_detail, name="collection-detail"),
]
