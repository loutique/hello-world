from django.db import migrations


def set_initial_style(apps, schema_editor):
    Campaign = apps.get_model("registrations", "RegistrationCampaign")
    Campaign.objects.using(schema_editor.connection.alias).filter(seed_key="initial-volunteers", visual_style="classic").update(visual_style="veles2026")


class Migration(migrations.Migration):
    dependencies = [("registrations", "0005_registrationcampaign_visual_style")]
    operations = [migrations.RunPython(set_initial_style, migrations.RunPython.noop)]
