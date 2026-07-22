from django.urls import path

from . import views

app_name = "listings"

urlpatterns = [
    path("", views.galerie, name="galerie"),
    path("recherche/", views.recherche, name="recherche"),
    path("resultats/", views.resultats, name="resultats"),
    path("etablissement/<slug:slug>/", views.detail, name="detail"),
    path("espace/etablissements/", views.mes_etablissements, name="mes_etablissements"),
    path("espace/etablissements/nouveau/", views.creer_etablissement, name="creer_etablissement"),
    path("espace/etablissements/<slug:slug>/modifier/", views.modifier_etablissement, name="modifier_etablissement"),
    path("espace/etablissements/<slug:slug>/publier/", views.publier_etablissement, name="publier_etablissement"),
]
