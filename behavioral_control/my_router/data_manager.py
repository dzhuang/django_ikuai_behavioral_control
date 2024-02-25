import hashlib
import json
from collections import defaultdict
from copy import deepcopy
from datetime import datetime
from urllib.parse import urljoin

from django.utils import timezone

from my_router.constants import CACHE_VERSION, DEFAULT_CACHE
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


def split_and_identify_dominant_strategies_weekly_future(
        data, future_days=7):

    data = [d for d in data if d["enabled"] is True]

    # 生成未来7天的日期列表
    future_dates = [timezone.now().date() + timezone.timedelta(days=i)
                    for i in range(future_days)]
    future_weekdays = [(d.weekday() + 1) % 7 + 1 for d in future_dates]

    # 将Python的weekday转换为1-7表示周一到周日
    all_times = sorted(
        set([time for d in data
             for time in [d['time'].split('-')[0], d['time'].split('-')[1]]]))
    time_ranges = [
        (all_times[i], all_times[i+1])
        for i in range(len(all_times)-1) if all_times[i] != all_times[i+1]]

    # 按照未来7天处理
    weekly_dominant_strategies = {str(day): [] for day in future_weekdays}

    for idx, day in enumerate(future_weekdays):
        for start, end in time_ranges:
            start_dt = datetime.strptime(start, '%H:%M')
            end_dt = datetime.strptime(end, '%H:%M')

            # 在此时间段内的所有策略
            strategies_in_range = [
                d for d in data
                if (str(day) in d['weekdays']
                    and datetime.strptime(d['time'].split('-')[0], '%H:%M') < end_dt
                    and datetime.strptime(d['time'].split('-')[1], '%H:%M') > start_dt)  # noqa
            ]

            if strategies_in_range:
                # 选出此时间段优先级最高的策略
                highest_priority_strategy = min(
                    strategies_in_range, key=lambda x: x['priority'])
                weekly_dominant_strategies[str(day)].append({
                    'date': future_dates[idx].isoformat(),
                    'time_range': f"{start}-{end}",
                    'policy': highest_priority_strategy['name'],
                    'priority': highest_priority_strategy['priority'],
                    'action': highest_priority_strategy['action'],
                    'app_proto': highest_priority_strategy['app_proto'],
                })

    # 将字典转换为列表
    dominant_strategies_weekly_future = []
    for strategies in weekly_dominant_strategies.values():
        dominant_strategies_weekly_future.extend(strategies)

    return dominant_strategies_weekly_future


def filter_and_merge_strategies(data, future_days=7):
    # 首先调用之前的函数获取未来几天的策略数据
    strategies = split_and_identify_dominant_strategies_weekly_future(
        data,
        future_days)

    print(strategies)

    # 筛选出action为drop且'app_proto'为'所有协议'的结果
    filtered_strategies = [
        strategy for strategy in strategies
        if strategy['action'] == 'drop' and strategy.get('app_proto') == '所有协议'
    ]

    # 合并连续的时间段
    merged_strategies = []
    for strategy in filtered_strategies:
        if not merged_strategies:
            merged_strategies.append(strategy)
        else:
            last_strategy = merged_strategies[-1]
            last_end_time = last_strategy['time_range'].split('-')[1]
            current_start_time = strategy['time_range'].split('-')[0]

            # 如果时间段连续且在同一天内，则合并
            if last_end_time == current_start_time and last_strategy['date'] == \
                    strategy['date']:
                new_time_range = (
                    f"{last_strategy['time_range'].split('-')[0]}"
                    f"-{strategy['time_range'].split('-')[1]}")
                last_strategy['time_range'] = new_time_range
            else:
                merged_strategies.append(strategy)

    # 转换日期为星期几
    for strategy in merged_strategies:
        strategy_date = datetime.strptime(strategy['date'], '%Y-%m-%d')
        strategy['day'] = strategy_date.isoweekday()
        del strategy['date']  # 删除日期键，仅保留星期几

    return merged_strategies


