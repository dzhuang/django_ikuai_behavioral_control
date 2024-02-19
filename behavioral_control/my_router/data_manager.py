from collections import defaultdict
from copy import deepcopy
from urllib.parse import urljoin

from django.utils.timezone import now

from my_router.constants import DEFAULT_CACHE
from my_router.models import Device
from my_router.serializers import (AclL7RuleSerializer, DeviceModelSerializer,
                                   DeviceParseSerializer,
                                   DeviceWithRuleParseSerializer,
                                   DomainBlackListSerializer,
                                   ResultDomainBlackListSerializer,
                                   ResultlistMacGroupsSerializer,
                                   ResultListMonitorLANIPSerializer,
                                   ResultProtocolRulesSerializer,
                                   ResultURLBlackRulesSerializer)
from my_router.utils import (get_acl_l7_list_cache_key,
                             get_device_db_cache_key,
                             get_device_list_cache_key,
                             get_domain_blacklist_cache_key,
                             get_mac_groups_cache_key,
                             get_router_all_devices_mac_cache_key,
                             get_router_device_cache_key,
                             get_url_black_list_cache_key)


class RouterDataManager:
    def __init__(self, router_instance=None, router_id=None):
        if router_instance is None and router_id is None:
            raise ValueError(
                "Either 'router_instance' or 'router_id' should be "
                "a non None value")

        if router_instance is None:
            from my_router.models import Router
            router_instance = Router.objects.get(id=router_id)

        router_id = router_instance.id
        self.router_id = router_id

        self.router_instance = router_instance
        self.ikuai_client = router_instance.get_client()

        self._devices = None
        self._device_dict = None
        self._online_mac_list = None
        self._mac_groups_list = None
        self._mac_groups_map = None
        self._mac_groups_map_reverse = None
        self._acl_l7_list = None
        self._url_black_list = None
        self._domain_black_list = None

        # {{{ cache_keys
        self.device_list_cache_key = get_device_list_cache_key(router_id)
        self.all_mac_cache_key = get_router_all_devices_mac_cache_key(router_id)
        self.all_info_cache_key = get_device_list_cache_key(router_id)
        self.url_black_list_cache_key = get_url_black_list_cache_key(router_id)
        self.mac_groups_cache_key = get_mac_groups_cache_key(router_id)
        self.acl_l7_list_cache_key = get_acl_l7_list_cache_key(router_id)
        self.domain_blacklist_cache_key = get_domain_blacklist_cache_key(router_id)
        # }}}

        self.is_initialized_from_cached_data = False

    def reset_property_cache(self):
        self._devices = None
        self._device_dict = None
        self._online_mac_list = None
        self._mac_groups_list = None
        self._mac_groups_map = None
        self._mac_groups_map_reverse = None
        self._acl_l7_list = None
        self._url_black_list = None
        self._domain_black_list = None

    def init_data_from_cache(self):
        self._devices = DEFAULT_CACHE.get(self.device_list_cache_key, [])
        self._url_black_list = DEFAULT_CACHE.get(self.url_black_list_cache_key, [])
        self._mac_groups_list = DEFAULT_CACHE.get(self.mac_groups_cache_key, [])
        self._acl_l7_list = DEFAULT_CACHE.get(self.acl_l7_list_cache_key, [])
        self._domain_black_list = DEFAULT_CACHE.get(
            self.domain_blacklist_cache_key, [])

        self.is_initialized_from_cached_data = True

    def cache_all_data(self):
        if not self.is_initialized_from_cached_data:
            DEFAULT_CACHE.set(self.device_list_cache_key, self.devices)
            DEFAULT_CACHE.set(self.url_black_list_cache_key, self.url_black_list)
            DEFAULT_CACHE.set(self.mac_groups_cache_key, self.mac_groups_list)
            DEFAULT_CACHE.set(self.acl_l7_list_cache_key, self.acl_l7_list)
            DEFAULT_CACHE.set(self.domain_blacklist_cache_key, self.domain_blacklist)

    def purge_local_cache_and_update_devices(self):
        # removed data cached in the instance
        self._devices = None
        return self.devices

    def update_device_db_instances(self):
        for device_info in self.devices:
            json_serializer = DeviceParseSerializer(data=device_info)
            json_serializer.is_valid(raise_exception=True)
            device_info_data = json_serializer.data

            mac = device_info_data["mac"]
            model_data = {"mac": mac}

            name = device_info_data.get("comment", device_info_data.get("hostname"))
            if name:
                model_data["name"] = name

            instances = Device.objects.filter(mac=mac)
            if instances.count():
                instance = instances[0]
            else:
                instance = None

            d_serializer = DeviceModelSerializer(instance=instance, data=model_data)
            d_serializer.is_valid(raise_exception=True)
            if instance is None:
                d_serializer.save(router=self.router_instance)
            else:
                # When fetching remote data, only name and mac is saved in
                # database. So it is expensive to save/update each existing
                # device at each fetch.
                # We cache the name for comparing before determine whether to do
                # the update.
                cached_device_name = DEFAULT_CACHE.get(get_device_db_cache_key(mac))
                if name and name != cached_device_name:
                    d_serializer.update(instance, d_serializer.data)

    @property
    def devices(self):
        if self._devices is None:
            devices_json = self.ikuai_client.list_monitor_lanip()
            serializer = ResultListMonitorLANIPSerializer(data=devices_json)
            serializer.is_valid(raise_exception=True)

            # fixme: default number of devices is maximum 100
            self._devices = serializer.data["data"]

            if not self.is_initialized_from_cached_data:
                self.update_device_db_instances()
                DEFAULT_CACHE.set(self.device_list_cache_key, self._devices)

        return self._devices

    @property
    def device_dict(self):
        if self._device_dict is None:
            ret = dict()

            for device_info in deepcopy(self.devices):
                mac = device_info["mac"]
                ret[mac] = device_info

            self._device_dict = ret

        return self._device_dict

    @property
    def online_mac_list(self):
        return list(self.device_dict.keys())

    def get_device_cache_key(self, mac):
        return get_router_device_cache_key(self.router_id, mac)

    def get_cached_all_mac(self):
        return DEFAULT_CACHE.get(self.all_mac_cache_key, set())

    def update_all_mac_cache(self):
        all_cached_macs = self.get_cached_all_mac()
        all_cached_macs = all_cached_macs | set(self.online_mac_list)

        # this should be done with a test
        def check_no_nesting(input_list):
            # 遍历列表中的每个元素
            for item in input_list:
                # 如果元素是列表，则返回False
                if isinstance(item, list):
                    return False
            # 如果所有元素都不是列表，则返回True
            return True

        assert check_no_nesting(all_cached_macs)

        if not self.is_initialized_from_cached_data:
            DEFAULT_CACHE.set(self.all_mac_cache_key, all_cached_macs)

    def get_cached_device_info(self, mac):
        return DEFAULT_CACHE.get(self.get_device_cache_key(mac))

    def cache_device_info(self, mac, info):
        DEFAULT_CACHE.set(self.get_device_cache_key(mac), info)

    def update_device_cache_info_attrs(self, mac, **kwargs):
        info = self.get_cached_device_info(mac)
        info.update(kwargs)
        self.cache_device_info(mac, info)

    # todo: remove single cached device
    def cache_each_device_info(self):
        if not self.is_initialized_from_cached_data:
            for mac, device_info in deepcopy(self.device_dict).items():
                device_info["last_seen"] = now()
                self.cache_device_info(mac, device_info)

    @property
    def mac_groups_list(self):
        if self._mac_groups_list is None:
            result = self.ikuai_client.list_mac_groups()
            serializer = ResultlistMacGroupsSerializer(data=result)
            serializer.is_valid(raise_exception=True)

            # Note: we are caching "total" and "data", not just "data"
            # because we want to use the map and reverse_map method
            # of the serializer later.
            self._mac_groups_list = serializer.data

            if not self.is_initialized_from_cached_data:
                DEFAULT_CACHE.set(self.mac_groups_cache_key, self._mac_groups_list)

        return self._mac_groups_list

    @property
    def mac_groups(self):
        if self._mac_groups_map is None:
            serializer = ResultlistMacGroupsSerializer(data=self.mac_groups_list)
            serializer.is_valid(raise_exception=True)
            self._mac_groups_map = serializer.map
            self.mac_groups_list  # noqa
        return self._mac_groups_map

    @property
    def mac_groups_reverse(self):
        if self._mac_groups_map_reverse is None:
            serializer = ResultlistMacGroupsSerializer(data=self.mac_groups_list)
            serializer.is_valid(raise_exception=True)
            self._mac_groups_map_reverse = serializer.reverse_map
        return self._mac_groups_map_reverse

    @property
    def acl_l7_list(self):
        if self._acl_l7_list is None:
            result = self.ikuai_client.list_acl_l7()
            serializer = ResultProtocolRulesSerializer(data=result)
            serializer.is_valid(raise_exception=True)
            self._acl_l7_list = serializer.data["data"]

            if not self.is_initialized_from_cached_data:
                DEFAULT_CACHE.set(self.acl_l7_list_cache_key, self._acl_l7_list)

        return self._acl_l7_list

    @property
    def url_black_list(self):
        # todo: note that ip_addr is in fact mac_addr

        if self._url_black_list is None:
            result = self.ikuai_client.list_url_black()
            serializer = ResultURLBlackRulesSerializer(data=result)
            serializer.is_valid(raise_exception=True)
            self._url_black_list = serializer.data["data"]

            if not self.is_initialized_from_cached_data:
                DEFAULT_CACHE.set(
                    self.url_black_list_cache_key, self._url_black_list)

        return self._url_black_list

    @property
    def domain_blacklist(self):
        # todo: note that ipaddr is in fact mac_addr

        if self._domain_black_list is None:
            result = self.ikuai_client.list_domain_blacklist()
            serializer = ResultDomainBlackListSerializer(data=result)
            serializer.is_valid(raise_exception=True)
            self._domain_black_list = serializer.data["data"]

            if not self.is_initialized_from_cached_data:
                DEFAULT_CACHE.set(
                    self.domain_blacklist_cache_key, self._domain_black_list)

        return self._domain_black_list

    def get_device_rule_dict(self):
        mac_rule_dict = defaultdict(dict)
        for domain_blacklist in deepcopy(self.domain_blacklist):
            ipaddrs = domain_blacklist["ipaddr"].split(",")
            for ipaddr in ipaddrs:
                if ipaddr in self.mac_groups:
                    for _mac in self.mac_groups[ipaddr]:
                        mac_rule_dict[_mac].setdefault("domain_blacklist", {})
                        if domain_blacklist["enabled"] == "yes":
                            mac_rule_dict[_mac]["domain_blacklist"].setdefault("enabled", [])  # noqa
                            if domain_blacklist not in mac_rule_dict[_mac][
                                    "domain_blacklist"]["enabled"]:
                                mac_rule_dict[_mac]["domain_blacklist"]["enabled"].append(  # noqa
                                    domain_blacklist)
                        else:
                            mac_rule_dict[_mac]["domain_blacklist"].setdefault(
                                "disabled", [])  # noqa
                            if domain_blacklist not in mac_rule_dict[_mac][
                                    "domain_blacklist"]["disabled"]:
                                mac_rule_dict[_mac]["domain_blacklist"][
                                    "disabled"].append(  # noqa
                                    domain_blacklist)

        for url_black in deepcopy(self.url_black_list):
            ip_addrs = url_black["ip_addr"].split(",")
            for ip_addr in ip_addrs:
                if ip_addr in self.mac_groups:
                    for _mac in self.mac_groups[ip_addr]:
                        mac_rule_dict[_mac].setdefault("url_black", {})
                        if url_black["enabled"] == "yes":
                            mac_rule_dict[_mac]["url_black"].setdefault("enabled", [])  # noqa
                            if url_black not in mac_rule_dict[_mac]["url_black"]["enabled"]:  # noqa
                                mac_rule_dict[_mac]["url_black"]["enabled"].append(
                                    url_black)
                        else:
                            mac_rule_dict[_mac]["url_black"].setdefault("disabled", [])  # noqa
                            if url_black not in mac_rule_dict[_mac]["url_black"]["disabled"]:  # noqa
                                mac_rule_dict[_mac]["url_black"]["disabled"].append(url_black)  # noqa

        for acl_l7 in deepcopy(self.acl_l7_list):
            src_addrs = acl_l7["src_addr"].split(",")
            for src_addr in src_addrs:
                if src_addr in self.mac_groups:
                    for _mac in self.mac_groups[src_addr]:
                        mac_rule_dict[_mac].setdefault("acl_l7", {})
                        if acl_l7["enabled"] == "yes":
                            mac_rule_dict[_mac]["acl_l7"].setdefault("enabled", [])
                            if acl_l7 not in mac_rule_dict[_mac][
                                    "acl_l7"]["enabled"]:
                                mac_rule_dict[_mac]["acl_l7"]["enabled"].append(
                                    acl_l7)
                        else:
                            mac_rule_dict[_mac]["acl_l7"].setdefault("disabled", [])
                            if acl_l7 not in mac_rule_dict[_mac][
                                    "acl_l7"]["disabled"]:
                                mac_rule_dict[_mac]["acl_l7"]["disabled"].append(
                                    acl_l7)

        return dict(mac_rule_dict)

    def get_device_rule_data(self):
        device_dict = deepcopy(self.device_dict)

        # {{{ include devices which were not online
        all_macs = list(DEFAULT_CACHE.get(self.all_mac_cache_key))

        for mac in all_macs:
            if mac in self.online_mac_list:
                continue

            cached_this_device_info = DEFAULT_CACHE.get(
                self.get_device_cache_key(mac), None)

            if not cached_this_device_info:
                continue

            serializer = DeviceParseSerializer(data=cached_this_device_info)
            if not serializer.is_valid():
                continue

            device_dict[mac] = cached_this_device_info
            device_dict[mac]["online"] = False

        # }}}

        mac_rule_dict = self.get_device_rule_dict()
        for mac, device_info in device_dict.items():
            if mac in mac_rule_dict:
                device_info.update(mac_rule_dict[mac])

        return self.get_device_list_for_views(device_dict)

    def get_device_list_for_views(self, device_dict):
        new_dict = {}

        for mac, device_info in device_dict.items():
            serializer = DeviceWithRuleParseSerializer(data=device_info)
            if not serializer.is_valid():
                continue

            new_dict[mac] = serializer.get_datatable_data()

        return new_dict

    def get_device_view_data(self):
        device_rule_data = self.get_device_rule_data()

        device_rule_data = dict(
            sorted(device_rule_data.items(), key=lambda x: x[1]['index']))

        device_list = list(device_rule_data.values())
        device_list_for_views = []

        for device_info in device_list:
            serializer = DeviceWithRuleParseSerializer(data=device_info)
            if not serializer.is_valid():
                continue

            device_list_for_views.append(serializer.data)
        return device_list

    def get_domain_blacklist_data(self):
        domain_blacklist = deepcopy(self.domain_blacklist)
        ret = {}

        for dblist_item in domain_blacklist:
            dblist_id = int(dblist_item["id"])
            serializer = DomainBlackListSerializer(data=dblist_item)
            if not serializer.is_valid():
                continue

            ret[dblist_id] = serializer.get_datatable_data(self.router_id)
        return ret

    def get_domain_blacklist_list_for_view(self):
        domain_blacklist_data = self.get_domain_blacklist_data()
        return list(domain_blacklist_data.values())

    @property
    def router_domain_blacklist_url(self):
        return urljoin(self.router_instance.url, "#/behavior/banned-site")

    @property
    def router_protocol_control_url(self):
        return urljoin(self.router_instance.url, "#/behavior/pro-control")

    def get_url_black_view_data(self):
        url_black = deepcopy(self.url_black_list)
        enabled = []
        disabled = []

        for url_black_item in url_black:
            mac_list = url_black_item["ip_addr"].split(",")
            url_black_item.update({"apply_to": mac_list})
            if url_black_item["enabled"] == "yes":
                enabled.append(url_black_item)
            else:
                disabled.append(url_black_item)

        return {"enabled": enabled, "disabled": disabled}

    def get_acl_l7_list_data(self):
        acl_l7 = deepcopy(self.acl_l7_list)

        ret = {}
        for acl_l7_item in acl_l7:
            acl_l7_id = int(acl_l7_item["id"])
            serializer = AclL7RuleSerializer(data=acl_l7_item)
            if not serializer.is_valid():
                continue

            ret[acl_l7_id] = serializer.get_datatable_data(self.router_id)

        return ret

    def get_acl_l7_list_for_view(self):
        acl_l7_list_data = self.get_acl_l7_list_data()

        return list(acl_l7_list_data.values())

    def get_view_data(self, info_name):
        assert info_name in [
            "device", "domain_blacklist", "url_black", "acl_l7"]

        if info_name == "device":
            return self.get_device_view_data()

        elif info_name == "domain_blacklist":
            return self.get_domain_blacklist_list_for_view()

        elif info_name == "url_black":
            return self.get_url_black_view_data()

        elif info_name == "acl_l7":
            return self.get_acl_l7_list_for_view()
