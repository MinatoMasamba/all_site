from django.contrib import admin
from django.utils import timezone

from .models import AbonnementNewsletter, Annonce
from .services import diffuser_annonce


@admin.register(AbonnementNewsletter)
class AbonnementNewsletterAdmin(admin.ModelAdmin):
    list_display = ("email", "numero_whatsapp", "actif", "cree_le")
    list_filter = ("actif",)
    search_fields = ("email", "numero_whatsapp")


@admin.register(Annonce)
class AnnonceAdmin(admin.ModelAdmin):
    list_display = (
        "titre", "etablissement", "creee_par", "cree_le",
        "envoyee_le", "nombre_emails_envoyes", "nombre_whatsapp_envoyes",
    )
    list_filter = ("envoyee_le",)
    search_fields = ("titre", "message")
    actions = ["diffuser_les_annonces_selectionnees"]

    @admin.action(description="Diffuser par email et WhatsApp les annonces sélectionnées non encore envoyées")
    def diffuser_les_annonces_selectionnees(self, request, queryset):
        for annonce in queryset.filter(envoyee_le__isnull=True):
            nb_emails, nb_whatsapp = diffuser_annonce(annonce)
            annonce.envoyee_le = timezone.now()
            annonce.nombre_emails_envoyes = nb_emails
            annonce.nombre_whatsapp_envoyes = nb_whatsapp
            annonce.save(update_fields=["envoyee_le", "nombre_emails_envoyes", "nombre_whatsapp_envoyes"])
