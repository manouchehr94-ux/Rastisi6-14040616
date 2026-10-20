"""Storefront journal routes using the canonical universal storefront shell."""

from django.urls import path

from . import views

app_name = "blog"

urlpatterns = [
    path("", views.journal_index, name="index"),
    path("<str:slug>/", views.journal_detail, name="detail"),
]
