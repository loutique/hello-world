from datetime import datetime, timezone
from django.db import migrations

# Freeze the organizer-approved copy in the migration; future edits stay in the database.
EVENT_FIELDS = {'event_title': 'Велесова ніч: що на Вас чекає', 'event_summary': 'Вечір української музики, танців, конкурсів, гарного настрою та трішечки містики. Ви вже зробили багато хорошого як волонтери — тепер запрошуємо Вас відпочити й класно провести вечір разом із нами!', 'event_description': 'Костюми та конкурс\nДуже радимо приходити в костюмах! На найкращий образ чекає грошовий приз 1000 ₪. Відьми, чаклуни, вампіри, казкові персонажі — усе вітається.\n\nПросимо обійтися без надто кривавих, жорстоких або реалістично страшних образів. З огляду на те, що зараз переживають Україна та Ізраїль, хочеться трохи менше таких асоціацій. А якщо костюма немає — взагалі не проблема! Приходьте такими, як Вам комфортно.\n\nЇжа та напої\nНа території вечірки працюватиме бар: можна буде придбати напої та перекусити. Буде й проста клубна їжа — піца, картопля фрі та інші закуски.\n\nЗа 3–5 хвилин пішки розташований ресторан української кухні SHO. Для гостей нашої вечірки там діятиме спеціальна знижка 10%.\n\nМузика й танці\nНа Вас чекають наші діджеї, українські хіти, сучасна танцювальна музика, веселі конкурси, інтерактиви та багато танців.\n\nПриходьте у зручному взутті! Це насамперед вечірка — ми дуже сподіваємося, що сидіти Вам особливо не захочеться.\n\nЩо далі?\nЗа день до вечірки організатори окремо надішлють підтвердженим учасникам лист на email з корисними деталями: як нас знайти, як дістатися та що потрібно знати перед входом. Ця реєстраційна сторінка не надсилає листів або квитків автоматично.\n\nДуже раді, що Ви будете з нами. До зустрічі 30 жовтня на DISCO UKRAÏNA! 💙💛', 'event_venue': 'CALLAS TLV', 'event_address': 'Menachem Begin 37, Тель-Авів'}
EVENT_FIELDS["event_starts_at"] = datetime(2026, 10, 30, 17, 0, tzinfo=timezone.utc)
INITIAL_INTRO = 'Привіт, наші дорогі волонтери «Здибанки»! 💙💛\n\nМи дуже раді запросити Вас на DISCO UKRAÏNA — Велесову ніч: український Гелловін у Тель-Авіві! Для волонтерів ми підготували безкоштовні квитки на вхід.\n\nЗалиште свої контакти нижче. Ми звіримо список з організаторами «Здибанки», а після підтвердження Ви отримаєте квиток окремо.'
INITIAL_SUCCESS = 'Вашу заявку отримано. Дякуємо!\n\nМи звіримо список з організаторами «Здибанки». У разі підтвердження організатори окремо надішлють Вам квиток. Сама реєстрація не є підтвердженням квитка.\n\nДо зустрічі на DISCO UKRAÏNA!'
OLD_INTRO = 'Ми підготували для волонтерів «Здибанки» безкоштовні квитки на DISCO UKRAÏNA.\n\nБудь ласка, залиште свої контактні дані нижче.\n\nПісля реєстрації ми звіримо список з організаторами «Здибанки». Після підтвердження Ви отримаєте квиток окремо.'
OLD_SUCCESS = 'Вашу заявку отримано.\n\nПісля перевірки списку ми зв’яжемося з Вами та, у разі підтвердження, надішлемо квиток.'


def fill_event_information(apps, schema_editor):
    Campaign = apps.get_model("registrations", "RegistrationCampaign")
    for campaign in Campaign.objects.using(schema_editor.connection.alias).filter(seed_key="initial-volunteers"):
        updates = {}
        for field, value in EVENT_FIELDS.items():
            current = getattr(campaign, field)
            if not current or (field == "event_title" and current == "Про подію"):
                updates[field] = value
        if campaign.intro_text == OLD_INTRO:
            updates["intro_text"] = INITIAL_INTRO
        if campaign.success_text == OLD_SUCCESS:
            updates["success_text"] = INITIAL_SUCCESS
        if updates:
            Campaign.objects.using(schema_editor.connection.alias).filter(pk=campaign.pk).update(**updates)


class Migration(migrations.Migration):
    dependencies = [("registrations", "0008_registrationcampaign_event_address_and_more")]
    operations = [migrations.RunPython(fill_event_information, migrations.RunPython.noop)]
