from pathlib import Path

from django.conf import settings
from django.http import HttpResponse


def service_worker(request):
    """Serves the service worker from the site root so its scope covers the whole app."""
    contenu = (Path(settings.BASE_DIR) / "static" / "js" / "sw.js").read_text(encoding="utf-8")
    return HttpResponse(contenu, content_type="application/javascript")
