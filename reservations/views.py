from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from listings.models import Etablissement

from .forms import PaiementMobileMoneyForm, ReservationForm
from .models import Paiement, Reservation


@login_required
def reserver(request, slug):
    etablissement = get_object_or_404(Etablissement, slug=slug, statut=Etablissement.Statut.PUBLIE)

    if request.user.est_proprietaire or request.user.est_mediateur:
        messages.error(request, "Seuls les visiteurs peuvent effectuer une réservation.")
        return redirect("listings:detail", slug=slug)

    if request.method == "POST":
        form = ReservationForm(request.POST)
        if form.is_valid():
            reservation = form.save(commit=False)
            reservation.utilisateur = request.user
            reservation.etablissement = etablissement
            reservation.save()

            if reservation.mode_paiement == Reservation.ModePaiement.EN_LIGNE:
                messages.info(
                    request,
                    "Votre réservation est enregistrée. Effectuez maintenant le paiement "
                    "Mobile Money : les fonds seront conservés par la plateforme jusqu'à "
                    "votre arrivée sur place.",
                )
                return redirect("reservations:payer", reservation_id=reservation.pk)

            messages.success(
                request,
                "Votre réservation est enregistrée. Vous payerez directement sur place.",
            )
            return redirect("reservations:mes_reservations")
    else:
        form = ReservationForm()

    return render(request, "reservations/reserver.html", {"form": form, "etablissement": etablissement})


@login_required
def payer(request, reservation_id):
    reservation = get_object_or_404(
        Reservation, pk=reservation_id, utilisateur=request.user,
        mode_paiement=Reservation.ModePaiement.EN_LIGNE,
    )

    if hasattr(reservation, "paiement"):
        return redirect("reservations:mes_reservations")

    if request.method == "POST":
        form = PaiementMobileMoneyForm(request.POST)
        if form.is_valid():
            paiement = form.save(commit=False)
            paiement.reservation = reservation
            paiement.statut = Paiement.Statut.BLOQUE
            paiement.save()
            reservation.statut = Reservation.Statut.CONFIRMEE
            reservation.save(update_fields=["statut"])
            messages.success(
                request,
                "Paiement reçu et conservé en sécurité par la plateforme. Il sera "
                "reversé à l'établissement dès que vous aurez tous les deux confirmé "
                "votre présence sur place.",
            )
            return redirect("reservations:mes_reservations")
    else:
        form = PaiementMobileMoneyForm()

    return render(request, "reservations/payer.html", {"form": form, "reservation": reservation})


@login_required
def mes_reservations(request):
    reservations = (
        Reservation.objects.filter(utilisateur=request.user)
        .select_related("etablissement", "paiement")
    )
    return render(request, "reservations/mes_reservations.html", {"reservations": reservations})


@login_required
def confirmer_presence_client(request, reservation_id):
    reservation = get_object_or_404(
        Reservation, pk=reservation_id, utilisateur=request.user,
    )
    paiement = getattr(reservation, "paiement", None)
    if request.method == "POST" and paiement:
        paiement.confirme_par_client = True
        paiement.save(update_fields=["confirme_par_client"])
        statut = paiement.liberer_si_confirme()
        if statut == Paiement.Statut.LIBERE:
            messages.success(request, "Votre présence est confirmée des deux côtés : les fonds ont été reversés à l'établissement.")
        else:
            messages.success(request, "Votre présence est confirmée. En attente de la confirmation de l'établissement pour libérer le paiement.")
    return redirect("reservations:mes_reservations")


def _peut_gerer_des_reservations(utilisateur):
    return utilisateur.is_authenticated and (
        utilisateur.est_proprietaire or utilisateur.est_gestionnaire
    )


exige_proprietaire = user_passes_test(_peut_gerer_des_reservations, login_url="accounts:connexion")


@exige_proprietaire
def reservations_etablissement(request):
    if request.user.est_gestionnaire:
        etablissements = Etablissement.objects.all()
    else:
        etablissements = Etablissement.objects.filter(proprietaire=request.user)

    reservations = (
        Reservation.objects.filter(etablissement__in=etablissements)
        .select_related("utilisateur", "etablissement", "paiement")
    )
    return render(request, "reservations/reservations_etablissement.html", {"reservations": reservations})


@exige_proprietaire
def confirmer_presence_etablissement(request, reservation_id):
    if request.user.est_gestionnaire:
        filtre = Q()
    else:
        filtre = Q(etablissement__proprietaire=request.user)

    reservation = get_object_or_404(Reservation.objects.filter(filtre), pk=reservation_id)
    paiement = getattr(reservation, "paiement", None)
    if request.method == "POST" and paiement:
        paiement.confirme_par_etablissement = True
        paiement.save(update_fields=["confirme_par_etablissement"])
        statut = paiement.liberer_si_confirme()
        if statut == Paiement.Statut.LIBERE:
            messages.success(request, "Présence confirmée des deux côtés : les fonds ont été reversés à votre établissement.")
        else:
            messages.success(request, "Présence du client confirmée. En attente de sa confirmation pour libérer le paiement.")
    return redirect("reservations:reservations_etablissement")
