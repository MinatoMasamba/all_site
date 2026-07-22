from django.urls import path

from . import views

app_name = "notifications"

urlpatterns = [
    path("abonnement/", views.abonnement, name="abonnement"),
    path("annonces/", views.annonces, name="annonces"),
    path("annonces/nouvelle/", views.creer_annonce, name="creer_annonce"),
    path("annonces/<int:annonce_id>/diffuser/", views.diffuser, name="diffuser"),
    path("push/abonner/", views.push_subscribe, name="push_subscribe"),
    path("push/desabonner/", views.push_unsubscribe, name="push_unsubscribe"),
]
