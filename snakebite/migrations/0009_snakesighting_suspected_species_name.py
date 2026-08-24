from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('snakebite', '0008_snakesighting_patientcase_member_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='snakesighting',
            name='suspected_species_name',
            field=models.CharField(blank=True, max_length=150),
        ),
    ]
