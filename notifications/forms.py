from django import forms

from .models import AbonnementNewsletter


class AbonnementNewsletterForm(forms.ModelForm):
    class Meta:
        model = AbonnementNewsletter
        fields = ["email"]
        widgets = {
            "email": forms.EmailInput(attrs={"placeholder": "Votre adresse email"}),
        }
