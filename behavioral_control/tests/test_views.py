from unittest.mock import MagicMock, patch

from django.db.models.signals import post_save
from django.test import TestCase
from django.urls import reverse
from factories import RouterFactory
from tests.mixins import MockRouterClientMixin, RequestTestMixin

from my_router.models import Router
from my_router.receivers import create_or_update_router_fetch_task
from my_router.views import fetch_new_info_save_and_set_cache


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


class FetchNewInfoSaveAndSetCacheTest(MockRouterClientMixin, TestCase):
    # testing my_router.views.fetch_new_info_save_and_set_cache

    @patch('my_router.views.RouterDataManager')
    @patch('my_router.models.Router.objects.filter')
    def test_fetch_new_info_with_router_id(self, mock_filter, mock_rd_manager_class):
        # Setup
        router_id = 1
        mock_router = MagicMock()
        mock_router.id = router_id
        mock_filter.return_value.count.return_value = 1
        mock_filter.return_value.__iter__.return_value = [mock_router]
        mock_rd_manager_instance = mock_rd_manager_class.return_value

        # Act
        fetch_new_info_save_and_set_cache(router_id=router_id)

        # Assert
        mock_filter.assert_called_once_with(id=router_id)
        mock_rd_manager_class.assert_called_once_with(router_instance=mock_router)
        mock_rd_manager_instance.cache_each_device_info.assert_called_once()
        mock_rd_manager_instance.cache_all_data.assert_called_once()
        mock_rd_manager_instance.update_all_mac_cache.assert_called_once()
        mock_rd_manager_instance.update_mac_control_rule_from_acl_l7.assert_called_once()  # noqa

    @patch('my_router.views.RouterDataManager')
    def test_fetch_new_info_with_real_router_instance(self, MockRouterDataManager):
        # 配置mock对象
        mock_rd_manager = MockRouterDataManager.return_value
        mock_rd_manager.cache_each_device_info.return_value = None
        mock_rd_manager.cache_all_data.return_value = None
        mock_rd_manager.update_all_mac_cache.return_value = None
        mock_rd_manager.update_mac_control_rule_from_acl_l7.return_value = None

        # 调用函数
        fetch_new_info_save_and_set_cache(router=self.router)

        # 验证RouterDataManager的方法是否被调用
        mock_rd_manager.cache_each_device_info.assert_called_once()
        mock_rd_manager.cache_all_data.assert_called_once()
        mock_rd_manager.update_all_mac_cache.assert_called_once()
        mock_rd_manager.update_mac_control_rule_from_acl_l7.assert_called_once()

    @patch('my_router.views.RouterDataManager')
    def test_fetch_new_info_with_no_router_instance(self, MockRouterDataManager):
        mock_rd_manager = MockRouterDataManager.return_value
        mock_rd_manager.cache_each_device_info.return_value = None
        mock_rd_manager.cache_all_data.return_value = None
        mock_rd_manager.update_all_mac_cache.return_value = None
        mock_rd_manager.update_mac_control_rule_from_acl_l7.return_value = None

        # 调用函数
        fetch_new_info_save_and_set_cache(router_id=100)

        # 验证RouterDataManager的方法是否被调用
        mock_rd_manager.cache_each_device_info.assert_not_called()
        mock_rd_manager.cache_all_data.assert_not_called()
        mock_rd_manager.update_all_mac_cache.assert_not_called()
        mock_rd_manager.update_mac_control_rule_from_acl_l7.assert_not_called()


@patch('my_router.views.RouterDataManager')
class FetchCachedInfoTest(MockRouterClientMixin, RequestTestMixin, TestCase):
    def get_fetch_info_url(self, info_name, router_id=None):
        router_id = router_id or self.router.id
        return reverse("fetch-cached-info", args=(router_id, info_name))

    def test_get_request_with_mocked_manager(self, mock_rd_manager):
        # 配置mock对象
        mock_instance = mock_rd_manager.return_value
        mock_instance.init_data_from_cache.return_value = None
        mock_instance.get_view_data.return_value = {"mocked_data": "some_value"}

        response = self.client.get(self.get_fetch_info_url("device"))

        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(str(response.content, encoding='utf8'),
                             {"mocked_data": "some_value"})

    def test_exception_handling(self, mock_rd_manager):
        mock_rd_manager.side_effect = Exception("Test exception")
        response = self.client.get(self.get_fetch_info_url("device"))
        self.assertEqual(response.status_code, 400)
        self.assertJSONEqual(
            str(response.content, encoding='utf8'),
            {"error": "Exception: Test exception"})

    def test_not_authenticated(self, mock_rd_manager):
        self.client.logout()
        resp = self.client.get(self.get_fetch_info_url("device"))
        self.assertEqual(resp.status_code, 302)

    def test_post_not_allowed(self, mock_rd_manager):
        resp = self.client.post(self.get_fetch_info_url("device"), data={})
        self.assertEqual(resp.status_code, 403)
