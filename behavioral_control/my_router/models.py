import json

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django_celery_beat.models import IntervalSchedule, PeriodicTask
from pyikuai import IKuaiClient

from my_router.constants import (DEFAULT_CACHE, ROUTER_STATUS_CHOICES,
                                 router_status)
from my_router.fields import MACAddressField
from my_router.utils import (get_device_db_cache_key,
                             get_router_device_cache_key)


class Router(models.Model):
    name = models.CharField(
        max_length=255, verbose_name=_("Router name"))
    description = models.CharField(
        verbose_name=_("Description"),
        max_length=255, null=True, blank=True)
    url = models.URLField(
        null=False, help_text=_("The admin URL of the router"), unique=True)

    admin_username = models.CharField(
        verbose_name=_("Admin username"),
        help_text=_("Admin username of the iKuai router"),
        null=False, max_length=255)

    admin_password = models.CharField(
        verbose_name=_("Admin password"),
        help_text=_("Admin password of the iKuai router"),
        null=False, max_length=255)

    # todo: allow select api by model
    ikuai_version = models.CharField(
        max_length=255, verbose_name=_("iKuai version"), blank=True
    )

    status = models.CharField(
        max_length=50,
        verbose_name=_("Router status"),
        help_text=_("This determines whether remote information will be "
                    "fetched periodically"),
        choices=ROUTER_STATUS_CHOICES, default=router_status.active)

    fetch_interval = models.PositiveIntegerField(
        verbose_name=_("Fetch interval"),
        help_text=_("The interval of the app to fetch the information "
                    "on the router, in seconds"),
        default=getattr(settings, "BEHAVIORAL_CONTROL_FETCH_INFO_INTERVAL", 10),
        validators=[MinValueValidator(1)]
    )

    task = models.OneToOneField(
        PeriodicTask, on_delete=models.CASCADE, null=True, blank=True)

    class Meta:
        verbose_name = _("Router")
        verbose_name_plural = _("Routers")

    def __str__(self):
        return self.name

    def get_client(self):
        return IKuaiClient(
            url=self.url, username=self.admin_username,
            password=self.admin_password)

    def setup_task(self):
        self.task = PeriodicTask.objects.create(
            name=_("Fetch info and set cache"),
            task="fetch_devices_and_set_cache",
            interval=self.interval_schedule,
            args=json.dumps([self.id]),
            start_time=now()
        )
        self.save()

    @property
    def interval_schedule(self):
        instance, created = IntervalSchedule.objects.get_or_create(
            every=self.fetch_interval, period="seconds")
        return instance

    def delete(self, *args, **kwargs):
        if self.task is not None:
            self.task.delete()
        return super(Router, self).delete(*args, **kwargs)


class Device(models.Model):
    name = models.CharField(
        verbose_name=_("Device name"),
        max_length=31, blank=True, null=True)
    mac = MACAddressField(
        verbose_name=_("MAC address"),
        blank=False, db_index=True)
    router = models.ForeignKey(
        Router, verbose_name=_("Router connected"),
        on_delete=models.CASCADE)
    known = models.BooleanField(
        verbose_name=_("Known device"),
        default=False, help_text=_("This devices is known."))
    ignore = models.BooleanField(
        verbose_name=_("Ignored device"),
        default=False, help_text=_(
            "This device will be ignored when listing and bulk applying "
            "constraints."))
    added_datetime = models.DateTimeField(
        default=now, verbose_name=_("Added datetime"))

    class Meta:
        verbose_name = _("Device")
        verbose_name_plural = _("Devices")
        unique_together = ("router", "mac")
        ordering = ("-added_datetime",)

    def save(self, *args, **kwargs):
        # Don't save object if no field changes.
        # Get updated_fields: https://stackoverflow.com/a/55005137/3437454
        if self.pk:
            # If self.pk is not None then it's an update.
            cls = self.__class__

            # This will get the current model state since super().save()
            # isn't called yet.
            old = cls.objects.get(pk=self.pk)

            # This gets the newly instantiated Mode object with the new values.
            new = self
            changed_fields = []
            for field in cls._meta.get_fields():
                field_name = field.name
                try:
                    if getattr(old, field_name) != getattr(new, field_name):
                        changed_fields.append(field_name)
                except Exception:
                    # Catch field does not exist exception
                    pass
            kwargs['update_fields'] = changed_fields
        super().save(*args, **kwargs)

    def update_name_cache(self):
        # The name cache is a cache whose key is build by self.mac, and the value
        # is the name. It is used to decide whether we need to save the
        # device: if the name is not changed, then we skip the saving.
        DEFAULT_CACHE.set(get_device_db_cache_key(self.mac), self.name)

    def remove_cache(self):
        # Remove both the name cache and router device cache.
        DEFAULT_CACHE.delete(get_device_db_cache_key(self.mac))
        DEFAULT_CACHE.delete(get_router_device_cache_key(self.router.id, self.mac))

    def __str__(self):
        return _("{device} on {router}").format(device=self.name, router=self.router)

    def get_absolute_url(self):
        return reverse("device-edit", args=(self.router.pk, self.pk,))
