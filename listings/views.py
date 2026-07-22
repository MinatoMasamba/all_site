from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.text import slugify

from .forms import EtablissementForm, ImageEtablissementFormSet
from .models import Categorie, Commune, Etablissement


def _peut_gerer_des_etablissements(utilisateur):
    return utilisateur.is_authenticated and (
        utilisateur.est_proprietaire or utilisateur.est_mediateur or utilisateur.est_gestionnaire
    )


exige_gestionnaire_etablissement = user_passes_test(
    _peut_gerer_des_etablissements,
    login_url="accounts:connexion",
)


def _etablissements_geres_par(utilisateur):
    if utilisateur.est_gestionnaire:
        return Etablissement.objects.all()
    return Etablissement.objects.filter(
        Q(proprietaire=utilisateur) | Q(enregistre_par=utilisateur)
    )


TRANCHES_PRIX = [
    ("0-10",  "Moins de 10 $"),
    ("10-30", "10 $ – 30 $"),
    ("30-60", "30 $ – 60 $"),
    ("60-100","60 $ – 100 $"),
    ("100+",  "Plus de 100 $"),
]


def _etablissements_filtres(request):
    etablissements = Etablissement.objects.filter(statut=Etablissement.Statut.PUBLIE)

    terme = request.GET.get("q", "").strip()
    categorie_slug = request.GET.get("categorie", "")
    commune_id = request.GET.get("commune", "")
    prix_tranche = request.GET.get("prix", "")
    note_min = request.GET.get("note", "")

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
    if prix_tranche:
        if prix_tranche == "100+":
            etablissements = etablissements.filter(prix_minimum__gt=100)
        elif "-" in prix_tranche:
            lo, hi = prix_tranche.split("-")
            etablissements = etablissements.filter(
                prix_minimum__gte=lo, prix_minimum__lt=hi
            )
    if note_min:
        etablissements = etablissements.filter(evaluation__gte=note_min)

    filtres = {
        "terme": terme,
        "categorie_active": categorie_slug,
        "commune_active": commune_id,
        "prix_actif": prix_tranche,
        "note_active": note_min,
    }
    qs = etablissements.select_related("categorie", "commune").prefetch_related("images")
    return qs, filtres


def galerie(request):
    """Accueil : mise en avant + populaires, à partir des établissements publiés."""
    publies = (
        Etablissement.objects.filter(statut=Etablissement.Statut.PUBLIE)
        .select_related("categorie", "commune")
        .prefetch_related("images")
    )
    a_la_une = publies.exclude(evaluation__isnull=True).order_by("-evaluation", "-nombre_avis").first()
    populaires = publies.exclude(pk=a_la_une.pk if a_la_une else None).order_by("-evaluation", "-nombre_avis")[:9]

    contexte = {
        "categories": Categorie.objects.all(),
        "a_la_une": a_la_une,
        "populaires": populaires,
    }
    return render(request, "listings/galerie.html", contexte)


def recherche(request):
    """Formulaire de filtres, avant d'afficher les résultats."""
    etablissements, filtres = _etablissements_filtres(request)
    contexte = {
        "categories": Categorie.objects.all(),
        "communes": Commune.objects.all(),
        "tranches_prix": TRANCHES_PRIX,
        "nb_resultats": etablissements.count(),
        **filtres,
    }
    return render(request, "listings/recherche.html", contexte)


def resultats(request):
    """Liste des établissements correspondant aux filtres choisis."""
    etablissements, filtres = _etablissements_filtres(request)
    contexte = {
        "etablissements": etablissements,
        "categories": Categorie.objects.all(),
        "communes": Commune.objects.all(),
        "tranches_prix": TRANCHES_PRIX,
        **filtres,
    }
    return render(request, "listings/resultats.html", contexte)


def detail(request, slug):
    etablissement = get_object_or_404(
        Etablissement.objects.select_related("categorie", "commune").prefetch_related("images"),
        slug=slug,
        statut=Etablissement.Statut.PUBLIE,
    )
    return render(request, "listings/detail.html", {"etablissement": etablissement})


@exige_gestionnaire_etablissement
def mes_etablissements(request):
    etablissements = _etablissements_geres_par(request.user).select_related("categorie", "commune")
    return render(request, "listings/mes_etablissements.html", {"etablissements": etablissements})


def _slug_disponible(nom, instance=None):
    base = slugify(nom)
    slug = base
    compteur = 2
    qs = Etablissement.objects.all()
    if instance and instance.pk:
        qs = qs.exclude(pk=instance.pk)
    while qs.filter(slug=slug).exists():
        slug = f"{base}-{compteur}"
        compteur += 1
    return slug


@exige_gestionnaire_etablissement
def creer_etablissement(request):
    if request.method == "POST":
        form = EtablissementForm(request.POST)
        if form.is_valid():
            etablissement = form.save(commit=False)
            etablissement.slug = _slug_disponible(etablissement.nom)
            if request.user.est_proprietaire:
                etablissement.proprietaire = request.user
            else:
                etablissement.enregistre_par = request.user
            etablissement.statut = Etablissement.Statut.BROUILLON
            etablissement.save()
            messages.success(
                request,
                "Votre établissement a été enregistré en brouillon. "
                "Ajoutez maintenant des photos puis publiez la fiche.",
            )
            return redirect("listings:modifier_etablissement", slug=etablissement.slug)
    else:
        form = EtablissementForm()
    return render(request, "listings/formulaire_etablissement.html", {
        "form": form, "titre": "Enregistrer un établissement",
    })


@exige_gestionnaire_etablissement
def modifier_etablissement(request, slug):
    etablissement = get_object_or_404(_etablissements_geres_par(request.user), slug=slug)

    if request.method == "POST":
        form = EtablissementForm(request.POST, instance=etablissement)
        formset = ImageEtablissementFormSet(request.POST, request.FILES, instance=etablissement)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            messages.success(request, "La fiche de l'établissement a été mise à jour.")
            return redirect("listings:modifier_etablissement", slug=etablissement.slug)
    else:
        form = EtablissementForm(instance=etablissement)
        formset = ImageEtablissementFormSet(instance=etablissement)

    return render(request, "listings/formulaire_etablissement.html", {
        "form": form,
        "formset": formset,
        "etablissement": etablissement,
        "titre": f"Modifier « {etablissement.nom} »",
    })


@exige_gestionnaire_etablissement
def publier_etablissement(request, slug):
    etablissement = get_object_or_404(_etablissements_geres_par(request.user), slug=slug)
    if request.method == "POST":
        if etablissement.statut == Etablissement.Statut.PUBLIE:
            etablissement.statut = Etablissement.Statut.BROUILLON
            messages.info(request, "La fiche a été repassée en brouillon et n'est plus visible publiquement.")
        else:
            etablissement.statut = Etablissement.Statut.PUBLIE
            messages.success(request, "La fiche est maintenant publiée et visible dans la galerie.")
        etablissement.save(update_fields=["statut"])
    return redirect("listings:modifier_etablissement", slug=etablissement.slug)
