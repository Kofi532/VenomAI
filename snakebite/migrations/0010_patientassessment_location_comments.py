from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('snakebite', '0009_snakesighting_suspected_species_name'),
    ]

    operations = [
        migrations.AddField(
            model_name='patientassessment',
            name='location',
            field=models.CharField(blank=True, max_length=150),
        ),
        migrations.AddField(
            model_name='patientassessment',
            name='comments',
            field=models.TextField(blank=True),
        ),
    ]
