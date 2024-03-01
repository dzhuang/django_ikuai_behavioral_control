from datetime import datetime
from unittest import mock
from unittest.mock import MagicMock

from django.db.models.signals import post_save
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone
from tests.data_for_tests import (DEFAULT_IKUAI_CLIENT_LIST_ACL_L7,
                                  DEFAULT_IKUAI_CLIENT_LIST_DOMAIN_BLACKLIST,
                                  DEFAULT_IKUAI_CLIENT_LIST_MAC_GROUPS,
                                  DEFAULT_IKUAI_CLIENT_LIST_MONITOR_LANIP,
                                  DEFAULT_IKUAI_CLIENT_LIST_URL_BLACK)
from tests.factories import RouterFactory, UserFactory

from my_router.data_manager import RouterDataManager
from my_router.models import Router
from my_router.receivers import create_or_update_router_fetch_task


class CacheMixin:
    def setUp(self):  # noqa
        super().setUp()
        import django.core.cache as cache
        self.test_cache = cache.caches["default"]
        self.addCleanup(self.test_cache.clear)


class RequestTestMixin(CacheMixin):
    @classmethod
    def setUpTestData(cls):  # noqa
        # Create superuser
        cls.client = Client()
        super().setUpTestData()

    def setUp(self):
        super().setUp()
        self.user = UserFactory()
        self.client.force_login(self.user)

    @property
    def login_url(self):
        return reverse("login")

    def assertFormErrorLoose(self, response, errors, form_name="form"):  # noqa
        """Assert that errors is found in response.context['form'] errors"""
        import itertools
        if errors is None:
            errors = []
        if not isinstance(errors, (list, tuple)):
            errors = [errors]
        try:
            form_errors = ". ".join(list(
                itertools.chain(*response.context[form_name].errors.values())))
        except TypeError:
            form_errors = None

        if form_errors is None or not form_errors:
            if errors:
                self.fail("%s has no error" % form_name)
            else:
                return

        if form_errors:
            if not errors:
                self.fail("%s unexpectedly has following errors: %s"
                          % (form_name, repr(form_errors)))

        for err in errors:
            self.assertIn(err, form_errors)

    def get_response_context_value_by_name(self, response, context_name):
        try:
            value = response.context[context_name]
        except KeyError:
            self.fail("%s does not exist in given response" % context_name)
        else:
            return value

    def assertResponseContextEqual(self, resp, context_name, expected_value):  # noqa
        value = self.get_response_context_value_by_name(resp, context_name)
        try:
            self.assertTrue(float(value) - float(expected_value) <= 1e-04)
            return
        except Exception:
            self.assertEqual(value, expected_value)


class MockAddMessageMixing(object):
    """
    The mixing for testing django.contrib.messages.add_message
    """

    def setUp(self):
        super(MockAddMessageMixing, self).setUp()
        self._fake_add_message_path = "django.contrib.messages.add_message"
        fake_add_message = mock.patch(self._fake_add_message_path)

        self._mock_add_message = fake_add_message.start()
        self.addCleanup(fake_add_message.stop)

    def _get_added_messages(self, join=True):
        try:
            msgs = [
                "'%s'" % str(arg[2])
                for arg, _ in self._mock_add_message.call_args_list]
        except IndexError:
            self.fail("%s is unexpectedly not called." % self._fake_add_message_path)
        else:
            if join:
                return "; ".join(msgs)
            return msgs

    def assertAddMessageCallCount(self, expected_call_count, reset=False):  # noqa
        fail_msg = (
            "%s is unexpectedly called %d times, instead of %d times." %
            (self._fake_add_message_path, self._mock_add_message.call_count,
             expected_call_count))
        if self._mock_add_message.call_count > 0:
            fail_msg += ("The called messages are: %s"
                         % repr(self._get_added_messages(join=False)))
        self.assertEqual(
            self._mock_add_message.call_count, expected_call_count, msg=fail_msg)
        if reset:
            self._mock_add_message.reset_mock()

    def assertAddMessageCalledWith(self, expected_messages, reset=True):  # noqa
        joined_msgs = self._get_added_messages()

        if not isinstance(expected_messages, list):
            expected_messages = [expected_messages]

        not_called = []
        for msg in expected_messages:
            if msg not in joined_msgs:
                not_called.append(msg)

        if not_called:
            fail_msg = "%s unexpectedly not added in messages. " % repr(not_called)
            if joined_msgs:
                fail_msg += "the actual message are \"%s\"" % joined_msgs
            self.fail(fail_msg)
        if reset:
            self._mock_add_message.reset_mock()

    def assertAddMessageNotCalledWith(self, expected_messages, reset=False):  # noqa
        joined_msgs = self._get_added_messages()

        if not isinstance(expected_messages, list):
            expected_messages = [expected_messages]

        called = []
        for msg in expected_messages:
            if msg in joined_msgs:
                called.append(msg)

        if called:
            fail_msg = "%s unexpectedly added in messages. " % repr(called)
            fail_msg += "the actual message are \"%s\"" % joined_msgs
            self.fail(fail_msg)
        if reset:
            self._mock_add_message.reset_mock()

    def reset_add_message_mock(self):
        self._mock_add_message.reset_mock()


