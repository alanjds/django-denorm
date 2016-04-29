# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('test_app', '0004_auto_20160218_1249'),
    ]

    operations = [
        migrations.AlterField(
            model_name='forum',
            name='authors',
            field=models.ManyToManyField(to='test_app.Member', editable=False, blank=True),
            preserve_default=True,
        ),
    ]
