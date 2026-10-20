from django.contrib import admin

from .models import BlogPost


@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
    list_display = ("title", "store", "category_label", "published_at")
    list_filter = ("store", "category_label")
    search_fields = ("title", "excerpt", "body")
    prepopulated_fields = {"slug": ("title",)}
