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

from my_router.constants import DAYS_CHOICES, DEFAULT_CACHE, days_const
from my_router.data_manager import RouterDataManager
from my_router.models import Device, Router
from my_router.serializers import \
    DeviceWithRuleParseSerializer  # DeviceDataReverseSerializer,; InfoSerializer
from my_router.utils import (StyledForm, StyledModelForm,
                             days_string_conversion,
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


@login_required
def list_devices(request, router_id):
    return render(request, "my_router/device-list.html", {
        "router_id": router_id,
        "form_description": _("List of devices"),
    })


def fetch_new_info_save_and_set_cache(router_id: int | None = None,
                                      router: Router | None = None):
    """
    Either router_id or router should be specified, the former is used in task
    calling
    """
    if router is None:
        assert router_id is not None, \
            "Either router_id or router should be specified"
        routers = Router.objects.filter(id=router_id)
        if not routers.count():
            return

        router, = routers
    else:
        router_id = router.id

    assert router is not None and router_id is not None

    rd_manager = RouterDataManager(router_instance=router)
    rd_manager.cache_each_device_info()
    rd_manager.cache_all_data()
    rd_manager.update_all_mac_cache()


@login_required
def fetch_cached_info(request, router_id, info_name):
    if request.method == "GET":
        router = get_object_or_404(Router, id=router_id)

        try:
            rd_manager = RouterDataManager(router_instance=router)
            rd_manager.init_data_from_cache()
            info = rd_manager.get_view_data(info_name=info_name)
            return JsonResponse(data=info, safe=False)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return JsonResponse(
                data={"error": f"{type(e).__name__}: {str(e)}"}, status=400)

    # POST not allowed
    return HttpResponseForbidden()


class DeviceForm(StyledModelForm):
    class Meta:
        model = Device
        fields = ["name", "mac", "ignore", "known",
                  "added_datetime"]

    def __init__(self, *args, **kwargs):
        # todo: mac_group joining & leaving
        # todo: down_limit up_limit

        is_blocked = kwargs.pop("reject", False)
        has_error = kwargs.pop("has_error", False)
        super().__init__(*args, **kwargs)

        self.fields["mac"].disabled = True
        self.fields["added_datetime"].disabled = True

        self.fields["reject"] = forms.BooleanField(
            label=_("Blocked"),
            initial=is_blocked, required=False)

        if not has_error:
            self.helper.add_input(
                Submit("submit", _("Submit"), css_class="pc-submit-btn"))

    def clean_added_datetime(self):
        return self.initial['added_datetime']

    def clean_mac(self):
        return self.initial['mac']


class DeviceUpdateView(LoginRequiredMixin, UpdateView):
    object: Device
    model = Device
    form_class = DeviceForm

    def __init__(self, **kwargs):
        super(DeviceUpdateView, self).__init__(**kwargs)
        self.rd_manager = None
        self.serialized_cached_device_data = None
        self.changed_fields = []
        self.instance_data = None
        self._original_data = None
        self._remote_updated = False

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()

        router_id = self.kwargs["router_id"]
        self.rd_manager = RouterDataManager(router_id=router_id)

        device_with_rules = self.rd_manager.get_device_rule_data()[self.object.mac]
        self._original_data = deepcopy(device_with_rules)

        try:
            kwargs["reject"] = bool(device_with_rules["reject"])
        except Exception as e:
            import traceback
            traceback.print_exc()
            self._original_data = None
            messages.add_message(
                self.request, messages.ERROR, f"{type(e).__name__}: {str(e)}")
            kwargs["has_error"] = True

        return kwargs

    def get_queryset(self):
        router = get_object_or_404(Router, id=int(self.kwargs["router_id"]))
        return super().get_queryset().filter(router=router)

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)
        context_data["form_description"] = _(
            "Update Device {device_name}").format(device_name=self.object.name)
        return context_data

    def update_router_data(self, changed_data, form_data):
        if not changed_data:
            return False

        remote_updated = False

        assert isinstance(self.rd_manager, RouterDataManager)

        # we need to update cached_data, because the device might be offline
        update_cache_kwargs = {}
        mac = self._original_data["mac"]

        if "name" in changed_data:
            new_name = form_data["name"]
            mac_comment_list = (
                self.rd_manager.ikuai_client.list_mac_comment().get("data", []))
            for item in mac_comment_list:
                if item["mac"] == mac:
                    self.rd_manager.ikuai_client.edit_mac_comment(
                        mac_comment_id=item["id"], mac=mac, comment=new_name
                    )
            else:
                self.rd_manager.ikuai_client.add_mac_comment(
                    mac=mac, comment=new_name
                )

            update_cache_kwargs["comment"] = new_name

            remote_updated = True

        if "reject" in changed_data:
            if form_data["reject"] is True:
                self.rd_manager.ikuai_client.add_acl_mac(
                    mac=self._original_data["mac"]
                )
                update_cache_kwargs["reject"] = 1
            else:
                acl_mac_list = (
                    self.rd_manager.ikuai_client.list_acl_mac().get("data", []))

                ids_to_rm = [acl_mac["id"] for acl_mac in acl_mac_list]

                for _id in ids_to_rm:
                    self.rd_manager.ikuai_client.del_acl_mac(_id)

                update_cache_kwargs["reject"] = 0
            remote_updated = True

        if update_cache_kwargs:
            self.rd_manager.update_device_cache_info_attrs(
                mac, **update_cache_kwargs)

        return remote_updated

    def form_valid(self, form):

        data = form.cleaned_data
        try:
            if form.has_changed():
                self._remote_updated = self.update_router_data(
                    form.changed_data, data)
            messages.add_message(
                self.request, messages.INFO, _("Successfully updated device."))
        except Exception as e:
            messages.add_message(
                self.request, messages.ERROR, f"{type(e).__name__}： {str(e)}")
            return self.form_invalid(form)
        else:
            need_db_save = False
            for _field in form.changed_data:
                if _field in ["name", "known", "ignore"]:
                    need_db_save = True
                    break

            if need_db_save:
                with transaction.atomic():
                    self.object = form.save()

        if self._remote_updated:
            self.refresh_all_info_cache()

        return HttpResponseRedirect(self.get_success_url())

    def refresh_all_info_cache(self):
        # We put it as a new method to facilitate tests.
        fetch_new_info_save_and_set_cache(router=self.object.router)


