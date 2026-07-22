"""Génère une nouvelle paire de clés VAPID pour les notifications push.

Régénérer ces clés invalide tous les abonnements déjà enregistrés (les
navigateurs devront se réabonner) : à utiliser uniquement en cas de besoin,
puis reporter les valeurs affichées dans les variables d'environnement
VAPID_PUBLIC_KEY et VAPID_PRIVATE_KEY.
"""
import base64

from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from django.core.management.base import BaseCommand
from py_vapid import Vapid02


class Command(BaseCommand):
    help = "Génère une nouvelle paire de clés VAPID pour les notifications push."

    def handle(self, *args, **options):
        vapid = Vapid02()
        vapid.generate_keys()

        raw_public = vapid.public_key.public_bytes(
            encoding=Encoding.X962, format=PublicFormat.UncompressedPoint
        )
        public_b64 = base64.urlsafe_b64encode(raw_public).rstrip(b"=").decode()

        raw_private = vapid.private_key.private_numbers().private_value.to_bytes(32, "big")
        private_b64 = base64.urlsafe_b64encode(raw_private).rstrip(b"=").decode()

        self.stdout.write(f"VAPID_PUBLIC_KEY={public_b64}")
        self.stdout.write(f"VAPID_PRIVATE_KEY={private_b64}")
