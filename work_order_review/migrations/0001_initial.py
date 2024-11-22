# Generated by Django 5.1.3 on 2024-11-22 21:43

import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Assessment',
            fields=[
                ('id', models.CharField(max_length=100, primary_key=True, serialize=False)),
                ('rawData', models.JSONField()),
                ('tenantId', models.CharField(max_length=100)),
                ('facilityScenarioId', models.CharField(max_length=100)),
            ],
            options={
                'db_table': 'assessments',
            },
        ),
        migrations.CreateModel(
            name='Asset',
            fields=[
                ('id', models.CharField(max_length=100, primary_key=True, serialize=False)),
                ('rawData', models.JSONField()),
                ('tenantId', models.CharField(max_length=100)),
                ('facilityScenarioId', models.CharField(max_length=100)),
            ],
            options={
                'db_table': 'assets',
            },
        ),
        migrations.CreateModel(
            name='Component',
            fields=[
                ('id', models.CharField(max_length=100, primary_key=True, serialize=False)),
                ('rawData', models.JSONField()),
                ('tenantId', models.CharField(max_length=100)),
                ('facilityScenarioId', models.CharField(max_length=100)),
            ],
            options={
                'db_table': 'components',
            },
        ),
        migrations.CreateModel(
            name='Facility',
            fields=[
                ('id', models.CharField(max_length=100, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=255)),
                ('rawData', models.JSONField()),
            ],
            options={
                'db_table': 'facilities',
            },
        ),
        migrations.CreateModel(
            name='Tenant',
            fields=[
                ('id', models.CharField(max_length=100, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=255)),
                ('rawData', models.JSONField()),
            ],
            options={
                'db_table': 'tenants',
            },
        ),
        migrations.CreateModel(
            name='WorkOrder',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('externalId', models.CharField(max_length=100, unique=True)),
                ('rawData', models.JSONField()),
                ('tenantId', models.CharField(max_length=100)),
                ('facilityScenarioId', models.CharField(max_length=100)),
            ],
            options={
                'db_table': 'workOrders',
            },
        ),
        migrations.CreateModel(
            name='FacilityScenario',
            fields=[
                ('id', models.CharField(max_length=100, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=255)),
                ('rawData', models.JSONField()),
                ('facilityId', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='work_order_review.facility')),
                ('tenantId', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='work_order_review.tenant')),
            ],
            options={
                'db_table': 'facilityScenarios',
            },
        ),
        migrations.AddField(
            model_name='facility',
            name='tenantId',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='work_order_review.tenant'),
        ),
    ]