class SelectDay(forms.SelectMultiple):
    def __init__(self, attrs=None, choices=()):
        attrs = {"class": "vSelectDay", **(attrs or {})}
        super().__init__(attrs=attrs, choices=choices)


class TimePickerInput(AdminTimeWidget):
    input_type = 'time'

    class Media:
        extend = False
        js = [
            # "admin/js/calendar.js",
            "js/TimePickerWidgetShortcuts.js",
        ]


class TimePickerEndInput(TimePickerInput):
    def __init__(self, attrs=None, format=None):
        attrs = {"class": "vTimeEndField", "size": "8", **(attrs or {})}
        super().__init__(attrs=attrs, format=format)


class MinutesWidget(forms.Select):
    class_name = "vMinutesField"

    def __init__(self, attrs=None):
        super().__init__(attrs={"class": self.class_name, **(attrs or {})})


def turn_str_time_to_time_obj(str_time):
    if not str_time.strip():
        return None
    hour, minute = str_time.split(":")
    return time(int(hour), int(minute))


def get_mac_choice_tuple(router: Router) -> list:
    all_mac_cache_key = get_router_all_devices_mac_cache_key(router.id)
    all_macs = DEFAULT_CACHE.get(all_mac_cache_key)
    apply_to_choices = []
    ignored_device_mac = (
        Device.objects.filter(
            router=router, ignore=True).values_list("mac", flat=True))
    for mac in all_macs:
        if mac in ignored_device_mac:
            continue

        _host_info = DEFAULT_CACHE.get(get_router_device_cache_key(router.id, mac))
        if not _host_info:
            continue

        apply_to_choices.append((mac, _host_info["hostname"]))

    return apply_to_choices


