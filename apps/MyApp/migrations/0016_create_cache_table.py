import os
from django.core.management.commands.createcachetable import Command as CreateCacheTableCommand
from django.db import migrations


def create_cache_table(apps, schema_editor):
    table_name = os.getenv('DJANGO_CACHE_TABLE', 'sutawane_cache_table')
    cmd = CreateCacheTableCommand()
    cmd.verbosity = 0
    cmd.create_table(schema_editor.connection.alias, table_name, dry_run=False)


class Migration(migrations.Migration):

    atomic = False

    dependencies = [
        ('core', '0015_websitenotification_websitenotificationdocument'),
    ]

    operations = [
        migrations.RunPython(create_cache_table, reverse_code=migrations.RunPython.noop),
    ]
