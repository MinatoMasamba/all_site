"""
Remplit la base de données avec les établissements de Kinshasa
issus des fichiers JSON de recherche (hôtels, restaurants, bars, sites).

Lit directement les fixtures JSON dans listings/fixtures/.
Déduplique les entrées identiques présentes dans plusieurs sources et
fusionne les champs pour obtenir la fiche la plus complète possible.

Usage : python manage.py seed_kinshasa
"""
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re
from django.core.management.base import BaseCommand
from django.utils.text import slugify
from django.contrib.auth import get_user_model

from listings.models import Categorie, Commune, Etablissement, ImageEtablissement

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent / "fixtures"


def _load_json(filename):
    with open(FIXTURES_DIR / filename, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Helper: slug availability (avoid collisions with existing slugs)
# ---------------------------------------------------------------------------

def _slug_disponible(nom, instance=None):
    """
    Retourne un slug unique pour le nom donné. Si le slug de base est vide
    (nom non-ASCII comme caractères chinois), utilise un fallback numérique.
    Si le slug existe déjà sur une autre entrée, ajoute un suffixe numérique.
    """
    base = slugify(nom)
    if not base:
        base = f"etablissement"
    slug = base
    qs = Etablissement.objects.filter(slug=slug)
    if instance and instance.pk:
        qs = qs.exclude(pk=instance.pk)
    n = 1
    while qs.exists():
        slug = f"{base}-{n}"
        qs = Etablissement.objects.filter(slug=slug)
        if instance and instance.pk:
            qs = qs.exclude(pk=instance.pk)
        n += 1
    return slug


# ---------------------------------------------------------------------------
# Helper: category detection
# ---------------------------------------------------------------------------

def detect_categorie(categorie_str, type_str=""):
    """Retourne le nom de catégorie à partir d'une chaîne descriptive."""
    txt = f"{categorie_str or ''} {type_str or ''}".lower()

    hotel_kw = ["hotel", "hôtel", "auberge", "guest house", "guesthouse", "flat", "refuge", "inn", "suites"]
    bar_kw = ["nightclub", "club", "lounge bar", "lounge"]
    bar_exact = ["bar"]
    restaurant_kw = [
        "restaurant", "bistro", "fast-food", "fastfood", "café", "cafe",
        "brasserie", "maquis", "nganda", "grill", "snack", "tea house",
        "tea room", "salon de thé"
    ]
    tourist_kw = [
        "musée", "musee", "parc", "zoo", "plage", "monument", "attraction",
        "jardin", "safari", "agence", "carrefour", "site naturel", "site",
        "roue", "parc de loisirs"
    ]

    # Hotel check
    for kw in hotel_kw:
        if kw in txt:
            return "Hôtels"

    # Restaurant check (restaurant keyword takes priority over bar)
    for kw in restaurant_kw:
        if kw in txt:
            return "Restaurants"

    # Bar check: bar/nightclub/club/lounge WITHOUT restaurant keyword
    has_restaurant = any(kw in txt for kw in restaurant_kw)
    if not has_restaurant:
        for kw in bar_kw:
            if kw in txt:
                return "Bars"
        for kw in bar_exact:
            if re.search(r'\b' + kw + r'\b', txt):
                return "Bars"

    # Tourist sites
    for kw in tourist_kw:
        if kw in txt:
            return "Sites touristiques"

    return "Sites touristiques"


# ---------------------------------------------------------------------------
# Helper: commune detection
# ---------------------------------------------------------------------------

def detect_commune(adresse, commune_hint=None):
    """
    Retourne le nom de la commune à partir de l'adresse ou d'un hint explicite.
    """
    if commune_hint:
        return commune_hint

    txt = (adresse or "").lower()

    if "ngaba" in txt:
        return "Ngaba"
    if "lemba" in txt:
        return "Lemba"
    if "limete" in txt or "limetté" in txt or "limeté" in txt:
        return "Limete"
    if "ling" in txt or "ligwala" in txt or "lingwala" in txt:
        return "Lingwala"
    if "kalamu" in txt or "matonge" in txt or "matonge" in txt:
        return "Kalamu"
    if "kasa-vubu" in txt or "kasa vubu" in txt or "kasavubu" in txt:
        return "Kasa-Vubu"
    if "maluku" in txt:
        return "Maluku"
    if "ngafula" in txt:
        return "Mont-Ngafula"
    if "barumbu" in txt:
        return "Barumbu"
    if "gombe" in txt:
        return "Gombe"
    return "Gombe"


# ---------------------------------------------------------------------------
# Helper: price parsing
# ---------------------------------------------------------------------------

def parse_prix(s):
    """
    Retourne (prix_minimum, prix_maximum) en Decimal ou None.
    """
    if not s or s in ("N/A", "À vérifier", ""):
        return None, None

    sl = s.strip().lower()

    if sl in ("gratuit", "gratuit/libre", "gratuit / libre"):
        return Decimal("0"), None

    # Skip CDF-only prices (contain fc or cdf but no $)
    if ("fc" in sl or "cdf" in sl) and "$" not in sl and "usd" not in sl:
        return None, None

    # Range: $150-250 or $45-80 or $5-10
    m = re.search(r'\$?\s*(\d+)\s*[-–]\s*(\d+)', s)
    if m:
        return Decimal(m.group(1)), Decimal(m.group(2))

    # Single: $45 or ~30 USD or ~10 USD
    m = re.search(r'[~$]?\s*(\d+)\s*(?:USD|usd|\$)?', s)
    if m and ("$" in s or "usd" in sl or "~" in s):
        return Decimal(m.group(1)), None

    return None, None


# ---------------------------------------------------------------------------
# Helper: star parsing
# ---------------------------------------------------------------------------

def parse_etoiles(categorie_str):
    """Retourne une chaîne '0'..'5' ou '' selon la catégorie."""
    if not categorie_str:
        return ""
    txt = categorie_str.lower()
    if "5 étoile" in txt or "5 etoile" in txt:
        return "5"
    if "4 étoile" in txt or "4 etoile" in txt:
        return "4"
    if "3 étoile" in txt or "3 etoile" in txt:
        return "3"
    if "2 étoile" in txt or "2 etoile" in txt:
        return "2"
    if "1 étoile" in txt or "1 etoile" in txt:
        return "1"
    if "0-étoile" in txt or "0 étoile" in txt or "0-etoile" in txt or "0 etoile" in txt:
        return "0"
    return ""


# ---------------------------------------------------------------------------
# Helper: services list → string
# ---------------------------------------------------------------------------

def format_services(services_list):
    """Joins a list of services, skipping N/A entries."""
    if not services_list:
        return ""
    cleaned = [s for s in services_list if s and s != "N/A"]
    return ", ".join(cleaned)


# ---------------------------------------------------------------------------
# Helper: URL validation
# ---------------------------------------------------------------------------

def _clean(val):
    """Return val if it's a non-empty, non-N/A string, else empty string."""
    if not val or str(val).strip() in ("N/A", "null", "None", ""):
        return ""
    return str(val).strip()


def valid_image_url(url):
    """Accept only direct image file URLs (.jpg .jpeg .png .webp .gif)."""
    url = _clean(url)
    if not url or not url.startswith("http"):
        return False
    lower = url.lower().split("?")[0]
    return any(lower.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"))


def valid_web_url(url):
    """Accept any https:// URL that is not N/A."""
    url = _clean(url)
    return bool(url and url.startswith("http"))


def valid_facebook_url(url):
    url = _clean(url)
    return bool(url and url.startswith("http") and "facebook.com" in url)


def valid_tiktok_url(url):
    url = _clean(url)
    return bool(url and url.startswith("http") and "tiktok.com" in url)


# ---------------------------------------------------------------------------
# Merge helper
# ---------------------------------------------------------------------------

def _prefer(a, b):
    """Return a if a is non-None and not 'N/A', else b."""
    if a is not None and a != "N/A" and a != "":
        return a
    return b


def merge_entry(existing, new_entry):
    """Merge new_entry into existing dict, preferring non-null/non-N/A values."""
    for key, new_val in new_entry.items():
        old_val = existing.get(key)
        if new_val is None or new_val == "N/A":
            continue
        if old_val is None or old_val == "N/A" or old_val == "":
            existing[key] = new_val
        elif isinstance(new_val, list) and isinstance(old_val, list):
            # Merge lists (deduplicate)
            merged = list(old_val)
            for item in new_val:
                if item not in merged:
                    merged.append(item)
            existing[key] = merged
        # Otherwise keep existing (first-seen wins for scalars)
    return existing


# ---------------------------------------------------------------------------
# Data definitions
# ---------------------------------------------------------------------------

def _build_entries():
    """
    Lit les 5 fichiers JSON de fixtures et construit un dict dédupliqué.
    Clé : slug normalisé. Valeur : dict de tous les champs disponibles.
    """
    entries = {}

    def _add(entry):
        """Ajoute ou fusionne une entrée dans le catalogue."""
        key = slugify(entry["nom"]).lower()
        if not key:
            key = entry["nom"].lower()[:30]
        if key in entries:
            merge_entry(entries[key], entry)
        else:
            entries[key] = entry

    def _norm(item, commune_hint=None):
        """Normalise un item JSON en dict uniforme."""
        # Prix
        prix_min, prix_max = parse_prix(item.get("prix_estimé") or item.get("prix_estimé"))
        # Téléphone (ngaba restaurants ont deux champs)
        telephone = (_clean(item.get("telephone_local"))
                     or _clean(item.get("telephone"))
                     or _clean(item.get("telephone_chaine"))
                     or "")
        # Évaluation (ngaba restaurants ont evaluation_chaine)
        evaluation = item.get("evaluation") or item.get("evaluation_chaine")
        if evaluation == "N/A":
            evaluation = None
        nombre_avis = item.get("nombre_avis") or item.get("nombre_avis_chaine")
        if nombre_avis == "N/A":
            nombre_avis = None
        # Services
        svcs = item.get("services") or []
        if isinstance(svcs, str):
            svcs = [s.strip() for s in svcs.split(",") if s.strip()]
        services_str = format_services(svcs)
        # Étoiles
        etoiles = _clean(item.get("etoiles", ""))
        if not etoiles:
            etoiles = parse_etoiles(
                _clean(item.get("type", "")) + " " + _clean(item.get("categorie", ""))
            )
        # URLs
        url_img = item.get("url_image") or ""
        if not valid_image_url(url_img):
            url_img = ""
        site_web = item.get("site_web") or ""
        if not valid_web_url(site_web):
            # Use map page links (Google Maps, OSM) as site_web when no real site exists
            map_url = _clean(item.get("url_image", ""))
            if map_url and ("google.com/maps" in map_url or "openstreetmap.org" in map_url):
                site_web = map_url
            else:
                site_web = ""
        fb = item.get("facebook") or ""
        if not valid_facebook_url(fb):
            fb = ""
        tk = item.get("tiktok") or ""
        if not valid_tiktok_url(tk):
            tk = ""

        return {
            "nom": item["nom"],
            "commune_hint": commune_hint,
            "adresse": _clean(item.get("adresse", "")),
            "description": _clean(item.get("description", "")),
            "telephone": telephone,
            "services_list": svcs,
            "services": services_str,
            "prix_min": prix_min,
            "prix_max": prix_max,
            "categorie_str": _clean(item.get("categorie", "")),
            "type_str": _clean(item.get("type", "")),
            "url_image": url_img,
            "site_web": site_web,
            "facebook": fb,
            "tiktok": tk,
            "email": _clean(item.get("email", "")),
            "latitude": item.get("latitude"),
            "longitude": item.get("longitude"),
            "evaluation": evaluation,
            "nombre_avis": nombre_avis,
            "horaires": _clean(item.get("horaires", "")),
            "type_cuisine": _clean(item.get("type_cuisine", "")),
            "nombre_chambres": _clean(str(item.get("nombre_chambres") or "")),
            "etoiles_str": etoiles,
        }

    # -----------------------------------------------------------------------
    # Source 1 : ngaba_hotels_restaurants.json
    # -----------------------------------------------------------------------
    ngaba = _load_json("ngaba_hotels_restaurants.json")

    for item in ngaba.get("hotels_officiels_0_etoile", []):
        _add(_norm(item, commune_hint="Ngaba"))

    for item in ngaba.get("hotels_modernes_references", []):
        _add(_norm(item, commune_hint="Ngaba"))

    for item in ngaba.get("restaurants_cafes_bars", []):
        _add(_norm(item, commune_hint="Ngaba"))

    # -----------------------------------------------------------------------
    # Source 2 : lemba_commune_complete.json
    # -----------------------------------------------------------------------
    lemba = _load_json("lemba_commune_complete.json")

    for item in lemba.get("attractions_touristiques", []):
        _add(_norm(item, commune_hint="Lemba"))

    for item in lemba.get("restaurants_cafes", []):
        _add(_norm(item, commune_hint="Lemba"))

    for item in lemba.get("hotels", []):
        _add(_norm(item, commune_hint="Lemba"))

    # -----------------------------------------------------------------------
    # Source 3 : lingwala_hotels_restaurants.json
    # -----------------------------------------------------------------------
    lingwala = _load_json("lingwala_hotels_restaurants.json")

    for item in lingwala.get("hotels", []):
        _add(_norm(item, commune_hint="Lingwala"))

    for item in lingwala.get("restaurants", []):
        _add(_norm(item, commune_hint="Lingwala"))

    # -----------------------------------------------------------------------
    # Source 4 : kinshasa_hotels_100.json
    # -----------------------------------------------------------------------
    hotels100 = _load_json("kinshasa_hotels_100.json")

    for item in hotels100.get("hotels", []):
        entry = _norm(item)
        # Force étoiles from the "type" field (e.g. "Hôtel 5 étoiles")
        if not entry["etoiles_str"]:
            entry["etoiles_str"] = parse_etoiles(
                _clean(item.get("type", ""))
            )
        # Nombre de chambres
        if not entry["nombre_chambres"]:
            entry["nombre_chambres"] = _clean(str(item.get("nombre_chambres") or ""))
        _add(entry)

    # -----------------------------------------------------------------------
    # Source 5 : kinshasa_tourism_data.json
    # -----------------------------------------------------------------------
    tourism = _load_json("kinshasa_tourism_data.json")

    for item in tourism.get("attractions_touristiques", []):
        _add(_norm(item))

    for item in tourism.get("restaurants", []):
        _add(_norm(item))

    return entries



# ---------------------------------------------------------------------------
# Create Etablissement objects
# ---------------------------------------------------------------------------

def _create_etablissements(entries, gestionnaire, categories, communes):
    """Creates or updates Etablissement records from the merged entries dict."""
    created_count = 0
    updated_count = 0

    for key, data in entries.items():
        nom = data["nom"]
        adresse = data.get("adresse", "")
        commune_hint = data.get("commune_hint")
        commune_name = commune_hint if commune_hint else detect_commune(adresse)

        # Resolve commune
        commune = communes.get(commune_name)
        if not commune:
            commune = communes.get("Gombe")

        # Detect category
        cat_name = detect_categorie(
            data.get("categorie_str", ""),
            data.get("type_str", "")
        )
        categorie = categories.get(cat_name)
        if not categorie:
            categorie = categories.get("Sites touristiques")

        # Build slug
        slug = slugify(nom)
        # Check for collisions with a temp approach
        base_slug = slug
        n = 1
        while True:
            existing = Etablissement.objects.filter(slug=slug).first()
            if not existing or existing.nom.lower() == nom.lower():
                break
            slug = f"{base_slug}-{n}"
            n += 1

        # Services (already formatted as string by _norm(), fallback to list)
        services_str = data.get("services") or format_services(data.get("services_list", []))

        # Evaluation
        eval_val = data.get("evaluation")
        if eval_val is not None:
            try:
                eval_val = Decimal(str(eval_val))
            except (InvalidOperation, TypeError):
                eval_val = None

        # Coordinates
        lat = data.get("latitude")
        lon = data.get("longitude")
        if lat is not None:
            try:
                lat = Decimal(str(lat))
            except (InvalidOperation, TypeError):
                lat = None
        if lon is not None:
            try:
                lon = Decimal(str(lon))
            except (InvalidOperation, TypeError):
                lon = None

        # Social & web links (re-validate from data)
        fb = data.get("facebook") or ""
        tk = data.get("tiktok") or ""
        sw = data.get("site_web") or ""
        fb = fb if valid_facebook_url(fb) else ""
        tk = tk if valid_tiktok_url(tk) else ""
        sw = sw if valid_web_url(sw) else ""

        # URL image (only direct image file URLs)
        url_img = data.get("url_image") or ""
        if not valid_image_url(url_img):
            url_img = ""

        defaults = {
            "categorie": categorie,
            "commune": commune,
            "adresse": adresse,
            "description": data.get("description", ""),
            "telephone": data.get("telephone", ""),
            "email_contact": data.get("email", ""),
            "prix_minimum": data.get("prix_min"),
            "prix_maximum": data.get("prix_max"),
            "latitude": lat,
            "longitude": lon,
            "evaluation": eval_val,
            "nombre_avis": data.get("nombre_avis"),
            "horaires": data.get("horaires", ""),
            "site_web": sw,
            "facebook": fb,
            "tiktok": tk,
            "services": services_str,
            "nombre_chambres": data.get("nombre_chambres", ""),
            "etoiles": data.get("etoiles_str", ""),
            "type_cuisine": data.get("type_cuisine", ""),
            "statut": Etablissement.Statut.PUBLIE,
            "enregistre_par": gestionnaire,
        }

        obj, created = Etablissement.objects.get_or_create(
            slug=slug,
            defaults={"nom": nom, **defaults},
        )

        if created:
            created_count += 1
        else:
            # Update existing with better data
            changed = False
            for field, value in defaults.items():
                old_val = getattr(obj, field)
                if value and not old_val:
                    setattr(obj, field, value)
                    changed = True
            if changed:
                obj.save()
                updated_count += 1

        # Create image if valid URL
        if url_img and not obj.images.filter(url_image=url_img).exists():
            ImageEtablissement.objects.create(
                etablissement=obj,
                url_image=url_img,
            )

    return created_count, updated_count


# ---------------------------------------------------------------------------
# Management command
# ---------------------------------------------------------------------------

class Command(BaseCommand):
    help = "Remplit la base avec les établissements de Kinshasa (fusion multi-sources)"

    def handle(self, *args, **options):
        self.stdout.write("Démarrage du seed Kinshasa...")

        User = get_user_model()

        # Ensure gestionnaire account exists
        gestionnaire, _ = User.objects.get_or_create(
            username="gestionnaire_plateforme",
            defaults={
                "email": "gestion@decouvrir-kinshasa.cd",
                "is_staff": True,
            },
        )

        # Ensure all categories exist
        cat_names = ["Hôtels", "Restaurants", "Bars", "Sites touristiques"]
        categories = {}
        for nom in cat_names:
            cat, _ = Categorie.objects.get_or_create(
                nom=nom,
                defaults={"slug": slugify(nom)},
            )
            categories[nom] = cat

        # Ensure all communes exist
        commune_names = [
            "Gombe", "Limete", "Lemba", "Ngaliema", "Kalamu", "Ngaba", "Kintambo",
            "Lingwala", "Kasa-Vubu", "Maluku", "Mont-Ngafula", "Barumbu", "Bandalungwa",
        ]
        communes = {}
        for nom in commune_names:
            c, _ = Commune.objects.get_or_create(nom=nom)
            communes[nom] = c

        self.stdout.write(f"  {len(categories)} catégories, {len(communes)} communes prêtes.")

        # Build merged entries dict
        self.stdout.write("  Construction du catalogue (fusion multi-sources)...")
        entries = _build_entries()
        self.stdout.write(f"  {len(entries)} entrées uniques après déduplication.")

        # Create/update records
        self.stdout.write("  Création des établissements...")
        created, updated = _create_etablissements(entries, gestionnaire, categories, communes)

        total = Etablissement.objects.count()
        self.stdout.write(self.style.SUCCESS(
            f"\nSeed Kinshasa terminé : {created} créés, {updated} mis à jour, "
            f"{total} établissements au total."
        ))
