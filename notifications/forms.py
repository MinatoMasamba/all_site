from django import forms

from .models import AbonnementNewsletter, Annonce

_SELECT_CLASS = (
    "w-full px-4 py-2.5 rounded-xl border border-brun-200 bg-brun-50 "
    "text-brun-900 text-sm form-field focus:border-brun-500 focus:bg-brun-100 transition-colors"
)


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
            "etablissement": forms.Select(attrs={"class": _SELECT_CLASS}),
        }
