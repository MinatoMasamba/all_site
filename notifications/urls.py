from django.urls import path

from . import views

app_name = "notifications"

urlpatterns = [
    path("abonnement/", views.abonnement, name="abonnement"),
    path("annonces/", views.annonces, name="annonces"),
    path("annonces/nouvelle/", views.creer_annonce, name="creer_annonce"),
    path("annonces/<int:annonce_id>/diffuser/", views.diffuser, name="diffuser"),
]
