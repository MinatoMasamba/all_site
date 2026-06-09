from django.conf import settings
from django.db import models
from django.urls import reverse


class Categorie(models.Model):
    nom = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True)
    icone = models.CharField(
        max_length=50,
        blank=True,
        help_text="Nom d'une icône (ex: hotel, restaurant, bar, site)",
    )

    class Meta:
        verbose_name = "Catégorie"
        verbose_name_plural = "Catégories"
        ordering = ["nom"]

    def __str__(self):
        return self.nom


class Commune(models.Model):
    """Une commune ou un quartier de Kinshasa, pour la recherche par position."""

    nom = models.CharField(max_length=100, unique=True)

    class Meta:
        verbose_name = "Commune"
        verbose_name_plural = "Communes"
        ordering = ["nom"]

    def __str__(self):
        return self.nom


class Etablissement(models.Model):
    class Statut(models.TextChoices):
        BROUILLON = "brouillon", "Brouillon"
        PUBLIE = "publie", "Publié"
        ARCHIVE = "archive", "Archivé"

    nom = models.CharField(max_length=150)
    slug = models.SlugField(max_length=180, unique=True)
    categorie = models.ForeignKey(
        Categorie, on_delete=models.PROTECT, related_name="etablissements"
    )
    commune = models.ForeignKey(
        Commune, on_delete=models.PROTECT, related_name="etablissements"
    )
    adresse = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    prix_minimum = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Prix indicatif le plus bas, en USD",
    )
    prix_maximum = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Prix indicatif le plus haut, en USD",
    )
    telephone = models.CharField(max_length=20, blank=True)
    email_contact = models.EmailField(
        blank=True,
        help_text="Email de réservation (hôtels et restaurants)",
    )
    whatsapp_contact = models.CharField(
        max_length=20,
        blank=True,
        help_text="Numéro WhatsApp pour les réservations, ex: +243800000000 (hôtels et restaurants)",
    )

    proprietaire = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="etablissements_geres",
        help_text="Compte du propriétaire, une fois la fiche réclamée",
    )
    enregistre_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="etablissements_enregistres",
        help_text="Médiateur ou gestionnaire ayant créé la fiche",
    )
    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.BROUILLON)

    cree_le = models.DateTimeField(auto_now_add=True)
    modifie_le = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Établissement"
        verbose_name_plural = "Établissements"
        ordering = ["-cree_le"]

    def __str__(self):
        return self.nom

    def get_absolute_url(self):
        return reverse("listings:detail", kwargs={"slug": self.slug})

    @property
    def image_principale(self):
        return self.images.first()


class ImageEtablissement(models.Model):
    etablissement = models.ForeignKey(
        Etablissement, on_delete=models.CASCADE, related_name="images"
    )
    image = models.ImageField(upload_to="etablissements/%Y/%m/")
    legende = models.CharField(max_length=200, blank=True)
    ordre = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Image"
        verbose_name_plural = "Images"
        ordering = ["ordre", "id"]

    def __str__(self):
        return f"Image de {self.etablissement.nom}"
