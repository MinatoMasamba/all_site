"""Envoi des notifications d'offres et de nouveautés par email et WhatsApp."""

import logging

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


def envoyer_email(destinataire, sujet, message):
    """Envoie un email. Utilise le backend configuré (console en développement)."""
    send_mail(
        subject=sujet,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[destinataire],
        fail_silently=False,
    )


def whatsapp_configure():
    return bool(
        settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN and settings.TWILIO_WHATSAPP_FROM
    )


def envoyer_whatsapp(numero, message):
    """
    Envoie un message WhatsApp via l'API Twilio.

    Si les identifiants Twilio ne sont pas configurés (variables d'environnement
    TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_WHATSAPP_FROM), le message
    est simplement journalisé pour ne pas bloquer le développement local.
    """
    if not whatsapp_configure():
        logger.info("WhatsApp non configuré — message simulé pour %s : %s", numero, message)
        return

    from twilio.rest import Client

    client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    client.messages.create(
        from_=f"whatsapp:{settings.TWILIO_WHATSAPP_FROM}",
        to=f"whatsapp:{numero}",
        body=message,
    )


def envoyer_message_bienvenue(utilisateur):
    """
    Envoie un message de bienvenue chaleureux par email et WhatsApp juste
    après l'inscription, pour accueillir le nouvel utilisateur et lui
    annoncer qu'il recevra bientôt les offres et nouveautés de la plateforme.

    Les erreurs d'envoi sont journalisées sans bloquer l'inscription : on ne
    veut pas qu'un souci d'email ou de WhatsApp empêche quelqu'un de créer
    son compte.
    """
    prenom = utilisateur.first_name or utilisateur.username
    sujet = "🌸 Bienvenue dans la famille Découvrir Kinshasa !"
    message = (
        f"Bonjour {prenom}, et bienvenue ! 🌺\n\n"
        "Quel plaisir de vous compter parmi nous ! Vous venez de rejoindre "
        "Découvrir Kinshasa, la plateforme qui rassemble les meilleurs "
        "hôtels, restaurants, bars et sites touristiques de la ville, avec "
        "leurs photos, leurs quartiers et leurs tarifs, pour que vous "
        "puissiez explorer Kinshasa en toute confiance — que ce soit pour "
        "découvrir un nouvel endroit ou redécouvrir vos coins préférés.\n\n"
        "À partir de maintenant, gardez l'œil ouvert : vous recevrez bientôt "
        "ici même, par email et par WhatsApp, nos meilleures offres, "
        "promotions et nouveautés, directement des établissements de la "
        "ville. 🌷\n\n"
        "Merci de votre confiance, installez-vous confortablement, et à très "
        "vite pour de belles découvertes !\n\n"
        "Avec toute notre chaleur,\n"
        "🌸 L'équipe Découvrir Kinshasa"
    )

    if utilisateur.email:
        try:
            envoyer_email(utilisateur.email, sujet, message)
        except Exception:
            logger.exception("Échec de l'envoi de l'email de bienvenue à %s", utilisateur.email)

    if utilisateur.telephone:
        try:
            envoyer_whatsapp(utilisateur.telephone, message)
        except Exception:
            logger.exception("Échec de l'envoi du message WhatsApp de bienvenue à %s", utilisateur.telephone)


def diffuser_annonce(annonce):
    """
    Envoie une annonce (offre ou nouveauté) par email et WhatsApp à tous les
    abonnés actifs : visiteurs abonnés à la newsletter et utilisateurs inscrits
    ayant activé la réception des notifications.

    Renvoie le nombre d'emails et de messages WhatsApp envoyés.
    """
    from django.contrib.auth import get_user_model

    from .models import AbonnementNewsletter

    sujet = f"🌸 {annonce.titre} — Découvrir Kinshasa"
    corps = f"{annonce.message}\n\n— L'équipe Découvrir Kinshasa"

    emails_envoyes = set()
    whatsapp_envoyes = set()

    for abonnement in AbonnementNewsletter.objects.filter(actif=True):
        if abonnement.email not in emails_envoyes:
            envoyer_email(abonnement.email, sujet, corps)
            emails_envoyes.add(abonnement.email)
        if abonnement.numero_whatsapp and abonnement.numero_whatsapp not in whatsapp_envoyes:
            envoyer_whatsapp(abonnement.numero_whatsapp, corps)
            whatsapp_envoyes.add(abonnement.numero_whatsapp)

    Utilisateur = get_user_model()
    for utilisateur in Utilisateur.objects.filter(recevoir_notifications=True).exclude(email=""):
        if utilisateur.email not in emails_envoyes:
            envoyer_email(utilisateur.email, sujet, corps)
            emails_envoyes.add(utilisateur.email)
        if utilisateur.telephone and utilisateur.telephone not in whatsapp_envoyes:
            envoyer_whatsapp(utilisateur.telephone, corps)
            whatsapp_envoyes.add(utilisateur.telephone)

    return len(emails_envoyes), len(whatsapp_envoyes)
