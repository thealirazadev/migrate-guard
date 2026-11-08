from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="new_field",
            field=models.CharField(max_length=100, null=True),
        ),
    ]
