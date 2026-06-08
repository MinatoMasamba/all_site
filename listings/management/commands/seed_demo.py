from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils.text import slugify

from listings.models import Categorie, Commune, Etablissement

DONNEES_DEMO = [
    {
        "nom": "Hôtel Memling",
        "categorie": "Hôtels",
        "commune": "Gombe",
        "adresse": "Avenue Bas-Congo",
        "description": "Hôtel de standing au cœur de la Gombe, chambres climatisées, piscine et restaurant panoramique.",
        "prix_minimum": 120,
        "prix_maximum": 350,
        "telephone": "+243 81 000 0001",
    },
    {
        "nom": "Restaurant Chez Maman Aida",
        "categorie": "Restaurants",
        "commune": "Limete",
        "adresse": "Avenue de la Paix",
        "description": "Cuisine congolaise familiale : poulet moambe, pondu et poisson braisé dans une ambiance conviviale.",
        "prix_minimum": 8,
        "prix_maximum": 25,
        "telephone": "+243 81 000 0002",
    },
    {
        "nom": "Bar-Lounge Le Texaf",
        "categorie": "Bars",
        "commune": "Gombe",
        "adresse": "Avenue du Drapeau",
        "description": "Terrasse au bord du fleuve Congo, cocktails, musique live le week-end et vue sur Brazzaville.",
        "prix_minimum": 5,
        "prix_maximum": 30,
        "telephone": "+243 81 000 0003",
    },
    {
        "nom": "Jardin Botanique de Kinshasa",
        "categorie": "Sites touristiques",
        "commune": "Kintambo",
        "adresse": "Route de Mont-Ngafula",
        "description": "Espace vert paisible aux portes de la ville, parfait pour une balade en famille et la photographie nature.",
        "prix_minimum": 2,
        "prix_maximum": 5,
        "telephone": "+243 81 000 0004",
    },
    {
        "nom": "Hôtel Pullman Kinshasa Grand",
        "categorie": "Hôtels",
        "commune": "Gombe",
        "adresse": "Avenue Batetela",
        "description": "Hôtel international avec salles de conférence, spa et vue sur le fleuve Congo.",
        "prix_minimum": 150,
        "prix_maximum": 420,
        "telephone": "+243 81 000 0005",
    },
    {
        "nom": "Restaurant La Cantine de Lemba",
        "categorie": "Restaurants",
        "commune": "Lemba",
        "adresse": "Avenue de l'Université",
        "description": "Petit restaurant prisé des étudiants, plats du jour à prix doux et jus de fruits frais.",
        "prix_minimum": 4,
        "prix_maximum": 12,
        "telephone": "+243 81 000 0006",
    },
]


class Command(BaseCommand):
    help = "Crée un compte gestionnaire interne et des établissements de démonstration."

    def handle(self, *args, **options):
        Utilisateur = get_user_model()

        gestionnaire, cree = Utilisateur.objects.get_or_create(
            username="gestionnaire_plateforme",
            defaults={
                "email": "gestion@decouvrir-kinshasa.cd",
                "role": Utilisateur.Role.GESTIONNAIRE,
                "is_staff": True,
            },
        )
        if cree:
            gestionnaire.set_password("ChangezMoi123!")
            gestionnaire.save()
            self.stdout.write(self.style.SUCCESS(
                "Compte gestionnaire interne créé : gestionnaire_plateforme / ChangezMoi123!"
            ))

        for nom in ["Hôtels", "Restaurants", "Bars", "Sites touristiques"]:
            Categorie.objects.get_or_create(nom=nom, defaults={"slug": slugify(nom)})

        for nom in ["Gombe", "Limete", "Lemba", "Kintambo", "Ngaliema", "Kalamu"]:
            Commune.objects.get_or_create(nom=nom)

        for donnee in DONNEES_DEMO:
            categorie = Categorie.objects.get(nom=donnee["categorie"])
            commune = Commune.objects.get(nom=donnee["commune"])
            Etablissement.objects.get_or_create(
                nom=donnee["nom"],
                defaults={
                    "slug": slugify(donnee["nom"]),
                    "categorie": categorie,
                    "commune": commune,
                    "adresse": donnee["adresse"],
                    "description": donnee["description"],
                    "prix_minimum": donnee["prix_minimum"],
                    "prix_maximum": donnee["prix_maximum"],
                    "telephone": donnee["telephone"],
                    "statut": Etablissement.Statut.PUBLIE,
                    "enregistre_par": gestionnaire,
                },
            )

        self.stdout.write(self.style.SUCCESS("Données de démonstration installées."))
