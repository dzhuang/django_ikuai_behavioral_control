from __future__ import annotations

from copy import deepcopy
from datetime import time

from crispy_forms.layout import Layout, Submit
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import (Http404, HttpResponseForbidden, HttpResponseRedirect,
                         JsonResponse)
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic.edit import FormView, UpdateView

from my_router.constants import DEFAULT_CACHE
from my_router.data_manager import RouterDataManager
from my_router.forms import BaseEditForm
from my_router.models import Device, Router
from my_router.utils import (StyledForm, StyledModelForm,
                             find_data_with_id_from_list_of_dict,
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

        mac_group_choices = kwargs.pop("mac_group_choices", ())
        mac_group_initial = kwargs.pop("mac_group_initial", ())
        is_blocked = kwargs.pop("reject", False)
        has_error = kwargs.pop("has_error", False)
        super().__init__(*args, **kwargs)

        self.fields["mac"].disabled = True
        self.fields["added_datetime"].disabled = True

        self.fields["reject"] = forms.BooleanField(
            label=_("Blocked"),
            initial=is_blocked, required=False)

        self.fields["mac_group"] = forms.MultipleChoiceField(
            label=_("Mac Group"),
            choices=mac_group_choices, initial=mac_group_initial,
            required=False)

        if not has_error:
            self.helper.add_input(
                Submit("submit", _("Submit"), css_class="bc-submit-btn"))

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

            mac_groups = list(self.rd_manager.mac_groups.keys())

            kwargs["mac_group_choices"] = (
                (v, v) for v in mac_groups)

            kwargs["mac_group_initial"] = (
                self.rd_manager.mac_groups_reverse.get(self.object.mac, ()))

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

        if "mac_group" in changed_data:
            group_names_contain = form_data["mac_group"]
            router_mac_group_infos = self.rd_manager.mac_groups_list["data"]

            for info in router_mac_group_infos:
                group_name = info["group_name"]
                addr_pools = info["addr_pool"].split(",")
                group_id = info["id"]

                if group_name not in group_names_contain:
                    addr_pools = [v for v in addr_pools if v != self.object.mac]
                    if not addr_pools:
                        messages.add_message(
                            self.request,
                            messages.ERROR,
                            _(
                                "The device is the only element in group '%s' "
                                "and can't be removed.") % (group_name,))
                        continue
                else:
                    addr_pools.append(self.object.mac)

                self.rd_manager.ikuai_client.edit_mac_group(
                    group_id=group_id, group_name=group_name,
                    addr_pools=addr_pools)

            self.rd_manager.reset_property_cache()
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
            import traceback
            traceback.print_exc()
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


@login_required
def list_devices(request, router_id):
    return render(request, "my_router/device-list.html", {
        "router_id": router_id,
        "form_description": _("List of devices"),
    })


class DomainBlacklistEditForm(BaseEditForm):
    def __init__(self, domain_group_choices,
                 init_domain_group=None, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["domain_group"] = forms.ChoiceField(
            label=_("Domain Groups"),
            required=True,
            choices=domain_group_choices,
            initial=init_domain_group)

        # 确保domain_group在前面
        self.helper.layout = Layout(
            'name',
            'domain_group',
            'enabled',
            'start_time',
            'length',
            'end_time',
            self.weekdays_field_name,
            'apply_to',
        )


@login_required
def list_domain_blacklist(request, router_id):
    router = get_object_or_404(Router, id=router_id)
    rd_manager = RouterDataManager(router_instance=router)

    return render(request, "my_router/domain_blacklist-list.html", {
        "router_id": router_id,
        "form_description": _("List of Domain blacklist"),
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


class AddEditViewMixin(LoginRequiredMixin):
    # form_class = DomainBlacklistEditForm
    # form_weekdays_field_name = "weekdays"
    # template_name = 'my_router/domain_blacklist-page.html'
    # id_name = "domain_blacklist_id"
    # success_url_name = "domain_blacklist-edit"
    # form_description_for_edit = _("Edit Domain Blacklist")
    # form_description_for_add = _("Add Domain Blacklist")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._rd_manager = None
        self._is_add_new = None
        self._router = None
        self._id_value = None

        self._all_data_with_id_as_key = None
        self._data_item = None

        self.new_id = None

    @property
    def router(self):
        if self._router is None:
            router_id = self.kwargs['router_id']
            self._router = get_object_or_404(Router, id=router_id)
        return self._router

    @property
    def rd_manager(self):
        if self._rd_manager is None:
            self._rd_manager = RouterDataManager(router_instance=self.router)
        return self._rd_manager

    @property
    def is_add_new(self):
        if self._is_add_new is None:
            self._is_add_new = int(self.kwargs[self.id_name]) == -1
        return self._is_add_new

    @property
    def id_value(self):
        if self._id_value is None:
            self._id_value = self.kwargs[self.id_name]
            self._id_value = int(self._id_value)
        return self._id_value

    def get_all_data_with_id_as_key(self):
        raise NotImplementedError()

    @property
    def all_data_with_id_as_key(self):
        if self._all_data_with_id_as_key is None:
            self._all_data_with_id_as_key = self.get_all_data_with_id_as_key()
        return self._all_data_with_id_as_key

    def validate_id_value(self):
        if self.id_value == -1:
            return
        if self.id_value not in self.all_data_with_id_as_key:
            raise Http404()

    def get_apply_to_choices(self):
        return ((v, v) for v in list(self.rd_manager.mac_groups.keys()))

    def get_data_item(self):
        return self.all_data_with_id_as_key[self.id_value]

    @property
    def data_item(self):
        if self._data_item is None:
            self._data_item = self.get_data_item()
        return self._data_item

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()

        apply_to_choices = self.get_apply_to_choices()

        kwargs.update({
            'add_new': self.is_add_new,
            'apply_to_choices': apply_to_choices,
            'weekdays_field_name': self.form_weekdays_field_name
        })

        if self.is_add_new:
            kwargs.update({
                'name': '',
                'start_time': turn_str_time_to_time_obj("00:00"),
                'end_time': turn_str_time_to_time_obj("23:59"),
                'days': ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'],
                'enabled': True,
                'apply_to_initial': []
            })
        else:
            kwargs.update({
                'name': self.data_item.get("comment", ""),
                'start_time': turn_str_time_to_time_obj(
                    self.data_item.get("start_time")),
                'end_time': turn_str_time_to_time_obj(
                    self.data_item.get("end_time")),
                'days': self.data_item["days"],
                'enabled': self.data_item["enabled"],
                'apply_to_initial': (
                    self.data_item["apply_to"]
                    if self.data_item["apply_to"] != [''] else [])
            })

        kwargs.update(self.get_extra_form_kwargs())
        return kwargs

    def get_extra_form_kwargs(self):
        raise NotImplementedError()

    def update_info_on_router(self, form):
        raise NotImplementedError()

    def form_invalid(self, form):
        # print(form.errors)
        return super().form_invalid(form)

    def form_valid(self, form):
        self.update_info_on_router(form=form)
        fetch_new_info_save_and_set_cache(router=self.router)
        return redirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['router_id'] = self.kwargs['router_id']
        context['form_description'] = (
            self.form_description_for_add
            if self.is_add_new else self.form_description_for_edit)

        context.update(self.get_extra_context_data())
        return context

    def get_extra_context_data(self):
        return {}

    def get_success_url(self):
        # 设置操作成功后的重定向URL
        id_value = self.kwargs[self.id_name]
        if self.is_add_new:
            assert self.new_id is not None
            id_value = self.new_id

        return reverse_lazy(
            self.success_url_name,
            kwargs={'router_id': self.kwargs['router_id'],
                    self.id_name: id_value})


class DomainBlacklistEditView(AddEditViewMixin, FormView):
    form_class = DomainBlacklistEditForm
    form_weekdays_field_name = "weekdays"
    template_name = 'my_router/domain_blacklist-page.html'
    id_name = "domain_blacklist_id"
    success_url_name = "domain_blacklist-edit"
    form_description_for_edit = _("Edit Domain Blacklist")
    form_description_for_add = _("Add Domain Blacklist")

    def get_all_data_with_id_as_key(self):
        return self.rd_manager.get_domain_blacklist_data()

    def get_extra_form_kwargs(self):
        extra_kwargs = {}

        init_domain_group_value = None
        if not self.is_add_new:
            init_domain_group_value = self.data_item["domain_group"]

        extra_kwargs['init_domain_group'] = init_domain_group_value

        available_domain_black_list = set(
            value["domain_group"]
            for value in self.all_data_with_id_as_key.values())

        extra_kwargs["domain_group_choices"] = (
                    (v, v) for v in available_domain_black_list)

        return extra_kwargs

    def get_ikuai_client_kwargs(self, form):
        client_kwargs = deepcopy(form.cleaned_data)
        client_kwargs["domain_groups"] = client_kwargs.pop("domain_group").split(",")
        client_kwargs["comment"] = client_kwargs.pop("name")
        client_kwargs["time"] = "-".join(
            [client_kwargs.pop("start_time"), client_kwargs.pop("end_time")])
        client_kwargs["ipaddrs"] = client_kwargs.pop("apply_to")
        client_kwargs.pop("length", None)
        return client_kwargs

    def update_info_on_router(self, form):
        client_kwargs = self.get_ikuai_client_kwargs(form)

        # 执行添加或更新操作
        try:
            if self.is_add_new:
                result = (
                    self.rd_manager.ikuai_client.add_domain_blacklist(**client_kwargs))  # noqa
                self.new_id = result["RowId"]
                messages.success(
                    self.request, _("Successfully added domain blacklist."))
            else:
                client_kwargs["domain_blacklist_id"] = (
                    self.kwargs["domain_blacklist_id"])
                self.rd_manager.ikuai_client.edit_domain_blacklist(**client_kwargs)
                messages.success(
                    self.request, _("Successfully updated domain blacklist."))
        except Exception as e:
            messages.error(
                self.request,
                (_("Failed to update domain blacklist: ")
                 + f"{type(e).__name__}: {str(e)}"))

            return self.form_invalid(form)

    def get_extra_context_data(self):
        return {
            "router_domain_blacklist_url":
                self.rd_manager.router_domain_blacklist_url}


class ACLL7EditForm(BaseEditForm):
    def __init__(self, protocols_choices, initial_protocols=None,
                 initial_action="accept",
                 initial_priority=28, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["app_proto"] = forms.ChoiceField(
            label=_("APP protocols"),
            required=True,
            choices=protocols_choices,
            initial=initial_protocols)

        self.fields["action"] = forms.ChoiceField(
            label=_("Action"),
            required=True,
            choices=(("drop", "阻断"), ("accept", "允许")),
            initial=initial_action)

        self.fields["prio"] = forms.IntegerField(
            label=_("Priority"),
            help_text=_("Lower in value means higher priority"),
            required=True,
            max_value=32,
            min_value=1,
            initial=initial_priority)

        self.helper.layout = Layout(
            'name',
            'action',
            'app_proto',
            'enabled',
            'prio',
            'start_time',
            'length',
            'end_time',
            self.weekdays_field_name,
            'apply_to',
        )


class ACLL7EditView(AddEditViewMixin, FormView):
    form_class = ACLL7EditForm
    form_weekdays_field_name = "week"
    template_name = 'my_router/protocol_control-page.html'
    id_name = "acl_l7_id"
    success_url_name = "acl_l7-edit"
    form_description_for_edit = _("Edit Protocol Control")
    form_description_for_add = _("Add Protocol Control")

    def get_all_data_with_id_as_key(self):
        return self.rd_manager.get_acl_l7_list_data()

    def get_extra_form_kwargs(self):
        extra_kwargs = {}

        init_app_proto_value = None
        if not self.is_add_new:
            init_app_proto_value = self.data_item["app_proto"]

        extra_kwargs['initial_protocols'] = init_app_proto_value

        available_protocol_list = set(
            value["app_proto"]
            for value in self.all_data_with_id_as_key.values())

        extra_kwargs["protocols_choices"] = (
                    (v, v) for v in available_protocol_list)

        if not self.is_add_new:
            extra_kwargs["initial_action"] = self.data_item["action"]
            extra_kwargs["initial_priority"] = self.data_item["prio"]

        return extra_kwargs

    def get_ikuai_client_kwargs(self, form):
        client_kwargs = deepcopy(form.cleaned_data)
        client_kwargs["app_protos"] = client_kwargs.pop("app_proto").split(",")
        client_kwargs["comment"] = client_kwargs.pop("name")
        client_kwargs["time"] = "-".join(
            [client_kwargs.pop("start_time"), client_kwargs.pop("end_time")])
        client_kwargs["src_addrs"] = client_kwargs.pop("apply_to")
        client_kwargs.pop("length", None)
        return client_kwargs

    def update_info_on_router(self, form):
        client_kwargs = self.get_ikuai_client_kwargs(form)

        # 执行添加或更新操作
        try:
            if self.is_add_new:
                result = (
                    self.rd_manager.ikuai_client.add_acl_l7(**client_kwargs))  # noqa
                self.new_id = result["RowId"]
                messages.success(
                    self.request, _("Successfully added acl_l7 (protocol control)."))
            else:
                client_kwargs[self.id_name] = (
                    self.kwargs[self.id_name])
                self.rd_manager.ikuai_client.edit_acl_l7(**client_kwargs)
                messages.success(
                    self.request,
                    _("Successfully updated acl_l7 (protocol control)."))
        except Exception as e:
            messages.error(
                self.request,
                (_("Failed to update domain blacklist: ")
                 + f"{type(e).__name__}: {str(e)}"))

            return self.form_invalid(form)

    def get_extra_context_data(self):
        return {
            "router_protocol_control_url":
                self.rd_manager.router_protocol_control_url}


@login_required
def list_acl_l7(request, router_id):
    router = get_object_or_404(Router, id=router_id)
    rd_manager = RouterDataManager(router_instance=router)

    return render(request, "my_router/protocol_control_list.html", {
        "router_id": router_id,
        "form_description": _("List of Protocol control"),
        "router_protocol_control_url": rd_manager.router_protocol_control_url
    })


@login_required
def delete_acl_l7(request, router_id, acl_l7_id):
    router = get_object_or_404(Router, id=router_id)

    rd_manager = RouterDataManager(router_instance=router)

    if request.method != "POST":
        return HttpResponseForbidden()
    try:
        rd_manager.ikuai_client.del_acl_l7(acl_l7_id)
    except Exception as e:
        return JsonResponse(
            data={"error": f"{type(e).__name__}： {str(e)}"}, status=400)

    fetch_new_info_save_and_set_cache(router=router)

    return JsonResponse(data={"success": True})


@login_required
def list_mac_group(request, router_id):
    return render(request, "my_router/mac_group-list.html", {
        "router_id": router_id,
        "form_description": _("List of mac groups"),
    })


class MacGroupEditForm(StyledForm):

    def __init__(self, add_new, name_initial,
                 apply_to_choices, apply_to_initial, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["group_name"] = forms.CharField(
            label=_("Group name"),
            max_length=64, required=True,
            initial=name_initial)

        self.fields["apply_to"] = forms.MultipleChoiceField(
            label=_("Apply to"),
            choices=apply_to_choices, initial=apply_to_initial,
            required=False
        )

        if add_new:
            self.helper.add_input(
                Submit("submit", _("Add"), css_class="bc-submit-btn"))
        else:
            self.helper.add_input(
                Submit("submit", _("Update"), css_class="bc-submit-btn"))


@login_required
def edit_mac_group(request, router_id, group_id):
    router = get_object_or_404(Router, id=router_id)
    rd_manager = RouterDataManager(router_instance=router)

    group_id = int(group_id)

    is_add_new = group_id == -1
    name_initial = ""
    apply_to_initial = []
    if not is_add_new:
        try:
            data_item = find_data_with_id_from_list_of_dict(
                rd_manager.mac_groups_list["data"], group_id)
        except ValueError:
            raise Http404()

        name_initial = data_item["group_name"]
        apply_to_initial = data_item["addr_pool"].split(",")

    apply_to_choices = []
    all_devices = Device.objects.filter(router=router)
    for d in all_devices:
        apply_to_choices.append((d.mac, d.name or d.mac))

    kwargs = dict(
        add_new=is_add_new,
        name_initial=name_initial,
        apply_to_choices=apply_to_choices,
        apply_to_initial=apply_to_initial)

    form_description = _("Edit mac groups")
    if is_add_new:
        form_description = _("Add mac groups")
    context = {
        "router_id": router_id,
        "form_description": form_description,
        "router_mac_group_url": rd_manager.router_mac_group_url
    }

    if request.method == "POST":
        kwargs.update(data=request.POST)
        form = MacGroupEditForm(**kwargs)
        context.update({"form": form})

        if form.is_valid():
            if not form.has_changed():
                return render(request, "my_router/mac_group-page.html", context)

            client_kwargs = dict(group_name=form.cleaned_data["group_name"],
                                 addr_pools=form.cleaned_data["apply_to"])

            try:
                if is_add_new:
                    result = rd_manager.ikuai_client.add_mac_group(**client_kwargs)
                    messages.success(
                        request,
                        _("Successfully added mac group."))

                    rd_manager.reset_property_cache()
                    return HttpResponseRedirect(
                        reverse(
                            "mac_group-edit", args=(router_id, result["RowId"])))
                else:
                    client_kwargs.update(group_id=group_id)
                    rd_manager.ikuai_client.edit_mac_group(**client_kwargs)
                    messages.success(
                        request, _("Successfully updated mac group."))

            except Exception as e:
                messages.add_message(
                    request, messages.ERROR, f"{type(e).__name__}: {str(e)}")

            finally:
                rd_manager.reset_property_cache()
                fetch_new_info_save_and_set_cache(router=router)

    else:
        form = MacGroupEditForm(**kwargs)
        context.update({"form": form})

    return render(request, "my_router/mac_group-page.html", context)


@login_required
def delete_mac_group(request, router_id, group_id):
    router = get_object_or_404(Router, id=router_id)

    rd_manager = RouterDataManager(router_instance=router)

    if request.method != "POST":
        return HttpResponseForbidden()
    try:
        rd_manager.ikuai_client.del_mac_group(group_id)
    except Exception as e:
        return JsonResponse(
            data={"error": f"{type(e).__name__}： {str(e)}"}, status=400)

    fetch_new_info_save_and_set_cache(router=router)

    return JsonResponse(data={"success": True})
