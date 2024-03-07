from collections import defaultdict
from copy import deepcopy
from datetime import datetime, time, timedelta
from urllib.parse import urljoin

from django.utils import timezone

from my_router import logger
from my_router.constants import DEFAULT_CACHE
from my_router.models import Device
from my_router.serializers import (AclL7RuleSerializer, DeviceModelSerializer,
                                   DeviceParseSerializer,
                                   DeviceWithRuleParseSerializer,
                                   DomainBlackListSerializer,
                                   MacGroupRuleSerializer,
                                   ResultDomainBlackListSerializer,
                                   ResultlistMacGroupsSerializer,
                                   ResultListMonitorLANIPSerializer,
                                   ResultProtocolRulesSerializer,
                                   ResultURLBlackRulesSerializer)
from my_router.utils import (get_acl_l7_list_cache_key,
                             get_block_mac_by_acl_l7_cache_key,
                             get_device_db_cache_key,
                             get_device_list_cache_key,
                             get_domain_blacklist_cache_key,
                             get_mac_groups_cache_key,
                             get_router_all_devices_mac_cache_key,
                             get_router_device_cache_key,
                             get_url_black_list_cache_key)


class RuleDataFilter:
    def __init__(self, rule_data):
        rule_data = [r for r in rule_data if r["enabled"] is True]
        self.rule_data = rule_data
        self.active_drop_all_protocol_strategies = (
            self.split_and_identify_active_drop_all_protocol_strategies_weekly())

    def _merge_daily_adjacent_strategies(self, strategies, extra_ignored_keys=None):
        extra_ignored_keys = extra_ignored_keys or []
        ignored_keys = ['start_time', 'end_time'] + extra_ignored_keys

        sorted_strategies = sorted(
            strategies, key=lambda x: (x["day"], x['start_time']))

        # 合并逻辑
        def merge_adjacent(sorted_list):
            merged_list = []
            prev = None
            for strategy in sorted_list:
                if (prev is not None
                        and ((strategy['start_time'] == prev['end_time']
                             or (datetime.strptime(strategy['start_time'], "%H:%M")
                                 - datetime.strptime(prev['end_time'], "%H:%M")
                                 <= timedelta(minutes=1)))
                             and all(strategy[k] == prev[k]
                                     for k in strategy
                                     if k not in ignored_keys))):

                    # 更新结束时间以合并
                    prev['end_time'] = strategy['end_time']
                else:
                    if prev is not None:
                        merged_list.append(prev)
                    prev = strategy.copy()  # 使用副本以避免修改原始输入
            if prev is not None:
                merged_list.append(prev)
            return merged_list

        # 递归合并直到没有变化
        while True:
            merged_strategies = merge_adjacent(sorted_strategies)

            # 如果长度没有变化，结束循环
            if len(merged_strategies) == len(sorted_strategies):
                break
            sorted_strategies = merged_strategies  # 准备下一轮合并

        return merged_strategies

    def split_and_identify_active_drop_all_protocol_strategies_weekly(self):
        weekdays = "1234567"  # From Monday to Sunday
        rule_data = deepcopy(self.rule_data)

        weekly_dominant_strategies = {day: [] for day in weekdays}

        for day in weekdays:
            times_for_day = set()
            for rd in rule_data:
                if day not in rd["weekdays"]:
                    continue

                times_for_day.update(set([d for d in rd['time'].split('-')]))

            if not times_for_day:
                continue

            times_for_day = sorted(times_for_day)

            time_ranges = [(times_for_day[i], times_for_day[i + 1]) for i in
                           range(len(times_for_day) - 1)]

            for start, end in time_ranges:
                start_dt = datetime.strptime(start, '%H:%M')
                end_dt = datetime.strptime(end, '%H:%M')

                # All strategies within this time range
                strategies_in_range = [
                    d for d in self.rule_data
                    if (day in d["weekdays"]
                        and datetime.strptime(
                                d['time'].split('-')[0], '%H:%M') <= start_dt
                        and datetime.strptime(
                                d['time'].split('-')[1], '%H:%M') >= end_dt)
                ]

                strategies_in_range = sorted(
                    strategies_in_range, key=lambda x: (
                        x['priority'], x['action'] != 'drop'))

                for strategy in strategies_in_range:
                    if strategy["action"] == "accept":
                        break

                    if strategy["app_proto"] == "所有协议":
                        weekly_dominant_strategies[day].append({
                            'day': day,
                            'start_time': start,
                            'end_time': end,
                            'policy': strategy['name'],
                            'priority': strategy['priority'],
                            'action': strategy['action'],
                            'app_proto': strategy['app_proto']
                        })
                        break

        # Convert the dictionary to a list
        dominant_strategies_weekly = []
        for day, strategies in weekly_dominant_strategies.items():
            dominant_strategies_weekly.extend(strategies)

        return dominant_strategies_weekly

    def get_dropping_all_proto_strategies(self):
        merge_strategies = self._merge_daily_adjacent_strategies(
            self.active_drop_all_protocol_strategies,
            extra_ignored_keys=["priority", "policy", "action", "app_proto"]
        )

        return [
            {k: v for k, v in d.items()
             if k not in ["priority", "policy", "action", "app_proto"]}
            for d in merge_strategies]

    @staticmethod
    def find_continuous_substrings(s):
        # Define the adjacency list for the graph, considering 7 is connected to 1
        adjacency_list = {
            '1': ['2', '7'],
            '2': ['1', '3'],
            '3': ['2', '4'],
            '4': ['3', '5'],
            '5': ['4', '6'],
            '6': ['5', '7'],
            '7': ['6', '1']
        }

        # Convert the string into a set for O(1) lookups
        digits_set = set(s)

        # Helper function to perform DFS and find connected components
        def dfs(node, visited, component):
            visited.add(node)
            component.append(node)
            for neighbour in adjacency_list[node]:
                if neighbour in digits_set and neighbour not in visited:
                    dfs(neighbour, visited, component)

        visited = set()
        components = []

        # Perform DFS for each digit in the string that hasn't been visited
        for digit in s:
            if digit not in visited:
                component = []
                dfs(digit, visited, component)
                components.append(''.join(sorted(component, key=lambda x: int(x))))

        # Special case handling for '7' and '1' to ensure '7' comes before '1'
        for i, component in enumerate(components):
            if '7' in component and '1' in component:
                components[i] = ''.join(
                    sorted(component, key=lambda x: ('1' if x == '7' else '0', x)))

        return components

    def merge_days(self, days):
        """合并连续的天数列表。"""
        return self.find_continuous_substrings(days)

    def merge_similar_strategies_by_day(self):
        dropping_all_proto_strategies = self.get_dropping_all_proto_strategies()
        strategies_by_signature = {}

        # Group strategies by their "signature"
        for strategy in dropping_all_proto_strategies:
            signature = tuple(
                (k, strategy[k]) for k in sorted(strategy) if k != 'day')
            if signature not in strategies_by_signature:
                strategies_by_signature[signature] = []
            strategies_by_signature[signature].append(strategy['day'])

        merged_strategies = []
        for signature, days in strategies_by_signature.items():
            merged_days_segments = self.merge_days(days)
            for segment in merged_days_segments:
                strategy = {k: v for k, v in signature}
                strategy['day'] = segment
                merged_strategies.append(strategy)

        return merged_strategies

    def find_current_and_next_range(self, now_datetime):
        block_time_range = self.merge_similar_strategies_by_day()

        if not block_time_range:
            return None, None

        current_range = None
        next_range = None
        current_day = now_datetime.isoweekday()
        current_time = now_datetime.time()

        # 为方便比较，将当前时间转换为分钟
        current_time_in_minutes = current_time.hour * 60 + current_time.minute

        # 初始化一个列表，用于存储转换后的时间范围及其原始数据
        parsed_ranges_with_original = []
        for block in block_time_range:
            days = [int(day) for day in block['day']]
            start_time = datetime.strptime(block['start_time'], '%H:%M').time()
            end_time = datetime.strptime(block['end_time'], '%H:%M').time()
            start_time_in_minutes = start_time.hour * 60 + start_time.minute
            end_time_in_minutes = end_time.hour * 60 + end_time.minute
            for day in days:
                parsed_ranges_with_original.append(
                    (day, start_time_in_minutes, end_time_in_minutes, block))

        # 查找当前时间范围
        for day, start_time, end_time, original_block in parsed_ranges_with_original:
            if day == current_day and start_time <= current_time_in_minutes < end_time:  # noqa
                current_range = original_block
                break

        # 查找下一个时间范围
        sorted_ranges = sorted(
            parsed_ranges_with_original, key=lambda x: (x[0], x[1]))
        for day, start_time, end_time, original_block in sorted_ranges:
            if day > current_day or (
                    day == current_day and start_time > current_time_in_minutes):
                next_range = original_block
                break
        # 如果没有找到下一个时间范围，可能下一个时间范围在下周
        if not next_range and sorted_ranges:
            next_range = sorted_ranges[0][3]  # 获取排序后的第一个时间范围的原始数据

        return current_range, next_range


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
        self._macs_block_mac_by_acl_l7 = None

        # {{{ cache_keys
        self.device_list_cache_key = get_device_list_cache_key(router_id)
        self.all_mac_cache_key = get_router_all_devices_mac_cache_key(router_id)
        self.url_black_list_cache_key = get_url_black_list_cache_key(router_id)
        self.mac_groups_cache_key = get_mac_groups_cache_key(router_id)
        self.acl_l7_list_cache_key = get_acl_l7_list_cache_key(router_id)
        self.domain_blacklist_cache_key = get_domain_blacklist_cache_key(router_id)
        self.macs_block_mac_by_acl_l7_cache_key = (
            get_block_mac_by_acl_l7_cache_key(router_id))
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
        self._macs_block_mac_by_acl_l7 = None

    def init_data_from_cache(self):
        self._devices = DEFAULT_CACHE.get(self.device_list_cache_key, [])
        self._url_black_list = DEFAULT_CACHE.get(self.url_black_list_cache_key, [])
        self._mac_groups_list = DEFAULT_CACHE.get(self.mac_groups_cache_key, [])
        self._acl_l7_list = DEFAULT_CACHE.get(self.acl_l7_list_cache_key, [])
        self._domain_black_list = DEFAULT_CACHE.get(
            self.domain_blacklist_cache_key, [])
        self._macs_block_mac_by_acl_l7 = DEFAULT_CACHE.get(
            self.macs_block_mac_by_acl_l7_cache_key, []
        )

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
    def macs_block_mac_by_acl_l7(self):
        if self._macs_block_mac_by_acl_l7 is None:
            ret = list(Device.objects.filter(
                router=self.router_instance,
                block_mac_by_proto_ctrl=True).values_list("mac", flat=True))
            self._macs_block_mac_by_acl_l7 = ret

            DEFAULT_CACHE.set(
                self.macs_block_mac_by_acl_l7_cache_key, ret)
        return self._macs_block_mac_by_acl_l7

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

        for mac in all_cached_macs:
            assert isinstance(mac, str)

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
                device_info["last_seen"] = timezone.now()
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
                            mac_rule_dict[_mac]["domain_blacklist"]["enabled"].append(  # noqa
                                domain_blacklist)
                        else:
                            mac_rule_dict[_mac]["domain_blacklist"].setdefault(
                                "disabled", [])  # noqa
                            mac_rule_dict[_mac]["domain_blacklist"][
                                "disabled"].append(domain_blacklist)

        for url_black in deepcopy(self.url_black_list):
            ip_addrs = url_black["ip_addr"].split(",")
            for ip_addr in ip_addrs:
                if ip_addr in self.mac_groups:
                    for _mac in self.mac_groups[ip_addr]:
                        mac_rule_dict[_mac].setdefault("url_black", {})
                        if url_black["enabled"] == "yes":
                            mac_rule_dict[_mac]["url_black"].setdefault("enabled", [])  # noqa
                            mac_rule_dict[_mac]["url_black"]["enabled"].append(url_black)  # noqa
                        else:
                            mac_rule_dict[_mac]["url_black"].setdefault("disabled", [])  # noqa
                            mac_rule_dict[_mac]["url_black"]["disabled"].append(url_black)  # noqa

        for acl_l7 in deepcopy(self.acl_l7_list):
            src_addrs = acl_l7["src_addr"].split(",")
            for src_addr in src_addrs:
                if src_addr in self.mac_groups:
                    for _mac in self.mac_groups[src_addr]:
                        mac_rule_dict[_mac].setdefault("acl_l7", {})
                        if acl_l7["enabled"] == "yes":
                            mac_rule_dict[_mac]["acl_l7"].setdefault("enabled", [])
                            mac_rule_dict[_mac]["acl_l7"]["enabled"].append(acl_l7)
                        else:
                            mac_rule_dict[_mac]["acl_l7"].setdefault("disabled", [])
                            mac_rule_dict[_mac]["acl_l7"]["disabled"].append(
                                acl_l7)

        return dict(mac_rule_dict)

    def get_device_rule_data(self):
        device_dict = deepcopy(self.device_dict)

        # {{{ include devices which were not online
        all_macs = list(self.get_cached_all_mac())

        for mac in all_macs:
            if mac in self.online_mac_list:
                continue

            cached_this_device_info = self.get_cached_device_info(mac)

            if not cached_this_device_info:
                continue

            serializer = DeviceParseSerializer(data=cached_this_device_info)
            serializer.is_valid(raise_exception=True)

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
            serializer.is_valid(raise_exception=True)

            new_dict[mac] = serializer.get_datatable_data()

        return new_dict

    def get_device_view_data(self):
        device_rule_data = self.get_device_rule_data()

        device_rule_data = dict(
            sorted(device_rule_data.items(), key=lambda x: x[1]['index']))

        device_list = list(device_rule_data.values())
        device_list_for_views = []

        for device_info in device_list:
            device_list_for_views.append(device_info)
        return device_list

    def get_domain_blacklist_data(self):
        domain_blacklist = deepcopy(self.domain_blacklist)
        ret = {}

        for dblist_item in domain_blacklist:
            dblist_id = int(dblist_item["id"])
            serializer = DomainBlackListSerializer(data=dblist_item)
            serializer.is_valid(raise_exception=True)

            ret[dblist_id] = serializer.get_datatable_data(self.router_id)
        return ret

    def get_domain_blacklist_list_for_view(self):
        domain_blacklist_data = self.get_domain_blacklist_data()
        return list(domain_blacklist_data.values())

    @property
    def router_domain_blacklist_url(self):
        return urljoin(self.router_instance.url, "/#/behavior/banned-site")

    @property
    def router_protocol_control_url(self):
        return urljoin(self.router_instance.url, "/#/behavior/pro-control")

    @property
    def router_mac_control_url(self):
        return urljoin(self.router_instance.url, "/#/behavior/mac-control")

    @property
    def router_mac_group_url(self):
        return urljoin(self.router_instance.url, "/#/behavior/mac-group")

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
            serializer.is_valid(raise_exception=True)

            ret[acl_l7_id] = serializer.get_datatable_data(self.router_id)

        return ret

    def get_acl_l7_list_for_view(self):
        acl_l7_list_data = self.get_acl_l7_list_data()

        return list(acl_l7_list_data.values())

    def get_mac_groups_data(self):
        mac_groups = deepcopy(self.mac_groups_list["data"])

        ret = {}
        for m_group in mac_groups:
            group_id = int(m_group["id"])
            serializer = MacGroupRuleSerializer(data=m_group)
            serializer.is_valid(raise_exception=True)

            ret[group_id] = serializer.get_datatable_data(self.router_id)

        return ret

    def get_mac_group_list_for_view(self):
        mac_groups_data = self.get_mac_groups_data()
        mac_groups_list = list(mac_groups_data.values())
        for mac_group in mac_groups_list:
            exist_macs = mac_group["apply_to"]

            devices = Device.objects.filter(
                router=self.router_instance, mac__in=exist_macs)

            macs = []
            for device in devices:
                serializer = DeviceModelSerializer(instance=device)
                macs.append(serializer.data)
            mac_group["apply_to"] = macs

        return mac_groups_list

    def get_view_data(self, info_name):
        assert info_name in [
            "device", "domain_blacklist", "url_black", "acl_l7", "mac_group"]

        if info_name == "device":
            return self.get_device_view_data()

        elif info_name == "domain_blacklist":
            return self.get_domain_blacklist_list_for_view()

        # todo: not implemented yet
        elif info_name == "url_black":
            return self.get_url_black_view_data()

        elif info_name == "acl_l7":
            return self.get_acl_l7_list_for_view()

        elif info_name == "mac_group":
            return self.get_mac_group_list_for_view()

        raise NotImplementedError()

    def get_active_acl_mac_rule_of_device(self, mac):
        acl_mac_list = self.ikuai_client.list_acl_mac()["data"]

        for acl_mac in acl_mac_list:
            if acl_mac["mac"] == mac and acl_mac["enabled"] == "yes":
                return acl_mac

        return None

    def remove_active_acl_mac_rule_of_device(self, mac):
        logger.debug(f"Removed acl_mac of {mac}.")

        active_acl_mac = self.get_active_acl_mac_rule_of_device(mac)

        if active_acl_mac is None:
            return

        return self.ikuai_client.del_acl_mac(acl_mac_id=active_acl_mac["id"])

    def add_acl_mac_rule(self, data):
        logger.debug(f"Added acl_mac: {data}.")
        return self.ikuai_client.add_acl_mac(**data)

    def update_mac_control_rule_from_acl_l7_by_time(self, now_datetime=None):

        # now_datetime，使用当前UTC时间
        if now_datetime is None:
            now_datetime = timezone.now()

        # 检查now_datetime是否为tz-aware
        if (now_datetime.tzinfo is None  # pragma: no cover
                or now_datetime.tzinfo.utcoffset(now_datetime) is None):
            raise ValueError("now_datetime must be timezone aware")

        now_datetime = timezone.localtime(now_datetime)
        t23_59 = datetime.combine(
            now_datetime.date(), time(23, 59), tzinfo=now_datetime.tzinfo)

        time_difference = now_datetime - t23_59

        if timedelta(seconds=0) <= time_difference <= timedelta(seconds=60):
            logger.info("Skip updating when the time is between 23:59 and 00:00")
            return

        macs_linking_mac_ctl_to_acl_l7 = self.macs_block_mac_by_acl_l7
        device_rule_data = self.get_device_rule_data()

        for mac in macs_linking_mac_ctl_to_acl_l7:
            acl_l7_list = device_rule_data[mac]["acl_l7"]

            if not acl_l7_list:
                self.remove_active_acl_mac_rule_of_device(mac)
                continue

            rule_filter = RuleDataFilter(acl_l7_list)

            current_tr, next_tr = (
                rule_filter.find_current_and_next_range(now_datetime))

            active_acl_mac_rule = self.get_active_acl_mac_rule_of_device(mac)
            logger.debug(f"Active acl_mac is {active_acl_mac_rule}.")

            def convert_time_rule_to_acl_mac_data(_mac, _time_rule):
                return {
                    "mac": _mac,
                    "week": _time_rule["day"],
                    "time": f"{_time_rule['start_time']}-{_time_rule['end_time']}"}

            if current_tr is None and next_tr is None:
                logger.debug(f"Both current_tr and next_tr for '{mac}' are None")
                self.remove_active_acl_mac_rule_of_device(mac)

                continue

            if current_tr is not None:
                logger.debug(f"current_tr is {current_tr}")

                current_tr_acl_mac_data = (
                    convert_time_rule_to_acl_mac_data(mac, current_tr))

                need_update_active_rule = False

                if active_acl_mac_rule is None:
                    need_update_active_rule = True
                else:
                    for key in ["week", "time"]:
                        if active_acl_mac_rule[key] != current_tr_acl_mac_data[key]:
                            need_update_active_rule = True

                if need_update_active_rule:
                    self.add_acl_mac_rule(current_tr_acl_mac_data)

                assert next_tr is not None

                logger.debug(f"next_tr is '{next_tr}'")
                if current_tr == next_tr:
                    logger.debug(
                        "current_tr and next_tr are the same, nothing to do")
                    pass
                else:
                    logger.debug(
                        "need to create a task to add acl_mac rule for next_tr")

            else:
                assert current_tr is None
                logger.debug(f"current_tr is {current_tr}")

                assert next_tr is not None
                logger.debug(f"next_tr is '{next_tr}'")

                next_tr_acl_mac_data = (
                    convert_time_rule_to_acl_mac_data(mac, next_tr))
                need_update_active_rule = False

                if active_acl_mac_rule is None:
                    need_update_active_rule = True
                else:
                    for key in ["week", "time"]:
                        if active_acl_mac_rule[key] != next_tr_acl_mac_data[key]:
                            need_update_active_rule = True

                if need_update_active_rule:
                    self.add_acl_mac_rule(next_tr_acl_mac_data)

    def update_mac_control_rule_from_acl_l7(self):
        return self.update_mac_control_rule_from_acl_l7_by_time(timezone.now())
