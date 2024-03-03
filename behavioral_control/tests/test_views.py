from copy import deepcopy
from unittest.mock import MagicMock, patch

from django.db.models.signals import post_save
from django.test import TestCase
from django.urls import reverse
from factories import RouterFactory
from tests.data_for_tests import (DEFAULT_IKUAI_CLIENT_LIST_MAC_GROUPS,
                                  DEFAULT_IKUAI_CLIENT_LIST_MONITOR_LANIP)
from tests.mixins import (DataManagerDefaultRetMixin, MockRouterClientMixin,
                          RequestTestMixin)

from my_router.models import Device, Router
from my_router.receivers import create_or_update_router_fetch_task
from my_router.views import fetch_new_info_save_and_set_cache


class MockRouterDataManagerViewMixin(
        MockRouterClientMixin, DataManagerDefaultRetMixin):
    def setUp(self):
        super().setUp()

        # post_save.disconnect(create_or_update_router_fetch_task, sender=Router)

        self.mock_get_client_patcher = patch('my_router.views.Router.get_client')
        self.mock_get_client = self.mock_get_client_patcher.start()
        self.mock_get_client.return_value = MagicMock()
        self.mock_client = self.mock_get_client.return_value
        self.router.get_client = MagicMock(return_value=self.mock_client)
        self.addCleanup(self.mock_get_client_patcher.stop)

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


class HomeViewTest(MockRouterClientMixin, RequestTestMixin, TestCase):
    @property
    def home_url(self):
        return reverse("home")

    def test_get_home_ok(self):
        resp = self.client.get(self.home_url)
        self.assertEqual(resp.status_code, 302)

    def test_get_home_ok_more_than_1_routers(self):
        post_save.disconnect(create_or_update_router_fetch_task, sender=Router)
        RouterFactory()
        resp = self.client.get(self.home_url)
        self.assertEqual(resp.status_code, 302)

    def test_login_required(self):
        self.client.logout()
        resp = self.client.get(self.home_url)
        self.assertEqual(resp.status_code, 302)


class FetchNewInfoSaveAndSetCacheTest(MockRouterDataManagerViewMixin, TestCase):
    # testing my_router.views.fetch_new_info_save_and_set_cache

    def setUp(self):
        super().setUp()
        mock_rd_manager = patch('my_router.views.RouterDataManager')

        self.mock_rd_manager_klass = mock_rd_manager.start()
        self.mock_rd_manager = self.mock_rd_manager_klass.return_value

        self.addCleanup(mock_rd_manager.stop)

    @patch('my_router.models.Router.objects.filter')
    def test_fetch_new_info_with_router_id(self, mock_filter):
        # Setup
        router_id = 1
        mock_router = MagicMock()
        mock_router.id = router_id
        mock_filter.return_value.count.return_value = 1
        mock_filter.return_value.__iter__.return_value = [mock_router]

        # Act
        fetch_new_info_save_and_set_cache(router_id=router_id)

        # Assert
        mock_filter.assert_called_once_with(id=router_id)
        self.mock_rd_manager_klass.assert_called_once_with(
            router_instance=mock_router)
        self.mock_rd_manager.cache_each_device_info.assert_called_once()
        self.mock_rd_manager.cache_all_data.assert_called_once()
        self.mock_rd_manager.update_all_mac_cache.assert_called_once()
        self.mock_rd_manager.update_mac_control_rule_from_acl_l7.assert_called_once()

    def test_fetch_new_info_with_real_router_instance(self):
        # 配置mock对象
        self.mock_rd_manager.cache_each_device_info.return_value = None
        self.mock_rd_manager.cache_all_data.return_value = None
        self.mock_rd_manager.update_all_mac_cache.return_value = None
        self.mock_rd_manager.update_mac_control_rule_from_acl_l7.return_value = None

        # 调用函数
        fetch_new_info_save_and_set_cache(router=self.router)

        # 验证RouterDataManager的方法是否被调用
        self.mock_rd_manager.cache_each_device_info.assert_called_once()
        self.mock_rd_manager.cache_all_data.assert_called_once()
        self.mock_rd_manager.update_all_mac_cache.assert_called_once()
        self.mock_rd_manager.update_mac_control_rule_from_acl_l7.assert_called_once()

    def test_fetch_new_info_with_no_router_instance(self):
        self.mock_rd_manager.cache_each_device_info.return_value = None
        self.mock_rd_manager.cache_all_data.return_value = None
        self.mock_rd_manager.update_all_mac_cache.return_value = None
        self.mock_rd_manager.update_mac_control_rule_from_acl_l7.return_value = None

        # 调用函数
        fetch_new_info_save_and_set_cache(router_id=100)

        # 验证RouterDataManager的方法是否被调用
        self.mock_rd_manager.cache_each_device_info.assert_not_called()
        self.mock_rd_manager.cache_all_data.assert_not_called()
        self.mock_rd_manager.update_all_mac_cache.assert_not_called()
        self.mock_rd_manager.update_mac_control_rule_from_acl_l7.assert_not_called()


