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
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 5}),
        }


ImageEtablissementFormSet = inlineformset_factory(
    Etablissement,
    ImageEtablissement,
    fields=["image", "legende"],
    extra=0,
    max_num=20,
    can_delete=True,
)
