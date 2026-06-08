from django.db.models import Q
from django.shortcuts import get_object_or_404, render

from .models import Categorie, Commune, Etablissement


def galerie(request):
    etablissements = Etablissement.objects.filter(statut=Etablissement.Statut.PUBLIE)

    terme = request.GET.get("q", "").strip()
    categorie_slug = request.GET.get("categorie", "")
    commune_id = request.GET.get("commune", "")

    if terme:
        etablissements = etablissements.filter(
            Q(nom__icontains=terme)
            | Q(description__icontains=terme)
            | Q(adresse__icontains=terme)
            | Q(commune__nom__icontains=terme)
        )
    if categorie_slug:
        etablissements = etablissements.filter(categorie__slug=categorie_slug)
    if commune_id:
        etablissements = etablissements.filter(commune_id=commune_id)

    contexte = {
        "etablissements": etablissements.select_related("categorie", "commune").prefetch_related("images"),
        "categories": Categorie.objects.all(),
        "communes": Commune.objects.all(),
        "terme": terme,
        "categorie_active": categorie_slug,
        "commune_active": commune_id,
    }
    return render(request, "listings/galerie.html", contexte)


def detail(request, slug):
    etablissement = get_object_or_404(
        Etablissement.objects.select_related("categorie", "commune").prefetch_related("images"),
        slug=slug,
        statut=Etablissement.Statut.PUBLIE,
    )
    return render(request, "listings/detail.html", {"etablissement": etablissement})
