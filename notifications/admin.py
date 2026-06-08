from django.contrib import admin

from .models import AbonnementNewsletter


@admin.register(AbonnementNewsletter)
class AbonnementNewsletterAdmin(admin.ModelAdmin):
    list_display = ("email", "actif", "cree_le")
    list_filter = ("actif",)
    search_fields = ("email",)
