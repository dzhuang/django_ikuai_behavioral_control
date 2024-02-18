from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Submit
from django import forms
from django.contrib.admin.widgets import AdminTimeWidget
from django.utils.translation import gettext_lazy as _

# 假设这些是必要的导入和定义
from my_router.constants import DAYS_CHOICES  # 这需要你根据实际情况定义或导入
from my_router.utils import StyledFormMixin, days_string_conversion


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


class BaseEditForm(StyledFormMixin, forms.Form):
    class Media:
        css = {
            "all": ("admin/css/widgets.css",)
        }

    def __init__(self, add_new, name, start_time, end_time,
                 days, apply_to_choices, apply_to_initial, enabled,
                 *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["name"] = forms.CharField(
            label=_("Name"),
            max_length=32, required=True,
            initial=name)

        self.fields["start_time"] = forms.TimeField(
            label=_("Start time"),
            initial=start_time,
            widget=TimePickerInput)

        self.fields["length"] = forms.ChoiceField(
            label=_("length"),
            required=False,
            choices=(("", "----------"),) + tuple((i, i) for i in range(1, 361)),
            widget=MinutesWidget,
            help_text=_("Length of time in minutes")
        )

        self.fields["end_time"] = forms.TimeField(
            label=_("End time"),
            initial=end_time,
            widget=TimePickerEndInput)

        self.fields["weekdays"] = forms.MultipleChoiceField(
            label=_("Weekdays"), initial=days,
            choices=DAYS_CHOICES,
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

        # 定义FormHelper和布局
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal"
        self.helper.label_class = "col-lg-2"
        self.helper.field_class = "col-lg-8"

        # 定义基础布局，具体子类可以扩展或修改它
        self.helper.layout = Layout(
            'name',
            # 'domain_group' 将在子类中定义
            'start_time',
            'end_time',
            'weekdays',
            'apply_to',
            'enabled',
            # Submit按钮将在子类中根据需要添加
        )

        if add_new:
            self.helper.add_input(
                Submit("submit", _("Add"), css_class="pc-submit-btn"))
        else:
            self.helper.add_input(
                Submit("submit", _("Update"), css_class="pc-submit-btn"))

    def clean(self):
        cleaned_data = super().clean()
        start_time = cleaned_data["start_time"]
        end_time = cleaned_data["end_time"]
        if end_time < start_time:
            raise forms.ValidationError(
                _('"end_time" should be greater than "start_time"')
            )
        cleaned_data["start_time"] = start_time.strftime("%H:%M")
        cleaned_data["end_time"] = end_time.strftime("%H:%M")

        cleaned_data["weekdays"] = days_string_conversion(
            cleaned_data["weekdays"], reverse_=True)

        return cleaned_data