class DomainBlacklistEditForm(StyledForm):
    class Media:
        css = {
            "all": ("admin/css/widgets.css",)
        }

    def __init__(self, add_new, name, start_time, end_time,
                 days, apply_to_choices, apply_to_initial, enabled,
                 domain_group_choices, domain_group=None,
                 *args, **kwargs):
        super().__init__(*args, **kwargs)

        disabled = False
        self.fields["name"] = forms.CharField(
            label=_("Name"),
            max_length=32, required=True,
            disabled=disabled,
            initial=name)

        self.fields["domain_group"] = forms.ChoiceField(
            label=_("Domain Groups"),
            required=True,
            choices=domain_group_choices,
            # disabled=disabled,
            initial=domain_group)

        self.fields["start_time"] = forms.TimeField(
            label=_("Start time"),
            disabled=disabled, initial=start_time,
            widget=TimePickerInput)

        self.fields["length"] = forms.ChoiceField(
            label=_("length"),
            required=False,
            disabled=disabled,
            choices=(("", "----------"),) + tuple((i, i) for i in range(1, 361)),
            widget=MinutesWidget,
            help_text=_("Length of time in minutes")
        )

        self.fields["end_time"] = forms.TimeField(
            label=_("End time"),
            disabled=disabled, initial=end_time,
            widget=TimePickerEndInput)

        self.fields["weekdays"] = forms.MultipleChoiceField(
            label=_("Weekdays"), initial=days,
            disabled=disabled, choices=DAYS_CHOICES,
            required=False,
            widget=SelectDay
        )

        self.fields["apply_to"] = forms.MultipleChoiceField(
            label=_("Apply to"),
            choices=apply_to_choices, initial=apply_to_initial,
            required=False
        )

        self.fields["enabled"] = forms.BooleanField(
            label=_("Enabled"),
            required=False,
            initial=enabled
        )

        if add_new:
            self.helper.add_input(
                Submit("submit", _("Add"), css_class="pc-submit-btn"))
        else:
            self.helper.add_input(
                Submit("submit", _("Update"), css_class="pc-submit-btn"))

    def clean(self):
        start_time = self.cleaned_data["start_time"]
        end_time = self.cleaned_data["end_time"]
        if end_time < start_time:
            raise forms.ValidationError(
                _('"end_time" should be greater than "start_time"')
            )
        self.cleaned_data["start_time"] = start_time.strftime("%H:%M")
        self.cleaned_data["end_time"] = end_time.strftime("%H:%M")

        self.cleaned_data["weekdays"] = days_string_conversion(
            self.cleaned_data["weekdays"], reverse_=True)

        return self.cleaned_data


@login_required
def list_domain_blacklist(request, router_id):
    router = get_object_or_404(Router, id=router_id)
    rd_manager = RouterDataManager(router_instance=router)

    return render(request, "my_router/domain_blacklist_list.html", {
        "router_id": router_id,
        "form_description": _("List of Domain blacklist"),
        "router_domain_blacklist_url": rd_manager.router_domain_blacklist_url
    })


