from unittest.mock import MagicMock, patch

from django.db.models.signals import post_save
from django.test import TestCase
from tests.factories import RouterFactory
from tests.mixins import CacheMixin, MockRouterClientMixin

from my_router.data_manager import RouterDataManager, RuleDataFilter
from my_router.models import Device, Router
from my_router.receivers import create_or_update_router_fetch_task

MAC1 = "44:a8:bc:43:97:2d"
MAC2 = "00:04:4a:86:32:9b"
MAC_GROUP_1 = "IPAD"
MAC_GROUP_2 = "ALL"


class DataManagerTestBase(CacheMixin, MockRouterClientMixin):
    @property
    def default_ikuai_client_list_monitor_lanip(self):
        return {
            'total': 2,
            'data': [{'uptime': '2024-02-25 13:32:36',
                      'mac': f'{MAC1}',
                      'dtalk_name': '',
                      'uprate': '',
                      'link_addr': '',
                      'bssid': '',
                      'comment': 'iPad',
                      'downrate': '',
                      'reject': 0,
                      'hostname': 'iPad',
                      'apmac': '',
                      'frequencies': '',
                      'ssid': '',
                      'apname': '',
                      'ip_addr_int': 3232263691,
                      'connect_num': 1,
                      'upload': 0,
                      'download': 0,
                      'auth_type': 0,
                      'client_type': 'Unknown',
                      'client_device': 'Unknown',
                      'timestamp': 1708839156,
                      'id': 1,
                      'ac_gid': 0,
                      'webid': 0,
                      'ppptype': '',
                      'ip_addr': '192.168.110.11',
                      'username': '',
                      'total_up': 2387003,
                      'total_down': 1913202,
                      'signal': ''},
                     {'uptime': '2024-02-25 13:32:55',
                      'mac': MAC2,
                      'dtalk_name': '',
                      'uprate': '',
                      'link_addr': '',
                      'bssid': '',
                      'comment': 'TVBOX',
                      'downrate': '',
                      'reject': 0,
                      'hostname': 'TVBOX',
                      'apmac': '',
                      'frequencies': '',
                      'ssid': '',
                      'apname': '',
                      'ip_addr_int': 3232263684,
                      'connect_num': 1,
                      'upload': 0,
                      'download': 0,
                      'auth_type': 0,
                      'client_type': 'Unknown',
                      'client_device': 'Xiaomi',
                      'timestamp': 1708839175,
                      'id': 2,
                      'ac_gid': 0,
                      'webid': 0,
                      'ppptype': '',
                      'ip_addr': '192.168.110.4',
                      'username': '',
                      'total_up': 2022282,
                      'total_down': 2002042,
                      'signal': ''}]}

    @property
    def default_ikuai_client_list_mac_groups(self):
        return {'total': 2,
                'data': [{'group_name': f'{MAC_GROUP_1}',
                          'addr_pool': f'{MAC1}',
                          'id': 1,
                          'comment': ''},
                         {'group_name': MAC_GROUP_2,
                          'addr_pool': f'{MAC2},{MAC1}',
                          'id': 8,
                          'comment': ''}]}

    @property
    def default_ikuai_client_list_acl_l7(self):
        return {'total': 9,
                'data': [{'prio': 28,
                          'action': 'drop',
                          'app_proto': '所有协议',
                          'src_addr': MAC_GROUP_1,
                          'dst_addr': '',
                          'week': '1234567',
                          'time': '00:00-23:59',
                          'id': 2,
                          'enabled': 'yes',
                          'comment': '阻断全部上网'},
                         {'prio': 10,
                          'action': 'accept',
                          'app_proto': '所有协议',
                          'src_addr': MAC_GROUP_1,
                          'dst_addr': '',
                          'week': '6',
                          'time': '21:36-22:04',
                          'id': 4,
                          'enabled': 'no',
                          'comment': 'ipad临时'},
                         {'prio': 8,
                          'action': 'drop',
                          'app_proto': '网络游戏',
                          'src_addr': MAC_GROUP_1,
                          'dst_addr': '',
                          'week': '1234567',
                          'time': '00:00-23:59',
                          'id': 5,
                          'enabled': 'yes',
                          'comment': '阻止游戏'},
                         {'prio': 8,
                          'action': 'drop',
                          'app_proto': '网络视频',
                          'src_addr': MAC_GROUP_1,
                          'dst_addr': '',
                          'week': '1234567',
                          'time': '00:00-23:59',
                          'id': 6,
                          'enabled': 'yes',
                          'comment': '阻止视频'},
                         {'prio': 16,
                          'action': 'drop',
                          'app_proto': '国内视频',
                          'src_addr': MAC_GROUP_2,
                          'dst_addr': '',
                          'week': '1234567',
                          'time': '00:00-23:30',
                          'id': 7,
                          'enabled': 'yes',
                          'comment': '阻止电视'},
                         {'prio': 32,
                          'action': 'drop',
                          'app_proto': '淘宝视频,淘宝通用账号,淘宝',
                          'src_addr': MAC_GROUP_2,
                          'dst_addr': '',
                          'week': '1234567',
                          'time': '00:00-23:59',
                          'id': 8,
                          'enabled': 'yes',
                          'comment': '禁止淘宝'},
                         {'prio': 1,
                          'action': 'accept',
                          'app_proto': '所有协议',
                          'src_addr': MAC_GROUP_2,
                          'dst_addr': '',
                          'week': '3',
                          'time': '22:10-22:25',
                          'id': 9,
                          'enabled': 'yes',
                          'comment': '允许电视'},
                         {'prio': 15,
                          'action': 'drop',
                          'app_proto': '所有协议',
                          'src_addr': MAC_GROUP_2,
                          'dst_addr': '',
                          'week': '1234567',
                          'time': '00:00-23:59',
                          'id': 10,
                          'enabled': 'yes',
                          'comment': '禁止电视'},
                         {'prio': 2,
                          'action': 'accept',
                          'app_proto': '所有协议',
                          'src_addr': MAC_GROUP_2,
                          'dst_addr': '',
                          'week': '1234567',
                          'time': '00:00-05:00',
                          'id': 11,
                          'enabled': 'yes',
                          'comment': '允许电视'}]}

    @property
    def default_ikuai_client_list_domain_blacklist(self):
        return {'total': 2,
                'data': [{'time': '00:00-23:59',
                          'id': 1,
                          'enabled': 'yes',
                          'comment': '',
                          'domain_group': '游戏网站',
                          'weekdays': '12345',
                          'ipaddr': MAC_GROUP_1},
                         {'time': '00:00-23:59',
                          'id': 2,
                          'enabled': 'no',
                          'comment': '',
                          'domain_group': '视频网站',
                          'weekdays': '67',
                          'ipaddr': MAC_GROUP_1}
                         ]}

    @property
    def default_ikuai_client_list_url_black(self):
        return {'total': 2,
                'data': [{'ip_addr': MAC_GROUP_1,
                          'id': 1,
                          'enabled': 'no',
                          'week': '1234567',
                          'comment': 'foo',
                          'time': '00:00-23:59',
                          'domain': 'foo.bar.com,bar.foo.com',
                          'mode': 0},
                         {'ip_addr': MAC_GROUP_1,
                          'id': 2,
                          'enabled': 'yes',
                          'week': '1234567',
                          'comment': 'bar',
                          'time': '00:00-23:59',
                          'domain': 'bar.com.foo,foo.com.bar',
                          'mode': 0}
                         ]}

    def setUp(self):
        super().setUp()

        post_save.disconnect(create_or_update_router_fetch_task, sender=Router)

        router_instance = RouterFactory()
        self.mock_client = MagicMock()

        router_instance.get_client = MagicMock(return_value=self.mock_client)

        self.rd_manager = RouterDataManager(router_instance=router_instance)

        self.mock_client.list_monitor_lanip.return_value = (
            self.default_ikuai_client_list_monitor_lanip)

        self.mock_client.list_mac_groups.return_value = (
            self.default_ikuai_client_list_mac_groups)

        self.mock_client.list_acl_l7.return_value = (
            self.default_ikuai_client_list_acl_l7)

        self.mock_client.list_domain_blacklist.return_value = (
            self.default_ikuai_client_list_domain_blacklist)

        self.mock_client.list_url_black.return_value = (
            self.default_ikuai_client_list_url_black)

    def tearDown(self):
        # 重新连接信号
        post_save.connect(create_or_update_router_fetch_task, sender=Router)