class FetchCachedInfoTest(
        MockRouterDataManagerViewMixin, RequestTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        mock_rd_manager = patch('my_router.views.RouterDataManager')

        self.mock_rd_manager_klass = mock_rd_manager.start()
        self.mock_rd_manager = self.mock_rd_manager_klass.return_value

        self.addCleanup(mock_rd_manager.stop)

    def get_fetch_info_url(self, info_name, router_id=None):
        router_id = router_id or self.router.id
        return reverse("fetch-cached-info", args=(router_id, info_name))

    def test_get_request_with_mocked_manager(self):
        # 配置mock对象
        self.mock_rd_manager.init_data_from_cache.return_value = None
        self.mock_rd_manager.get_view_data.return_value = (
            {"mocked_data": "some_value"})

        response = self.client.get(self.get_fetch_info_url("device"))

        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(str(response.content, encoding='utf8'),
                             {"mocked_data": "some_value"})

    def test_exception_handling(self):
        self.mock_rd_manager_klass.side_effect = Exception("Test exception")
        response = self.client.get(self.get_fetch_info_url("device"))
        self.assertEqual(response.status_code, 400)
        self.assertJSONEqual(
            str(response.content, encoding='utf8'),
            {"error": "Exception: Test exception"})

    def test_not_authenticated(self):
        self.client.logout()
        resp = self.client.get(self.get_fetch_info_url("device"))
        self.assertEqual(resp.status_code, 302)

    def test_post_not_allowed(self):
        resp = self.client.post(self.get_fetch_info_url("device"), data={})
        self.assertEqual(resp.status_code, 403)


class ViewTestMixin(MockRouterDataManagerViewMixin):
    def setUp(self):
        super().setUp()
        fetch_new_info_save_and_set_cache(router=self.router)
        self.first_device = Device.objects.first()

        mac_groups = []
        for d in DEFAULT_IKUAI_CLIENT_LIST_MAC_GROUPS["data"]:
            if self.first_device.mac in d["addr_pool"].split(","):
                mac_groups.append(d["group_name"])
        self.init_mac_groups = mac_groups


class DeviceUpdateViewTest(ViewTestMixin, RequestTestMixin, TestCase):
    def get_update_device_url(self, pk=None):
        pk = pk or self.first_device.pk
        return reverse("device-edit", args=(self.router.id, pk))

    def get_device_post_data(self, pk=None):
        if pk:
            device = Device.objects.get(pk=pk)
        else:
            device = self.first_device

        from django.forms.models import model_to_dict
        return model_to_dict(device)

    def test_get_ok(self):
        resp = self.client.get(self.get_update_device_url())
        self.assertEqual(resp.status_code, 200)

    def test_get_not_authenticated(self):
        self.client.logout()
        resp = self.client.get(self.get_update_device_url())
        self.assertEqual(resp.status_code, 302)

    def test_post_not_changed(self):
        url = self.get_update_device_url()

        post_data = self.get_device_post_data()
        post_data["mac_group"] = self.init_mac_groups

        resp = self.client.post(url, data=post_data)
        self.assertEqual(resp.status_code, 302)

    def test_post_mac_group_changed(self):
        url = self.get_update_device_url()

        # mac_group is empty
        post_data = self.get_device_post_data()

        resp = self.client.post(url, data=post_data)
        self.assertEqual(resp.status_code, 302)

    def test_post_name_not_changed(self):
        url = self.get_update_device_url()

        post_data = self.get_device_post_data()
        post_data["mac_group"] = self.init_mac_groups

        post_data["name"] = "foo"

        resp = self.client.post(url, data=post_data)
        self.assertEqual(resp.status_code, 302)

        self.assertEqual(Device.objects.first().name, "foo")
        # todo: assert mac comment changed

    def test_post_reject(self):
        url = self.get_update_device_url()

        post_data = self.get_device_post_data()
        post_data["mac_group"] = self.init_mac_groups

        post_data_copy = deepcopy(post_data)
        post_data_copy["reject"] = True

        resp = self.client.post(url, data=post_data_copy)
        self.assertEqual(resp.status_code, 302)
        # todo: assert acl_mac changed, and make change
        #  in the returned value of list_monitor_lanip

        # Change reject to 1
        list_lanip = deepcopy(DEFAULT_IKUAI_CLIENT_LIST_MONITOR_LANIP)
        list_lanip["data"][1]['reject'] = 1

        self.mock_client.list_monitor_lanip.return_value = list_lanip
        fetch_new_info_save_and_set_cache(router=self.router)

        resp = self.client.post(url, data=post_data)
        post_data_copy["reject"] = False
        self.assertEqual(resp.status_code, 302)

        # todo: assert acl_mac changed


class DomainBlacklistEditView(
        ViewTestMixin, RequestTestMixin, TestCase):

    def get_update_domain_blacklist_url(self, domain_blacklist_id=None):
        domain_blacklist_id = domain_blacklist_id or 1
        return reverse("domain_blacklist-edit",
                       args=(self.router.id, domain_blacklist_id))

    def test_get_ok(self):
        resp = self.client.get(self.get_update_domain_blacklist_url())
        self.assertEqual(resp.status_code, 200)

    def test_get_add_ok(self):
        resp = self.client.get(self.get_update_domain_blacklist_url(-1))
        self.assertEqual(resp.status_code, 200)

    def test_get_not_authenticated(self):
        self.client.logout()
        resp = self.client.get(self.get_update_domain_blacklist_url())
        self.assertEqual(resp.status_code, 302)


class AclL7EditView(
        ViewTestMixin, RequestTestMixin, TestCase):

    def get_update_acl_l7_url(self, acl_l7_id=None):
        acl_l7_id = acl_l7_id or 2
        return reverse("acl_l7-edit",
                       args=(self.router.id, acl_l7_id))

    def test_get_ok(self):
        resp = self.client.get(self.get_update_acl_l7_url())
        self.assertEqual(resp.status_code, 200)

    def test_get_add_ok(self):
        resp = self.client.get(self.get_update_acl_l7_url(-1))
        self.assertEqual(resp.status_code, 200)

    def test_get_not_authenticated(self):
        self.client.logout()
        resp = self.client.get(self.get_update_acl_l7_url())
        self.assertEqual(resp.status_code, 302)


class MacGroupEditView(
        ViewTestMixin, RequestTestMixin, TestCase):

    def get_update_mac_group_url(self, mac_group=None):
        mac_group = mac_group or 1
        return reverse("mac_group-edit",
                       args=(self.router.id, mac_group))

    def test_get_ok(self):
        resp = self.client.get(self.get_update_mac_group_url())
        self.assertEqual(resp.status_code, 200)

    def test_get_add_ok(self):
        resp = self.client.get(self.get_update_mac_group_url(-1))
        self.assertEqual(resp.status_code, 200)

    def test_get_not_authenticated(self):
        self.client.logout()
        resp = self.client.get(self.get_update_mac_group_url())
        self.assertEqual(resp.status_code, 302)
