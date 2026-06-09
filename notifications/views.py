from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import AbonnementNewsletterForm, AnnonceForm
from .models import Annonce
from .services import diffuser_annonce


def abonnement(request):
    if request.method == "POST":
        form = AbonnementNewsletterForm(request.POST)
        if form.is_valid():
            form.save()
            request.session["newsletter_abonne"] = True
            messages.success(
                request,
                "Merci ! Vous recevrez désormais les offres et nouveautés des "
                "établissements de la plateforme par email"
                + (" et WhatsApp" if form.cleaned_data.get("numero_whatsapp") else "")
                + ".",
            )
        else:
            messages.error(request, "Veuillez vérifier votre adresse email et votre numéro WhatsApp.")
    return redirect(request.META.get("HTTP_REFERER", "listings:galerie"))


def _peut_diffuser_des_annonces(utilisateur):
    return utilisateur.is_authenticated and (
        utilisateur.est_proprietaire or utilisateur.est_gestionnaire
    )


exige_diffuseur = user_passes_test(_peut_diffuser_des_annonces, login_url="accounts:connexion")


@exige_diffuseur
def annonces(request):
    queryset = Annonce.objects.select_related("etablissement")
    if not request.user.est_gestionnaire:
        queryset = queryset.filter(creee_par=request.user)
    return render(request, "notifications/annonces.html", {"annonces": queryset})


@exige_diffuseur
def creer_annonce(request):
    if request.method == "POST":
        form = AnnonceForm(request.POST)
        if form.is_valid():
            annonce = form.save(commit=False)
            annonce.creee_par = request.user
            annonce.save()
            messages.success(
                request,
                "L'annonce est enregistrée. Vous pouvez maintenant la diffuser "
                "par email et WhatsApp à tous les abonnés.",
            )
            return redirect("notifications:annonces")
    else:
        form = AnnonceForm()

    if not request.user.est_gestionnaire:
        form.fields["etablissement"].queryset = form.fields["etablissement"].queryset.filter(
            proprietaire=request.user
        )

    return render(request, "notifications/formulaire_annonce.html", {"form": form})


@exige_diffuseur
def diffuser(request, annonce_id):
    queryset = Annonce.objects.all()
    if not request.user.est_gestionnaire:
        queryset = queryset.filter(creee_par=request.user)
    annonce = get_object_or_404(queryset, pk=annonce_id)

    if request.method == "POST" and not annonce.est_envoyee:
        nb_emails, nb_whatsapp = diffuser_annonce(annonce)
        annonce.envoyee_le = timezone.now()
        annonce.nombre_emails_envoyes = nb_emails
        annonce.nombre_whatsapp_envoyes = nb_whatsapp
        annonce.save(update_fields=["envoyee_le", "nombre_emails_envoyes", "nombre_whatsapp_envoyes"])
        messages.success(
            request,
            f"Annonce diffusée : {nb_emails} email(s) et {nb_whatsapp} message(s) WhatsApp envoyés.",
        )
    return redirect("notifications:annonces")
