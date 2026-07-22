from django.conf import settings
from django.db import models


class AbonnementNewsletter(models.Model):
    """Permet à un visiteur (même non inscrit) de recevoir les offres et nouveautés."""

    email = models.EmailField(unique=True)
    numero_whatsapp = models.CharField(
        max_length=20,
        blank=True,
        help_text="Numéro au format international, ex: +243800000000 (optionnel)",
    )
    cree_le = models.DateTimeField(auto_now_add=True)
    actif = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Abonnement newsletter"
        verbose_name_plural = "Abonnements newsletter"
        ordering = ["-cree_le"]

    def __str__(self):
        return self.email


class Annonce(models.Model):
    """
    Une offre ou une nouveauté diffusée par email et WhatsApp à tous les
    abonnés actifs (visiteurs abonnés et utilisateurs inscrits qui ont
    activé les notifications).
    """

    titre = models.CharField(max_length=150)
    message = models.TextField()
    etablissement = models.ForeignKey(
        "listings.Etablissement",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="annonces",
        help_text="Établissement concerné (optionnel)",
    )
    creee_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
    )
    cree_le = models.DateTimeField(auto_now_add=True)
    envoyee_le = models.DateTimeField(null=True, blank=True)
    nombre_emails_envoyes = models.PositiveIntegerField(default=0)
    nombre_whatsapp_envoyes = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Annonce"
        verbose_name_plural = "Annonces"
        ordering = ["-cree_le"]

    def __str__(self):
        return self.titre

    @property
    def est_envoyee(self):
        return self.envoyee_le is not None


class PushSubscription(models.Model):
    """
    Abonnement Web Push d'un appareil (navigateur ou PWA installée) d'un
    utilisateur connecté, utilisé pour le notifier — indépendamment de
    l'email et du WhatsApp — quand un nouvel établissement est publié.
    """

    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="abonnements_push",
    )
    endpoint = models.URLField(max_length=500, unique=True)
    p256dh = models.CharField(max_length=255)
    auth = models.CharField(max_length=255)
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Abonnement push"
        verbose_name_plural = "Abonnements push"
        ordering = ["-cree_le"]

    def __str__(self):
        return f"Abonnement push de {self.utilisateur}"
