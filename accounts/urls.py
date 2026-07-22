from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("connexion/", views.ConnexionView.as_view(), name="connexion"),
    path("deconnexion/", views.DeconnexionView.as_view(), name="deconnexion"),
    path("inscription/", views.inscription, name="inscription"),
    path("inscription/proprietaire/", views.inscription_proprietaire, name="inscription_proprietaire"),
    path("inscription/mediateur/", views.inscription_mediateur, name="inscription_mediateur"),
    path("devenir-mediateur/", views.devenir_mediateur, name="devenir_mediateur"),
    path("compte/", views.compte, name="compte"),
]
