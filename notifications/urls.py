from django.urls import path

from . import views

app_name = "notifications"

urlpatterns = [
    path("abonnement/", views.abonnement, name="abonnement"),
]
