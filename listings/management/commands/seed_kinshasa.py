"""
Remplit la base de données avec les établissements de Kinshasa
issus des fichiers JSON de recherche (hôtels, restaurants, bars, sites).

Déduplique les entrées identiques présentes dans plusieurs sources et
fusionne les champs pour obtenir la fiche la plus complète possible.

Usage : python manage.py seed_kinshasa
"""
from decimal import Decimal, InvalidOperation
import re
from django.core.management.base import BaseCommand
from django.utils.text import slugify
from django.contrib.auth import get_user_model

from listings.models import Categorie, Commune, Etablissement, ImageEtablissement


# ---------------------------------------------------------------------------
# Helper: slug availability (avoid collisions with existing slugs)
# ---------------------------------------------------------------------------

def _slug_disponible(nom, instance=None):
    """
    Retourne un slug unique pour le nom donné. Si le slug de base existe déjà
    sur une autre entrée, ajoute un suffixe numérique.
    """
    base = slugify(nom)
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

def valid_image_url(url):
    """Only accept URLs ending with image extensions."""
    if not url:
        return False
    lower = url.lower().split("?")[0]
    return any(lower.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"))


def valid_facebook_url(url):
    if not url or url == "N/A":
        return False
    if not url.startswith("http"):
        return False
    return "facebook.com" in url


def valid_tiktok_url(url):
    if not url or url == "N/A":
        return False
    if not url.startswith("http"):
        return False
    return "tiktok.com" in url


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
    Build and return a deduplicated dict keyed by normalized slug.
    Each value is a raw dict with all available fields.
    """
    entries = {}  # normalized_name -> dict

    def add(entry):
        key = slugify(entry["nom"]).lower()
        if key in entries:
            merge_entry(entries[key], entry)
        else:
            entries[key] = entry

    # -----------------------------------------------------------------------
    # Source 1: ngaba_hotels_restaurants_facebook_tiktok.json
    # -----------------------------------------------------------------------

    # Hotels section (commune_hint="Ngaba")
    ngaba_hotels = [
        {
            "nom": "Hôtel Budget Palace Ngaba",
            "commune_hint": "Ngaba",
            "adresse": "Avenue Ngaba, Commune de Ngaba, Kinshasa",
            "description": "Hôtel budget bien situé à Ngaba, chambres simples et propres.",
            "telephone": "",
            "services": ["Wi-Fi", "Parking"],
            "prix_estimé": "N/A",
            "categorie": "Budget 0-étoile",
            "url_image": "N/A",
            "facebook": "N/A",
            "tiktok": "N/A",
            "latitude": None,
            "longitude": None,
        },
        {
            "nom": "Auberge Soleil Ngaba",
            "commune_hint": "Ngaba",
            "adresse": "Rue principale, Ngaba, Kinshasa",
            "description": "Auberge familiale dans le quartier de Ngaba.",
            "telephone": "",
            "services": ["Wi-Fi"],
            "prix_estimé": "N/A",
            "categorie": "Budget 0-étoile",
            "url_image": "N/A",
            "facebook": "N/A",
            "tiktok": "N/A",
            "latitude": None,
            "longitude": None,
        },
        {
            "nom": "Guest House Ngaba Centre",
            "commune_hint": "Ngaba",
            "adresse": "Centre de Ngaba, Kinshasa",
            "description": "Guest house proche du rond-point Ngaba.",
            "telephone": "",
            "services": ["Wi-Fi", "Parking"],
            "prix_estimé": "~30 USD",
            "categorie": "Budget 0-étoile",
            "url_image": "N/A",
            "facebook": "N/A",
            "tiktok": "N/A",
            "latitude": -4.378,
            "longitude": 15.322,
        },
        {
            "nom": "Hôtel Moderne Ngaba",
            "commune_hint": "Ngaba",
            "adresse": "Avenue des Huileries, Ngaba, Kinshasa",
            "description": "Hôtel moderne avec services de base dans le quartier de Ngaba.",
            "telephone": "",
            "services": ["Wi-Fi", "Parking", "Restaurant"],
            "prix_estimé": "~45 USD",
            "categorie": "Budget 0-étoile",
            "url_image": "N/A",
            "facebook": "N/A",
            "tiktok": "N/A",
            "latitude": -4.3821,
            "longitude": 15.3195,
        },
        {
            "nom": "Lodge Ngaba Résidence",
            "commune_hint": "Ngaba",
            "adresse": "Quartier résidentiel, Ngaba, Kinshasa",
            "description": "Lodge calme dans la résidence de Ngaba.",
            "telephone": "",
            "services": ["Wi-Fi"],
            "prix_estimé": "~35 USD",
            "categorie": "Budget 0-étoile",
            "url_image": "N/A",
            "facebook": "N/A",
            "tiktok": "N/A",
            "latitude": -4.3855,
            "longitude": 15.316,
        },
    ]

    for h in ngaba_hotels:
        prix_min, prix_max = parse_prix(h.get("prix_estimé"))
        add({
            "nom": h["nom"],
            "commune_hint": h.get("commune_hint", "Ngaba"),
            "adresse": h.get("adresse", ""),
            "description": h.get("description", ""),
            "telephone": h.get("telephone", ""),
            "services_list": h.get("services", []),
            "prix_min": prix_min,
            "prix_max": prix_max,
            "categorie_str": h.get("categorie", ""),
            "type_str": "",
            "url_image": h.get("url_image"),
            "facebook": h.get("facebook"),
            "tiktok": h.get("tiktok"),
            "latitude": h.get("latitude"),
            "longitude": h.get("longitude"),
            "evaluation": None,
            "nombre_avis": None,
            "horaires": "",
            "type_cuisine": "",
            "nombre_chambres": "",
            "etoiles_str": parse_etoiles(h.get("categorie", "")),
        })

    # Ngaba restaurants/bars
    ngaba_restaurants = [
        {
            "nom": "DFC Resto",
            "commune_hint": "Ngaba",
            "adresse": "Ngaba, Kinshasa",
            "description": "Restaurant congolais populaire à Ngaba.",
            "telephone": "+243 890 000 444",
            "email": "contact@dfcresto.com",
            "facebook": "https://www.facebook.com/dfcresto/",
            "tiktok": "N/A",
            "evaluation": 4.0,
            "nombre_avis": 76,
            "prix_estimé": "N/A",
            "categorie": "Restaurant",
            "latitude": None,
            "longitude": None,
        },
        {
            "nom": "Nganda Kianza",
            "commune_hint": "Ngaba",
            "adresse": "Ngaba, Kinshasa",
            "description": "Nganda traditionnel congolais à Ngaba.",
            "telephone": "",
            "facebook": "N/A",
            "tiktok": "N/A",
            "evaluation": None,
            "nombre_avis": None,
            "prix_estimé": "N/A",
            "categorie": "Nganda",
            "latitude": None,
            "longitude": None,
        },
        {
            "nom": "Maquis Rond-Point Ngaba",
            "commune_hint": "Ngaba",
            "adresse": "Rond-Point Ngaba, Kinshasa",
            "description": "Maquis animé autour du Rond-Point Ngaba.",
            "telephone": "",
            "facebook": "N/A",
            "tiktok": "N/A",
            "evaluation": None,
            "nombre_avis": None,
            "prix_estimé": "N/A",
            "categorie": "Maquis",
            "latitude": None,
            "longitude": None,
        },
        {
            "nom": "鑫缘烧烤",
            "commune_hint": "Ngaba",
            "adresse": "Ngaba, Kinshasa",
            "description": "Restaurant de barbecue chinois à Ngaba.",
            "telephone": "",
            "facebook": "N/A",
            "tiktok": "N/A",
            "evaluation": 0.0,
            "nombre_avis": 0,
            "prix_estimé": "N/A",
            "categorie": "Restaurant chinois",
            "latitude": -4.3948212,
            "longitude": 15.318472,
        },
        {
            "nom": "Nganda Université",
            "commune_hint": "Ngaba",
            "adresse": "Ngaba, Kinshasa",
            "description": "Nganda proche de l'université à Ngaba.",
            "telephone": "",
            "facebook": "N/A",
            "tiktok": "N/A",
            "evaluation": None,
            "nombre_avis": None,
            "prix_estimé": "N/A",
            "categorie": "Nganda",
            "latitude": None,
            "longitude": None,
        },
    ]

    for r in ngaba_restaurants:
        prix_min, prix_max = parse_prix(r.get("prix_estimé"))
        entry = {
            "nom": r["nom"],
            "commune_hint": r.get("commune_hint", "Ngaba"),
            "adresse": r.get("adresse", ""),
            "description": r.get("description", ""),
            "telephone": r.get("telephone", ""),
            "email": r.get("email", ""),
            "services_list": [],
            "prix_min": prix_min,
            "prix_max": prix_max,
            "categorie_str": r.get("categorie", ""),
            "type_str": "",
            "url_image": None,
            "facebook": r.get("facebook"),
            "tiktok": r.get("tiktok"),
            "latitude": r.get("latitude"),
            "longitude": r.get("longitude"),
            "evaluation": r.get("evaluation"),
            "nombre_avis": r.get("nombre_avis"),
            "horaires": "",
            "type_cuisine": "",
            "nombre_chambres": "",
            "etoiles_str": "",
        }
        add(entry)

    # -----------------------------------------------------------------------
    # Source 2: lemba_commune_complete.json
    # -----------------------------------------------------------------------

    # Tourist sites (commune_hint="Lemba")
    lemba_sites = [
        {
            "nom": "Ravin de Lemba",
            "categorie_str": "Site naturel",
            "adresse": "Lemba, Kinshasa",
            "latitude": -4.393511, "longitude": 15.333047,
            "evaluation": None, "nombre_avis": None,
            "prix_estimé": "Gratuit/Libre",
            "horaires": "",
        },
        {
            "nom": "Percy Mulamba",
            "categorie_str": "Site naturel",
            "adresse": "Lemba, Kinshasa",
            "latitude": -4.3714268, "longitude": 15.3530707,
            "evaluation": 5.0, "nombre_avis": 1,
            "prix_estimé": "Gratuit",
            "horaires": "",
        },
        {
            "nom": "Tour de l'Échangeur",
            "categorie_str": "Monument",
            "adresse": "Échangeur de Limete, Kinshasa",
            "latitude": -4.374398, "longitude": 15.345267,
            "evaluation": 4.2, "nombre_avis": 214,
            "prix_estimé": "Gratuit",
            "horaires": "",
        },
        {
            "nom": "Ir Fils Mawete",
            "categorie_str": "Attraction",
            "adresse": "Lemba, Kinshasa",
            "telephone": "+243 839 682 706",
            "latitude": -4.4043942, "longitude": 15.3163556,
            "evaluation": None, "nombre_avis": None,
            "prix_estimé": "À vérifier",
            "horaires": "",
        },
        {
            "nom": "Espace Gladoluxe",
            "categorie_str": "Attraction",
            "adresse": "Lemba, Kinshasa",
            "latitude": -4.379951, "longitude": 15.352718,
            "evaluation": 3.3, "nombre_avis": 3,
            "prix_estimé": "$5-10",
            "horaires": "",
        },
        {
            "nom": "Ekenga Samuel",
            "categorie_str": "Attraction",
            "adresse": "Lemba, Kinshasa",
            "telephone": "+243 852 449 848",
            "latitude": -4.3782032, "longitude": 15.318260,
            "evaluation": 4.5, "nombre_avis": 2,
            "prix_estimé": "N/A",
            "horaires": "",
        },
        {
            "nom": "Rond Point Ngaba",
            "categorie_str": "Attraction",
            "adresse": "Rond-Point Ngaba, Kinshasa",
            "telephone": "+243 817 347 010",
            "latitude": -4.3760802, "longitude": 15.3236623,
            "evaluation": 4.3, "nombre_avis": 4,
            "prix_estimé": "N/A",
            "horaires": "",
        },
        {
            "nom": "Entre Cité Maman Mobutu",
            "categorie_str": "Site naturel",
            "adresse": "Cité Maman Mobutu, Lemba, Kinshasa",
            "latitude": -4.4448895, "longitude": 15.2934298,
            "evaluation": 3.5, "nombre_avis": 2,
            "prix_estimé": "N/A",
            "horaires": "Lun-Ven: 8:30-16:00 | Sam-Dim: Fermé",
        },
        {
            "nom": "Kasavubu Monument",
            "categorie_str": "Monument",
            "adresse": "Lemba, Kinshasa",
            "latitude": -4.3959962, "longitude": 15.356185,
            "evaluation": None, "nombre_avis": None,
            "prix_estimé": "Gratuit",
            "horaires": "",
        },
        {
            "nom": "Faustin Site",
            "categorie_str": "Attraction",
            "adresse": "Lemba, Kinshasa",
            "latitude": -4.3829896, "longitude": 15.315039,
            "evaluation": 5.0, "nombre_avis": 1,
            "prix_estimé": "N/A",
            "horaires": "",
        },
    ]

    for s in lemba_sites:
        prix_min, prix_max = parse_prix(s.get("prix_estimé"))
        add({
            "nom": s["nom"],
            "commune_hint": "Lemba",
            "adresse": s.get("adresse", "Lemba, Kinshasa"),
            "description": "",
            "telephone": s.get("telephone", ""),
            "services_list": [],
            "prix_min": prix_min,
            "prix_max": prix_max,
            "categorie_str": s.get("categorie_str", "Site naturel"),
            "type_str": "",
            "url_image": None,
            "facebook": None,
            "tiktok": None,
            "latitude": s.get("latitude"),
            "longitude": s.get("longitude"),
            "evaluation": s.get("evaluation"),
            "nombre_avis": s.get("nombre_avis"),
            "horaires": s.get("horaires", ""),
            "type_cuisine": "",
            "nombre_chambres": "",
            "etoiles_str": "",
        })

    # Lemba restaurants/bars
    lemba_restaurants = [
        {
            "nom": "B-Kin Bistro",
            "telephone": "+243 826 579 453",
            "latitude": -4.3782729, "longitude": 15.343476,
            "evaluation": 5.0, "nombre_avis": 7,
            "horaires": "Lun-Mar/Jeu: 8:30-21:30 | Mer/Ven: 8:00-21:30 | Sam: 8:00-22:00 | Dim: 8:30-21:30",
            "type_cuisine": "International",
            "prix_estimé": "$10-20",
            "categorie": "Restaurant",
        },
        {
            "nom": "Levantè",
            "telephone": "+243 979 333 332",
            "latitude": -4.3257743, "longitude": 15.275931,
            "evaluation": 4.4, "nombre_avis": 41,
            "type_cuisine": "Italienne",
            "prix_estimé": "$12-25",
            "categorie": "Restaurant",
            "horaires": "",
        },
        {
            "nom": "Meet Designers",
            "telephone": "+243 827 129 048",
            "latitude": -4.3976147, "longitude": 15.316470,
            "evaluation": 4.3, "nombre_avis": 3,
            "horaires": "Mar-Sam: 9:00-21:30 | Dim: 11:00-21:30 | Lun: Fermé",
            "prix_estimé": "$8-15",
            "categorie": "Restaurant",
            "type_cuisine": "",
        },
        {
            "nom": "Village SEBO",
            "telephone": "+243 818 689 703",
            "latitude": -4.383949, "longitude": 15.333337,
            "evaluation": 3.0, "nombre_avis": 1,
            "horaires": "Lun-Sam: 9:30-00:00",
            "type_cuisine": "Congolaise",
            "prix_estimé": "$10-18",
            "categorie": "Restaurant",
        },
        {
            "nom": "Restaurant Lemba",
            "telephone": "",
            "latitude": -4.386213, "longitude": 15.328099,
            "evaluation": 3.3, "nombre_avis": 6,
            "type_cuisine": "Congolaise",
            "prix_estimé": "$8-12",
            "categorie": "Restaurant",
            "horaires": "",
        },
        {
            "nom": "Le Fumoir",
            "telephone": "+243 990 718 473",
            "latitude": -4.3839079, "longitude": 15.332515,
            "evaluation": 5.0, "nombre_avis": 2,
            "horaires": "Lun-Dim: 12:00-00:33",
            "type_cuisine": "Grillée/BBQ",
            "prix_estimé": "$15-30",
            "categorie": "Restaurant",
        },
        {
            "nom": "Fête Parfaite",
            "telephone": "+243 823 906 110",
            "latitude": -4.3892235, "longitude": 15.334602,
            "evaluation": 5.0, "nombre_avis": 1,
            "type_cuisine": "Internationale",
            "prix_estimé": "$12-25",
            "categorie": "Restaurant",
            "horaires": "",
        },
        {
            "nom": "Club des Résidents",
            "telephone": "",
            "latitude": -4.4322682, "longitude": 15.310593,
            "evaluation": 3.3, "nombre_avis": 22,
            "horaires": "Lun-Sam: 8:00-22:00 | Dim: Fermé",
            "type_cuisine": "Africaine",
            "prix_estimé": "$10-20",
            "categorie": "Restaurant",
        },
        {
            "nom": "Le Dôme Aurora",
            "telephone": "",
            "latitude": -4.4221298, "longitude": 15.308202,
            "evaluation": 4.5, "nombre_avis": 4,
            "type_cuisine": "Internationale",
            "prix_estimé": "$12-22",
            "categorie": "Restaurant",
            "horaires": "",
        },
        {
            "nom": "Fox Lemba",
            "telephone": "+243 999 072 442",
            "latitude": -4.3800026, "longitude": 15.339087,
            "evaluation": 4.2, "nombre_avis": 14,
            "horaires": "Lun-Dim: 10:00-04:00",
            "type_cuisine": "Snacks/Drinks",
            "prix_estimé": "$5-15",
            "categorie": "Bar/Nightclub",
        },
        {
            "nom": "Aljo Club",
            "telephone": "+243 818 909 003",
            "latitude": -4.3794018, "longitude": 15.333577,
            "evaluation": 3.3, "nombre_avis": 3,
            "horaires": "Lun-Jeu/Ven: 14:00-23:30 | Sam-Dim: 24h",
            "prix_estimé": "$5-12",
            "categorie": "Lounge Bar",
            "type_cuisine": "",
        },
        {
            "nom": "Metro Bar Lemba",
            "telephone": "+243 811 501 111",
            "latitude": -4.382252, "longitude": 15.334248,
            "evaluation": 3.6, "nombre_avis": 7,
            "horaires": "Lun-Ven: 12:00-04:00",
            "prix_estimé": "$5-10",
            "categorie": "Bar",
            "type_cuisine": "",
        },
    ]

    for r in lemba_restaurants:
        prix_min, prix_max = parse_prix(r.get("prix_estimé"))
        add({
            "nom": r["nom"],
            "commune_hint": "Lemba",
            "adresse": "Lemba, Kinshasa",
            "description": "",
            "telephone": r.get("telephone", ""),
            "services_list": [],
            "prix_min": prix_min,
            "prix_max": prix_max,
            "categorie_str": r.get("categorie", "Restaurant"),
            "type_str": "",
            "url_image": None,
            "facebook": None,
            "tiktok": None,
            "latitude": r.get("latitude"),
            "longitude": r.get("longitude"),
            "evaluation": r.get("evaluation"),
            "nombre_avis": r.get("nombre_avis"),
            "horaires": r.get("horaires", ""),
            "type_cuisine": r.get("type_cuisine", ""),
            "nombre_chambres": "",
            "etoiles_str": "",
        })

    # Lemba hotels
    lemba_hotels = [
        {
            "nom": "IXORAS HOTEL LEMBA",
            "telephone": "+243 893 898 888",
            "latitude": -4.3794887, "longitude": 15.3348532,
            "evaluation": 3.8, "nombre_avis": 43,
            "services": ["Restaurant", "Wi-Fi", "Parking", "Service de chambre", "Petit-déjeuner inclus"],
            "etoiles": "3", "prix_estimé": "$45-80", "nb_chambres": "65+",
        },
        {
            "nom": "Hôtel Stella",
            "telephone": "+243 900 002 999",
            "latitude": -4.38416, "longitude": 15.3571995,
            "evaluation": 4.1, "nombre_avis": 76,
            "services": ["Restaurant", "Wi-Fi", "Parking", "Service de chambre", "Petit-déjeuner"],
            "etoiles": "3", "prix_estimé": "$50-95", "nb_chambres": "65+",
        },
        {
            "nom": "La Treizième",
            "telephone": "+243 827 043 522",
            "latitude": -4.3608932, "longitude": 15.3385257,
            "evaluation": 3.8, "nombre_avis": 24,
            "services": ["Restaurant", "Bar", "Wi-Fi", "Cable TV", "Mini-bar", "Musique live"],
            "etoiles": "3", "prix_estimé": "$40-80", "nb_chambres": "50+",
        },
        {
            "nom": "Mike's Flat Hotel",
            "telephone": "+243 829 358 218",
            "latitude": -4.3862047, "longitude": 15.3361339,
            "evaluation": 4.0, "nombre_avis": 19,
            "services": ["Restaurant", "Bar", "Wi-Fi", "Parking", "Service de chambre", "Event venue"],
            "etoiles": "4", "prix_estimé": "$70-120", "nb_chambres": "40+",
        },
        {
            "nom": "Les Béatitudes Hôtel",
            "telephone": "+243 815 103 112",
            "latitude": -4.3809059, "longitude": 15.3400242,
            "evaluation": 3.8, "nombre_avis": 65,
            "services": ["Restaurant", "Bar", "Gym", "Salle banquet", "Wi-Fi", "Parking", "Rooftop lounge"],
            "etoiles": "3", "prix_estimé": "$50-100", "nb_chambres": "80+",
        },
        {
            "nom": "Hotel Imperium",
            "telephone": "",
            "latitude": -4.4004092, "longitude": 15.3303407,
            "evaluation": 4.1, "nombre_avis": 13,
            "services": ["Restaurant", "Bar", "Wi-Fi", "Parking", "Service de chambre"],
            "etoiles": "3", "prix_estimé": "$45-85", "nb_chambres": "55+",
        },
        {
            "nom": "ABC Suite Hotel",
            "telephone": "",
            "latitude": -4.3748032, "longitude": 15.341262,
            "evaluation": 4.0, "nombre_avis": 2,
            "services": ["Restaurant", "Wi-Fi", "Parking", "Service de chambre"],
            "etoiles": "3", "prix_estimé": "$40-75", "nb_chambres": "45+",
        },
        {
            "nom": "Hôtel New Baron",
            "telephone": "+243 852 809 586",
            "latitude": -4.3921506, "longitude": 15.337458,
            "evaluation": 3.8, "nombre_avis": 6,
            "services": ["Restaurant", "Bar", "Piscine", "Wi-Fi", "Parking"],
            "etoiles": "3", "prix_estimé": "$40-80", "nb_chambres": "50+",
        },
        {
            "nom": "Aqua Inn",
            "telephone": "+243 999 960 222",
            "latitude": -4.3627669, "longitude": 15.352451,
            "evaluation": 3.3, "nombre_avis": 10,
            "services": ["Wi-Fi", "Parking"],
            "etoiles": "2", "prix_estimé": "$25-45", "nb_chambres": "35+",
        },
    ]

    for h in lemba_hotels:
        prix_min, prix_max = parse_prix(h.get("prix_estimé"))
        add({
            "nom": h["nom"],
            "commune_hint": "Lemba",
            "adresse": "Lemba, Kinshasa",
            "description": "",
            "telephone": h.get("telephone", ""),
            "services_list": h.get("services", []),
            "prix_min": prix_min,
            "prix_max": prix_max,
            "categorie_str": "hôtel",
            "type_str": "",
            "url_image": None,
            "facebook": None,
            "tiktok": None,
            "latitude": h.get("latitude"),
            "longitude": h.get("longitude"),
            "evaluation": h.get("evaluation"),
            "nombre_avis": h.get("nombre_avis"),
            "horaires": "",
            "type_cuisine": "",
            "nombre_chambres": h.get("nb_chambres", ""),
            "etoiles_str": h.get("etoiles", ""),
        })

    # -----------------------------------------------------------------------
    # Source 3: ligwala_hotels_restaurants_complete.json (commune_hint="Lingwala")
    # -----------------------------------------------------------------------

    lingwala_hotels = [
        {
            "nom": "Hôtel Stella",
            "commune_hint": "Lingwala",
            "telephone": "+243 900 002 999",
            "latitude": -4.38416, "longitude": 15.3571995,
            "evaluation": 4.1, "nombre_avis": 76,
            "services": ["Restaurant", "Wi-Fi", "Parking", "Service de chambre", "Petit-déjeuner"],
            "etoiles": "3", "prix_estimé": "$50-95", "nb_chambres": "65+",
        },
        {
            "nom": "AFRICANA PALACE",
            "commune_hint": "Lingwala",
            "telephone": "+243 825 616 958",
            "latitude": -4.3255162, "longitude": 15.3063152,
            "evaluation": 4.0, "nombre_avis": 155,
            "services": ["Restaurant", "Bar", "Gym", "Piscine", "Wi-Fi", "Parking", "Salle de banquet"],
            "etoiles": "4", "prix_estimé": "$80-150", "nb_chambres": "120+",
        },
        {
            "nom": "Hotel Eden 24 Novembre",
            "commune_hint": "Lingwala",
            "telephone": "+243 852 899 999",
            "latitude": -4.3258123, "longitude": 15.2957662,
            "evaluation": 4.8, "nombre_avis": 9,
            "services": [],
            "etoiles": "3", "prix_estimé": "$55-100", "nb_chambres": "50+",
        },
        {
            "nom": "Hôtel Finesse 3",
            "commune_hint": "Lingwala",
            "telephone": "+242 06 402 8437",
            "latitude": -4.3195318, "longitude": 15.2983039,
            "evaluation": 3.8, "nombre_avis": 4,
            "services": [],
            "etoiles": "2", "prix_estimé": "$35-60", "nb_chambres": "30+",
        },
        {
            "nom": "Emilton Hotel",
            "commune_hint": "Lingwala",
            "telephone": "+243 834 615 068",
            "latitude": -4.3266769, "longitude": 15.2991859,
            "evaluation": 3.6, "nombre_avis": 10,
            "services": [],
            "etoiles": "2", "prix_estimé": "$35-65", "nb_chambres": "40+",
        },
        {
            "nom": "Hotel Everest RD CONGO",
            "commune_hint": "Lingwala",
            "telephone": "+243 829 243 160",
            "latitude": -4.3253302, "longitude": 15.3069524,
            "evaluation": 3.7, "nombre_avis": 44,
            "services": ["Restaurant", "Bar", "Wi-Fi", "Parking", "Band/Musique"],
            "etoiles": "3", "prix_estimé": "$50-90", "nb_chambres": "60+",
        },
        {
            "nom": "Hôtel Invest",
            "commune_hint": "Lingwala",
            "telephone": "+243 852 493 571",
            "latitude": -4.3297849, "longitude": 15.300087,
            "evaluation": 3.7, "nombre_avis": 47,
            "services": ["Restaurant/Outdoor", "Bar", "Piscine", "Gym", "Wi-Fi", "Parking", "Jardin"],
            "etoiles": "3", "prix_estimé": "$60-110", "nb_chambres": "70+",
        },
        {
            "nom": "Hotel Pour Vous",
            "commune_hint": "Lingwala",
            "telephone": "+243 891 008 786",
            "latitude": -4.3045822, "longitude": 15.3120894,
            "evaluation": 3.8, "nombre_avis": 50,
            "services": [],
            "etoiles": "2", "prix_estimé": "$35-65", "nb_chambres": "45+",
        },
        {
            "nom": "Carpe Diem Hotel Kinshasa",
            "commune_hint": "Lingwala",
            "telephone": "+243 814 360 590",
            "latitude": -4.326293, "longitude": 15.2989855,
            "evaluation": 3.7, "nombre_avis": 21,
            "services": ["Restaurant", "Lounge bar", "Piscine", "Wi-Fi", "Parking", "Salle de fonction"],
            "etoiles": "3", "prix_estimé": "$50-95", "nb_chambres": "55+",
        },
        {
            "nom": "IXORAS HOTEL VICTOIRE",
            "commune_hint": "Kalamu",
            "telephone": "+243 896 628 888",
            "latitude": -4.341446, "longitude": 15.31588,
            "evaluation": 3.6, "nombre_avis": 28,
            "services": [],
            "etoiles": "3", "prix_estimé": "$50-90", "nb_chambres": "70+",
        },
        {
            "nom": "Hotel Golf Coast",
            "commune_hint": "Lingwala",
            "telephone": "+243 999 992 606",
            "latitude": -4.3131028, "longitude": 15.2925323,
            "evaluation": 4.4, "nombre_avis": 52,
            "services": [],
            "etoiles": "3", "prix_estimé": "$60-105", "nb_chambres": "80+",
        },
        {
            "nom": "Eriges Lodge",
            "commune_hint": "Lingwala",
            "telephone": "+243 827 851 854",
            "latitude": -4.3133415, "longitude": 15.289802,
            "evaluation": 3.7, "nombre_avis": 35,
            "services": [],
            "etoiles": "3", "prix_estimé": "$45-85", "nb_chambres": "50+",
        },
        {
            "nom": "Flat Hotel Kandolo Gombe",
            "commune_hint": "Gombe",
            "telephone": "+243 843 297 575",
            "latitude": -4.3201199, "longitude": 15.2729976,
            "evaluation": 3.9, "nombre_avis": 11,
            "services": [],
            "etoiles": "3", "prix_estimé": "$40-75", "nb_chambres": "40+",
        },
        {
            "nom": "Hotel Amani Inn",
            "commune_hint": "Lingwala",
            "telephone": "+243 830 073 843",
            "latitude": -4.3327734, "longitude": 15.3161752,
            "evaluation": 4.5, "nombre_avis": 4,
            "services": [],
            "etoiles": "4", "prix_estimé": "$70-120", "nb_chambres": "45+",
        },
    ]

    for h in lingwala_hotels:
        prix_min, prix_max = parse_prix(h.get("prix_estimé"))
        add({
            "nom": h["nom"],
            "commune_hint": h.get("commune_hint", "Lingwala"),
            "adresse": f"{h.get('commune_hint', 'Lingwala')}, Kinshasa",
            "description": "",
            "telephone": h.get("telephone", ""),
            "services_list": h.get("services", []),
            "prix_min": prix_min,
            "prix_max": prix_max,
            "categorie_str": "hôtel",
            "type_str": "",
            "url_image": None,
            "facebook": None,
            "tiktok": None,
            "latitude": h.get("latitude"),
            "longitude": h.get("longitude"),
            "evaluation": h.get("evaluation"),
            "nombre_avis": h.get("nombre_avis"),
            "horaires": "",
            "type_cuisine": "",
            "nombre_chambres": h.get("nb_chambres", ""),
            "etoiles_str": h.get("etoiles", ""),
        })

    # Lingwala restaurants
    lingwala_restaurants = [
        {
            "nom": "Le Z Restaurant & Lounge",
            "telephone": "+243 828 664 628",
            "latitude": -4.3094647, "longitude": 15.2917054,
            "evaluation": 4.3, "nombre_avis": 25,
            "horaires": "Mar/Mer/Ven: 12:00-01:00 | Jeu/Sam: 15:00-01:00 | Lun: Fermé | Dim: 12:00-01:00",
            "type_cuisine": "Afro-fusion",
            "prix_estimé": "$15-30",
            "categorie": "Restaurant",
        },
        {
            "nom": "MALAMU",
            "telephone": "+243 820 625 268",
            "latitude": -4.3076193, "longitude": 15.2884453,
            "evaluation": 4.1, "nombre_avis": 143,
            "horaires": "Mar-Dim: 12:00-00:00 | Lun: Fermé",
            "type_cuisine": "Congolaise",
            "prix_estimé": "$12-25",
            "categorie": "Restaurant",
        },
        {
            "nom": "Nzungu ya maman",
            "telephone": "+243 821 063 838",
            "latitude": -4.3187625, "longitude": 15.2959844,
            "evaluation": 5.0, "nombre_avis": 1,
            "horaires": "Lun-Dim: 12:00-22:30",
            "type_cuisine": "Congolaise",
            "prix_estimé": "$10-20",
            "categorie": "Restaurant",
        },
        {
            "nom": "O Poeta",
            "telephone": "+243 819 922 909",
            "latitude": -4.310200, "longitude": 15.2913859,
            "evaluation": 4.1, "nombre_avis": 331,
            "horaires": "Lun-Sam: 7:30-23:00 | Dim: 10:30-22:30",
            "type_cuisine": "Italienne/Congolaise",
            "prix_estimé": "$12-22",
            "categorie": "Restaurant",
        },
        {
            "nom": "Cook's Bistro",
            "telephone": "+243 858 566 034",
            "latitude": -4.3154824, "longitude": 15.291989,
            "evaluation": 4.2, "nombre_avis": 46,
            "type_cuisine": "Tunisienne",
            "prix_estimé": "$15-28",
            "categorie": "Restaurant",
            "horaires": "",
        },
        {
            "nom": "Levantè",
            "telephone": "+243 979 333 332",
            "latitude": -4.3257743, "longitude": 15.275931,
            "evaluation": 4.4, "nombre_avis": 41,
            "type_cuisine": "Italienne",
            "prix_estimé": "$12-25",
            "categorie": "Restaurant",
            "horaires": "",
        },
        {
            "nom": "Jemi's Cuisine",
            "telephone": "+243 999 909 365",
            "latitude": -4.3139506, "longitude": 15.2760979,
            "evaluation": 4.6, "nombre_avis": 125,
            "horaires": "Lun-Jeu: 13:00-23:55 | Ven-Sam: 13:00-00:30 | Dim: 13:00-00:30",
            "type_cuisine": "Asiatique",
            "prix_estimé": "$20-35",
            "categorie": "Restaurant",
        },
        {
            "nom": "Wabi Sabi",
            "telephone": "+243 900 000 702",
            "latitude": -4.302239, "longitude": 15.310593,
            "evaluation": 4.4, "nombre_avis": 127,
            "horaires": "Mar-Sam: 12:00-01:00 | Dim: 12:00-01:00 | Lun: Fermé",
            "type_cuisine": "Pan-asiatique",
            "prix_estimé": "$25-40",
            "categorie": "Restaurant",
        },
        {
            "nom": "La Case Resto-Grill",
            "telephone": "+243 812 420 260",
            "latitude": -4.3268295, "longitude": 15.2959604,
            "evaluation": 4.1, "nombre_avis": 15,
            "horaires": "24h/24",
            "type_cuisine": "Grillée",
            "prix_estimé": "$12-25",
            "categorie": "Restaurant",
        },
        {
            "nom": "Maison Des Mezzes",
            "telephone": "+243 818 998 621",
            "latitude": -4.3072613, "longitude": 15.2967362,
            "evaluation": 4.4, "nombre_avis": 45,
            "horaires": "Lun-Dim: 9:00-23:00",
            "type_cuisine": "Grecque",
            "prix_estimé": "$15-25",
            "categorie": "Restaurant",
        },
        {
            "nom": "Cafe Roots",
            "telephone": "+243 850 530 225",
            "latitude": -4.301159, "longitude": 15.3106096,
            "evaluation": 4.2, "nombre_avis": 102,
            "horaires": "Lun-Dim: 6:30-22:00",
            "type_cuisine": "International",
            "prix_estimé": "$10-18",
            "categorie": "Café/Restaurant",
        },
        {
            "nom": "Ex Ça va bien",
            "telephone": "+243 820 061 001",
            "latitude": -4.3312835, "longitude": 15.300321,
            "evaluation": 5.0, "nombre_avis": 1,
            "horaires": "Lun-Sam: 9:00-22:00 | Dim: 12:00-22:00",
            "type_cuisine": "International",
            "prix_estimé": "$10-20",
            "categorie": "Restaurant",
        },
        {
            "nom": "Restaurant les Présages",
            "telephone": "+243 898 268 610",
            "latitude": -4.3211026, "longitude": 15.294726,
            "evaluation": 4.5, "nombre_avis": 4,
            "horaires": "24h/24",
            "type_cuisine": "Congolaise",
            "prix_estimé": "$10-18",
            "categorie": "Restaurant",
        },
        {
            "nom": "SMOKIN' HUT & SIPS",
            "telephone": "+243 999 998 632",
            "latitude": -4.3153884, "longitude": 15.2918965,
            "evaluation": 4.5, "nombre_avis": 4,
            "horaires": "Lun-Ven: 10:00-22:00 | Sam-Dim: 10:00-23:00",
            "type_cuisine": "Burgers/Snacks",
            "prix_estimé": "$8-15",
            "categorie": "Restaurant",
        },
        {
            "nom": "Restaurant Honoré",
            "telephone": "",
            "latitude": -4.3268726, "longitude": 15.3019378,
            "evaluation": 5.0, "nombre_avis": 1,
            "horaires": "Lun-Ven: 8:00-22:00",
            "type_cuisine": "International",
            "prix_estimé": "$12-20",
            "categorie": "Restaurant",
        },
        {
            "nom": "Le Colibri",
            "telephone": "+243 810 452 604",
            "latitude": -4.305001, "longitude": 15.296258,
            "evaluation": 4.2, "nombre_avis": 34,
            "horaires": "Lun-Sam: 11:00-23:00 | Dim: 15:00-23:00",
            "type_cuisine": "International",
            "prix_estimé": "$10-20",
            "categorie": "Restaurant",
        },
        {
            "nom": "Le kebab kinois",
            "telephone": "+243 897 229 453",
            "latitude": -4.3223394, "longitude": 15.3006436,
            "evaluation": 2.8, "nombre_avis": 21,
            "horaires": "Lun-Sam: 9:00-22:00 | Dim: 13:00-20:00",
            "type_cuisine": "Kebab/Middle Eastern",
            "prix_estimé": "$8-15",
            "categorie": "Bar/Restaurant",
        },
        {
            "nom": "Muka_kin01 Resto-Bar",
            "telephone": "+243 991 231 015",
            "latitude": -4.3222398, "longitude": 15.3106212,
            "evaluation": 4.8, "nombre_avis": 18,
            "horaires": "Lun-Dim: 8:30-23:00",
            "type_cuisine": "Congolaise",
            "prix_estimé": "$12-22",
            "categorie": "Restaurant",
        },
        {
            "nom": "La Citadelle Restaurent & Lounge",
            "telephone": "+243 852 160 053",
            "latitude": -4.3190438, "longitude": 15.292599,
            "evaluation": 5.0, "nombre_avis": 3,
            "horaires": "Lun-Dim: 10:00-00:00",
            "type_cuisine": "Africaine/Congolaise",
            "prix_estimé": "$15-28",
            "categorie": "Restaurant",
        },
    ]

    for r in lingwala_restaurants:
        prix_min, prix_max = parse_prix(r.get("prix_estimé"))
        add({
            "nom": r["nom"],
            "commune_hint": "Lingwala",
            "adresse": "Lingwala, Kinshasa",
            "description": "",
            "telephone": r.get("telephone", ""),
            "services_list": [],
            "prix_min": prix_min,
            "prix_max": prix_max,
            "categorie_str": r.get("categorie", "Restaurant"),
            "type_str": "",
            "url_image": None,
            "facebook": None,
            "tiktok": None,
            "latitude": r.get("latitude"),
            "longitude": r.get("longitude"),
            "evaluation": r.get("evaluation"),
            "nombre_avis": r.get("nombre_avis"),
            "horaires": r.get("horaires", ""),
            "type_cuisine": r.get("type_cuisine", ""),
            "nombre_chambres": "",
            "etoiles_str": "",
        })

    # -----------------------------------------------------------------------
    # Source 4: kinshasa_hotels_100.json (various communes - detect from adresse)
    # -----------------------------------------------------------------------

    kinshasa_hotels = [
        {
            "nom": "Pullman Kinshasa Grand Hotel",
            "adresse": "4, 9535 Av. des Batetela, Kinshasa",
            "telephone": "+243 858 000 111",
            "latitude": -4.312448, "longitude": 15.273440,
            "evaluation": 4.8, "nombre_avis": 7218,
            "services": ["Restaurant", "Bar", "Piscine", "Spa", "Salle de gym", "Wi-Fi", "Parking", "Service de chambre 24h"],
            "etoiles": "5", "prix_estimé": "$150-250", "nb_chambres": "200+",
        },
        {
            "nom": "Hilton Kinshasa",
            "adresse": "10 Ave Wagenia, Kinshasa",
            "telephone": "+243 815 590 080",
            "latitude": -4.298516, "longitude": 15.312124,
            "evaluation": 4.7, "nombre_avis": 669,
            "services": ["Restaurant", "Bars (3)", "Lounges (2)", "Rooftop Lounge", "Piscine", "Salle de gym", "Wi-Fi", "Parking", "Service de chambre", "Business center"],
            "etoiles": "4", "prix_estimé": "$120-200", "nb_chambres": "180+",
        },
        {
            "nom": "Fleuve Congo Hotel by Blazon Hotels",
            "adresse": "119 Bd Colonel Tshatshi, Kinshasa",
            "telephone": "+243 808 500 600",
            "latitude": -4.312714, "longitude": 15.270329,
            "evaluation": 4.4, "nombre_avis": 827,
            "services": [],
            "etoiles": "4", "prix_estimé": "$100-180", "nb_chambres": "150+",
        },
        {
            "nom": "Hotel Memling",
            "adresse": "5D, Avenue de la Republique du Tchad, Kinshasa",
            "telephone": "+243 817 001 111",
            "latitude": -4.304039, "longitude": 15.311930,
            "evaluation": 4.1, "nombre_avis": 564,
            "services": [],
            "etoiles": "3", "prix_estimé": "$70-120", "nb_chambres": "80+",
        },
        {
            "nom": "Kin Plaza Arjaan by Rotana",
            "adresse": "Gombe, Kinshasa",
            "telephone": "+243 818 978 888",
            "latitude": -4.318661, "longitude": 15.274283,
            "evaluation": 4.2, "nombre_avis": 498,
            "services": [],
            "etoiles": "4", "prix_estimé": "$90-150", "nb_chambres": "120+",
        },
        {
            "nom": "LUNTU HOTEL",
            "adresse": "Gombe, Kinshasa",
            "telephone": "+243 811 451 899",
            "latitude": -4.327006, "longitude": 15.272889,
            "evaluation": 3.9, "nombre_avis": 30,
            "services": [],
            "etoiles": "3", "prix_estimé": "$60-100", "nb_chambres": "70+",
        },
        {
            "nom": "Hotel Royal",
            "adresse": "Gombe, Kinshasa",
            "telephone": "+243 815 555 666",
            "latitude": -4.305899, "longitude": 15.305885,
            "evaluation": 4.0, "nombre_avis": 243,
            "services": [],
            "etoiles": "3", "prix_estimé": "$50-90", "nb_chambres": "100+",
        },
        {
            "nom": "Novotel Kinshasa La Gombe",
            "adresse": "76 Ave Bandundu, Kinshasa",
            "telephone": "+243 840 655 111",
            "latitude": -4.304059, "longitude": 15.305191,
            "evaluation": 4.6, "nombre_avis": 1016,
            "services": [],
            "etoiles": "4", "prix_estimé": "$80-140", "nb_chambres": "140+",
        },
        {
            "nom": "Béatrice Hotel",
            "adresse": "Gombe, Kinshasa",
            "telephone": "+243 812 535 000",
            "latitude": -4.300232, "longitude": 15.317538,
            "evaluation": 3.6, "nombre_avis": 236,
            "services": [],
            "etoiles": "3", "prix_estimé": "$55-95", "nb_chambres": "110+",
        },
        {
            "nom": "Sultani Hotel",
            "adresse": "Gombe, Kinshasa",
            "telephone": "+243 897 000 113",
            "latitude": -4.308360, "longitude": 15.289927,
            "evaluation": 3.8, "nombre_avis": 226,
            "services": [],
            "etoiles": "3", "prix_estimé": "$50-85", "nb_chambres": "90+",
        },
        {
            "nom": "Hotel Kirikou",
            "adresse": "Gombe, Kinshasa",
            "telephone": "+243 991 307 377",
            "latitude": -4.305919, "longitude": 15.314474,
            "evaluation": 3.8, "nombre_avis": 13,
            "services": [],
            "etoiles": "3", "prix_estimé": "$40-70", "nb_chambres": "50+",
        },
        {
            "nom": "Cana Hotel",
            "adresse": "Gombe, Kinshasa",
            "telephone": "+243 998 881 448",
            "latitude": -4.313920, "longitude": 15.285520,
            "evaluation": 3.2, "nombre_avis": 55,
            "services": ["Restaurant", "Bar", "Piscine", "Billard", "WiFi", "Parking"],
            "etoiles": "2", "prix_estimé": "$30-60", "nb_chambres": "60+",
        },
        {
            "nom": "Hôtel Chez Belle Vie",
            "adresse": "Gombe, Kinshasa",
            "telephone": "+243 816 367 421",
            "latitude": -4.306679, "longitude": 15.295523,
            "evaluation": 3.3, "nombre_avis": 53,
            "services": [],
            "etoiles": "2", "prix_estimé": "$25-50", "nb_chambres": "40+",
        },
        {
            "nom": "Guest House Sunny Day",
            "adresse": "Gombe, Kinshasa",
            "telephone": "+243 999 906 425",
            "latitude": -4.308036, "longitude": 15.287888,
            "evaluation": 4.1, "nombre_avis": 9,
            "services": [],
            "etoiles": "3", "prix_estimé": "$45-75", "nb_chambres": "25+",
        },
        {
            "nom": "Hotel Ka-Be De luxe",
            "adresse": "66, Avenue Maringa Q.Mudiba, C. Kanshi, Kasa-Vubu, Kinshasa",
            "telephone": "+243 834 935 203",
            "latitude": -4.342156, "longitude": 15.308548,
            "evaluation": 3.3, "nombre_avis": 15,
            "services": [],
            "etoiles": "2", "prix_estimé": "$30-55", "nb_chambres": "35+",
        },
        {
            "nom": "Villa Abis",
            "adresse": "7 Av. SNEL, Kinshasa",
            "telephone": "",
            "latitude": -4.440297, "longitude": 15.247586,
            "evaluation": 2.8, "nombre_avis": 5,
            "services": [],
            "etoiles": "1", "prix_estimé": "$20-40", "nb_chambres": "8+",
        },
        {
            "nom": "Hotel Pour Vous",
            "adresse": "Lingwala, Kinshasa",
            "telephone": "+243 891 008 786",
            "latitude": -4.3045822, "longitude": 15.3120894,
            "evaluation": 3.8, "nombre_avis": 50,
            "services": [],
            "etoiles": "2", "prix_estimé": "$35-65", "nb_chambres": "45+",
        },
        {
            "nom": "La Treizième",
            "adresse": "Lemba, Kinshasa",
            "telephone": "+243 827 043 522",
            "latitude": -4.3608932, "longitude": 15.3385257,
            "evaluation": 3.8, "nombre_avis": 24,
            "services": ["Restaurant", "Bar", "Wi-Fi", "Cable TV", "Mini-bar", "Musique live"],
            "etoiles": "3", "prix_estimé": "$40-80", "nb_chambres": "50+",
        },
        {
            "nom": "Leon Hotel",
            "adresse": "Gombe, Kinshasa",
            "telephone": "+243 813 209 121",
            "latitude": -4.303098, "longitude": 15.313903,
            "evaluation": 4.0, "nombre_avis": 422,
            "services": ["Restaurant (2)", "Bar", "Piscine", "Gym", "Wi-Fi", "Parking", "Service de chambre", "Business center"],
            "etoiles": "3", "prix_estimé": "$60-110", "nb_chambres": "100+",
        },
        {
            "nom": "Hotel Belle Vie",
            "adresse": "Gombe, Kinshasa",
            "telephone": "+243 976 050 000",
            "latitude": -4.304865, "longitude": 15.315393,
            "evaluation": 3.7, "nombre_avis": 147,
            "services": [],
            "etoiles": "3", "prix_estimé": "$55-100", "nb_chambres": "85+",
        },
        {
            "nom": "Ixoras Hotel",
            "adresse": "Av. Ixoras n° 382, 7ème rue, C/Limetté Q/Résidentiel, Kinshasa",
            "telephone": "+243 817 081 255",
            "latitude": -4.351661, "longitude": 15.333827,
            "evaluation": 4.0, "nombre_avis": 50,
            "services": [],
            "etoiles": "3", "prix_estimé": "$45-85", "nb_chambres": "70+",
        },
        {
            "nom": "O'Castelo Hotel",
            "adresse": "Gombe, Kinshasa",
            "telephone": "+39 347 119 1965",
            "latitude": -4.323416, "longitude": 15.281573,
            "evaluation": 3.9, "nombre_avis": 49,
            "services": [],
            "etoiles": "3", "prix_estimé": "$40-75", "nb_chambres": "60+",
        },
        {
            "nom": "Aqua Inn",
            "adresse": "Lemba, Kinshasa",
            "telephone": "+243 999 960 222",
            "latitude": -4.3627669, "longitude": 15.352451,
            "evaluation": 3.3, "nombre_avis": 10,
            "services": ["Wi-Fi", "Parking"],
            "etoiles": "2", "prix_estimé": "$25-45", "nb_chambres": "35+",
        },
        {
            "nom": "SAPHIR HOTEL",
            "adresse": "Rue Ikelemba, Q/Matonge, Kinshasa",
            "telephone": "+243 816 008 000",
            "latitude": -4.342169, "longitude": 15.313767,
            "evaluation": 3.9, "nombre_avis": 8,
            "services": [],
            "etoiles": "3", "prix_estimé": "$35-60", "nb_chambres": "45+",
        },
        {
            "nom": "Hotel Selton",
            "adresse": "Gombe, Kinshasa",
            "telephone": "+243 810 661 880",
            "latitude": -4.306528, "longitude": 15.305752,
            "evaluation": 4.1, "nombre_avis": 169,
            "services": [],
            "etoiles": "3", "prix_estimé": "$55-100", "nb_chambres": "90+",
        },
        {
            "nom": "Relax Hotel",
            "adresse": "Gombe, Kinshasa",
            "telephone": "+243 897 000 045",
            "latitude": -4.304058, "longitude": 15.315964,
            "evaluation": 3.7, "nombre_avis": 46,
            "services": [],
            "etoiles": "3", "prix_estimé": "$40-75", "nb_chambres": "55+",
        },
        {
            "nom": "Protea Hotel by Marriott Kinshasa",
            "adresse": "Gombe, Kinshasa",
            "telephone": "+243 808 567 777",
            "latitude": -4.302673, "longitude": 15.298797,
            "evaluation": 4.5, "nombre_avis": 59,
            "services": [],
            "etoiles": "4", "prix_estimé": "$100-170", "nb_chambres": "130+",
        },
        {
            "nom": "Four Points by Sheraton Kinshasa",
            "adresse": "Gombe, Kinshasa",
            "telephone": "+243 808 557 777",
            "latitude": -4.306303, "longitude": 15.295841,
            "evaluation": 4.7, "nombre_avis": 27,
            "services": [],
            "etoiles": "4", "prix_estimé": "$110-180", "nb_chambres": "140+",
        },
        {
            "nom": "Hôtel Stella",
            "adresse": "Lemba, Kinshasa",
            "telephone": "+243 900 002 999",
            "latitude": -4.38416, "longitude": 15.3571995,
            "evaluation": 4.1, "nombre_avis": 76,
            "services": ["Restaurant", "Wi-Fi", "Parking", "Service de chambre", "Petit-déjeuner"],
            "etoiles": "3", "prix_estimé": "$50-95", "nb_chambres": "65+",
        },
        {
            "nom": "Hôtel Indigo",
            "adresse": "Kinshasa",
            "telephone": "",
            "latitude": -4.392202, "longitude": 15.375679,
            "evaluation": 3.6, "nombre_avis": 38,
            "services": [],
            "etoiles": "2", "prix_estimé": "$30-60", "nb_chambres": "40+",
        },
        {
            "nom": "Golden Tulip Kin-Oasis Kinshasa",
            "adresse": "Cite Kin-Oasis, Ave Kasa-Vubu, Kinshasa",
            "telephone": "+243 857 688 888",
            "latitude": -4.346644, "longitude": 15.290075,
            "evaluation": 4.7, "nombre_avis": 59,
            "services": [],
            "etoiles": "4", "prix_estimé": "$90-150", "nb_chambres": "120+",
        },
        {
            "nom": "Hôtel Eden",
            "adresse": "Gombe, Kinshasa",
            "telephone": "+243 900 992 111",
            "latitude": -4.324720, "longitude": 15.286399,
            "evaluation": 4.6, "nombre_avis": 21,
            "services": [],
            "etoiles": "3", "prix_estimé": "$45-85", "nb_chambres": "50+",
        },
        {
            "nom": "SULTANI RIVER HÔTEL",
            "adresse": "Gombe, Kinshasa",
            "telephone": "+243 897 000 132",
            "latitude": -4.330893, "longitude": 15.258631,
            "evaluation": 3.8, "nombre_avis": 48,
            "services": [],
            "etoiles": "3", "prix_estimé": "$50-90", "nb_chambres": "75+",
        },
        {
            "nom": "KertelSuites",
            "adresse": "Gombe, Kinshasa",
            "telephone": "+243 990 999 957",
            "latitude": -4.303285, "longitude": 15.306875,
            "evaluation": 4.5, "nombre_avis": 40,
            "services": [],
            "etoiles": "4", "prix_estimé": "$100-160", "nb_chambres": "100+",
        },
        {
            "nom": "Hotel Platinum",
            "adresse": "Gombe, Kinshasa",
            "telephone": "+243 999 936 553",
            "latitude": -4.306374, "longitude": 15.316124,
            "evaluation": 4.1, "nombre_avis": 169,
            "services": [],
            "etoiles": "3", "prix_estimé": "$55-100", "nb_chambres": "95+",
        },
        {
            "nom": "Hotel Golf Coast",
            "adresse": "Lingwala, Kinshasa",
            "telephone": "+243 999 992 606",
            "latitude": -4.3131028, "longitude": 15.2925323,
            "evaluation": 4.4, "nombre_avis": 52,
            "services": [],
            "etoiles": "3", "prix_estimé": "$60-105", "nb_chambres": "80+",
        },
        {
            "nom": "Flat Hotel Kandolo Gombe",
            "adresse": "Gombe, Kinshasa",
            "telephone": "+243 843 297 575",
            "latitude": -4.3201199, "longitude": 15.2729976,
            "evaluation": 3.9, "nombre_avis": 11,
            "services": [],
            "etoiles": "3", "prix_estimé": "$40-75", "nb_chambres": "40+",
        },
        {
            "nom": "IXORAS HOTEL VICTOIRE",
            "adresse": "Kalamu, Kinshasa",
            "telephone": "+243 896 628 888",
            "latitude": -4.341446, "longitude": 15.31588,
            "evaluation": 3.6, "nombre_avis": 28,
            "services": [],
            "etoiles": "3", "prix_estimé": "$50-90", "nb_chambres": "70+",
        },
        {
            "nom": "IXORAS HOTEL LEMBA",
            "adresse": "Lemba, Kinshasa",
            "telephone": "+243 893 898 888",
            "latitude": -4.3794887, "longitude": 15.3348532,
            "evaluation": 3.8, "nombre_avis": 43,
            "services": ["Restaurant", "Wi-Fi", "Parking", "Service de chambre", "Petit-déjeuner inclus"],
            "etoiles": "3", "prix_estimé": "$45-80", "nb_chambres": "65+",
        },
    ]

    for h in kinshasa_hotels:
        prix_min, prix_max = parse_prix(h.get("prix_estimé"))
        commune = detect_commune(h.get("adresse", ""), h.get("commune_hint"))
        add({
            "nom": h["nom"],
            "commune_hint": commune,
            "adresse": h.get("adresse", "Kinshasa"),
            "description": "",
            "telephone": h.get("telephone", ""),
            "services_list": h.get("services", []),
            "prix_min": prix_min,
            "prix_max": prix_max,
            "categorie_str": "hôtel",
            "type_str": "",
            "url_image": None,
            "facebook": None,
            "tiktok": None,
            "latitude": h.get("latitude"),
            "longitude": h.get("longitude"),
            "evaluation": h.get("evaluation"),
            "nombre_avis": h.get("nombre_avis"),
            "horaires": "",
            "type_cuisine": "",
            "nombre_chambres": h.get("nb_chambres", ""),
            "etoiles_str": h.get("etoiles", ""),
        })

    # -----------------------------------------------------------------------
    # Source 5: kinshasa_tourism_data.json
    # -----------------------------------------------------------------------

    # Tourist sites
    kinshasa_sites = [
        {
            "nom": "Grande Roue De Kinshasa",
            "adresse": "2 Ave Isiro, Kinshasa",
            "telephone": "+243 854 163 963",
            "latitude": -4.3013655, "longitude": 15.317212,
            "evaluation": 3.8, "nombre_avis": 38,
            "horaires": "",
            "categorie": "Attraction",
        },
        {
            "nom": "Musée National de la RDC",
            "adresse": "Kinshasa",
            "telephone": "+243 814 932 524",
            "latitude": -4.3352625, "longitude": 15.299359,
            "evaluation": 4.1, "nombre_avis": 422,
            "horaires": "Mar-Dim: 9:00-17:30 | Lun: Fermé",
            "categorie": "Musée",
        },
        {
            "nom": "Mbudi Nature",
            "adresse": "J5QM+FGC, Brazzaville, RDC",
            "telephone": "+243 810 136 517",
            "latitude": -4.3613009, "longitude": 15.183771,
            "evaluation": 3.8, "nombre_avis": 121,
            "horaires": "Lun-Dim: 8:00-21:30",
            "categorie": "Parc",
            "commune_hint": "Ngaliema",
        },
        {
            "nom": "Congo Tours",
            "adresse": "Kinshasa",
            "telephone": "+243 858 352 414",
            "latitude": -4.2994037, "longitude": 15.3180369,
            "evaluation": 4.8, "nombre_avis": 9,
            "horaires": "Lun: 8:30-17:30 | Mar-Ven: 8:30-17:00 | Sam: 8:30-15:30 | Dim: Fermé",
            "categorie": "Agence",
        },
        {
            "nom": "Place de l'Indépendance",
            "adresse": "Kinshasa",
            "telephone": "+243 825 690 005",
            "latitude": -4.3014049, "longitude": 15.317035,
            "evaluation": 3.6, "nombre_avis": 7,
            "horaires": "24h/24",
            "categorie": "Monument",
        },
        {
            "nom": "Africa Park Aventure",
            "adresse": "Lac Ma, Vallee, Kinshasa",
            "telephone": "+243 825 001 115",
            "latitude": -4.493240, "longitude": 15.281603,
            "evaluation": 4.1, "nombre_avis": 93,
            "horaires": "8:00-20:00",
            "categorie": "Parc",
            "commune_hint": "Mont-Ngafula",
        },
        {
            "nom": "King's Beach",
            "adresse": "Route de matadi, Kinshasa",
            "telephone": "+243 821 583 115",
            "latitude": -4.499350, "longitude": 15.203392,
            "evaluation": 4.4, "nombre_avis": 11,
            "horaires": "",
            "categorie": "Plage",
            "commune_hint": "Mont-Ngafula",
        },
        {
            "nom": "Home of Patrice Lumumba",
            "adresse": "Kinshasa",
            "telephone": "",
            "latitude": -4.307524, "longitude": 15.292915,
            "evaluation": None, "nombre_avis": None,
            "horaires": "",
            "categorie": "Monument",
        },
        {
            "nom": "Symphonies Naturelles",
            "adresse": "Zamba ya Nda-Ngye, Kinshasa",
            "telephone": "+243 815 523 118",
            "latitude": -4.366472, "longitude": 15.230279,
            "evaluation": 5.0, "nombre_avis": 4,
            "horaires": "Lun-Dim: 8:00-17:00",
            "categorie": "Parc",
            "commune_hint": "Ngaliema",
        },
        {
            "nom": "Kinshasa Zoo",
            "adresse": "1 Avenue Kasa-Vubu, Kinshasa",
            "telephone": "",
            "latitude": -4.310795, "longitude": 15.306899,
            "evaluation": 3.4, "nombre_avis": 131,
            "horaires": "Lun-Dim: 7:00-18:00",
            "categorie": "Zoo",
        },
        {
            "nom": "Institut des Musées Nationaux",
            "adresse": "Kinshasa",
            "telephone": "+243 821 495 702",
            "latitude": -4.335471, "longitude": 15.299647,
            "evaluation": 4.4, "nombre_avis": 7,
            "horaires": "",
            "categorie": "Musée",
        },
        {
            "nom": "Musée National de Rumba",
            "adresse": "Kinshasa",
            "telephone": "",
            "latitude": -4.353786, "longitude": 15.256052,
            "evaluation": None, "nombre_avis": None,
            "horaires": "",
            "categorie": "Musée",
        },
        {
            "nom": "Parc de la Vallée de la N'Sele",
            "adresse": "C/Maluku, Route de Mbenzale",
            "telephone": "+243 812 316 882",
            "latitude": -4.257124, "longitude": 15.630096,
            "evaluation": 4.4, "nombre_avis": 385,
            "horaires": "Sam-Dim: 7:30-16:30 | Lun-Ven: Fermé",
            "categorie": "Parc",
            "commune_hint": "Maluku",
        },
        {
            "nom": "Aqua Splash DRC",
            "adresse": "Kinshasa",
            "telephone": "+243 992 077 777",
            "latitude": -4.362571, "longitude": 15.352578,
            "evaluation": 4.3, "nombre_avis": 420,
            "horaires": "Mer-Dim: 12:00-20:00 | Lun-Mar: Fermé",
            "categorie": "Parc de loisirs",
        },
        {
            "nom": "Jardin Botanique",
            "adresse": "Kinshasa",
            "telephone": "",
            "latitude": -4.309811, "longitude": 15.309460,
            "evaluation": 3.8, "nombre_avis": 118,
            "horaires": "Lun-Dim: 8:30-17:30",
            "categorie": "Jardin",
        },
    ]

    for s in kinshasa_sites:
        commune = detect_commune(s.get("adresse", ""), s.get("commune_hint"))
        add({
            "nom": s["nom"],
            "commune_hint": commune,
            "adresse": s.get("adresse", "Kinshasa"),
            "description": "",
            "telephone": s.get("telephone", ""),
            "services_list": [],
            "prix_min": None,
            "prix_max": None,
            "categorie_str": s.get("categorie", "Attraction"),
            "type_str": "",
            "url_image": None,
            "facebook": None,
            "tiktok": None,
            "latitude": s.get("latitude"),
            "longitude": s.get("longitude"),
            "evaluation": s.get("evaluation"),
            "nombre_avis": s.get("nombre_avis"),
            "horaires": s.get("horaires", ""),
            "type_cuisine": "",
            "nombre_chambres": "",
            "etoiles_str": "",
        })

    # Kinshasa restaurants (Source 5)
    kinshasa_restaurants = [
        {
            "nom": "Royal Garden",
            "adresse": "Gombe, Kinshasa",
            "telephone": "+243 830 429 132",
            "latitude": -4.314935, "longitude": 15.283184,
            "evaluation": 4.5, "nombre_avis": 31,
            "horaires": "24h/24",
            "type_cuisine": "International",
            "prix_estimé": "N/A",
            "categorie": "Restaurant",
        },
        {
            "nom": "Jemi's Cuisine",
            "adresse": "Lingwala, Kinshasa",
            "telephone": "+243 999 909 365",
            "latitude": -4.3139506, "longitude": 15.2760979,
            "evaluation": 4.6, "nombre_avis": 125,
            "horaires": "Lun-Jeu: 13:00-23:55 | Ven-Sam: 13:00-00:30 | Dim: 13:00-00:30",
            "type_cuisine": "Asiatique",
            "prix_estimé": "$20-35",
            "categorie": "Restaurant",
        },
        {
            "nom": "A Casa Mia Kinshasa",
            "adresse": "Gombe, Kinshasa",
            "telephone": "+243 812 331 938",
            "latitude": -4.310348, "longitude": 15.275364,
            "evaluation": 4.3, "nombre_avis": 315,
            "horaires": "Mar-Dim: 12:00-22:30 | Lun: Fermé",
            "type_cuisine": "Italienne",
            "prix_estimé": "$12-30",
            "categorie": "Restaurant",
        },
        {
            "nom": "O Poeta",
            "adresse": "Lingwala, Kinshasa",
            "telephone": "+243 819 922 909",
            "latitude": -4.310200, "longitude": 15.2913859,
            "evaluation": 4.1, "nombre_avis": 331,
            "horaires": "Lun-Sam: 7:30-23:00 | Dim: 10:30-22:30",
            "type_cuisine": "Italienne/Congolaise",
            "prix_estimé": "$12-22",
            "categorie": "Restaurant",
        },
        {
            "nom": "MALAMU",
            "adresse": "Lingwala, Kinshasa",
            "telephone": "+243 820 625 268",
            "latitude": -4.3076193, "longitude": 15.2884453,
            "evaluation": 4.1, "nombre_avis": 143,
            "horaires": "Mar-Dim: 12:00-00:00 | Lun: Fermé",
            "type_cuisine": "Congolaise",
            "prix_estimé": "$12-25",
            "categorie": "Restaurant",
        },
        {
            "nom": "Le Z Restaurant & Lounge",
            "adresse": "Lingwala, Kinshasa",
            "telephone": "+243 828 664 628",
            "latitude": -4.3094647, "longitude": 15.2917054,
            "evaluation": 4.3, "nombre_avis": 25,
            "horaires": "Mar/Mer/Ven: 12:00-01:00 | Jeu/Sam: 15:00-01:00 | Lun: Fermé | Dim: 12:00-01:00",
            "type_cuisine": "Afro-fusion",
            "prix_estimé": "$15-30",
            "categorie": "Restaurant",
        },
        {
            "nom": "INDUS Terrace & Bar",
            "adresse": "Gombe, Kinshasa",
            "telephone": "+243 818 554 749",
            "latitude": -4.305385, "longitude": 15.310040,
            "evaluation": 4.3, "nombre_avis": 181,
            "horaires": "Lun: 12:00-23:00 | Mar-Dim: 11:00-23:00",
            "type_cuisine": "Indienne",
            "prix_estimé": "N/A",
            "categorie": "Restaurant",
        },
        {
            "nom": "Chez Gaby",
            "adresse": "Gombe, Kinshasa",
            "telephone": "+243 819 904 213",
            "latitude": -4.305122, "longitude": 15.290286,
            "evaluation": 4.2, "nombre_avis": 157,
            "horaires": "Lun-Sam: 12:00-22:00 | Dim: Fermé",
            "type_cuisine": "Portugaise/Européenne",
            "prix_estimé": "N/A",
            "categorie": "Restaurant",
        },
        {
            "nom": "Wabi Sabi",
            "adresse": "Lingwala, Kinshasa",
            "telephone": "+243 900 000 702",
            "latitude": -4.302239, "longitude": 15.310593,
            "evaluation": 4.4, "nombre_avis": 127,
            "horaires": "Mar-Sam: 12:00-01:00 | Dim: 12:00-01:00 | Lun: Fermé",
            "type_cuisine": "Pan-asiatique",
            "prix_estimé": "$25-40",
            "categorie": "Restaurant",
        },
        {
            "nom": "Terra Cotta",
            "adresse": "Gombe, Kinshasa",
            "telephone": "+243 855 477 777",
            "latitude": -4.314623, "longitude": 15.286873,
            "evaluation": 4.8, "nombre_avis": 16,
            "horaires": "Mar-Dim: 12:00-22:30 | Lun: Fermé",
            "type_cuisine": "International",
            "prix_estimé": "N/A",
            "categorie": "Restaurant",
        },
        {
            "nom": "Tandoor Grills & Curries",
            "adresse": "Gombe, Kinshasa",
            "telephone": "+243 810 691 999",
            "latitude": -4.305699, "longitude": 15.322548,
            "evaluation": 4.3, "nombre_avis": 97,
            "horaires": "Mar-Dim: 11:00-23:00 | Lun: Fermé",
            "type_cuisine": "Indienne",
            "prix_estimé": "N/A",
            "categorie": "Restaurant",
        },
        {
            "nom": "Muskoka Coffee & Tea House",
            "adresse": "Gombe, Kinshasa",
            "telephone": "+243 829 562 818",
            "latitude": -4.313104, "longitude": 15.283221,
            "evaluation": 4.7, "nombre_avis": 29,
            "horaires": "Lun-Sam: 7:00-21:00 | Dim: 10:00-20:00",
            "type_cuisine": "International/Pâtisserie",
            "prix_estimé": "N/A",
            "categorie": "Café/Salon de thé",
        },
        {
            "nom": "Cafe Roots",
            "adresse": "Lingwala, Kinshasa",
            "telephone": "+243 850 530 225",
            "latitude": -4.301159, "longitude": 15.3106096,
            "evaluation": 4.2, "nombre_avis": 102,
            "horaires": "Lun-Dim: 6:30-22:00",
            "type_cuisine": "International",
            "prix_estimé": "$10-18",
            "categorie": "Café/Restaurant",
        },
        {
            "nom": "PAPILLON CAFÉ BAR",
            "adresse": "Gombe, Kinshasa",
            "telephone": "+243 856 261 433",
            "latitude": -4.301867, "longitude": 15.310631,
            "evaluation": 5.0, "nombre_avis": 13,
            "horaires": "Lun-Sam: 9:00-20:00 | Dim: 9:00-20:00",
            "type_cuisine": "Chinoise/Congolaise",
            "prix_estimé": "N/A",
            "categorie": "Café/Bar",
        },
        {
            "nom": "Le Colibri",
            "adresse": "Lingwala, Kinshasa",
            "telephone": "+243 810 452 604",
            "latitude": -4.305001, "longitude": 15.296258,
            "evaluation": 4.2, "nombre_avis": 34,
            "horaires": "Lun-Sam: 11:00-23:00 | Dim: 15:00-23:00",
            "type_cuisine": "International",
            "prix_estimé": "$10-20",
            "categorie": "Restaurant",
        },
        {
            "nom": "Café Muzik",
            "adresse": "Gombe, Kinshasa",
            "telephone": "+243 817 000 045",
            "latitude": -4.306511, "longitude": 15.295896,
            "evaluation": 3.9, "nombre_avis": 108,
            "horaires": "Lun-Dim: 11:00-23:00",
            "type_cuisine": "Indienne",
            "prix_estimé": "N/A",
            "categorie": "Bar/Restaurant",
        },
        {
            "nom": "Le Centre",
            "adresse": "Gombe, Kinshasa",
            "telephone": "+243 843 000 003",
            "latitude": -4.301647, "longitude": 15.309008,
            "evaluation": 3.9, "nombre_avis": 68,
            "horaires": "Lun-Dim: 11:30-01:30",
            "type_cuisine": "International",
            "prix_estimé": "N/A",
            "categorie": "Restaurant",
        },
        {
            "nom": "Pâtes en Folie",
            "adresse": "Gombe, Kinshasa",
            "telephone": "+243 830 003 423",
            "latitude": -4.298501, "longitude": 15.312112,
            "evaluation": 4.5, "nombre_avis": 23,
            "horaires": "Lun-Sam: 12:00-22:00 | Dim: Fermé",
            "type_cuisine": "Italienne",
            "prix_estimé": "N/A",
            "categorie": "Restaurant",
        },
        {
            "nom": "Green Olive",
            "adresse": "Gombe, Kinshasa",
            "telephone": "+243 895 222 777",
            "latitude": -4.305192, "longitude": 15.302015,
            "evaluation": 4.0, "nombre_avis": 76,
            "horaires": "Lun-Dim: 11:00-00:00",
            "type_cuisine": "Grillée",
            "prix_estimé": "N/A",
            "categorie": "Restaurant",
        },
        {
            "nom": "Snack Away Kinshasa",
            "adresse": "Gombe, Kinshasa",
            "telephone": "+243 997 090 562",
            "latitude": -4.302972, "longitude": 15.308257,
            "evaluation": 4.2, "nombre_avis": 16,
            "horaires": "Lun-Dim: 9:00-22:00",
            "type_cuisine": "Burgers/Rapide",
            "prix_estimé": "N/A",
            "categorie": "Restaurant",
        },
        {
            "nom": "Parc des Princes",
            "adresse": "Avenue Tshikapa, Kinshasa",
            "telephone": "+243 824 251 628",
            "latitude": -4.333815, "longitude": 15.312349,
            "evaluation": 4.4, "nombre_avis": 37,
            "horaires": "Lun-Dim: 12:00-06:00",
            "type_cuisine": "Grillée/Congolaise",
            "prix_estimé": "N/A",
            "categorie": "Bar/Restaurant",
            "commune_hint": "Kalamu",
        },
    ]

    for r in kinshasa_restaurants:
        prix_min, prix_max = parse_prix(r.get("prix_estimé"))
        commune = detect_commune(r.get("adresse", ""), r.get("commune_hint"))
        add({
            "nom": r["nom"],
            "commune_hint": commune,
            "adresse": r.get("adresse", "Kinshasa"),
            "description": "",
            "telephone": r.get("telephone", ""),
            "services_list": [],
            "prix_min": prix_min,
            "prix_max": prix_max,
            "categorie_str": r.get("categorie", "Restaurant"),
            "type_str": "",
            "url_image": None,
            "facebook": None,
            "tiktok": None,
            "latitude": r.get("latitude"),
            "longitude": r.get("longitude"),
            "evaluation": r.get("evaluation"),
            "nombre_avis": r.get("nombre_avis"),
            "horaires": r.get("horaires", ""),
            "type_cuisine": r.get("type_cuisine", ""),
            "nombre_chambres": "",
            "etoiles_str": "",
        })

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

        # Services
        services_str = format_services(data.get("services_list", []))

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

        # Facebook / TikTok
        fb = data.get("facebook") or ""
        tk = data.get("tiktok") or ""
        fb = fb if valid_facebook_url(fb) else ""
        tk = tk if valid_tiktok_url(tk) else ""

        # URL image
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
