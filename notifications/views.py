from django.contrib import messages
from django.shortcuts import redirect

from .forms import AbonnementNewsletterForm


def abonnement(request):
    if request.method == "POST":
        form = AbonnementNewsletterForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(
                request,
                "Merci ! Vous recevrez désormais les offres et nouveautés des "
                "établissements de la plateforme.",
            )
        else:
            messages.error(request, "Veuillez saisir une adresse email valide.")
    return redirect(request.META.get("HTTP_REFERER", "listings:galerie"))
