from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('aa_sov_monitor', '0008_update_verbose_names'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='sovsystem',
            name='has_tcu',
        ),
    ]
