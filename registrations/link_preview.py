from django.templatetags.static import static
from django.urls import reverse
from django.utils.html import strip_tags
from django.utils.text import Truncator

from .models import RegistrationCampaign


def link_preview(request, campaign):
    """Expose only public campaign content, never submitted contacts or query strings."""
    if not campaign.is_open:
        description = campaign.closed_text
    else:
        description = " · ".join(filter(None, [
            campaign.public_subtitle,
            campaign.event_summary or campaign.intro_text,
        ]))
    description = Truncator(" ".join(strip_tags(description).split())).chars(220)
    preview = {
        "title": f"{campaign.public_title} · DISCO UKRAÏNA",
        "description": description,
        "url": request.build_absolute_uri(reverse("register", args=[campaign.slug])),
    }
    if campaign.share_image_hash:
        preview.update({
            "image": request.build_absolute_uri(reverse("campaign_preview_image", args=[campaign.slug, campaign.share_image_hash])),
            "image_width": campaign.share_image_width,
            "image_height": campaign.share_image_height,
            "image_type": campaign.share_image_mime,
            "image_alt": campaign.share_image_alt or campaign.public_title,
        })
    elif campaign.visual_style == RegistrationCampaign.VisualStyle.VELES:
        preview.update({
            "image": request.build_absolute_uri(static("registrations/artwork/veles-2026-small.jpg")),
            "image_type": "image/jpeg",
            "image_width": 569,
            "image_height": 800,
            "image_alt": "Афіша DISCO UKRAÏNA — Велесова ніч, український Гелловін у Тель-Авіві",
        })
    return {"link_preview": preview}
