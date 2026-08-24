from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('snakebite', '0007_patientcase_photo'),
    ]

    operations = [
        migrations.AddField(
            model_name='patientcase',
            name='member_type',
            field=models.CharField(default='community', max_length=30),
        ),
        migrations.AddField(
            model_name='snakesighting',
            name='member_type',
            field=models.CharField(default='community', max_length=30),
        ),
    ]
