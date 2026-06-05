from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('submissions', '0005_alter_articlesubmission_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='articlesubmission',
            name='is_archived',
            field=models.BooleanField(default=False),
        ),
    ]
