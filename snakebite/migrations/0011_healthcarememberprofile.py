from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('snakebite', '0010_patientassessment_location_comments'),
    ]

    operations = [
        migrations.CreateModel(
            name='HealthcareMemberProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('occupation', models.CharField(max_length=150)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='healthcare_profile', to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
