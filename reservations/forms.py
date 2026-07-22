from django import forms

from .models import Paiement, Reservation

_SELECT_CLASS = (
    "w-full px-4 py-2.5 rounded-xl border border-brun-200 bg-brun-50 "
    "text-brun-900 text-sm form-field focus:border-brun-500 focus:bg-brun-100 transition-colors"
)


class ReservationForm(forms.ModelForm):
    class Meta:
        model = Reservation
        fields = ["date_prevue", "nombre_personnes", "mode_paiement", "note"]
        widgets = {
            "date_prevue": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "mode_paiement": forms.Select(attrs={"class": _SELECT_CLASS}),
            "note": forms.Textarea(attrs={"rows": 3, "placeholder": "Précisions pour l'établissement (optionnel)"}),
        }


class PaiementMobileMoneyForm(forms.ModelForm):
    class Meta:
        model = Paiement
        fields = ["montant", "operateur", "reference_transaction"]
        widgets = {
            "operateur": forms.Select(attrs={"class": _SELECT_CLASS}),
            "reference_transaction": forms.TextInput(attrs={
                "placeholder": "Référence de la transaction Mobile Money",
            }),
        }
