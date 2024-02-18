from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import datetime
from urllib.parse import quote

from django.urls import reverse
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from my_router.models import Device
from my_router.utils import days_string_conversion


def split_name(s, replace_quote_blank=True):
    s = s.strip()
    s = s.replace(" ", "")
    if replace_quote_blank:
        s = s.replace(quote(" "), "")
    if not s:
        return []
    return s.split(",")


class UnknownAsEmptyField(serializers.CharField):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.allow_blank = kwargs.pop('allow_blank', True)

    def to_representation(self, value):
        if value == 'Unknown':
            return ""
        return value


class BoolToZeroOneField(serializers.Field):
    def to_internal_value(self, data):
        if isinstance(data, bool):
            return data

        msg = _("must be 0 or 1, while got {data}.").format(data=str(data))

        try:
            data = int(data)
        except ValueError:
            raise serializers.ValidationError(msg)
        else:
            if data not in [0, 1]:
                raise serializers.ValidationError(msg)

        return bool(data)

    def to_representation(self, value):
        return "1" if value else "0"


class BoolToYesNoField(serializers.Field):
    def to_internal_value(self, data):
        if isinstance(data, bool):
            return data

        msg = _("must be 'no' or 'yes', while got {data}.").format(data=str(data))

        if data not in ['no', 'yes']:
            raise serializers.ValidationError(msg)

        return True if data == "yes" else False

    def to_representation(self, value):
        return "yes" if value else "no"


class TimestampField(serializers.Field):
    def to_representation(self, value):
        return int(value.timestamp())

    def to_internal_value(self, data):
        return datetime.fromtimestamp(int(data))


class MacAddressField(serializers.Field):
    def to_internal_value(self, data):
        return data.replace("-", ":")

    def to_representation(self, value):
        return value
        # return value.replace(":", "-")


class DeviceModelSerializer(serializers.ModelSerializer):
    class Meta:
        model = Device
        fields = ["name", "mac", "known", "ignore", "added_datetime"]

    def create(self, validated_data):
        """
        创建一个新的Device实例。
        """
        # 可以直接使用validated_data，因为字段名称与模型匹配
        # 对于那些不在validated_data中但需要默认值的字段，可以直接设置
        validated_data.setdefault('known', False)
        validated_data.setdefault('ignore', False)
        validated_data.setdefault('added_datetime', now())

        # 使用Device模型创建新实例
        device = Device.objects.create(**validated_data)
        return device

    def update(self, instance, validated_data):
        """
        更新现有的Device实例。
        """
        instance.name = validated_data.get('name', instance.name)
        instance.mac = validated_data.get('mac', instance.mac)
        instance.known = validated_data.get('known', instance.known)
        instance.ignore = validated_data.get('ignore', instance.ignore)
        instance.save()
        return instance


class DeviceJsonSerializer(serializers.Serializer):  # noqa

    index = serializers.IntegerField(default=0, source="id")
    mac = MacAddressField()
    ignore = serializers.BooleanField(default=False)
    added_datetime = serializers.DateTimeField(default=now)
    reject = serializers.IntegerField()
    up_time = serializers.DateTimeField(allow_null=True, required=False)
    online = serializers.BooleanField(allow_null=True, required=False, default=True)
    ip_addr = serializers.IPAddressField(allow_null=True)
    hostname = UnknownAsEmptyField(max_length=64, allow_null=True, required=False)
    comment = UnknownAsEmptyField(max_length=64, allow_null=True, required=False)
    client_type = UnknownAsEmptyField(max_length=64, allow_null=True, required=False)
    client_device = UnknownAsEmptyField(
        max_length=64, allow_null=True, required=False)

    def validate_reject(self, value):
        if value not in [0, 1, "0", "1"]:
            raise serializers.ValidationError(
                "Invalid reject. Only 0-1 are allowed.")
        return value


