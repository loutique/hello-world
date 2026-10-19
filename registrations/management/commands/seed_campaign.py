from django.core.management.base import BaseCommand
from registrations.models import RegistrationCampaign

class Command(BaseCommand):
    help = "Create the first campaign without overwriting existing edits"
    def handle(self, *args, **options):
        _, created = RegistrationCampaign.objects.get_or_create(seed_key="initial-volunteers", defaults={
            "slug": "zdybanky",
            "internal_name": "Здибанки — Volunteers 30.10",
            "public_title": "Реєстрація для волонтерів «Здибанки»",
            "public_subtitle": "ВЕЛЕСОВА НІЧ · 30 ЖОВТНЯ 2026 · ТЕЛЬ-АВІВ",
            "intro_text": "Ми підготували для волонтерів «Здибанки» безкоштовні квитки на DISCO UKRAÏNA.\n\nБудь ласка, залиште свої контактні дані нижче.\n\nПісля реєстрації ми звіримо список з організаторами «Здибанки». Після підтвердження Ви отримаєте квиток окремо.",
            "success_text": "Вашу заявку отримано.\n\nПісля перевірки списку ми зв’яжемося з Вами та, у разі підтвердження, надішлемо квиток.",
        })
        self.stdout.write("Campaign created" if created else "Existing campaign preserved")
