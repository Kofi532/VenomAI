from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('snakebite', '0011_healthcarememberprofile'),
    ]

    operations = [
        migrations.CreateModel(
            name='TransportOperator',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('operator_name', models.CharField(max_length=150)),
                ('phone_number', models.CharField(max_length=30)),
                ('service_area', models.CharField(max_length=150)),
                ('vehicle_type', models.CharField(max_length=80)),
                ('is_available', models.BooleanField(default=True)),
                ('is_verified', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'ordering': ['-is_verified', 'operator_name'],
                'indexes': [
                    models.Index(fields=['service_area'], name='snakebite_t_service_a276f5_idx'),
                    models.Index(fields=['is_available'], name='snakebite_t_is_avai_f21e32_idx'),
                    models.Index(fields=['is_verified'], name='snakebite_t_is_veri_446e33_idx'),
                ],
            },
        ),
    ]