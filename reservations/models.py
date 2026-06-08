from django.conf import settings
from django.db import models

from listings.models import Etablissement


class Reservation(models.Model):
    class ModePaiement(models.TextChoices):
        EN_LIGNE = "en_ligne", "Payer en ligne (Mobile Money)"
        SUR_PLACE = "sur_place", "Payer sur place"

    class Statut(models.TextChoices):
        EN_ATTENTE = "en_attente", "En attente de confirmation"
        CONFIRMEE = "confirmee", "Confirmée"
        TERMINEE = "terminee", "Terminée"
        ANNULEE = "annulee", "Annulée"

    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reservations"
    )
    etablissement = models.ForeignKey(
        Etablissement, on_delete=models.CASCADE, related_name="reservations"
    )
    date_prevue = models.DateTimeField()
    nombre_personnes = models.PositiveIntegerField(default=1)
    mode_paiement = models.CharField(max_length=20, choices=ModePaiement.choices)
    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.EN_ATTENTE)
    note = models.TextField(blank=True)

    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Réservation"
        verbose_name_plural = "Réservations"
        ordering = ["-cree_le"]

    def __str__(self):
        return f"{self.utilisateur} → {self.etablissement} ({self.date_prevue:%d/%m/%Y})"


class Paiement(models.Model):
    """
    Paiement Mobile Money séquestré : les fonds sont conservés par la
    plateforme jusqu'à ce que le client ET l'établissement confirment que
    le service a bien eu lieu. Ce n'est qu'à ce moment que l'argent est
    reversé à l'établissement.
    """

    class Statut(models.TextChoices):
        BLOQUE = "bloque", "Bloqué sur la plateforme"
        LIBERE = "libere", "Reversé à l'établissement"
        REMBOURSE = "rembourse", "Remboursé au client"

    class Operateur(models.TextChoices):
        MPESA = "mpesa", "M-Pesa"
        AIRTEL_MONEY = "airtel_money", "Airtel Money"
        ORANGE_MONEY = "orange_money", "Orange Money"

    reservation = models.OneToOneField(
        Reservation, on_delete=models.CASCADE, related_name="paiement"
    )
    montant = models.DecimalField(max_digits=10, decimal_places=2)
    operateur = models.CharField(max_length=20, choices=Operateur.choices)
    reference_transaction = models.CharField(max_length=100, blank=True)
    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.BLOQUE)

    confirme_par_client = models.BooleanField(
        default=False, verbose_name="Le client confirme être arrivé sur place"
    )
    confirme_par_etablissement = models.BooleanField(
        default=False, verbose_name="L'établissement confirme la présence du client"
    )

    cree_le = models.DateTimeField(auto_now_add=True)
    libere_le = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Paiement"
        verbose_name_plural = "Paiements"
        ordering = ["-cree_le"]

    def __str__(self):
        return f"Paiement {self.montant} USD pour {self.reservation}"

    @property
    def double_confirmation(self):
        return self.confirme_par_client and self.confirme_par_etablissement

    def liberer_si_confirme(self):
        """Libère les fonds vers l'établissement dès que les deux parties ont confirmé."""
        from django.utils import timezone

        if self.double_confirmation and self.statut == self.Statut.BLOQUE:
            self.statut = self.Statut.LIBERE
            self.libere_le = timezone.now()
            self.save(update_fields=["statut", "libere_le"])
        return self.statut
