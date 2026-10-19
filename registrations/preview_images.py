import hashlib
import io
import warnings

from django import forms
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_IMAGE_BYTES = 1024 * 1024


def prepare_preview_image(upload):
    raw = upload.read(MAX_IMAGE_BYTES + 1)
    if len(raw) > MAX_IMAGE_BYTES:
        raise forms.ValidationError("Файл слишком большой. Лимит загрузки — 1 МБ; желательно подготовить картинку до 300 КБ.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as image:
                image_format = image.format
                if image_format not in {"JPEG", "PNG"}:
                    raise forms.ValidationError("Поддерживаются только JPEG и PNG. Сохраните картинку в одном из этих форматов.")
                if getattr(image, "is_animated", False):
                    raise forms.ValidationError("Загрузите обычную статичную картинку, без анимации.")
                width, height = image.size
                if min(width, height) < 200 or max(width, height) > 4096:
                    raise forms.ValidationError("Каждая сторона должна быть от 200 до 4096 пикселей. Рекомендуемый размер — 1200 × 630.")
                # Re-encode actual pixels, without EXIF/GPS or other uploaded metadata.
                image.load()
                pixels = ImageOps.exif_transpose(image).convert("RGB" if image_format == "JPEG" else "RGBA")
                width, height = pixels.size
                pixels.info.clear()
                output = io.BytesIO()
                if image_format == "JPEG":
                    pixels.save(output, "JPEG", quality=90, optimize=True)
                else:
                    pixels.save(output, "PNG", optimize=True)
    except forms.ValidationError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise forms.ValidationError("Не удалось прочитать картинку. Попробуйте заново сохранить её как JPEG или PNG.")
    data = output.getvalue()
    if len(data) > MAX_IMAGE_BYTES:
        raise forms.ValidationError("После обработки картинка превышает 1 МБ. Уменьшите размер или сохраните её в JPEG.")
    return {
        "data": data,
        "mime": "image/jpeg" if image_format == "JPEG" else "image/png",
        "hash": hashlib.sha256(data).hexdigest(),
        "width": width,
        "height": height,
    }
