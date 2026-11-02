from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("system_settings", "0004_systemsettings_data_exfil_min_local_files"),
    ]

    operations = [
        migrations.AddField(
            model_name="systemsettings",
            name="notifications_enabled",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="systemsettings",
            name="telegram_bot_token",
            field=models.CharField(blank=True, default="", max_length=200),
        ),
        migrations.AddField(
            model_name="systemsettings",
            name="telegram_chat_id",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.AddField(
            model_name="systemsettings",
            name="webhook_url",
            field=models.URLField(blank=True, default="", max_length=500),
        ),
        migrations.AddField(
            model_name="systemsettings",
            name="notification_emails",
            field=models.CharField(blank=True, default="", max_length=500),
        ),
    ]