class DeviceParseSerializer(serializers.Serializer):  # noqa
    # downrate = serializers.CharField(allow_blank=True, required=False)
    # uprate = serializers.CharField(allow_blank=True, required=False)
    comment = UnknownAsEmptyField(max_length=64, allow_null=True, required=False)
    # connect_num = serializers.IntegerField()
    ip_addr = serializers.IPAddressField()
    # download = serializers.IntegerField()
    # total_up = serializers.IntegerField()
    # total_down = serializers.IntegerField()
    client_device = UnknownAsEmptyField(
        max_length=64, allow_null=True, required=False)
    uptime = serializers.DateTimeField()
    reject = serializers.IntegerField()
    mac = MacAddressField()
    id = serializers.IntegerField(required=False, allow_null=True)
    hostname = UnknownAsEmptyField(max_length=64, allow_null=True, required=False)
    timestamp = serializers.IntegerField()
    client_type = UnknownAsEmptyField(max_length=64, allow_null=True, required=False)
    # upload = serializers.IntegerField()
    online = serializers.BooleanField(required=False, allow_null=True)
    last_seen = serializers.DateTimeField(required=False, allow_null=True)


class ResultListMonitorLANIPSerializer(serializers.Serializer):  # noqa
    # IKuaiClient list_monitor_lanip() result
    total = serializers.IntegerField()
    data = DeviceParseSerializer(many=True)


class MacGroupSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    comment = UnknownAsEmptyField(allow_blank=True, required=False)
    group_name = serializers.CharField()
    addr_pool = serializers.CharField()


class ResultlistMacGroupsSerializer(serializers.Serializer):
    # IKuaiClient list_mac_groups() result
    total = serializers.IntegerField()
    data = MacGroupSerializer(many=True)

    @property
    def map(self):
        _data = self.validated_data["data"]

        ret = dict()

        for d in _data:
            ret[d["group_name"]] = split_name(d["addr_pool"])
        return dict(ret)

    @property
    def reverse_map(self):
        _data = self.validated_data["data"]

        ret = defaultdict(list)

        for d in _data:
            this_macs = split_name(d["addr_pool"])
            for mac in this_macs:
                ret[mac].append(d["group_name"])

        return dict(ret)


class ValidateMixin:
    def validate_week(self, value):
        # 确保week只包含1到7的数字
        if not set(value).issubset(set('1234567')):
            raise serializers.ValidationError(
                "Invalid week format. Only 1-7 are allowed.")
        return value

    def validate_weekdays(self, value):
        return self.validate_week(value)

    def validate_enabled(self, value):
        # 确保enabled字段是'yes'或'no'
        if value not in ['yes', 'no']:
            raise serializers.ValidationError("Enabled must be 'yes' or 'no'.")
        return value

    def validate_time(self, value):
        # 验证time字段的格式为'HH:MM-HH:MM'
        try:
            start_time, end_time = value.split('-')
            start_hour, start_minute = start_time.split(':')
            end_hour, end_minute = end_time.split(':')
            assert 0 <= int(start_hour) < 24 and 0 <= int(start_minute) < 60
            assert 0 <= int(end_hour) < 24 and 0 <= int(end_minute) < 60
        except (ValueError, AssertionError):
            raise serializers.ValidationError(
                "Invalid time format. Expected 'HH:MM-HH:MM'.")
        return value


class AclL7RuleSerializer(ValidateMixin, serializers.Serializer):  # noqa
    app_proto = serializers.CharField()
    src_addr = serializers.CharField()
    dst_addr = serializers.CharField(allow_blank=True)
    week = serializers.CharField()
    id = serializers.IntegerField()
    enabled = serializers.CharField()
    time = serializers.CharField()
    comment = serializers.CharField(allow_blank=True)
    prio = serializers.IntegerField()
    action = serializers.CharField()

    def validate_action(self, value):
        # 确保action字段是'allow'或'drop'
        if value not in ['accept', 'drop']:
            raise serializers.ValidationError("Action must be 'allow' or 'drop'.")
        return value


class ResultProtocolRulesSerializer(serializers.Serializer):
    # IKuaiClient list_acl_l7() result

    total = serializers.IntegerField()
    data = AclL7RuleSerializer(many=True)


class URLBlackRuleSerializer(ValidateMixin, serializers.Serializer):
    ip_addr = serializers.CharField(
        required=False, allow_blank=True, allow_null=True)
    id = serializers.IntegerField()
    enabled = serializers.CharField()
    week = serializers.CharField()
    comment = serializers.CharField(allow_blank=True)
    mode = serializers.IntegerField()
    domain = serializers.CharField()
    time = serializers.CharField()

    def validate_mode(self, value):
        if value not in [0, 1, "0", "1"]:
            raise serializers.ValidationError(
                "Invalid mode. Only digits 0, 1 are allowed.")
        return value


class ResultURLBlackRulesSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    data = URLBlackRuleSerializer(many=True)


class DomainBlackListSerializer(ValidateMixin, serializers.Serializer):
    ipaddr = serializers.CharField(
        required=False, allow_blank=True, allow_null=True)
    weekdays = serializers.CharField()
    id = serializers.IntegerField()
    enabled = serializers.CharField()
    comment = serializers.CharField(allow_blank=True)
    domain_group = serializers.CharField()
    time = serializers.CharField()

    def get_datatable_data(self, router_id):
        new_data = deepcopy(self.validated_data)

        ret = dict()
        ret["apply_to"] = new_data.pop("ipaddr", "").split(",")
        if ret["apply_to"] == ['']:
            ret["apply_to"] = []
        ret["enabled"] = new_data.pop("enabled") == "yes"
        ret["edit-url"] = reverse(
            "domain_blacklist-edit",
            kwargs={
                "router_id": router_id,
                "domain_blacklist_id": new_data["id"]})

        ret["delete-url"] = reverse(
            "domain_blacklist-delete",
            kwargs={
                "router_id": router_id,
                "domain_blacklist_id": new_data["id"]})

        weekdays = new_data.pop("weekdays")
        ret["days"] = []
        for day_name in days_string_conversion(weekdays):
            ret["days"].append(day_name)

        ret["start_time"], ret["end_time"] = new_data.pop("time").split("-")

        for k, v in new_data.items():
            ret[k] = v

        return ret


class ResultDomainBlackListSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    data = DomainBlackListSerializer(many=True)


class DomainBlacklistSubRuleSerializer(serializers.Serializer):
    enabled = DomainBlackListSerializer(many=True, required=False)
    disabled = DomainBlackListSerializer(many=True, required=False)


class URLBlackSubRuleSerializer(serializers.Serializer):
    enabled = URLBlackRuleSerializer(many=True, required=False)
    disabled = URLBlackRuleSerializer(many=True, required=False)


class AclL7SubRuleSerializer(serializers.Serializer):
    enabled = AclL7RuleSerializer(many=True, required=False)
    disabled = AclL7RuleSerializer(many=True, required=False)


class DeviceWithRuleParseSerializer(DeviceParseSerializer):
    domain_blacklist = DomainBlacklistSubRuleSerializer(required=False, default={})
    url_black = URLBlackSubRuleSerializer(required=False, default={})
    acl_l7 = AclL7SubRuleSerializer(required=False, default={})

    def get_datatable_data(self):
        new_data = deepcopy(self.validated_data)

        ret = {}

        try:
            device_instance = Device.objects.get(mac=new_data["mac"])
        except Device.DoesNotExist:
            device_instance = None

        # index
        new_data.pop("id", None)
        ret["index"] = device_instance.id if device_instance else None

        # name
        comment = new_data.pop("comment", None)
        ret["name"] = comment or new_data.get("hostname")

        # action
        ret["edit-url"] = None
        if device_instance:
            ret["edit-url"] = reverse(
                "device-edit",
                kwargs={
                    "router_id": device_instance.router.id,
                    "pk": device_instance.id
                })

        # online
        online = new_data.pop("online", True)
        if online is None:
            online = True
        ret["online"] = online

        # last_seen
        ret["last_seen"] = new_data.pop("last_seen", None)

        ret["ignored"] = False
        if device_instance:
            ret["ignored"] = device_instance.ignore

        ret["domain_blacklist"] = []

        if device_instance:
            domain_blacklist_data = new_data.pop("domain_blacklist")
            for enabled in ["enabled", "disabled"]:
                items = domain_blacklist_data.get(enabled, [])
                for item in items:
                    ret["domain_blacklist"].append({
                        "name": item["comment"] or "unknown",
                        "url": reverse(
                            "domain_blacklist-edit",
                            kwargs={
                                "router_id": device_instance.router.id,
                                "domain_blacklist_id": item["id"]}),
                        "enabled": enabled
                    })

        for k, v in new_data.items():
            # print(k)
            ret[k] = v

        return ret
