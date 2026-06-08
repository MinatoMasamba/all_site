from django.db import models


class AbonnementNewsletter(models.Model):
    """Permet à un visiteur (même non inscrit) de recevoir les offres et nouveautés."""

    email = models.EmailField(unique=True)
    cree_le = models.DateTimeField(auto_now_add=True)
    actif = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Abonnement newsletter"
        verbose_name_plural = "Abonnements newsletter"
        ordering = ["-cree_le"]

    def __str__(self):
        return self.email
