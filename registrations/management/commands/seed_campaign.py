from django.core.management.base import BaseCommand
from registrations.models import RegistrationCampaign
from registrations.campaign_content import INITIAL_INTRO, INITIAL_SUCCESS, INITIAL_EVENT_FIELDS

class Command(BaseCommand):
    help = "Create the first campaign without overwriting existing edits"
    def handle(self, *args, **options):
        _, created = RegistrationCampaign.objects.get_or_create(seed_key="initial-volunteers", defaults={
            "slug": "zdybanky",
            "visual_style": RegistrationCampaign.VisualStyle.VELES,
            "internal_name": "Здибанки — Volunteers 30.10",
            "public_title": "Реєстрація для волонтерів «Здибанки»",
            "public_subtitle": "ВЕЛЕСОВА НІЧ · 30 ЖОВТНЯ 2026 · ТЕЛЬ-АВІВ",
            "intro_text": INITIAL_INTRO,
            "success_text": INITIAL_SUCCESS,
            **INITIAL_EVENT_FIELDS,
        })
        self.stdout.write("Campaign created" if created else "Existing campaign preserved")
