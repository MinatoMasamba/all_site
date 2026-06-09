from .models import AbonnementNewsletter


def abonnement_status(request):
    """
    Injecte `est_abonne` dans tous les gabarits pour masquer le bandeau
    newsletter si l'utilisateur est déjà abonné.

    Logique :
    - Utilisateur connecté  → vérifie son email dans AbonnementNewsletter
    - Visiteur anonyme      → vérifie le flag de session posé après soumission
    """
    if request.user.is_authenticated and request.user.email:
        est_abonne = AbonnementNewsletter.objects.filter(
            email=request.user.email, actif=True
        ).exists()
    else:
        est_abonne = bool(request.session.get("newsletter_abonne"))
    return {"est_abonne": est_abonne}