class DataManagerPropertiesTest(DataManagerTestBase, TestCase):

    def test_device_and_dict(self):
        self.assertIsNone(self.rd_manager._devices)
        self.assertIsNotNone(self.rd_manager.devices)
        self.assertIsNotNone(self.rd_manager._devices)
        self.assertIsNotNone(self.rd_manager.devices)

        self.assertIsNone(self.rd_manager._device_dict)
        self.assertIsNotNone(self.rd_manager.device_dict)
        self.assertIsNotNone(self.rd_manager._device_dict)
        self.assertIsNotNone(self.rd_manager.device_dict)

        self.assertIsNotNone(self.rd_manager.online_mac_list)

    def test_mac_group_list(self):
        self.assertIsNone(self.rd_manager._mac_groups_list)
        self.assertIsNotNone(self.rd_manager.mac_groups_list)
        self.assertIsNotNone(self.rd_manager._mac_groups_list)

        self.assertIsNone(self.rd_manager._mac_groups_map)
        self.assertIsNotNone(self.rd_manager.mac_groups)
        self.assertIsNotNone(self.rd_manager.mac_groups)
        self.assertIsNotNone(self.rd_manager._mac_groups_map)

        self.assertIsNone(self.rd_manager._mac_groups_map_reverse)
        self.assertIsNotNone(self.rd_manager.mac_groups_reverse)
        self.assertIsNotNone(self.rd_manager.mac_groups_reverse)
        self.assertIsNotNone(self.rd_manager._mac_groups_map_reverse)

    def test_acl_l7_list(self):
        self.assertIsNone(self.rd_manager._acl_l7_list)
        self.assertIsNotNone(self.rd_manager.acl_l7_list)
        self.assertIsNotNone(self.rd_manager.acl_l7_list)
        self.assertIsNotNone(self.rd_manager._acl_l7_list)

    def test_domain_blacklist(self):
        self.assertIsNone(self.rd_manager._domain_black_list)
        self.assertIsNotNone(self.rd_manager.domain_blacklist)
        self.assertIsNotNone(self.rd_manager._domain_black_list)
        self.assertIsNotNone(self.rd_manager.domain_blacklist)

    def test_url_black_list(self):
        self.assertIsNone(self.rd_manager._url_black_list)
        self.assertIsNotNone(self.rd_manager.url_black_list)
        self.assertIsNotNone(self.rd_manager._url_black_list)
        self.assertIsNotNone(self.rd_manager.url_black_list)

    def test_macs_block_mac_by_acl_l7(self):
        self.assertIsNone(self.rd_manager._macs_block_mac_by_acl_l7)
        self.assertIsNotNone(self.rd_manager.macs_block_mac_by_acl_l7)
        self.assertIsNotNone(self.rd_manager._macs_block_mac_by_acl_l7)
        self.assertIsNotNone(self.rd_manager.macs_block_mac_by_acl_l7)


