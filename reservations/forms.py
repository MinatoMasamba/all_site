from django import forms

from .models import Paiement, Reservation


class ReservationForm(forms.ModelForm):
    class Meta:
        model = Reservation
        fields = ["date_prevue", "nombre_personnes", "mode_paiement", "note"]
        widgets = {
            "date_prevue": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "note": forms.Textarea(attrs={"rows": 3, "placeholder": "Précisions pour l'établissement (optionnel)"}),
        }


class PaiementMobileMoneyForm(forms.ModelForm):
    class Meta:
        model = Paiement
        fields = ["montant", "operateur", "reference_transaction"]
        widgets = {
            "reference_transaction": forms.TextInput(attrs={
                "placeholder": "Référence de la transaction Mobile Money",
            }),
        }
