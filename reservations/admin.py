from django.contrib import admin

from .models import Paiement, Reservation


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ("utilisateur", "etablissement", "date_prevue", "mode_paiement", "statut")
    list_filter = ("statut", "mode_paiement")
    search_fields = ("utilisateur__username", "etablissement__nom")


@admin.register(Paiement)
class PaiementAdmin(admin.ModelAdmin):
    list_display = (
        "reservation", "montant", "operateur", "statut",
        "confirme_par_client", "confirme_par_etablissement",
    )
    list_filter = ("statut", "operateur")
    actions = ["liberer_les_fonds_confirmes"]

    @admin.action(description="Libérer les fonds pour les paiements doublement confirmés")
    def liberer_les_fonds_confirmes(self, request, queryset):
        for paiement in queryset:
            paiement.liberer_si_confirme()
