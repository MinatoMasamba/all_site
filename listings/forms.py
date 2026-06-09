from django import forms
from django.forms import inlineformset_factory

from .models import Etablissement, ImageEtablissement


class EtablissementForm(forms.ModelForm):
    class Meta:
        model = Etablissement
        fields = [
            "nom", "categorie", "commune", "adresse", "description",
            "prix_minimum", "prix_maximum", "telephone",
            "email_contact", "whatsapp_contact",
            "horaires", "site_web", "facebook", "tiktok", "services",
            "nombre_chambres", "etoiles", "type_cuisine", "latitude", "longitude",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 5}),
            "horaires": forms.Textarea(attrs={"rows": 3}),
            "services": forms.TextInput(attrs={"placeholder": "Wi-Fi, Parking, Piscine, Restaurant…"}),
        }


ImageEtablissementFormSet = inlineformset_factory(
    Etablissement,
    ImageEtablissement,
    fields=["image", "url_image", "legende"],
    extra=0,
    max_num=20,
    can_delete=True,
)
