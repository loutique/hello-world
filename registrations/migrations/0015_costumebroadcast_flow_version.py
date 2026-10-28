from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("registrations", "0014_costumevotingbranding")]
    operations = [
        # Keep already-started shows on their original single-frame jury timeline.
        migrations.AddField(model_name="costumebroadcast", name="flow_version", field=models.PositiveSmallIntegerField(default=1)),
        migrations.AlterField(model_name="costumebroadcast", name="flow_version", field=models.PositiveSmallIntegerField(default=2)),
    ]
