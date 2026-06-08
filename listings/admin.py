from django.contrib import admin

from .models import Categorie, Commune, Etablissement, ImageEtablissement


class ImageEtablissementInline(admin.TabularInline):
    model = ImageEtablissement
    extra = 1


@admin.register(Etablissement)
class EtablissementAdmin(admin.ModelAdmin):
    list_display = ("nom", "categorie", "commune", "statut", "proprietaire", "enregistre_par")
    list_filter = ("statut", "categorie", "commune")
    search_fields = ("nom", "adresse", "description")
    prepopulated_fields = {"slug": ("nom",)}
    inlines = [ImageEtablissementInline]


@admin.register(Categorie)
class CategorieAdmin(admin.ModelAdmin):
    list_display = ("nom", "slug", "icone")
    prepopulated_fields = {"slug": ("nom",)}


@admin.register(Commune)
class CommuneAdmin(admin.ModelAdmin):
    list_display = ("nom",)
