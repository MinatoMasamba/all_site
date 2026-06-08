from django.contrib.auth.forms import UserCreationForm

from .models import Utilisateur


class InscriptionForm(UserCreationForm):
    """Inscription d'un visiteur qui veut suivre les offres et faire des réservations."""

    class Meta(UserCreationForm.Meta):
        model = Utilisateur
        fields = ("username", "email", "telephone", "recevoir_notifications")


class InscriptionProprietaireForm(UserCreationForm):
    """Un propriétaire d'établissement crée un compte pour gérer sa fiche."""

    class Meta(UserCreationForm.Meta):
        model = Utilisateur
        fields = ("username", "email", "telephone")

    def save(self, commit=True):
        utilisateur = super().save(commit=False)
        utilisateur.role = Utilisateur.Role.PROPRIETAIRE
        if commit:
            utilisateur.save()
        return utilisateur


class InscriptionMediateurForm(UserCreationForm):
    """Un médiateur référence des établissements qu'il connaît sur le terrain."""

    class Meta(UserCreationForm.Meta):
        model = Utilisateur
        fields = ("username", "email", "telephone")

    def save(self, commit=True):
        utilisateur = super().save(commit=False)
        utilisateur.role = Utilisateur.Role.MEDIATEUR
        if commit:
            utilisateur.save()
        return utilisateur