class DataManagerCacheTest(DataManagerTestBase, TestCase):
    def test_update_all_mac_cache(self):
        self.rd_manager.update_all_mac_cache()

    def test_cache_each_device_info(self):
        self.rd_manager.cache_each_device_info()

    def test_get_device_rule_data(self):
        self.rd_manager.update_all_mac_cache()
        ret = self.rd_manager.get_device_rule_data()

        for mac in [MAC1, MAC2]:
            self.assertIn(mac, ret.keys())

    def cache_instance_properties(self):
        # this will also cache the data in django cache
        self.assertIsNotNone(self.rd_manager.devices)
        self.assertIsNotNone(self.rd_manager.device_dict)
        self.assertIsNotNone(self.rd_manager.online_mac_list)
        self.assertIsNotNone(self.rd_manager.mac_groups_list)
        self.assertIsNotNone(self.rd_manager.mac_groups)
        self.assertIsNotNone(self.rd_manager.mac_groups_reverse)
        self.assertIsNotNone(self.rd_manager.domain_blacklist)
        self.assertIsNotNone(self.rd_manager.url_black_list)
        self.assertIsNotNone(self.rd_manager.macs_block_mac_by_acl_l7)

    def test_reset_property_cache(self):
        self.cache_instance_properties()

        self.rd_manager.reset_property_cache()

        self.assertIsNone(self.rd_manager._devices)
        self.assertIsNone(self.rd_manager._device_dict)
        self.assertIsNone(self.rd_manager._online_mac_list)
        self.assertIsNone(self.rd_manager._mac_groups_list)
        self.assertIsNone(self.rd_manager._mac_groups_map)
        self.assertIsNone(self.rd_manager._mac_groups_map_reverse)
        self.assertIsNone(self.rd_manager._domain_black_list)
        self.assertIsNone(self.rd_manager._url_black_list)
        self.assertIsNone(self.rd_manager._macs_block_mac_by_acl_l7)

    def test_init_data_from_cache(self):
        self.cache_instance_properties()
        self.rd_manager.reset_property_cache()

        self.rd_manager.init_data_from_cache()
        self.assertTrue(self.rd_manager.is_initialized_from_cached_data)


