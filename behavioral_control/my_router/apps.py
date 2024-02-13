from django.apps import AppConfig


class MyRouterConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "my_router"

    def ready(self):
        import my_router.receivers  # noqa
