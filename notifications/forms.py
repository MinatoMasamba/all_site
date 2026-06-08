from django import forms

from .models import AbonnementNewsletter, Annonce


class AbonnementNewsletterForm(forms.ModelForm):
    class Meta:
        model = AbonnementNewsletter
        fields = ["email", "numero_whatsapp"]
        widgets = {
            "email": forms.EmailInput(attrs={"placeholder": "Votre adresse email"}),
            "numero_whatsapp": forms.TextInput(attrs={
                "placeholder": "Numéro WhatsApp, ex: +243800000000 (optionnel)",
            }),
        }


class AnnonceForm(forms.ModelForm):
    class Meta:
        model = Annonce
        fields = ["titre", "message", "etablissement"]
        widgets = {
            "message": forms.Textarea(attrs={"rows": 5}),
        }