class DataManagerTest(DataManagerTestBase, TestCase):
    def test_get_device_view_data(self):
        ret = self.rd_manager.get_device_view_data()
        self.assertEqual(len(ret), 2)

        for key in ["domain_blacklist", "acl_l7", "url_black", "ignored"]:
            self.assertIn(key, ret[0].keys())

    def test_get_domain_blacklist_list_for_view(self):
        ret = self.rd_manager.get_domain_blacklist_list_for_view()
        self.assertEqual(len(ret), 2)

    def test_get_url_black_view_data(self):
        ret = self.rd_manager.get_mac_group_list_for_view()
        self.assertEqual(len(ret), 2)

    def test_get_mac_group_list_for_view(self):
        ret = self.rd_manager.get_url_black_view_data()
        self.assertEqual(len(ret), 2)

    def test_get_view_data(self):
        for info_name in [
                "device", "domain_blacklist", "url_black", "acl_l7", "mac_group"]:
            self.rd_manager.get_view_data(info_name)

    def test_get_ikuai_urls(self):
        for url in [self.rd_manager.router_domain_blacklist_url,
                    self.rd_manager.router_protocol_control_url,
                    self.rd_manager.router_mac_group_url]:
            self.assertIsNotNone(url)


class MacControlRuleFromAclL7Test(DataManagerTestBase, TestCase):

    def setUp(self):
        super().setUp()
        self.mock_client.del_acl_mac.return_value = {}
        self.mock_client.add_acl_mac.return_value = {}
        self.rd_manager.update_device_db_instances()
        device = Device.objects.get(mac=MAC2)
        device.block_mac_by_proto_ctrl = True
        device.save()

        self.mock_add_rule_patcher = patch(
            "my_router.data_manager.RouterDataManager.add_acl_mac_rule")
        self.mock_add_mac_rule = self.mock_add_rule_patcher.start()
        self.addCleanup(self.mock_add_rule_patcher.stop)

        self.mock_remove_rule_patcher = patch(
            "my_router.data_manager.RouterDataManager.remove_active_acl_mac_rule_of_device")  # noqa
        self.mock_remove_mac_rule = self.mock_remove_rule_patcher.start()
        self.addCleanup(self.mock_remove_rule_patcher.stop)

    @property
    def default_list_acl_mac_data(self):
        return {'total': 1,
                'data': [{'enabled': 'yes',
                          'comment:1': '',
                          'time': '05:00-23:59',
                          'week': '124567',
                          'comment': 'TVBOX',
                          'mac': MAC2,
                          'id': 1}]}

    def fake_set_mac_acl(self, data=None, empty=False):
        if empty:
            self.mock_client.list_acl_mac.return_value = {'total': 0, 'data': []}
            return

        self.mock_client.list_acl_mac.return_value = (
                data or self.default_list_acl_mac_data)

    def test_get_active_acl_mac_rule_of_device(self):
        self.fake_set_mac_acl()
        self.assertIsNotNone(
            self.rd_manager.get_active_acl_mac_rule_of_device(MAC2))
        self.assertIsNone(
            self.rd_manager.get_active_acl_mac_rule_of_device(MAC1))

    def test_add_acl_mac_rule(self):
        self.rd_manager.add_acl_mac_rule({})

    def test_update_mac_control_rule_from_acl_l7(self):
        self.rd_manager.update_mac_control_rule_from_acl_l7()

    def test_update_mac_control_rule_from_acl_l7_active_mac_rule_empty(self):
        self.fake_set_mac_acl(empty=True)

        self.rd_manager.update_mac_control_rule_from_acl_l7_by_time(
             self.get_local_time("2024-3-1 1:00"))
        self.mock_add_mac_rule.assert_called_once_with(
            {'mac': MAC2, 'week': '124567', 'time': '05:00-23:59'})
        self.mock_remove_mac_rule.assert_not_called()

    def test_update_mac_control_rule_from_acl_l7_23_59_not_called(self):
        self.fake_set_mac_acl()

        for time_str in ["23:59:00", "23:59:01", "23:59:59", "00:00:00"]:
            now_time = self.get_local_time(time_str)
            self.rd_manager.update_mac_control_rule_from_acl_l7_by_time(now_time)

        self.mock_add_mac_rule.assert_not_called()
        self.mock_remove_mac_rule.assert_not_called()

    def test_update_mac_control_rule_from_acl_l7_with_empty_acl_l7(self):
        self.mock_client.list_acl_l7.return_value = {'total': 0, 'data': []}

        self.rd_manager.update_mac_control_rule_from_acl_l7_by_time()
        self.mock_add_mac_rule.assert_not_called()
        self.mock_remove_mac_rule.assert_called_once()

    def test_update_with_no_current_and_next_time_range(self):
        self.mock_client.list_acl_l7.return_value = {
            'total': 1,
            'data': [{'prio': 28,
                      'action': 'accept',
                      'app_proto': '所有协议',
                      'src_addr': MAC_GROUP_2,
                      'dst_addr': '',
                      'week': '1234567',
                      'time': '00:00-23:59',
                      'id': 2,
                      'enabled': 'yes',
                      'comment': '阻断全部上网'}]}

        self.rd_manager.update_mac_control_rule_from_acl_l7_by_time()
        self.mock_add_mac_rule.assert_not_called()
        self.mock_remove_mac_rule.assert_called_once()

    def test_add_current_rule(self):
        self.fake_set_mac_acl(empty=True)

        # weekday 3 22:10-22:25 is accept, not drop
        now_time = self.get_local_time("2024-2-7 22:35")
        self.rd_manager.update_mac_control_rule_from_acl_l7_by_time(now_time)
        self.mock_add_mac_rule.assert_called_once()
        self.mock_add_mac_rule.assert_called_with(
            {'mac': MAC2, 'week': '3', 'time': '22:25-23:59'})
        self.mock_remove_mac_rule.assert_not_called()

    def test_update_current_none_next_equal_active_mac_rule(self):
        self.fake_set_mac_acl(
            {"total": 1,
             "data": [{
                 'mac': MAC2,
                 'week': '124567',
                 'comment': 'TVBOX',
                 'time': '05:00-23:59',
                 'enabled': 'yes',
                 'id': 2}]})

        self.rd_manager.update_mac_control_rule_from_acl_l7_by_time(
             self.get_local_time("2024-3-1 1:00"))
        self.mock_add_mac_rule.assert_not_called()
        self.mock_remove_mac_rule.assert_not_called()

    def test_update_current_none_next_not_equal_active_mac_rule(self):
        self.fake_set_mac_acl(
            {"total": 1,
             "data": [{
                 'mac': MAC2,
                 'week': '7',
                 'comment': 'TVBOX',
                 'time': '05:00-23:59',
                 'enabled': 'yes',
                 'id': 2}]})

        self.rd_manager.update_mac_control_rule_from_acl_l7_by_time(
             self.get_local_time("2024-3-1 1:00"))
        self.mock_add_mac_rule.assert_called_once_with(
            {'mac': MAC2, 'week': '124567', 'time': '05:00-23:59'})
        self.mock_remove_mac_rule.assert_not_called()

    def test_update_current_equal_next_no_update_active_mac_rule(self):
        self.fake_set_mac_acl()

        self.rd_manager.update_mac_control_rule_from_acl_l7_by_time(
             self.get_local_time("2024-3-1 6:00"))
        self.mock_add_mac_rule.assert_not_called()
        self.mock_remove_mac_rule.assert_not_called()

    def test_update_current_not_equal_active_mac_rule(self):
        self.fake_set_mac_acl(
            {"total": 1,
             "data": [{
                 'mac': MAC2,
                 'week': '124567',
                 'comment': 'TVBOX',
                 'time': '05:00-23:59',
                 'enabled': 'yes',
                 'id': 2}]})

        self.rd_manager.update_mac_control_rule_from_acl_l7_by_time(
             self.get_local_time("2024-2-28 6:00"))
        self.mock_add_mac_rule.assert_called_once_with(
            {'mac': MAC2, 'week': '3', 'time': '05:00-22:10'})
        self.mock_remove_mac_rule.assert_not_called()

    def test_acl_mac_rule(self):
        self.mock_add_rule_patcher.stop()
        self.mock_client.add_acl_mac.return_value = MagicMock()
        self.rd_manager.add_acl_mac_rule({})
        self.mock_client.add_acl_mac.assert_called_once()

    def test_remove_active_acl_mac_rule_of_device(self):
        self.mock_remove_rule_patcher.stop()
        self.fake_set_mac_acl()

        for mac in [MAC1, MAC2]:
            self.rd_manager.remove_active_acl_mac_rule_of_device(mac)

        self.mock_client.del_acl_mac.assert_called_once()


class RuleDataFilterTest(TestCase):
    def test_day_with_no_time_rule(self):
        rule_data = [{'priority': 15,
                      'action': 'accept',
                      'app_proto': '所有协议',
                      'weekdays': '12345',
                      'time': '10:00-11:59',
                      'id': 2,
                      'enabled': False,
                      'name': '允许上网'},
                     {'priority': 20,
                      'action': 'drop',
                      'app_proto': '所有协议',
                      'weekdays': '12345',
                      'time': '00:00-23:59',
                      'enabled': True,
                      'name': '阻断全部上网'}
                     ]

        rdf = RuleDataFilter(rule_data)
        days_str_with_strategies = "".join(
            [d["day"] for d in rdf.dominant_strategies])
        self.assertTrue('6' not in days_str_with_strategies)
        self.assertTrue('7' not in days_str_with_strategies)
