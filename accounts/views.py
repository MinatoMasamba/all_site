from django.contrib.auth import login
from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import redirect, render
from django.urls import reverse_lazy

from .forms import InscriptionForm, InscriptionMediateurForm, InscriptionProprietaireForm


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
    return _inscription(
        request, InscriptionMediateurForm, "accounts/inscription_mediateur.html",
        "Vous connaissez des établissements à Kinshasa qui ne sont pas encore "
        "sur la plateforme ? Devenez médiateur pour les référencer en attendant "
        "que leurs propriétaires viennent réclamer leur fiche.",
    )
