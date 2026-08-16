from django.db import migrations

# This file would execute side effects if evaluated as Python code
# But migrate-guard should use ast.parse without evaluation
# and should never trigger any imports

import sys

# This would set a marker if the file was imported
_BOOBY_TRAP_DJANGO_EXECUTED = True

class Migration(migrations.Migration):

    dependencies = [
        ('app', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='user',
            name='old_field',
        ),
    ]
