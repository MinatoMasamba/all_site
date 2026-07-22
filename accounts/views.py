from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.db.models import Count, Q
from django.shortcuts import redirect, render
from django.urls import reverse_lazy

from notifications.services import envoyer_message_bienvenue

from .forms import InscriptionForm, InscriptionMediateurForm, InscriptionProprietaireForm
from .models import Utilisateur


class ConnexionView(LoginView):
    template_name = "accounts/connexion.html"


class DeconnexionView(LogoutView):
    pass


def _inscription(request, form_class, template_name, message_bienvenue):
    if request.method == "POST":
        form = form_class(request.POST)
        if form.is_valid():
            utilisateur = form.save()
            login(request, utilisateur)
            envoyer_message_bienvenue(utilisateur)
            return redirect("listings:galerie")
    else:
        form = form_class()
    return render(request, template_name, {"form": form, "message_bienvenue": message_bienvenue})


def inscription(request):
    return _inscription(
        request, InscriptionForm, "accounts/inscription.html",
        "Inscrivez-vous pour recevoir les offres et nouveautés des hôtels, "
        "restaurants, bars et sites touristiques de Kinshasa.",
    )


def inscription_proprietaire(request):
    return _inscription(
        request, InscriptionProprietaireForm, "accounts/inscription_proprietaire.html",
        "Vous gérez un hôtel, un restaurant, un bar ou un site touristique ? "
        "Créez votre compte pour enregistrer votre établissement, ajouter des "
        "photos et une description, et gagner en visibilité.",
    )


def inscription_mediateur(request):
    # Redirect logged-in users to the contract acceptance page
    if request.user.is_authenticated:
        return redirect("accounts:devenir_mediateur")
    return _inscription(
        request, InscriptionMediateurForm, "accounts/inscription_mediateur.html",
        "Vous connaissez des établissements à Kinshasa qui ne sont pas encore "
        "sur la plateforme ? Devenez médiateur pour les référencer en attendant "
        "que leurs propriétaires viennent réclamer leur fiche.",
    )


def _etablissements_complets(user):
    """
    Retourne le nombre d'établissements 'complets' ajoutés par ce médiateur.
    Complet = a une image, une description, une adresse et un téléphone.
    """
    return (
        user.etablissements_enregistres
        .filter(
            images__isnull=False,
            description__gt="",
            adresse__gt="",
            telephone__gt="",
        )
        .distinct()
        .count()
    )


@login_required
def devenir_mediateur(request):
    user = request.user

    # Already mediator or gestionnaire
    if user.est_mediateur or user.est_gestionnaire:
        complets = _etablissements_complets(user)
        tranches_payees = complets // 5
        return render(request, "accounts/tableau_bord_mediateur.html", {
            "complets": complets,
            "tranches_payees": tranches_payees,
            "gains_estimes": tranches_payees,  # $1 par tranche
            "prochain_palier": 5 - (complets % 5),
        })

    if request.method == "POST":
        if request.POST.get("accepte") == "1":
            user.role = Utilisateur.Role.MEDIATEUR
            user.save(update_fields=["role"])
            messages.success(
                request,
                "Bienvenue dans l'équipe ! Votre compte est maintenant activé en tant que médiateur."
            )
            return redirect("listings:creer_etablissement")
        else:
            messages.error(request, "Vous devez accepter les conditions pour continuer.")

    return render(request, "accounts/devenir_mediateur.html")


@login_required
def compte(request):
    return render(request, "accounts/compte.html", {"vapid_public_key": settings.VAPID_PUBLIC_KEY})
