import phonenumbers
from django import forms
from .models import Registration

class RegistrationForm(forms.ModelForm):
    class Meta:
        model = Registration
        fields = ["first_name", "last_name", "phone", "email"]
        labels = {"first_name": "Ім’я", "last_name": "Прізвище", "phone": "Телефон", "email": "Email"}
        widgets = {"first_name": forms.TextInput(attrs={"autocomplete": "given-name"}), "last_name": forms.TextInput(attrs={"autocomplete": "family-name"}), "phone": forms.TextInput(attrs={"type": "tel", "autocomplete": "tel", "placeholder": "+972 50 234 5678", "pattern": r"[+0-9() .\-]{7,40}"}), "email": forms.EmailInput(attrs={"autocomplete": "email"})}
    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()
    def clean_phone(self):
        raw = self.cleaned_data["phone"]
        try:
            number = phonenumbers.parse(raw, "IL")
            if not phonenumbers.is_valid_number(number):
                raise ValueError()
        except (phonenumbers.NumberParseException, ValueError):
            raise forms.ValidationError("Введіть дійсний номер телефону з кодом країни або ізраїльський номер.")
        self.phone_normalized = phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)
        return raw
