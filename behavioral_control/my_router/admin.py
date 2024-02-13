from django.contrib import admin
from django.forms import ModelForm, PasswordInput

from my_router.models import Device, Router


class RouterForm(ModelForm):
    class Meta:
        model = Router
        widgets = {
            'admin_password': PasswordInput(),
        }
        exclude = ("task", )


class RouterAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "description",
        "url",
        "status",
        "fetch_interval"
    )
    list_editable = (
        "name",
        "description",
        "url",
        "status",
        "fetch_interval"
    )

    form = RouterForm
    save_on_top = True


admin.site.register(Router, RouterAdmin)


class DeviceAdminForm(ModelForm):
    class Meta:
        model = Device
        exclude = ()


class DeviceAdmin(admin.ModelAdmin):

    readonly_fields = ("mac", "name")
    form = DeviceAdminForm

    list_display = (
        "id",
        "mac",
        "name",
        "router",
        "ignore",
        "known",
    )
    list_editable = (
        "known",
        "ignore",
    )
    list_filter = (
        "ignore",
        "router",
        "known",
    )
    save_on_top = True


admin.site.register(Device, DeviceAdmin)
