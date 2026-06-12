from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('aa_sov_monitor', '0009_remove_sovsystem_has_tcu'),
    ]

    operations = [
        migrations.AddField(
            model_name='sovconfiguration',
            name='last_full_sync',
            field=models.DateTimeField(blank=True, help_text='Timestamp of the last full ESI sync run', null=True),
        ),
    ]
