from django.utils.translation import gettext as _

from celery import shared_task
from my_router.views import fetch_new_info_save_and_set_cache


@shared_task(bind=True, name="fetch_devices_and_set_cache")
def fetch_devices_and_set_cache(self, router_id):
    fetch_new_info_save_and_set_cache(router_id)
    return {"message": _("Done")}
