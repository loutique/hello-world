"""Lossless stage artwork ingestion preserving colors and existing alpha channels."""
import hashlib
import io
import warnings
from PIL import Image, ImageOps, UnidentifiedImageError
from django import forms

MAX_BYTES = 4 * 1024 * 1024


def prepare_artwork(upload):
    raw = upload.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise forms.ValidationError("Файл завеликий. Завантажте зображення до 4 МБ.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as image:
                if image.format not in {"PNG", "JPEG", "WEBP"} or getattr(image, "is_animated", False):
                    raise forms.ValidationError("Оберіть статичний PNG, JPEG або WebP. Для прозорого фону найкраще PNG.")
                if min(image.size) < 64 or image.width * image.height > 25000000:
                    raise forms.ValidationError("Кожна сторона має бути не менше 64 пікселів; загальний розмір — до 25 мегапікселів.")
                image.load()
                pixels = ImageOps.exif_transpose(image).convert("RGBA")
                pixels.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
                pixels.info.clear()
                buffer = io.BytesIO()
                pixels.save(buffer, "PNG", optimize=True)
    except forms.ValidationError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise forms.ValidationError("Не вдалося прочитати зображення. Спробуйте зберегти його як PNG.")
    data = buffer.getvalue()
    if len(data) > MAX_BYTES:
        raise forms.ValidationError("Після обробки файл перевищує 4 МБ. Зменште його розмір і повторіть спробу.")
    return {"data": data, "hash": hashlib.sha256(data).hexdigest()}


class StageBrandingForm(forms.Form):
    logo = forms.FileField(label="Логотип події", required=False, widget=forms.FileInput(attrs={"accept": "image/png,image/jpeg,image/webp"}))
    mascot = forms.FileField(label="Гарбуз або інший символ події", required=False, widget=forms.FileInput(attrs={"accept": "image/png,image/jpeg,image/webp"}))
    remove_logo = forms.BooleanField(label="Прибрати логотип", required=False)
    remove_mascot = forms.BooleanField(label="Прибрати символ події", required=False)

    def clean_logo(self):
        return prepare_artwork(self.cleaned_data["logo"]) if self.cleaned_data.get("logo") else None

    def clean_mascot(self):
        return prepare_artwork(self.cleaned_data["mascot"]) if self.cleaned_data.get("mascot") else None

    def clean(self):
        values = super().clean()
        for kind in ("logo", "mascot"):
            if values.get(kind) and values.get("remove_" + kind):
                raise forms.ValidationError("Оберіть одну дію для кожного файлу: замінити або прибрати.")
        return values
