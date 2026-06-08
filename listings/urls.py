from django.urls import path

from . import views

app_name = "listings"

urlpatterns = [
    path("", views.galerie, name="galerie"),
    path("etablissement/<slug:slug>/", views.detail, name="detail"),
]
