from django.contrib.auth.models import AbstractUser
from django.db import models


class Utilisateur(AbstractUser):
    """Utilisateur de la plateforme, avec un rôle qui détermine ses accès."""

    class Role(models.TextChoices):
        VISITEUR = "visiteur", "Visiteur inscrit"
        PROPRIETAIRE = "proprietaire", "Propriétaire d'établissement"
        MEDIATEUR = "mediateur", "Médiateur"
        GESTIONNAIRE = "gestionnaire", "Gestionnaire de la plateforme"

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.VISITEUR)
    telephone = models.CharField(max_length=20, blank=True)
    recevoir_notifications = models.BooleanField(
        default=True,
        verbose_name="Recevoir les offres et nouveautés par notification",
    )

    def __str__(self):
        return self.get_full_name() or self.username

    @property
    def est_proprietaire(self):
        return self.role == self.Role.PROPRIETAIRE

    @property
    def est_mediateur(self):
        return self.role == self.Role.MEDIATEUR

    @property
    def est_gestionnaire(self):
        return self.role == self.Role.GESTIONNAIRE or self.is_superuser
