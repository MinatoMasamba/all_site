from django.urls import path

from . import views

app_name = "reservations"

urlpatterns = [
    path("etablissement/<slug:slug>/reserver/", views.reserver, name="reserver"),
    path("<int:reservation_id>/payer/", views.payer, name="payer"),
    path("<int:reservation_id>/confirmer-presence/", views.confirmer_presence_client, name="confirmer_presence_client"),
    path("mes-reservations/", views.mes_reservations, name="mes_reservations"),
    path("recues/", views.reservations_etablissement, name="reservations_etablissement"),
    path("recues/<int:reservation_id>/confirmer-presence/", views.confirmer_presence_etablissement, name="confirmer_presence_etablissement"),
]
