from __future__ import annotations

from copy import deepcopy
from datetime import datetime, time

from crispy_forms.layout import Submit
from django import forms
from django.contrib import messages
from django.contrib.admin.widgets import AdminTimeWidget
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import (Http404, HttpResponseForbidden, HttpResponseRedirect,
                         JsonResponse)
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic.edit import UpdateView
from pyikuai import IKuai

from my_router import logger
from my_router.constants import DAYS_CHOICES, DEFAULT_CACHE, days_const
from my_router.models import Router#, Device
# from my_router.serializers import (DeviceDataReverseSerializer,
#                                    DeviceJsonSerializer, DeviceModelSerializer,
#                                    InfoSerializer)
from my_router.utils import (StyledForm, StyledModelForm,
                             get_all_info_cache_key, get_cached_forbid_domains,
                             get_cached_forbid_domains_cache_key,
                             get_cached_limit_times,
                             get_cached_limit_times_cache_key,
                             get_device_db_cache_key,
                             get_router_all_devices_mac_cache_key,
                             get_router_device_cache_key)


def routers_context_processor(request):
    if not request.user.is_authenticated:
        return {}
    return {
        "routers": Router.objects.all()
    }


def home(request):
    routers = Router.objects.all()

    if routers.count() != 1:
        return HttpResponseRedirect(reverse("profile"))

    return HttpResponseRedirect(
        reverse(
            "device-list", args=(routers[0].id,)))
