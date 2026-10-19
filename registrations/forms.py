import phonenumbers
from django import forms
from .models import Registration, RegistrationCampaign

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


class CampaignAdminForm(forms.ModelForm):
    share_image = forms.FileField(
        label="Загрузить картинку для WhatsApp",
        required=False,
        widget=forms.FileInput(attrs={"accept": "image/jpeg,image/png,.jpg,.jpeg,.png"}),
        help_text=(
            "Рекомендуем 1200 × 630 пикселей — горизонтальная картинка примерно 1,91:1. "
            "Формат JPEG или PNG; желательно до 300 КБ. Лимит загрузки здесь — 1 МБ, "
            "каждая сторона от 200 до 4096 пикселей. Другие пропорции допустимы, но WhatsApp "
            "может обрезать изображение: важный текст и лица лучше держать ближе к центру. "
            "Картинка будет публичной. Она сохранится после обновлений сайта. "
            "Выберите файл и нажмите «Сохранить». Без нового файла текущая картинка не изменится."
        ),
    )
    remove_share_image = forms.BooleanField(
        label="Удалить загруженную картинку",
        required=False,
        help_text="После сохранения вернётся афиша выбранного оформления, если она предусмотрена. Чтобы заменить картинку, просто загрузите новый файл — эту галочку ставить не нужно.",
    )

    class Meta:
        model = RegistrationCampaign
        fields = "__all__"

    def clean_share_image(self):
        upload = self.cleaned_data.get("share_image")
        if upload is None:
            return None
        from .preview_images import prepare_preview_image
        return prepare_preview_image(upload)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("share_image") and cleaned.get("remove_share_image"):
            raise forms.ValidationError("Выберите одно действие: загрузить новую картинку или удалить текущую.")
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        image = self.cleaned_data.get("share_image")
        if image:
            instance.share_image_data = image["data"]
            instance.share_image_hash = image["hash"]
            instance.share_image_size = len(image["data"])
            instance.share_image_mime = image["mime"]
            instance.share_image_width = image["width"]
            instance.share_image_height = image["height"]
        elif self.cleaned_data.get("remove_share_image"):
            instance.share_image_data = None
            instance.share_image_hash = ""
            instance.share_image_mime = ""
            instance.share_image_size = 0
            instance.share_image_width = None
            instance.share_image_height = None
            instance.share_image_alt = ""
        if commit:
            instance.save()
            self.save_m2m()
        return instance
