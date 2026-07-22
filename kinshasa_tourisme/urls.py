from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from . import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("sw.js", views.service_worker, name="service_worker"),
    path("comptes/", include("accounts.urls")),
    path("notifications/", include("notifications.urls")),
    path("reservations/", include("reservations.urls")),
    path("", include("listings.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
