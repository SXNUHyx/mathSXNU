from django.conf import settings
from django.db import migrations


def preserve_existing_teachers(apps, schema_editor):
    user_app, user_model = settings.AUTH_USER_MODEL.split(".")
    User = apps.get_model(user_app, user_model)
    Profile = apps.get_model("feedback", "AccountProfile")
    alias = schema_editor.connection.alias
    for user_id in User.objects.using(alias).values_list("pk", flat=True).iterator():
        Profile.objects.using(alias).get_or_create(user_id=user_id, defaults={"role": "teacher"})


class Migration(migrations.Migration):
    dependencies = [
        ("feedback", "0003_accountprofile_classroommembership_response_user_and_more"),
    ]
    operations = [migrations.RunPython(preserve_existing_teachers, reverse_code=migrations.RunPython.noop)]
