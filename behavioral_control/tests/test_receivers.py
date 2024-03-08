from unittest.mock import patch

from django.test import TestCase
from tests.data_for_tests import MAC2
from tests.mixins import CacheMixin, ViewTestMixin

from my_router.constants import DEFAULT_CACHE
from my_router.models import Device
from my_router.utils import (get_device_db_cache_key,
                             get_router_device_cache_key)


class RouterModelTest(CacheMixin, ViewTestMixin, TestCase):
    def test_delete_device_cache_removed(self):
        db_cache_key = get_device_db_cache_key(self.first_device.mac)
        device_cache_key = get_router_device_cache_key(
            self.router.id, self.first_device.mac)

        self.assertIsNotNone(self.test_cache.get(db_cache_key))
        self.assertIsNotNone(self.test_cache.get(device_cache_key))

        with patch("my_router.receivers.fetch_new_info_save_and_set_cache"
                   ) as mock_fetch_and_set_cache:
            Device.objects.first().delete()
            self.assertIsNone(DEFAULT_CACHE.get(db_cache_key))
            self.assertIsNone(DEFAULT_CACHE.get(device_cache_key))
            mock_fetch_and_set_cache.assert_called_once()

    def test_update_device_with_block_mac_by_proto_ctrl_to_False(self):
        self.first_device.block_mac_by_proto_ctrl = True
        self.first_device.save()

        acl_mac_id = 2
        self.mock_client.list_acl_mac.return_value = {
            "total": 1,
            "data": [{
                'mac': MAC2,
                'week': '124567',
                'comment': 'TVBOX',
                'time': '05:00-23:59',
                'enabled': 'yes',
                'id': acl_mac_id}]}

        self.first_device.block_mac_by_proto_ctrl = False
        self.first_device.save()

        self.mock_client.del_acl_mac.assert_called_with(acl_mac_id=acl_mac_id)
