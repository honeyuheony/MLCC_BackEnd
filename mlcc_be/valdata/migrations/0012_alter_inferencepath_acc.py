# Generated by Django 3.2.13 on 2022-10-11 10:43

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('valdata', '0011_auto_20221010_0118'),
    ]

    operations = [
        migrations.AlterField(
            model_name='inferencepath',
            name='acc',
            field=models.IntegerField(),
        ),
    ]