class TaskTestMixin(object):
    """
    This test is actually testing without celery dependency.
    """
    def setUp(self):
        super(TaskTestMixin, self).setUp()

        # Emulates the behavior of AsyncResult
        override_settings_kwargs = {"task_always_eager": True}
        celery_fake_overriding = (
            override_settings(**override_settings_kwargs))
        celery_fake_overriding.enable()
        self.addCleanup(celery_fake_overriding.disable)
        update_state_patcher = mock.patch(
            "celery.app.task.Task.update_state", side_effect=mock.MagicMock)
        self.mock_update_state = update_state_patcher.start()
        self.addCleanup(update_state_patcher.stop)


class MockRouterClientMixin:
    def setUp(self):
        super().setUp()

        with mock.patch(
                "my_router.receivers.fetch_new_info_save_and_set_cache"
        ) as mock_fetch_and_cache:
            mock_fetch_and_cache.return_value = None
            self.router = RouterFactory()

        get_ikuai_client_patch = mock.patch(
            "my_router.models.IKuaiClient.__init__", return_value=None)

        self.mock_get_ikuai_client_patch = (
            get_ikuai_client_patch.start())

        self.addCleanup(get_ikuai_client_patch.stop)

    def fetch_cached_info_url(self, info_name="device", router_id=None):
        router_id = router_id or self.router.id
        return reverse("fetch-cached-info", args=(router_id, info_name,))

    @staticmethod
    def get_local_time(time_str):
        current_tz = timezone.get_current_timezone()

        formats = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%H:%M:%S", "%H:%M"]

        for fmt in formats:
            try:
                # 尝试解析时间字符串
                time = datetime.strptime(time_str, fmt)
                # 如果时间字符串不包含日期，则添加当前日期
                if fmt in ["%H:%M:%S", "%H:%M"]:
                    now = timezone.now()
                    time = time.replace(year=now.year, month=now.month,
                                        day=now.day)
                break
            except ValueError:
                continue
        else:
            raise ValueError(f"时间字符串 '{time_str}' 不符合预期的格式")

        local_time = timezone.make_aware(time, current_tz)

        return local_time


class DataManagerTestMixin(CacheMixin, MockRouterClientMixin):
    @property
    def default_ikuai_client_list_monitor_lanip(self):
        return DEFAULT_IKUAI_CLIENT_LIST_MONITOR_LANIP

    @property
    def default_ikuai_client_list_mac_groups(self):
        return DEFAULT_IKUAI_CLIENT_LIST_MAC_GROUPS

    @property
    def default_ikuai_client_list_acl_l7(self):
        return DEFAULT_IKUAI_CLIENT_LIST_ACL_L7

    @property
    def default_ikuai_client_list_domain_blacklist(self):
        return DEFAULT_IKUAI_CLIENT_LIST_DOMAIN_BLACKLIST

    @property
    def default_ikuai_client_list_url_black(self):
        return DEFAULT_IKUAI_CLIENT_LIST_URL_BLACK

    def setUp(self):
        super().setUp()

        post_save.disconnect(create_or_update_router_fetch_task, sender=Router)

        router_instance = self.router
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
        super().tearDown()
        post_save.connect(create_or_update_router_fetch_task, sender=Router)