def merge_similar_strategies(data, future_days=7):
    strategies = filter_and_merge_strategies(data, future_days)

    # 检查是否所有条目除了day外都一样
    if not strategies:
        return []

    # 用于比较的键列表，除去'day'
    comparison_keys = [key for key in strategies[0] if key != 'day']

    # 检查除了'day'以外的所有键是否在所有策略中都相同
    all_same_except_day = all(
        all(strategy[key] == strategies[0][key]
            for key in comparison_keys) for strategy in strategies
    )

    if all_same_except_day:
        # 合并所有的'day'值，排序并去重
        merged_days = sorted(set(strategy['day'] for strategy in strategies))
        # 创建一个新的策略条目，其'day'值为合并后的结果，其它键值与原条目相同
        merged_strategy = {key: strategies[0][key] for key in strategies[0]}
        merged_strategy['day'] = ''.join(map(str, merged_days))
        return [merged_strategy]
    else:
        return strategies


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
        self.all_info_cache_key = get_device_list_cache_key(router_id)
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
    def macs_block_mac_by_acl_l7(self):
        if self._macs_block_mac_by_acl_l7 is None:
            ret = list(Device.objects.filter(
                router=self.router_instance,
                block_mac_by_proto_ctrl=True).values_list("mac", flat=True))
            self._macs_block_mac_by_acl_l7 = ret
            if not self.is_initialized_from_cached_data:
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
        return urljoin(self.router_instance.url, "/#/behavior/banned-site")

    @property
    def router_protocol_control_url(self):
        return urljoin(self.router_instance.url, "/#/behavior/pro-control")

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
            if not serializer.is_valid():
                continue

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
            if not serializer.is_valid():
                continue

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

    def _get_acl_l7_rule_md5(self, data):

        print(data)

        filtered_data = [item for item in data if item['app_proto'] == '所有协议']

        # 对每个字典内的键进行字母序排序，而不是整个列表基于特定关键字排序
        # 此处仅对字典内部进行排序，不改变字典间的顺序
        sorted_data_by_key = sorted(
            filtered_data,
            key=lambda x: json.dumps(x, sort_keys=True, ensure_ascii=False))

        # 将排序后的数据转换为JSON字符串
        json_str_by_key = json.dumps(
            sorted_data_by_key, ensure_ascii=False,
            sort_keys=True)

        # 使用MD5生成key
        md5_key_by_key = hashlib.md5(json_str_by_key.encode('utf-8')).hexdigest()
        return md5_key_by_key

    def get_block_mac_by_acl_l7_md5_cache_key(self, mac):
        return f"{self.router_id}:mac_link_md5_acl_l7:{mac}:{CACHE_VERSION}"

    def set_mac_link_md5_acl_l7_md5_cache(self, mac, data):
        DEFAULT_CACHE.set(self.get_block_mac_by_acl_l7_md5_cache_key(mac), data)

    def get_block_mac_by_acl_l7_md5_cache(self, mac):
        return DEFAULT_CACHE.get(
            self.get_block_mac_by_acl_l7_md5_cache_key(mac), None)

    def link_mac_control_to_acl_l7(self):
        macs_linking_mac_ctl_to_acl_l7 = self.macs_block_mac_by_acl_l7
        device_rule_data = self.get_device_rule_data()
        # print(macs_linking_mac_ctl_to_acl_l7)

        for mac in macs_linking_mac_ctl_to_acl_l7:
            exist_md5 = self.get_block_mac_by_acl_l7_md5_cache(mac)

            acl_l7_list = device_rule_data[mac]["acl_l7"]

            if not acl_l7_list:
                # todo: remove all tasks in the device
                pass
                continue

            acl_l7_md5 = self._get_acl_l7_rule_md5(acl_l7_list)

            print(acl_l7_md5)

            print(filter_and_merge_strategies(acl_l7_list, 7))

            print(merge_similar_strategies(acl_l7_list, 7))

            if acl_l7_md5 == exist_md5:
                continue
