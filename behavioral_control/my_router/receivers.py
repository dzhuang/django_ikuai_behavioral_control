from django.contrib.auth import get_user_model
from django.db.models.signals import post_delete, post_save  # noqa
from django.dispatch import receiver
from rest_framework.authtoken.models import Token

from my_router.constants import router_status  # noqa

# from my_router.models import Device, Router
# from my_router.views import fetch_new_info_save_and_set_cache


@receiver(post_save, sender=get_user_model())
def create_auth_token(sender, instance=None, created=False, **kwargs):
    if created:
        Token.objects.create(user=instance)