@login_required
def edit_domain_blacklist(request, router_id, domain_blacklist_id):
    router = get_object_or_404(Router, id=router_id)

    form_description = _("Edit Domain Blacklist")
    add_new = False
    if domain_blacklist_id == "-1":
        add_new = True
        form_description = _("Add Domain Blacklist")

    rd_manager = RouterDataManager(router_instance=router)

    all_domain_blacklist_data = rd_manager.get_domain_blacklist_data()
    available_domain_black_list = set()
    for value in all_domain_blacklist_data.values():
        available_domain_black_list.add(value["domain_group"])

    domain_blacklist_id = int(domain_blacklist_id)
    if domain_blacklist_id not in all_domain_blacklist_data:
        if not add_new:
            raise Http404()

    apply_to_initial = []
    days = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
    if add_new:
        start_time = "00:00"
        enabled = True
        name = ""
        end_time = "23:59"
        domain_group = None

    else:
        domain_blacklist_data = all_domain_blacklist_data[domain_blacklist_id]
        name = domain_blacklist_data.get("comment", "")
        apply_to_initial = domain_blacklist_data["apply_to"]
        if apply_to_initial == ['']:
            apply_to_initial = []
        days = domain_blacklist_data["days"]
        start_time = domain_blacklist_data.get("start_time")
        enabled = domain_blacklist_data["enabled"]
        end_time = domain_blacklist_data.get("end_time")
        domain_group = domain_blacklist_data["domain_group"]

    start_time = turn_str_time_to_time_obj(start_time)
    end_time = turn_str_time_to_time_obj(end_time)
    apply_to_choice_item = list(rd_manager.mac_groups.keys())
    apply_to_choices = ((v, v) for v in apply_to_choice_item)

    kwargs = dict(
        add_new=add_new,
        name=name,
        start_time=start_time,
        end_time=end_time,
        days=days,
        apply_to_choices=apply_to_choices,
        apply_to_initial=apply_to_initial,
        enabled=enabled,
        domain_group=domain_group,
        domain_group_choices=((v, v) for v in available_domain_black_list)
    )

    if request.method == "POST":
        kwargs.update(data=request.POST)
        form = DomainBlacklistEditForm(**kwargs)

        if form.is_valid():
            if not form.has_changed():
                return HttpResponseRedirect(
                    reverse(
                        "domain_blacklist-edit",
                        args=(router_id, domain_blacklist_id)))

            client_kwargs = deepcopy(form.cleaned_data)
            client_kwargs["domain_groups"] = (
                client_kwargs.pop("domain_group").split(","))
            client_kwargs["comment"] = client_kwargs.pop("name")
            client_kwargs["time"] = "-".join(
                [client_kwargs.pop("start_time"), client_kwargs.pop("end_time")])
            client_kwargs["ipaddrs"] = client_kwargs.pop("apply_to")
            client_kwargs.pop("length", None)

            try:
                if not add_new:
                    client_kwargs["domain_blacklist_id"] = domain_blacklist_id
                    rd_manager.ikuai_client.edit_domain_blacklist(**client_kwargs)
                    messages.add_message(
                        request, messages.INFO,
                        _("Successfully updated domain blacklist."))
                else:
                    result = (
                        rd_manager.ikuai_client.add_domain_blacklist(
                            **client_kwargs))
                    domain_blacklist_id = result["RowId"]
                    messages.add_message(
                        request, messages.INFO,
                        _("Successfully added domain blacklist."))
            except Exception as e:
                messages.add_message(
                    request, messages.ERROR,
                    _("Failed to update domain blacklist: "
                      + f"{type(e).__name__}: {str(e)}"))
            else:
                fetch_new_info_save_and_set_cache(router=router)
                return HttpResponseRedirect(
                    reverse(
                        "domain_blacklist-edit",
                        args=(router_id, domain_blacklist_id)))

    else:
        form = DomainBlacklistEditForm(**kwargs)

    return render(request, "my_router/domain_blacklist-page.html", {
        "router_id": router_id,
        "form": form,
        "form_description": form_description,
        "router_domain_blacklist_url": rd_manager.router_domain_blacklist_url
    })


@login_required
def delete_domain_blacklist(request, router_id, domain_blacklist_id):
    router = get_object_or_404(Router, id=router_id)

    rd_manager = RouterDataManager(router_instance=router)

    if request.method != "POST":
        return HttpResponseForbidden()
    try:
        rd_manager.ikuai_client.del_domain_blacklist(domain_blacklist_id)
    except Exception as e:
        return JsonResponse(
            data={"error": f"{type(e).__name__}： {str(e)}"}, status=400)

    fetch_new_info_save_and_set_cache(router=router)

    return JsonResponse(data={"success": True})
