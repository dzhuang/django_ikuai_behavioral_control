from django.contrib.auth import get_user_model
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver
from rest_framework.authtoken.models import Token

from my_router.constants import router_status
from my_router.models import Device, Router
from my_router.views import fetch_new_info_save_and_set_cache


@receiver(post_save, sender=get_user_model())
def create_auth_token(sender, instance=None, created=False, **kwargs):
    if created:
        Token.objects.create(user=instance)


@receiver(post_save, sender=Router)
def create_or_update_router_fetch_task(sender, instance: Router, created, **kwargs):
    if created:
        instance.setup_task()
        fetch_new_info_save_and_set_cache(router=instance)
    else:
        if instance.task is not None:
            instance.task.enabled = instance.status == router_status.active
            instance.task.save()


@receiver(pre_save, sender=Device)
def cache_device_old_block_mac_by_proto_ctrl_values(sender, instance, **kwargs):
    if instance.pk:
        existing_instance = sender.objects.get(pk=instance.pk)
        # 缓存旧值以便之后比较
        instance._old_values = {
            'block_mac_by_proto_ctrl': existing_instance.block_mac_by_proto_ctrl,
        }


@receiver(post_save, sender=Device)
def handle_device_info_after_save(sender, instance: Device, created, **kwargs):
    # cache_device_info_after_save
    instance.update_name_cache()

    if not created:
        if hasattr(instance, "_old_values"):
            old_value = instance._old_values['block_mac_by_proto_ctrl']
            if old_value is True and instance.block_mac_by_proto_ctrl is False:
                from my_router.data_manager import RouterDataManager
                rd_manager = RouterDataManager(router_instance=instance.router)
                rd_manager.remove_active_acl_mac_rule_of_device(instance.mac)


@receiver(post_delete, sender=Device)
def remove_device_cache_after_delete(sender, instance: Device, **kwargs):
    instance.remove_cache()
    fetch_new_info_save_and_set_cache(router=instance.router)
